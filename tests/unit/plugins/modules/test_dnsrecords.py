"""Unit tests for plugins/modules/dnsrecords.py (bulk DNS record create).

Covers GitLab issue #10's bulk-record-creation piece: batching multiple
dnsRecords into a single POST instead of dnsrecord.py's one-call-per-
record. Zone/view resolution is shared with dnsrecord.py via
module_utils.micetro.resolve_dns_zone_ref() - see test_micetro.py for
that logic's own coverage.
"""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dnsrecords,
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
    monkeypatch.setattr(dnsrecords.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(dnsrecords.AnsibleModule, "fail_json", fail_json)


def _run(**module_args):
    set_module_args(dict(mm_provider=MM_PROVIDER, **module_args))
    dnsrecords.run_module()


def _records(*names_and_data):
    return [{"name": n, "data": d} for n, d in names_and_data]


class TestZoneResolution:
    def test_invalid_zone_fails_before_any_record_lookup(self, mocker):
        mocker.patch.object(
            dnsrecords,
            "resolve_dns_zone_ref",
            return_value={"invalid": True, "warnings": "boom"},
        )
        get_single_refs = mocker.patch.object(dnsrecords, "get_single_refs")

        with pytest.raises(AnsibleFailJson) as exc:
            _run(dnszone="example.net.", records=_records(("host1", "1.2.3.4")))

        assert exc.value.args[0]["msg"] == "boom"
        get_single_refs.assert_not_called()


class TestSkipsExistingRecords:
    def test_all_records_already_exist_is_a_noop(self, mocker):
        mocker.patch.object(
            dnsrecords, "resolve_dns_zone_ref", return_value=ZONEINFO
        )
        mocker.patch.object(
            dnsrecords,
            "get_single_refs",
            return_value={
                "totalResults": 1,
                "dnsRecords": [
                    {"name": "host1", "type": "A", "data": "1.2.3.4"}
                ],
            },
        )
        doapi = mocker.patch.object(dnsrecords, "doapi")

        with pytest.raises(AnsibleExitJson) as exc:
            _run(dnszone="example.net.", records=_records(("host1", "1.2.3.4")))

        assert exc.value.args[0]["changed"] is False
        doapi.assert_not_called()


class TestBulkCreate:
    def test_creates_only_the_missing_records_in_one_call(self, mocker):
        mocker.patch.object(
            dnsrecords, "resolve_dns_zone_ref", return_value=ZONEINFO
        )
        mocker.patch.object(
            dnsrecords,
            "get_single_refs",
            side_effect=[
                # host1 already exists
                {
                    "totalResults": 1,
                    "dnsRecords": [
                        {"name": "host1", "type": "A", "data": "1.2.3.4"}
                    ],
                },
                # host2 does not
                {"totalResults": 0, "dnsRecords": []},
                {"totalResults": 0, "dnsRecords": []},
            ],
        )
        doapi = mocker.patch.object(
            dnsrecords,
            "doapi",
            return_value={
                "changed": True,
                "message": {
                    "result": {
                        "objRefs": ["dnsRecords/9"],
                        "errors": [],
                    }
                },
            },
        )

        with pytest.raises(AnsibleExitJson) as exc:
            _run(
                dnszone="example.net.",
                records=_records(("host1", "1.2.3.4"), ("host2", "1.2.3.5")),
            )

        url, method, provider, databody = doapi.call_args[0]
        assert url == "dnsRecords"
        assert method == "POST"
        assert provider == MM_PROVIDER
        assert databody["dnsZoneRef"] == "dnsZones/1"
        assert databody["dnsRecords"] == [
            {
                "name": "host2",
                "type": "A",
                "data": "1.2.3.5",
                "comment": "",
                "enabled": True,
                "aging": 0,
            }
        ]
        assert exc.value.args[0]["changed"] is True
        assert exc.value.args[0]["created"] == ["dnsRecords/9"]

    def test_http_failure_on_the_bulk_call_fails_the_task(self, mocker):
        mocker.patch.object(
            dnsrecords, "resolve_dns_zone_ref", return_value=ZONEINFO
        )
        mocker.patch.object(
            dnsrecords,
            "get_single_refs",
            return_value={"totalResults": 0, "dnsRecords": []},
        )
        mocker.patch.object(
            dnsrecords,
            "doapi",
            return_value={"changed": False, "warnings": "server exploded"},
        )

        with pytest.raises(AnsibleFailJson) as exc:
            _run(dnszone="example.net.", records=_records(("host1", "1.2.3.4")))

        assert exc.value.args[0]["msg"] == "server exploded"

    def test_partial_failure_fails_but_reports_what_was_created(self, mocker):
        mocker.patch.object(
            dnsrecords, "resolve_dns_zone_ref", return_value=ZONEINFO
        )
        mocker.patch.object(
            dnsrecords,
            "get_single_refs",
            side_effect=[
                {"totalResults": 0, "dnsRecords": []},
                {"totalResults": 0, "dnsRecords": []},
                {"totalResults": 0, "dnsRecords": []},
                {"totalResults": 0, "dnsRecords": []},
            ],
        )
        mocker.patch.object(
            dnsrecords,
            "doapi",
            return_value={
                "changed": True,
                "message": {
                    "result": {
                        "objRefs": ["dnsRecords/9", "unknown/0"],
                        "errors": [
                            "The data bogus is not a valid IP address "
                            "for A record host2."
                        ],
                    }
                },
            },
        )

        with pytest.raises(AnsibleFailJson) as exc:
            _run(
                dnszone="example.net.",
                records=_records(("host1", "1.2.3.4"), ("host2", "bogus")),
            )

        out = exc.value.args[0]
        assert out["created"] == ["dnsRecords/9"]
        assert out["changed"] is True
        assert "host2" in out["errors"][0]


class TestCheckMode:
    def test_check_mode_never_calls_the_api(self, mocker):
        resolve = mocker.patch.object(dnsrecords, "resolve_dns_zone_ref")
        doapi = mocker.patch.object(dnsrecords, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                dnszone="example.net.",
                records=_records(("host1", "1.2.3.4")),
                _ansible_check_mode=True,
            )
        )
        with pytest.raises(AnsibleExitJson) as exc:
            dnsrecords.run_module()

        assert exc.value.args[0]["changed"] is True
        resolve.assert_not_called()
        doapi.assert_not_called()
