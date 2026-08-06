"""Functional coverage for the `dhcpaddresspool` module.

Same constraint as test_dhcpsuperscope.py/test_dhcpgroup.py: this test
host has no DHCP server (and therefore no DHCP scopes) configured, so a
real create/update/delete round trip isn't achievable here. Covers the
DHCP scope reference validation that happens before any mutation, for
both states.
"""

import pytest

from .helpers import as_bool, collect_output


@pytest.mark.parametrize("state", ["present", "absent"])
def test_fails_cleanly_for_nonexistent_dhcp_scope_ref(
    run_playbook, mm_provider, state
):
    tasks = [
        {
            "name": "Try to manage an address pool on a DHCP scope that doesn't exist",
            "menandmice.ansible_micetro.dhcpaddresspool": {
                "state": state,
                "dhcp_scope_ref": "dhcpScopes/999999",
                "from_address": "172.16.17.100",
                "to_address": "172.16.17.150",
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
    assert "DHCP scope reference not found" in output["msg"]
