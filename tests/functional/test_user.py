"""Functional coverage for the `user` module against a live Micetro host."""

import uuid

from .helpers import as_bool, collect_output, uri_check


def test_user_create_and_delete(run_playbook, mm_provider):
    username = "claude-func-user-%s" % uuid.uuid4().hex[:8]
    users_url = (
        "{{ mm_provider.mm_url }}/mmws/api/v2/users?filter=name=" + username
    )

    tasks = [
        {
            "name": "Create user",
            "menandmice.ansible_micetro.user": {
                "username": username,
                "password": "TempPassw0rd!23",
                "full_name": "Claude Functional Test User",
                "authentication_type": "internal",
                "state": "present",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", users_url, "verify_created"),
        {
            "name": "Delete user",
            "menandmice.ansible_micetro.user": {
                "username": username,
                "state": "absent",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        uri_check("Verify gone", users_url, "verify_gone"),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_total_results": (
                    "verify_created.json.result.totalResults | int"
                ),
                "created_full_name": "verify_created.json.result.users[0].fullName",
                "delete_changed": "delete_result.changed | bool",
                "gone_total_results": "verify_gone.json.result.totalResults | int",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert int(output["created_total_results"]) == 1
    assert output["created_full_name"] == "Claude Functional Test User"
    assert as_bool(output["delete_changed"]) is True
    assert int(output["gone_total_results"]) == 0


def test_user_absent_on_nonexistent_user_is_a_noop(run_playbook, mm_provider):
    username = "claude-func-user-never-created-%s" % uuid.uuid4().hex[:8]

    tasks = [
        {
            "name": "Delete a user that was never created",
            "menandmice.ansible_micetro.user": {
                "username": username,
                "state": "absent",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        collect_output({"delete_changed": "delete_result.changed | bool"}),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["delete_changed"]) is False
