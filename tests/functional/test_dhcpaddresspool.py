"""Functional coverage for the `dhcpaddresspool` module.

If this host has a real DHCP server configured, the dhcp_server/
subnet_range fixtures provide a server and a usable leaf subnet and the
round-trip test below exercises the real thing end to end: a DHCP scope
is created on that subnet, a pool of two addresses from within it is
carved out, updated, and torn down. If not, those tests are skipped
(see tests/functional/conftest.py's dhcp_server fixture) and only the
DHCP scope reference validation coverage runs.
"""

import ipaddress
import uuid

import pytest

from .helpers import as_bool, collect_output, uri_check


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


def test_create_noop_update_delete(
    run_playbook, mm_provider, dhcp_server, subnet_range
):
    hosts = list(ipaddress.ip_network(subnet_range["name"]).hosts())
    from_address, to_address = str(hosts[2]), str(hosts[3])
    scope_name = "claude-func-scope-for-pool-%s" % uuid.uuid4().hex[:8]
    pool_name = "claude-func-pool-%s" % uuid.uuid4().hex[:8]
    pools_url = (
        '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpScopes?filter=name="'
        + scope_name
        + '"'
    )

    tasks = [
        {
            "name": "Create a DHCP scope to hold the address pool",
            "menandmice.ansible_micetro.dhcpscope": {
                "state": "present",
                "name": scope_name,
                "range_ref": subnet_range["ref"],
                "dhcp_server_refs": [dhcp_server["ref"]],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        uri_check("Look up the scope ref", pools_url, "scope_lookup"),
        {
            "name": "Create address pool",
            "menandmice.ansible_micetro.dhcpaddresspool": {
                "state": "present",
                "dhcp_scope_ref": (
                    "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                ),
                "from_address": from_address,
                "to_address": to_address,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check(
            "Verify created",
            (
                "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                "/dhcpAddressPools"
            ),
            "verify_created",
        ),
        {
            "name": "Re-run present with no changes",
            "menandmice.ansible_micetro.dhcpaddresspool": {
                "state": "present",
                "dhcp_scope_ref": (
                    "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                ),
                "from_address": from_address,
                "to_address": to_address,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        {
            "name": "Update pool's name",
            "menandmice.ansible_micetro.dhcpaddresspool": {
                "state": "present",
                "dhcp_scope_ref": (
                    "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                ),
                "from_address": from_address,
                "to_address": to_address,
                "name": pool_name,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "update_result",
        },
        uri_check(
            "Verify updated",
            (
                "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                "/dhcpAddressPools"
            ),
            "verify_updated",
        ),
        {
            "name": "Delete address pool",
            "menandmice.ansible_micetro.dhcpaddresspool": {
                "state": "absent",
                "dhcp_scope_ref": (
                    "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                ),
                "from_address": from_address,
                "to_address": to_address,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        uri_check(
            "Verify gone",
            (
                "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                "/dhcpAddressPools"
            ),
            "verify_gone",
        ),
        {
            "name": "Delete the scope",
            "menandmice.ansible_micetro.dhcpscope": {
                "state": "absent",
                "name": scope_name,
                "range_ref": subnet_range["ref"],
                "dhcp_server_refs": [dhcp_server["ref"]],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_total_results": (
                    "verify_created.json.result.totalResults | int"
                ),
                "noop_changed": "noop_result.changed | bool",
                "update_changed": "update_result.changed | bool",
                "updated_name": (
                    "verify_updated.json.result.dhcpAddressPools[0].name"
                ),
                "delete_changed": "delete_result.changed | bool",
                "gone_total_results": (
                    "verify_gone.json.result.totalResults | int"
                ),
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert int(output["created_total_results"]) == 1
    assert as_bool(output["noop_changed"]) is False
    assert as_bool(output["update_changed"]) is True
    assert output["updated_name"] == pool_name
    assert as_bool(output["delete_changed"]) is True
    assert int(output["gone_total_results"]) == 0
