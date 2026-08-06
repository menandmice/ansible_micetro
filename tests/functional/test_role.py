"""Functional coverage for the `role` module against a live Micetro host.

Mirrors test_group.py: role.py had the same membership-sync exists-check
issue as group.py, plus a databody-clobber bug that dropped its own
update call. Both are exercised here via a real update round trip.
"""

import uuid

from .helpers import as_bool, collect_output, uri_check


def test_role_create_noop_update_delete(run_playbook, mm_provider):
    name = "claude-func-role-%s" % uuid.uuid4().hex[:8]
    roles_url = "{{ mm_provider.mm_url }}/mmws/api/v2/roles?filter=name=" + name

    tasks = [
        {
            "name": "Create role",
            "menandmice.ansible_micetro.role": {
                "name": name,
                "desc": "created by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", roles_url, "verify_created"),
        {
            "name": "Re-run present with no changes",
            "menandmice.ansible_micetro.role": {
                "name": name,
                "desc": "created by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        {
            "name": "Update description",
            "menandmice.ansible_micetro.role": {
                "name": name,
                "desc": "updated by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "update_result",
        },
        uri_check("Verify updated", roles_url, "verify_updated"),
        {
            "name": "Delete role",
            "menandmice.ansible_micetro.role": {
                "name": name,
                "state": "absent",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        uri_check("Verify gone", roles_url, "verify_gone"),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_total_results": (
                    "verify_created.json.result.totalResults | int"
                ),
                "created_description": (
                    "verify_created.json.result.roles[0].description"
                ),
                "noop_changed": "noop_result.changed | bool",
                "update_changed": "update_result.changed | bool",
                "updated_description": (
                    "verify_updated.json.result.roles[0].description"
                ),
                "delete_changed": "delete_result.changed | bool",
                "gone_total_results": "verify_gone.json.result.totalResults | int",
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
