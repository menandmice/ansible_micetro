"""Unit tests for plugins/modules/dhcpaddresspool.py."""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dhcpaddresspool,
)
from .utils import AnsibleExitJson, exit_json, set_module_args

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

SCOPE_REF = "dhcpScopes/1"

EXISTING_POOL = {
    "ref": "dhcpAddressPools/6",
    "name": "local",
    "from": "172.16.17.100",
    "to": "172.16.17.150",
    "dhcpScopeRef": SCOPE_REF,
}


@pytest.fixture(autouse=True)
def _patch_exit_json(monkeypatch):
    monkeypatch.setattr(dhcpaddresspool.AnsibleModule, "exit_json", exit_json)


def _run_and_capture_exit(**module_args):
    set_module_args(
        dict(
            mm_provider=MM_PROVIDER,
            dhcp_scope_ref=SCOPE_REF,
            from_address="172.16.17.100",
            to_address="172.16.17.150",
            **module_args,
        )
    )
    with pytest.raises(AnsibleExitJson) as exc:
        dhcpaddresspool.run_module()
    return exc.value.args[0]


def _get_single_refs_side_effect(empty_list=True, existing=None, scope_ok=True):
    def _side_effect(objname, _mm_provider):
        if objname == SCOPE_REF:
            return {"ref": SCOPE_REF} if scope_ok else {"invalid": True}
        if objname == "%s/dhcpAddressPools" % SCOPE_REF:
            if empty_list:
                return {"dhcpAddressPools": [], "totalResults": 0}
            return {"dhcpAddressPools": [existing], "totalResults": 1}
        raise AssertionError("unexpected get_single_refs call: %s" % objname)

    return _side_effect


class TestPresent:
    def test_fails_when_scope_ref_invalid(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            return_value={"invalid": True, "warnings": "not found"},
        )
        doapi = mocker.patch.object(dhcpaddresspool, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                dhcp_scope_ref="dhcpScopes/999",
                from_address="172.16.17.100",
                to_address="172.16.17.150",
                state="present",
            )
        )
        with pytest.raises(SystemExit):
            dhcpaddresspool.run_module()

        doapi.assert_not_called()

    def test_creates_when_not_existing(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_list=True),
        )
        doapi = mocker.patch.object(
            dhcpaddresspool,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpAddressPools/9"}},
            },
        )

        result = _run_and_capture_exit(state="present")

        doapi.assert_called_once_with(
            "%s/dhcpAddressPools" % SCOPE_REF,
            "POST",
            MM_PROVIDER,
            {
                "dhcpAddressPool": {
                    "dhcpScopeRef": SCOPE_REF,
                    "from": "172.16.17.100",
                    "to": "172.16.17.150",
                },
                "saveComment": "Ansible API",
            },
        )
        assert result["changed"] is True

    def test_creates_with_name(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_list=True),
        )
        doapi = mocker.patch.object(
            dhcpaddresspool,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpAddressPools/9"}},
            },
        )

        _run_and_capture_exit(state="present", name="My Pool")

        sent_body = doapi.call_args[0][3]
        assert sent_body["dhcpAddressPool"]["name"] == "My Pool"

    def test_noop_when_nothing_changed(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_POOL
            ),
        )
        doapi = mocker.patch.object(dhcpaddresspool, "doapi")

        result = _run_and_capture_exit(state="present", name="local")

        doapi.assert_not_called()
        assert result["changed"] is False

    def test_noop_when_no_name_requested(self, mocker):
        # No name requested at all - matching pool already has one, but
        # nothing was asked to change so nothing should happen.
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_POOL
            ),
        )
        doapi = mocker.patch.object(dhcpaddresspool, "doapi")

        result = _run_and_capture_exit(state="present")

        doapi.assert_not_called()
        assert result["changed"] is False

    def test_updates_name_via_flat_properties_map(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_POOL
            ),
        )
        doapi = mocker.patch.object(
            dhcpaddresspool, "doapi", return_value={"changed": True}
        )

        result = _run_and_capture_exit(state="present", name="renamed")

        doapi.assert_called_once_with(
            "dhcpAddressPools/6",
            "PUT",
            MM_PROVIDER,
            {
                "ref": "dhcpAddressPools/6",
                "saveComment": "Ansible API",
                "properties": {"name": "renamed"},
            },
        )
        assert result["changed"] is True


class TestAbsent:
    def test_deletes_when_pool_already_exists(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_POOL
            ),
        )
        doapi = mocker.patch.object(
            dhcpaddresspool, "doapi", return_value={"changed": True}
        )

        result = _run_and_capture_exit(state="absent")

        doapi.assert_called_once_with(
            "dhcpAddressPools/6",
            "DELETE",
            MM_PROVIDER,
            {"saveComment": "Ansible API"},
        )
        assert result["changed"] is True

    def test_noop_when_pool_does_not_exist(self, mocker):
        mocker.patch.object(
            dhcpaddresspool,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_list=True),
        )
        doapi = mocker.patch.object(dhcpaddresspool, "doapi")

        result = _run_and_capture_exit(state="absent")

        doapi.assert_not_called()
        assert result["changed"] is False
