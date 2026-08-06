"""Shared helpers for exercising AnsibleModule-based modules in tests.

Standard pattern used across Ansible collections: feed module args in via
basic._ANSIBLE_ARGS, and replace exit_json/fail_json with variants that
raise instead of calling sys.exit(), so a test can assert on the result.
"""

import json

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes


def set_module_args(args):
    """Prepare arguments so they will be picked up by AnsibleModule."""
    args = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    basic._ANSIBLE_ARGS = to_bytes(args)


class AnsibleExitJson(Exception):
    """Raised by exit_json() instead of exiting the process."""


class AnsibleFailJson(Exception):
    """Raised by fail_json() instead of exiting the process."""


def exit_json(*args, **kwargs):
    if "changed" not in kwargs:
        kwargs["changed"] = False
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)
