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
import urllib.error
import urllib.request
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


def _direct_api_call(provider, path, method="GET", data=None):
    """A direct (non-ansible-playbook) API call for fixture setup that
    doesn't need a full playbook run just to look something up. Shares
    the same connection-limit retry behavior as run_playbook/run_inventory.
    """
    session_url = "%s/mmws/api/v2/micetro/sessions" % provider["mm_url"]
    login_body = json.dumps(
        {"loginName": provider["mm_user"], "password": provider["mm_password"]}
    ).encode()

    token = None
    for attempt in range(1, _CONNECTION_LIMIT_RETRIES + 1):
        try:
            req = urllib.request.Request(
                session_url,
                data=login_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                token = json.loads(resp.read())["result"]["session"]
            break
        except urllib.error.URLError:
            if attempt == _CONNECTION_LIMIT_RETRIES:
                raise
            time.sleep(_CONNECTION_LIMIT_BACKOFF_SECONDS)

    url = "%s/mmws/api/v2/%s" % (provider["mm_url"], path)
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


@pytest.fixture(scope="session")
def dhcp_server(mm_provider):
    """The first configured DHCP server's ref + name, or skip if this
    host has none (that's a real, valid state - not every test host
    has a DHCP server backing it).
    """
    result = _direct_api_call(mm_provider, "dhcpServers")["result"]
    if result["totalResults"] == 0:
        pytest.skip("No DHCP server configured on this host")
    server = result["dhcpServers"][0]
    return {"ref": server["ref"], "name": server["name"]}


@pytest.fixture(scope="session")
def dns_server(mm_provider):
    """The first configured DNS server's ref + name, or skip if this
    host has none.
    """
    result = _direct_api_call(mm_provider, "dnsServers")["result"]
    if result["totalResults"] == 0:
        pytest.skip("No DNS server configured on this host")
    server = result["dnsServers"][0]
    return {"ref": server["ref"], "name": server["name"]}


@pytest.fixture(scope="session")
def subnet_range(mm_provider):
    """A real, usable leaf subnet range (full object) to attach DHCP
    scopes to.

    Avoids ranges with child ranges (a "subnet: true" container range
    like a /10 with /24s underneath it isn't a usable individual subnet
    for DHCP scope creation - confirmed live, it fails with "Creation
    of DHCP scope did not produce a DHCP scope") and ranges that
    already have a DHCP scope on them (e.g. one the DHCP server
    auto-registered on setup). Skips if none is available.
    """
    result = _direct_api_call(mm_provider, "ranges")["result"]
    for candidate in result["ranges"]:
        if (
            candidate.get("subnet")
            and not candidate.get("childRanges")
            and not candidate.get("dhcpScopes")
        ):
            return candidate
    pytest.skip("No free leaf subnet range available on this host")


@pytest.fixture(scope="session")
def subnet_range_ref(subnet_range):
    """Just the ref of `subnet_range`, for tests that only need that."""
    return subnet_range["ref"]


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
    """Run the playbook/inventory command exactly once.

    Despite the name (kept so callers didn't need to change), this no
    longer retries the whole command. It used to: retry the entire
    ansible-playbook invocation whenever connection-limit marker text
    appeared in stdout. That's unsafe for *any* playbook containing a
    non-idempotent step (e.g. a raw `ansible.builtin.uri` POST that
    doesn't check for existence first, unlike this collection's own
    modules) - confirmed live, twice: once when a fully-successful run
    got needlessly re-run and left an orphaned dhcpsuperscope behind
    (marker text from a *recovered* per-task retry still showed up in
    stdout even though the play succeeded), and again when a genuinely
    failed run got retried from scratch and its own earlier, already-
    applied create step collided with itself on the second pass
    ("custom property name ... is already in use").

    Every registered task is wrapped in its own retries/until loop (see
    _with_connection_limit_retry(task) below) - that handles transient
    connection-limit hits without ever needing to restart the whole
    playbook, and does so per-task instead of per-run, which is the
    only way to retry safely when not every task is idempotent.
    """
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        # Generous: a playbook with several retry-wrapped tasks can
        # legitimately spend retries * delay seconds per task if the
        # connection limit is hit more than once across the run.
        timeout=600,
    )


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
