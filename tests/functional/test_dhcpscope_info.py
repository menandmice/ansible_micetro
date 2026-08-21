"""Functional coverage for the `dhcpscope_info` module.

Whether this host has any DHCP scopes at all varies (a real DHCP server
may or may not be configured, and may already have scopes of its own),
so the "empty result" case is tested by filtering on a name that can't
possibly match anything, rather than assuming zero scopes exist
globally - that's the only assumption that holds regardless of
environment.
"""

import uuid

from .helpers import as_bool, collect_output


def test_returns_empty_result_for_a_name_that_does_not_exist(
    run_playbook, mm_provider
):
    tasks = [
        {
            "name": "Gather DHCP scope info for a name that can't exist",
            "menandmice.ansible_micetro.dhcpscope_info": {
                "name": "claude-func-test-nonexistent-%s" % uuid.uuid4().hex,
                "limit": 5,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "result",
        },
        collect_output(
            {
                "changed": "result.changed | bool",
                "total_results": "result.total_results | int",
                "dhcp_scopes": "result.dhcp_scopes",
                "message": "result.message",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["changed"]) is False
    assert int(output["total_results"]) == 0
    assert output["dhcp_scopes"] == []
    assert output["message"] == "Returned 0 DHCP scope(s)"


def test_rejects_negative_limit(run_playbook, mm_provider):
    tasks = [
        {
            "name": "Gather DHCP scope info with an invalid limit",
            "menandmice.ansible_micetro.dhcpscope_info": {
                "limit": -1,
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
    assert "positive integer" in output["msg"]
