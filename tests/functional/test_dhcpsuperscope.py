"""Functional coverage for the `dhcpsuperscope` module.

If this host has a real DHCP server configured, the dhcp_server fixture
provides its ref/name and the round-trip tests below exercise the real
thing end to end. If not, those tests are skipped (see
tests/functional/conftest.py's dhcp_server fixture) and only the
reference-validation coverage runs - the same clean-failure path
documented in test_server_dependent_modules.py for zone/dnsrecord/dhcp/
dhcpscope.
"""

import uuid

import pytest

from .helpers import as_bool, collect_output, uri_check


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


def test_create_noop_update_delete(run_playbook, mm_provider, dhcp_server):
    name = "claude-func-superscope-%s" % uuid.uuid4().hex[:8]
    superscopes_url = (
        '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpSuperscopes?filter=name="'
        + name
        + '"'
    )

    tasks = [
        {
            "name": "Create superscope",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "present",
                "name": name,
                "description": "created by functional test",
                "dhcp_server_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", superscopes_url, "verify_created"),
        {
            "name": "Re-run present with no changes",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "present",
                "name": name,
                "description": "created by functional test",
                "dhcp_server_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        {
            "name": "Update description",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "present",
                "name": name,
                "description": "updated by functional test",
                "dhcp_server_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "update_result",
        },
        uri_check("Verify updated", superscopes_url, "verify_updated"),
        {
            "name": "Delete superscope",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "absent",
                "name": name,
                "dhcp_server_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        uri_check("Verify gone", superscopes_url, "verify_gone"),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_total_results": (
                    "verify_created.json.result.totalResults | int"
                ),
                "created_description": (
                    "verify_created.json.result.superscopes[0].description"
                ),
                "noop_changed": "noop_result.changed | bool",
                "update_changed": "update_result.changed | bool",
                "updated_description": (
                    "verify_updated.json.result.superscopes[0].description"
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
    assert output["created_description"] == "created by functional test"
    assert as_bool(output["noop_changed"]) is False
    assert as_bool(output["update_changed"]) is True
    assert output["updated_description"] == "updated by functional test"
    assert as_bool(output["delete_changed"]) is True
    assert int(output["gone_total_results"]) == 0


def test_create_with_initial_scope_refs(
    run_playbook, mm_provider, dhcp_server, subnet_range_ref
):
    superscope_name = "claude-func-superscope-scopes-%s" % uuid.uuid4().hex[:8]
    scope_name = "claude-func-scope-for-superscope-%s" % uuid.uuid4().hex[:8]

    tasks = [
        {
            "name": "Create a DHCP scope to seed the superscope with",
            "menandmice.ansible_micetro.dhcpscope": {
                "state": "present",
                "name": scope_name,
                "range_ref": subnet_range_ref,
                "dhcp_server_refs": [dhcp_server["ref"]],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        uri_check(
            "Look up the scope ref",
            '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpScopes?filter=name="'
            + scope_name
            + '"',
            "scope_lookup",
        ),
        {
            "name": "Create superscope with the scope pre-assigned",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "present",
                "name": superscope_name,
                "dhcp_server_ref": dhcp_server["ref"],
                "dhcp_scope_refs": [
                    "{{ scope_lookup.json.result.dhcpScopes[0].ref }}"
                ],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check(
            "Verify superscope has the scope",
            '{{ mm_provider.mm_url }}/mmws/api/v2/dhcpSuperscopes?filter=name="'
            + superscope_name
            + '"',
            "verify_created",
        ),
        {
            "name": "Delete superscope",
            "menandmice.ansible_micetro.dhcpsuperscope": {
                "state": "absent",
                "name": superscope_name,
                "dhcp_server_ref": dhcp_server["ref"],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        {
            "name": "Delete the seed scope",
            "menandmice.ansible_micetro.dhcpscope": {
                "state": "absent",
                "name": scope_name,
                "range_ref": subnet_range_ref,
                "dhcp_server_refs": [dhcp_server["ref"]],
                "mm_provider": "{{ mm_provider }}",
            },
        },
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "scope_count": (
                    "verify_created.json.result.superscopes[0].scopeCount | int"
                ),
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert int(output["scope_count"]) == 1
