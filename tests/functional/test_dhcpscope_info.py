"""Functional coverage for the `dhcpscope_info` module.

The test host has no DHCP server/scopes configured, so this covers the
read-only, empty-result path (which is itself the exact path
end-to-end-verified during the #7 v2 migration) plus basic parameter
validation - not a real scope's data, since none can exist here.
"""

from .helpers import as_bool, collect_output


def test_returns_empty_result_when_no_scopes_exist(run_playbook, mm_provider):
    tasks = [
        {
            "name": "Gather DHCP scope info",
            "menandmice.ansible_micetro.dhcpscope_info": {
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
