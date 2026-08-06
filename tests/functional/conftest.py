"""Functional test harness: runs real ansible-playbook invocations against a
live Micetro server.

Unlike tests/unit (which mocks the HTTP layer), these tests exercise the
full stack - AnsibleModule argument parsing, module_utils.micetro's
session-auth/retry logic, and the actual Micetro REST API - end to end.
They therefore require live credentials and will mutate real objects on
whatever host they're pointed at (always cleaned up afterward).

Credentials: set MM_HOST/MM_USER/MM_PASSWORD, or provide a
local/creds.env file (HOST=/USERNAME=/PASSWORD=, gitignored) at the repo
root. If neither is available the whole session is skipped rather than
failing, since these tests are opt-in (see tox.ini's `functional` env).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# module_utils.micetro logs in fresh for every module task and never logs
# back out (there's no session/logout endpoint in the v2 API - see the
# GitLab issue filed alongside this test suite). This test host enforces
# a low per-user concurrent-connection cap, so a playbook with more than
# a handful of tasks can trip "Too many open connections" even though
# nothing is actually wrong. The cap clears within a few seconds, so
# retry the whole (idempotent-by-design) playbook rather than treat it
# as a real failure.
_CONNECTION_LIMIT_MARKERS = (
    "Too many open connections",
    # module_utils.micetro._login() doesn't read the HTTPError body (it
    # only has the generic urllib message), so the connection-limit
    # error surfaces as this instead when it happens during login rather
    # than a later API call.
    "Failed to authenticate to",
    # Tasks that use ignore_errors: True to assert on an *expected*
    # fail_json() message can't be told apart from a real failure by
    # return code alone (ignore_errors makes the play "succeed"
    # either way) - MODULE FAILURE only ever shows up here when the
    # module raised an unhandled exception (i.e. the connection-limit
    # crash), never from a clean fail_json(), so it's safe to treat as
    # always retryable in this suite.
    "MODULE FAILURE",
)
_CONNECTION_LIMIT_RETRIES = 8
_CONNECTION_LIMIT_BACKOFF_SECONDS = 15


def _read_env_file(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def _load_creds():
    host = os.environ.get("MM_HOST")
    user = os.environ.get("MM_USER")
    password = os.environ.get("MM_PASSWORD")
    if host and user and password:
        return {
            "mm_url": host.rstrip("/"),
            "mm_user": user,
            "mm_password": password,
        }

    creds_file = REPO_ROOT / "local" / "creds.env"
    if creds_file.exists():
        values = _read_env_file(creds_file)
        if {"HOST", "USERNAME", "PASSWORD"} <= values.keys():
            return {
                "mm_url": values["HOST"].rstrip("/"),
                "mm_user": values["USERNAME"],
                "mm_password": values["PASSWORD"],
            }
    return None


@pytest.fixture(scope="session")
def mm_provider():
    provider = _load_creds()
    if provider is None:
        pytest.skip(
            "No live Micetro credentials found (set MM_HOST/MM_USER/"
            "MM_PASSWORD, or provide local/creds.env) - functional tests "
            "require a real server to run against."
        )
    return provider


@pytest.fixture(scope="session")
def collections_root(tmp_path_factory):
    """A throwaway collections tree with this repo registered as
    ansible_collections.menandmice.ansible_micetro, so the FQCN imports
    the collection's own code uses resolve without a real installation.
    """
    root = tmp_path_factory.mktemp("collections")
    namespace_dir = root / "ansible_collections" / "menandmice"
    namespace_dir.mkdir(parents=True)
    (namespace_dir / "ansible_micetro").symlink_to(
        REPO_ROOT, target_is_directory=True
    )
    return root


def _run_with_connection_limit_retry(cmd, cwd, env):
    proc = None
    for attempt in range(1, _CONNECTION_LIMIT_RETRIES + 1):
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            # Generous: a playbook with several retry-wrapped tasks can
            # legitimately spend retries * delay seconds per task inside
            # a single ansible-playbook invocation if the connection
            # limit is hit more than once.
            timeout=600,
        )
        # Checked regardless of return code: a task using
        # ignore_errors: True to assert on an expected fail_json()
        # message makes the overall play "succeed" (rc=0) even when a
        # task actually hit the connection-limit crash instead.
        hit_connection_limit = any(
            marker in proc.stdout for marker in _CONNECTION_LIMIT_MARKERS
        )
        if not hit_connection_limit or attempt == _CONNECTION_LIMIT_RETRIES:
            break
        time.sleep(_CONNECTION_LIMIT_BACKOFF_SECONDS)
    return proc


def _with_connection_limit_retry(task):
    """Wrap a registered task in Ansible's own retry loop, so a
    transient connection-limit hit only re-runs *that* task - not
    everything before it in the playbook. Re-running the whole playbook
    (the previous approach) made an already-successful "create" step
    look like a no-op "update" on the retried attempt, since the object
    it created was still there from the first attempt.

    Only applies to tasks that register a result; set_fact/copy helper
    tasks don't touch the network and don't need this.
    """
    if "register" not in task:
        return task
    reg = task["register"]
    task = dict(task)
    task.setdefault("retries", _CONNECTION_LIMIT_RETRIES)
    task.setdefault("delay", _CONNECTION_LIMIT_BACKOFF_SECONDS)
    task.setdefault(
        "until",
        "(%(r)s.failed is not defined) or (not %(r)s.failed) or "
        "(('MODULE FAILURE' not in (%(r)s.msg | default(''))) and "
        "('authenticate' not in (%(r)s.msg | default(''))))" % {"r": reg},
    )
    return task


def _base_env(collections_root):
    env = dict(os.environ)
    env["ANSIBLE_COLLECTIONS_PATH"] = str(collections_root)
    env["ANSIBLE_DEPRECATION_WARNINGS"] = "False"
    env["ANSIBLE_LOCALHOST_WARNING"] = "False"
    env["ANSIBLE_INVENTORY_UNPARSED_WARNING"] = "False"
    env["ANSIBLE_RETRY_FILES_ENABLED"] = "False"
    return env


@pytest.fixture
def run_playbook(tmp_path, collections_root):
    """Run a list of Ansible tasks as a one-play, localhost playbook.

    The task list must end by setting `test_output` via set_fact; this
    fixture appends a final task that writes it to a JSON file and
    returns the parsed contents. Use `| bool` / `| int` filters on
    templated values in test_output so to_nice_json emits real JSON
    types instead of strings.
    """

    def _run(tasks, provider, extra_vars=None):
        result_file = tmp_path / "result.json"
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": dict({"mm_provider": provider}, **(extra_vars or {})),
                "tasks": [_with_connection_limit_retry(t) for t in tasks]
                + [
                    {
                        "name": "__write_test_output__",
                        "ansible.builtin.copy": {
                            "content": "{{ test_output | to_nice_json }}",
                            "dest": str(result_file),
                        },
                    }
                ],
            }
        ]
        playbook_path = tmp_path / "playbook.yml"
        playbook_path.write_text(yaml.safe_dump(play, sort_keys=False))

        ansible_playbook = str(Path(sys.executable).parent / "ansible-playbook")
        proc = _run_with_connection_limit_retry(
            [ansible_playbook, str(playbook_path)],
            tmp_path,
            _base_env(collections_root),
        )

        if proc.returncode != 0:
            raise AssertionError(
                "ansible-playbook failed (rc=%s)\n--- stdout ---\n%s\n"
                "--- stderr ---\n%s"
                % (proc.returncode, proc.stdout, proc.stderr)
            )
        return json.loads(result_file.read_text())

    return _run


@pytest.fixture
def run_inventory(tmp_path, collections_root):
    """Run `ansible-inventory --list` against a temporary micetro.yml
    pointed at the live host, and return the parsed inventory dict.
    """

    def _run(provider, ranges=None, filters=None):
        config = {
            "plugin": "menandmice.ansible_micetro.inventory",
            "mm_url": provider["mm_url"],
            "mm_user": provider["mm_user"],
            "mm_password": provider["mm_password"],
        }
        if ranges:
            config["ranges"] = ranges
        if filters:
            config["filters"] = filters

        inventory_path = tmp_path / "micetro.yml"
        inventory_path.write_text(yaml.safe_dump(config, sort_keys=False))

        ansible_inventory = str(
            Path(sys.executable).parent / "ansible-inventory"
        )
        proc = _run_with_connection_limit_retry(
            [ansible_inventory, "-i", str(inventory_path), "--list"],
            tmp_path,
            _base_env(collections_root),
        )

        if proc.returncode != 0:
            raise AssertionError(
                "ansible-inventory failed (rc=%s)\n--- stdout ---\n%s\n"
                "--- stderr ---\n%s"
                % (proc.returncode, proc.stdout, proc.stderr)
            )
        return json.loads(proc.stdout)

    return _run
