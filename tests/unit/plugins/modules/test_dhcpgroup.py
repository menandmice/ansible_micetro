"""Unit tests for plugins/modules/dhcpgroup.py."""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dhcpgroup,
)
from .utils import AnsibleExitJson, exit_json, set_module_args

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

OWNER_REF = "dhcpServers/1"

EXISTING_GROUP = {
    "ref": "dhcpGroups/6",
    "name": "local",
    "ownerRef": OWNER_REF,
}


@pytest.fixture(autouse=True)
def _patch_exit_json(monkeypatch):
    monkeypatch.setattr(dhcpgroup.AnsibleModule, "exit_json", exit_json)


def _run_and_capture_exit(**module_args):
    set_module_args(
        dict(mm_provider=MM_PROVIDER, owner_ref=OWNER_REF, **module_args)
    )
    with pytest.raises(AnsibleExitJson) as exc:
        dhcpgroup.run_module()
    return exc.value.args[0]


def _get_single_refs_side_effect(
    empty_list=True, existing=None, owner_ok=True, known_refs=None
):
    known_refs = known_refs or {}

    def _side_effect(objname, _mm_provider):
        if objname == OWNER_REF:
            return {"ref": OWNER_REF} if owner_ok else {"invalid": True}
        if objname == "%s/dhcpGroups" % OWNER_REF:
            if empty_list:
                return {"dhcpGroups": [], "totalResults": 0}
            return {"dhcpGroups": [existing], "totalResults": 1}
        if objname in known_refs:
            return known_refs[objname]
        raise AssertionError("unexpected get_single_refs call: %s" % objname)

    return _side_effect


class TestPresent:
    def test_fails_when_owner_ref_invalid(self, mocker):
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            return_value={"invalid": True, "warnings": "not found"},
        )
        doapi = mocker.patch.object(dhcpgroup, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                owner_ref="dhcpServers/999",
                name="local",
                state="present",
            )
        )
        with pytest.raises(SystemExit):
            dhcpgroup.run_module()

        doapi.assert_not_called()

    def test_creates_when_not_existing(self, mocker):
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_list=True),
        )
        doapi = mocker.patch.object(
            dhcpgroup,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpGroups/9"}},
            },
        )

        result = _run_and_capture_exit(name="newgroup", state="present")

        doapi.assert_called_once_with(
            "%s/dhcpGroups" % OWNER_REF,
            "POST",
            MM_PROVIDER,
            {
                "dhcpGroup": {"name": "newgroup", "ownerRef": OWNER_REF},
                "saveComment": "Ansible API",
            },
        )
        assert result["changed"] is True

    def test_creates_with_parent_ref(self, mocker):
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=True,
                known_refs={"dhcpGroups/1": {"ref": "dhcpGroups/1"}},
            ),
        )
        doapi = mocker.patch.object(
            dhcpgroup,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "dhcpGroups/9"}},
            },
        )

        _run_and_capture_exit(
            name="newgroup", state="present", parent_ref="dhcpGroups/1"
        )

        sent_body = doapi.call_args[0][3]
        assert sent_body["dhcpGroup"]["parentRef"] == "dhcpGroups/1"

    def test_fails_when_parent_ref_invalid(self, mocker):
        def side_effect(objname, _mm_provider):
            if objname == OWNER_REF:
                return {"ref": OWNER_REF}
            if objname == "dhcpGroups/999":
                return {"invalid": True}
            raise AssertionError("unexpected call: %s" % objname)

        mocker.patch.object(
            dhcpgroup, "get_single_refs", side_effect=side_effect
        )
        doapi = mocker.patch.object(dhcpgroup, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                owner_ref=OWNER_REF,
                name="local",
                state="present",
                parent_ref="dhcpGroups/999",
            )
        )
        with pytest.raises(SystemExit):
            dhcpgroup.run_module()

        doapi.assert_not_called()

    def test_noop_when_group_already_exists(self, mocker):
        # A group is matched by name, so an existing group is always
        # found with group["name"] == the requested name - there's no
        # "rename" scenario reachable through this lookup, and no other
        # mutable field on a DHCP group (no description; parentRef/
        # ownerRef are create-only).
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_GROUP
            ),
        )
        doapi = mocker.patch.object(dhcpgroup, "doapi")

        result = _run_and_capture_exit(name="local", state="present")

        doapi.assert_not_called()
        assert result["changed"] is False


class TestAbsent:
    def test_deletes_when_group_already_exists(self, mocker):
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                empty_list=False, existing=EXISTING_GROUP
            ),
        )
        doapi = mocker.patch.object(
            dhcpgroup, "doapi", return_value={"changed": True}
        )

        result = _run_and_capture_exit(name="local", state="absent")

        doapi.assert_called_once_with(
            "dhcpGroups/6",
            "DELETE",
            MM_PROVIDER,
            {"saveComment": "Ansible API"},
        )
        assert result["changed"] is True

    def test_noop_when_group_does_not_exist(self, mocker):
        mocker.patch.object(
            dhcpgroup,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(empty_list=True),
        )
        doapi = mocker.patch.object(dhcpgroup, "doapi")

        result = _run_and_capture_exit(name="does-not-exist", state="absent")

        doapi.assert_not_called()
        assert result["changed"] is False
