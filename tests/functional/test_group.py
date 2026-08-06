"""Functional coverage for the `group` module against a live Micetro host.

Exercises the exact regression fixed in issue #3: state=absent actually
deleting an existing group, and state=present taking the update path
(not just create) with the flat properties-map body shape.
"""

import uuid

from .helpers import as_bool, collect_output, uri_check


def test_group_create_noop_update_delete(run_playbook, mm_provider):
    name = "claude-func-group-%s" % uuid.uuid4().hex[:8]
    groups_url = (
        "{{ mm_provider.mm_url }}/mmws/api/v2/groups?filter=name=" + name
    )

    tasks = [
        {
            "name": "Create group",
            "menandmice.ansible_micetro.group": {
                "name": name,
                "desc": "created by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", groups_url, "verify_created"),
        {
            "name": "Re-run present with no changes",
            "menandmice.ansible_micetro.group": {
                "name": name,
                "desc": "created by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        {
            "name": "Update description",
            "menandmice.ansible_micetro.group": {
                "name": name,
                "desc": "updated by functional test",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "update_result",
        },
        uri_check("Verify updated", groups_url, "verify_updated"),
        {
            "name": "Delete group",
            "menandmice.ansible_micetro.group": {
                "name": name,
                "state": "absent",
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
                "created_description": (
                    "verify_created.json.result.groups[0].description"
                ),
                "noop_changed": "noop_result.changed | bool",
                "update_changed": "update_result.changed | bool",
                "updated_description": (
                    "verify_updated.json.result.groups[0].description"
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


def test_group_absent_on_nonexistent_group_is_a_noop(run_playbook, mm_provider):
    name = "claude-func-group-never-created-%s" % uuid.uuid4().hex[:8]

    tasks = [
        {
            "name": "Delete a group that was never created",
            "menandmice.ansible_micetro.group": {
                "name": name,
                "state": "absent",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        collect_output({"delete_changed": "delete_result.changed | bool"}),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["delete_changed"]) is False
