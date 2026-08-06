"""Functional coverage for the `dhcpgroup` module.

If this host has a real DHCP server configured, the dhcp_server fixture
provides its ref/name and the round-trip tests below exercise the real
thing end to end. If not, those tests are skipped (see
tests/functional/conftest.py's dhcp_server fixture) and only the
owner-reference validation coverage runs - the same clean-failure path
documented in test_server_dependent_modules.py for zone/dnsrecord/dhcp/
dhcpscope.
"""

import uuid

import pytest

from .helpers import as_bool, collect_output, uri_check


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


def test_create_noop_delete(run_playbook, mm_provider, dhcp_server):
    name = "claude-func-group-%s" % uuid.uuid4().hex[:8]
    groups_url = (
        '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpGroups?filter=name="'
        + name
        + '"'
    )

    tasks = [
        {
            "name": "Create DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "present",
                "name": name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", groups_url, "verify_created"),
        {
            "name": "Re-run present with no changes",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "present",
                "name": name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        {
            "name": "Delete DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "absent",
                "name": name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        uri_check("Verify gone", groups_url, "verify_gone"),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_total_results": (
                    "verify_created.json.result.totalResults | int"
                ),
                "noop_changed": "noop_result.changed | bool",
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
    assert as_bool(output["delete_changed"]) is True
    assert int(output["gone_total_results"]) == 0


def test_create_nested_group_with_parent_ref(
    run_playbook, mm_provider, dhcp_server
):
    parent_name = "claude-func-group-parent-%s" % uuid.uuid4().hex[:8]
    child_name = "claude-func-group-child-%s" % uuid.uuid4().hex[:8]
    child_url = (
        '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpGroups?filter=name="'
        + child_name
        + '"'
    )

    tasks = [
        {
            "name": "Create parent DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "present",
                "name": parent_name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        uri_check(
            "Look up parent group ref",
            '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpGroups?filter=name="'
            + parent_name
            + '"',
            "parent_lookup",
        ),
        {
            "name": "Create nested DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "present",
                "name": child_name,
                "owner_ref": dhcp_server["ref"],
                "parent_ref": (
                    "{{ parent_lookup.json.result.dhcpGroups[0].ref }}"
                ),
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify nested group created", child_url, "verify_created"),
        {
            "name": "Delete nested DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "absent",
                "name": child_name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        {
            "name": "Delete parent DHCP group",
            "menandmice.ansible_micetro.dhcpgroup": {
                "state": "absent",
                "name": parent_name,
                "owner_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "parent_ref_matches": (
                    "verify_created.json.result.dhcpGroups[0].parentRef"
                ),
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert output["parent_ref_matches"]
