"""Unit tests for plugins/modules/dnsrecord.py's zone/view lookup.

Regression coverage for issue #18: on a BIND server with several DNS
views sharing a zone name, the bare-name `dnszone` filter can come back
ambiguous, and dnsrecord.py indexed straight into `zoneresp["dnsZones"]`
without checking for that, producing a raw KeyError instead of a clean
module failure. dnszone now also accepts the Management Console's own
disambiguated format, "zonename (viewname)", to resolve the ambiguity
up front via a dnsViewRef-scoped filter.
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

ZONE = {"ref": "dnsZones/1", "name": "example.net.", "type": "Primary"}


@pytest.fixture(autouse=True)
def _patch_exit_and_fail(monkeypatch):
    monkeypatch.setattr(dnsrecord.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(dnsrecord.AnsibleModule, "fail_json", fail_json)


def _run(**module_args):
    set_module_args(dict(mm_provider=MM_PROVIDER, **module_args))
    dnsrecord.run_module()


class TestBareZoneName:
    def test_looks_up_zone_by_bare_filter(self, mocker):
        get_single_refs = mocker.patch.object(
            dnsrecord,
            "get_single_refs",
            side_effect=[
                {"totalResults": 1, "dnsZones": [ZONE]},
                {"dnsRecords": [], "totalResults": 0},
                {"dnsRecords": [], "totalResults": 0},
            ],
        )
        mocker.patch.object(
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

        first_call_url = get_single_refs.call_args_list[0][0][0]
        assert first_call_url == "dnsZones?filter=example.net."

    def test_ambiguous_zone_match_fails_cleanly_instead_of_keyerror(
        self, mocker
    ):
        mocker.patch.object(
            dnsrecord,
            "get_single_refs",
            return_value={"invalid": True, "warnings": "ambiguous match"},
        )

        with pytest.raises(AnsibleFailJson) as exc:
            _run(
                name="beatles",
                data="172.16.17.2",
                rrtype="A",
                dnszone="example.net.",
            )

        assert "ambiguous match" in exc.value.args[0]["msg"]


class TestViewDisambiguatedZoneName:
    def test_resolves_view_then_filters_zone_by_dnsviewref(self, mocker):
        get_single_refs = mocker.patch.object(
            dnsrecord,
            "get_single_refs",
            side_effect=[
                {
                    "totalResults": 1,
                    "dnsViews": [{"ref": "dnsViews/3", "name": "internal"}],
                },
                {"totalResults": 1, "dnsZones": [ZONE]},
                {"dnsRecords": [], "totalResults": 0},
                {"dnsRecords": [], "totalResults": 0},
            ],
        )
        mocker.patch.object(
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
                dnszone="example.net. (internal)",
            )

        view_lookup_url = get_single_refs.call_args_list[0][0][0]
        zone_lookup_url = get_single_refs.call_args_list[1][0][0]
        assert view_lookup_url == "dnsViews?filter=internal"
        assert zone_lookup_url == (
            "dnsZones?filter=example.net.&dnsViewRef=dnsViews/3"
        )

    def test_unknown_view_fails_cleanly(self, mocker):
        get_single_refs = mocker.patch.object(
            dnsrecord,
            "get_single_refs",
            return_value={"totalResults": 0},
        )

        with pytest.raises(AnsibleFailJson) as exc:
            _run(
                name="beatles",
                data="172.16.17.2",
                rrtype="A",
                dnszone="example.net. (nosuchview)",
            )

        assert "nosuchview" in exc.value.args[0]["msg"]
        # Never got to the zone lookup at all.
        assert get_single_refs.call_count == 1
