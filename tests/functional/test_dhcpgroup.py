"""Functional coverage for the `dhcpgroup` module.

Same constraint as test_dhcpsuperscope.py: this test host has no DHCP
server configured, so a real create/update/delete round trip - or even
reaching the parent-reference validation, which only runs after the
owner reference checks out - isn't achievable here. Covers the
owner-reference validation that happens before any mutation, for both
states.
"""

import pytest

from .helpers import as_bool, collect_output


@pytest.mark.parametrize("state", ["present", "absent"])
def test_fails_cleanly_for_nonexistent_owner_ref(
    run_playbook, mm_provider, state
):
    tasks = [
        {
            "name": "Try to manage a DHCP group owned by a server that doesn't exist",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": state,
                "name": "claude-func-test-group",
                "owner_ref": "dhcpServers/999999",
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
    assert "Owner reference not found" in output["msg"]
