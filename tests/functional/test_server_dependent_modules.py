"""Functional coverage for modules that need a real DNS/DHCP server:
`zone`, `dnsrecord`, `dhcp`, `dhcpscope`.

The test host has IPAM-tracked ranges but no DNS or DHCP servers
configured (confirmed via the live API - GET dnsServers/dhcpServers
both return zero results), and creating one requires backend-specific
fields this environment can't satisfy (e.g. a Generic DNS server needs a
"DNS_ENV" field Micetro doesn't document via the REST API). Full
create/update/delete coverage for these four modules isn't achievable
here.

What *is* real, valuable coverage: each of these modules does a live
lookup before attempting any mutation (nameserver's DNS view, the DNS
zone, the IP's DHCP scope, the DHCP server/range reference), and should
fail cleanly and specifically when that lookup comes back empty - not
crash, not silently no-op. That path is exercised end-to-end here.
"""

import uuid

from .helpers import as_bool, collect_output


def test_zone_fails_cleanly_for_nonexistent_nameserver(
    run_playbook, mm_provider
):
    tasks = [
        {
            "name": "Try to create a zone on a nameserver that doesn't exist",
            "menandmice.ansible_micetro.zone": {
                "state": "present",
                "name": "claude-func-test-%s.example.com"
                % uuid.uuid4().hex[:8],
                "nameserver": "nonexistent-ns.example.invalid",
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
    assert "nameserver does not exist" in output["msg"]


def test_dnsrecord_fails_cleanly_for_nonexistent_zone(
    run_playbook, mm_provider
):
    zone_name = "claude-func-test-%s.example.com." % uuid.uuid4().hex[:8]
    tasks = [
        {
            "name": "Try to set a record in a zone that doesn't exist",
            "menandmice.ansible_micetro.dnsrecord": {
                "state": "present",
                "name": "host1",
                "data": "10.0.1.99",
                "dnszone": zone_name,
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
    assert "does not exist" in output["msg"]


def test_dhcp_fails_cleanly_when_no_dhcp_scope_covers_the_address(
    run_playbook, mm_provider
):
    tasks = [
        {
            "name": "Try to reserve an address with no covering DHCP scope",
            "menandmice.ansible_micetro.dhcp": {
                "state": "present",
                "name": "claude-func-test",
                "ipaddress": "10.0.1.200",
                "macaddress": "44:55:66:77:88:99",
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
    assert "No DHCP scope" in output["msg"]


def test_dhcpscope_fails_cleanly_for_nonexistent_range_ref(
    run_playbook, mm_provider
):
    tasks = [
        {
            "name": "Try to manage a DHCP scope against a range that doesn't exist",
            "menandmice.ansible_micetro.dhcpscope": {
                "state": "present",
                "name": "claude-func-test-scope",
                "range_ref": "ranges/999999",
                "dhcp_server_refs": ["dhcpServers/999999"],
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
    assert "Range reference not found" in output["msg"]
