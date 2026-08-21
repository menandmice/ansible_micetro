"""Unit tests for plugins/modules/dnsrecord.py.

Zone/view resolution itself now lives in module_utils.micetro's
resolve_dns_zone_ref() (shared with dnsrecords.py) and is covered by
tests/unit/plugins/module_utils/test_micetro.py. These tests just check
that dnsrecord.py calls it correctly and handles both outcomes.
"""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dnsrecord,
)
from .utils import (
    AnsibleExitJson,
    AnsibleFailJson,
    exit_json,
    fail_json,
    set_module_args,
)

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

ZONEINFO = {
    "ref": "dnsZones/1",
    "name": "example.net.",
    "display": "example.net.",
}


@pytest.fixture(autouse=True)
def _patch_exit_and_fail(monkeypatch):
    monkeypatch.setattr(dnsrecord.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(dnsrecord.AnsibleModule, "fail_json", fail_json)


def _run(**module_args):
    set_module_args(dict(mm_provider=MM_PROVIDER, **module_args))
    dnsrecord.run_module()


def test_creates_record_using_resolved_zone_ref(mocker):
    mocker.patch.object(
        dnsrecord, "resolve_dns_zone_ref", return_value=ZONEINFO
    )
    get_single_refs = mocker.patch.object(
        dnsrecord,
        "get_single_refs",
        side_effect=[
            {"dnsRecords": [], "totalResults": 0},
            {"dnsRecords": [], "totalResults": 0},
        ],
    )
    doapi = mocker.patch.object(
        dnsrecord,
        "doapi",
        return_value={
            "changed": True,
            "message": {"result": {"errors": None}},
        },
    )

    with pytest.raises(AnsibleExitJson):
        _run(
            name="beatles",
            data="172.16.17.2",
            rrtype="A",
            dnszone="example.net.",
        )

    # The record lookup is scoped under the ref resolve_dns_zone_ref
    # returned, not a bare zone name.
    assert get_single_refs.call_args_list[0][0][0].startswith(
        "dnsZones/1/dnsRecords?"
    )
    doapi.assert_called_once()


def test_invalid_zone_fails_cleanly(mocker):
    mocker.patch.object(
        dnsrecord,
        "resolve_dns_zone_ref",
        return_value={
            "invalid": True,
            "warnings": "DNS Zone 'example.net.' does not exist",
        },
    )
    get_single_refs = mocker.patch.object(dnsrecord, "get_single_refs")

    with pytest.raises(AnsibleFailJson) as exc:
        _run(
            name="beatles",
            data="172.16.17.2",
            rrtype="A",
            dnszone="example.net.",
        )

    assert "does not exist" in exc.value.args[0]["msg"]
    # Never got to the record lookup at all.
    get_single_refs.assert_not_called()
