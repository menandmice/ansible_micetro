"""Unit tests for plugins/modules/dhcpsuperscope.py."""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dhcpsuperscope,
)
from .utils import AnsibleExitJson, exit_json, set_module_args

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

EXISTING_SUPERSCOPE = {
    "ref": "dhcpSuperscopes/6",
    "name": "local",
    "description": "A local superscope",
    "dhcpServerRef": "dhcpServers/1",
    "scopeCount": 0,
}


@pytest.fixture(autouse=True)
def _patch_exit_json(monkeypatch):
    monkeypatch.setattr(dhcpsuperscope.AnsibleModule, "exit_json", exit_json)


def _run_and_capture_exit(**module_args):
    set_module_args(
        dict(
            mm_provider=MM_PROVIDER,
            dhcp_server_ref="dhcpServers/1",
            **module_args,
        )
    )
    with pytest.raises(AnsibleExitJson) as exc:
        dhcpsuperscope.run_module()
    return exc.value.args[0]


def _get_single_refs_side_effect(empty_search=True, existing=None):
    def _side_effect(objname, _mm_provider):
        if objname == "dhcpServers/1":
            return {"ref": "dhcpServers/1"}
        if objname.startswith("dhcpSuperscopes?"):
            if empty_search:
                return {"superscopes": [], "totalResults": 0}
            return {"superscopes": [existing], "totalResults": 1}
        raise AssertionError("unexpected get_single_refs call: %s" % objname)

    return _side_effect


class TestPresent:
    def test_fails_when_dhcp_server_ref_invalid(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            return_value={"invalid": True, "warnings": "not found"},
        )
        doapi = mocker.patch.object(dhcpsuperscope, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                dhcp_server_ref="dhcpServers/999",
                name="local",
                state="present",
            )
        )
        with pytest.raises(SystemExit):
            dhcpsuperscope.run_module()

        doapi.assert_not_called()

    def test_creates_when_not_existing(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_search=True),
        )
        doapi = mocker.patch.object(
            dhcpsuperscope,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpSuperscopes/9"}},
            },
        )

        result = _run_and_capture_exit(
            name="newscope", description="brand new", state="present"
        )

        doapi.assert_called_once_with(
            "dhcpSuperscopes",
            "POST",
            MM_PROVIDER,
            {
                "superscope": {
                    "name": "newscope",
                    "description": "brand new",
                    "dhcpServerRef": "dhcpServers/1",
                },
                "saveComment": "Ansible API",
            },
        )
        assert result["changed"] is True

    def test_creates_with_initial_scope_refs(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_search=True),
        )
        doapi = mocker.patch.object(
            dhcpsuperscope,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpSuperscopes/9"}},
            },
        )

        _run_and_capture_exit(
            name="newscope",
            description="brand new",
            state="present",
            dhcp_scope_refs=["dhcpScopes/1", "dhcpScopes/2"],
        )

        _, kwargs = doapi.call_args
        sent_body = doapi.call_args[0][3]
        assert sent_body["dhcpScopeRefs"] == ["dhcpScopes/1", "dhcpScopes/2"]

    def test_noop_when_nothing_changed(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_search=False, existing=EXISTING_SUPERSCOPE
            ),
        )
        doapi = mocker.patch.object(dhcpsuperscope, "doapi")

        result = _run_and_capture_exit(
            name="local", description="A local superscope", state="present"
        )

        doapi.assert_not_called()
        assert result["changed"] is False

    def test_updates_description_via_flat_properties_map(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_search=False, existing=EXISTING_SUPERSCOPE
            ),
        )
        doapi = mocker.patch.object(
            dhcpsuperscope, "doapi", return_value={"changed": True}
        )

        result = _run_and_capture_exit(
            name="local", description="new description", state="present"
        )

        doapi.assert_called_once_with(
            "dhcpSuperscopes/6",
            "PUT",
            MM_PROVIDER,
            {
                "ref": "dhcpSuperscopes/6",
                "saveComment": "Ansible API",
                "properties": {"description": "new description"},
            },
        )
        assert result["changed"] is True


class TestAbsent:
    def test_deletes_when_superscope_already_exists(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_search=False, existing=EXISTING_SUPERSCOPE
            ),
        )
        doapi = mocker.patch.object(
            dhcpsuperscope, "doapi", return_value={"changed": True}
        )

        result = _run_and_capture_exit(name="local", state="absent")

        doapi.assert_called_once_with(
            "dhcpSuperscopes/6", "DELETE", MM_PROVIDER, {}
        )
        assert result["changed"] is True

    def test_noop_when_superscope_does_not_exist(self, mocker):
        mocker.patch.object(
            dhcpsuperscope,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_search=True),
        )
        doapi = mocker.patch.object(dhcpsuperscope, "doapi")

        result = _run_and_capture_exit(name="does-not-exist", state="absent")

        doapi.assert_not_called()
        assert result["changed"] is False
