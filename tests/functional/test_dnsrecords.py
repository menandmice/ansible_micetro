"""Functional coverage for the `dnsrecords` bulk-create module against a
live Micetro host.

Uses the "localhost." zone, which every Micetro install ships by
default (confirmed on this test host - see test_server_dependent_
modules.py's docstring for why DNS/DHCP server-backed fixtures aren't
available here). Records are cleaned up afterward via the existing
`dnsrecord` module (state=absent), which issue #18 already covers for
zone/view lookup correctness.
"""

import uuid

from .helpers import as_bool, collect_output, uri_check


def _cleanup_task(name, data, rrtype="A"):
    return {
        "name": "Clean up %s" % name,
        "menandmice.ansible_micetro.dnsrecord": {
            "state": "absent",
            "name": name,
            "data": data,
            "rrtype": rrtype,
            "dnszone": "localhost.",
            "mm_provider": "{{ mm_provider }}",
        },
    }


def test_bulk_create_skips_existing_and_is_idempotent(
    run_playbook, mm_provider
):
    suffix = uuid.uuid4().hex[:8]
    name1, name2 = "claudebulk1%s" % suffix, "claudebulk2%s" % suffix

    tasks = [
        {
            "name": "Create two DNS records in one call",
            "menandmice.ansible_micetro.dnsrecords": {
                "dnszone": "localhost.",
                "records": [
                    {"name": name1, "data": "127.0.1.10"},
                    {"name": name2, "data": "127.0.1.11"},
                ],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check(
            "Verify first record exists",
            "{{ mm_provider.mm_url }}/mmws/api/v2/dnsZones/7/dnsRecords?"
            "filter=name=" + name1,
            "verify_created",
        ),
        {
            "name": "Re-run with the exact same records (idempotency check)",
            "menandmice.ansible_micetro.dnsrecords": {
                "dnszone": "localhost.",
                "records": [
                    {"name": name1, "data": "127.0.1.10"},
                    {"name": name2, "data": "127.0.1.11"},
                ],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        _cleanup_task(name1, "127.0.1.10"),
        _cleanup_task(name2, "127.0.1.11"),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_count": "create_result.created | length",
                "verified_total": "verify_created.json.result.totalResults",
                "noop_changed": "noop_result.changed | bool",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert int(output["created_count"]) == 2
    assert int(output["verified_total"]) == 1
    assert as_bool(output["noop_changed"]) is False


def test_partial_failure_fails_but_keeps_the_successful_record(
    run_playbook, mm_provider
):
    suffix = uuid.uuid4().hex[:8]
    good_name = "claudebulkgood%s" % suffix
    bad_name = "claudebulkbad%s" % suffix

    tasks = [
        {
            "name": "Create one valid and one invalid record in one call",
            "menandmice.ansible_micetro.dnsrecords": {
                "dnszone": "localhost.",
                "records": [
                    {"name": good_name, "data": "127.0.1.20"},
                    {"name": bad_name, "data": "not-a-valid-ip"},
                ],
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "result",
            "ignore_errors": True,
        },
        _cleanup_task(good_name, "127.0.1.20"),
        collect_output(
            {
                "failed": "result.failed | bool",
                "msg": "result.msg | default('')",
                "created": "result.created | default([])",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["failed"]) is True
    assert bad_name in output["msg"]
    assert len(output["created"]) == 1
