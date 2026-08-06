"""Functional coverage for the `dhcpsuperscope` module.

The test host has no DHCP server configured (confirmed via the live API
- GET dhcpServers returns zero results), and creating one isn't
achievable in this environment - same constraint documented in
test_server_dependent_modules.py. A real create/update/delete round
trip for a superscope isn't possible here.

What *is* real: dhcpsuperscope.py validates the DHCP server reference
before doing anything else, for both state=present and state=absent, so
this covers that validation actually happening and failing cleanly
rather than crashing or silently no-opping.
"""

import pytest

from .helpers import as_bool, collect_output


@pytest.mark.parametrize("state", ["present", "absent"])
def test_fails_cleanly_for_nonexistent_dhcp_server_ref(
    run_playbook, mm_provider, state
):
    tasks = [
        {
            "name": "Try to manage a superscope on a DHCP server that doesn't exist",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": state,
                "name": "claude-func-test-superscope",
                "dhcp_server_ref": "dhcpServers/999999",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "result",
            "ignore_errors": True,
        },
        collect_output(
            {
                "failed": "result.failed | bool",
                "msg": "result.msg | default('')",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["failed"]) is True
    assert "DHCP server reference not found" in output["msg"]
