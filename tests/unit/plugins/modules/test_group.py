"""Unit tests for plugins/modules/group.py.

Regression coverage for the fixed exists-check bug: `group.py` used to
gate its "get all groups" call behind `module.params.get("groups")`, a
parameter that group.py never actually defines, so the existing-groups
list was always empty and `group_exists` was always False. As a result
`state: absent` never issued a DELETE and `state: present` never took the
update path. See GitLab issue #3 / docs/API_GAP_ASSESSMENT.md.
"""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import group
from .utils import AnsibleExitJson, exit_json, set_module_args

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

EXISTING_GROUP = {
    "ref": "groups/6",
    "name": "local",
    "description": "A local group",
    "adIntegrated": False,
    "builtIn": False,
    "groupMembers": [],
    "roles": [],
}


@pytest.fixture(autouse=True)
def _patch_exit_json(monkeypatch):
    monkeypatch.setattr(group.AnsibleModule, "exit_json", exit_json)


def _run_and_capture_exit(**module_args):
    set_module_args(dict(mm_provider=MM_PROVIDER, **module_args))
    with pytest.raises(AnsibleExitJson) as exc:
        group.run_module()
    return exc.value.args[0]


class TestAbsent:
    def test_deletes_when_group_already_exists(self, mocker):
        mocker.patch.object(
            group,
            "getrefs",
            return_value={"message": {"result": {"groups": [EXISTING_GROUP]}}},
        )
        doapi = mocker.patch.object(
            group, "doapi", return_value={"changed": True, "message": ""}
        )

        result = _run_and_capture_exit(name="local", state="absent")

        # The bug made this a silent no-op; it must now actually delete,
        # using the bare ref (not a double-prefixed "groups/groups/6").
        doapi.assert_called_once_with(
            "groups/6",
            "DELETE",
            MM_PROVIDER,
            {"saveComment": "Ansible API"},
        )
        assert result["changed"] is True

    def test_noop_when_group_does_not_exist(self, mocker):
        mocker.patch.object(
            group,
            "getrefs",
            return_value={"message": {"result": {"groups": []}}},
        )
        doapi = mocker.patch.object(group, "doapi")

        result = _run_and_capture_exit(name="does-not-exist", state="absent")

        doapi.assert_not_called()
        assert result["changed"] is False


class TestPresent:
    def test_creates_when_group_does_not_exist(self, mocker):
        mocker.patch.object(
            group,
            "getrefs",
            return_value={"message": {"result": {"groups": []}}},
        )
        doapi = mocker.patch.object(
            group,
            "doapi",
            return_value={
                "changed": True,
                "message": {"result": {"ref": "groups/9"}},
            },
        )

        result = _run_and_capture_exit(
            name="newgroup", desc="brand new", state="present"
        )

        doapi.assert_called_once_with(
            "groups",
            "POST",
            MM_PROVIDER,
            {
                "saveComment": "Ansible API",
                "group": {
                    "name": "newgroup",
                    "description": "brand new",
                    "groupMembers": [],
                    "roles": [],
                    "builtIn": False,
                },
            },
        )
        assert result["changed"] is True

    def test_noop_when_nothing_changed(self, mocker):
        mocker.patch.object(
            group,
            "getrefs",
            return_value={"message": {"result": {"groups": [EXISTING_GROUP]}}},
        )
        doapi = mocker.patch.object(group, "doapi")

        result = _run_and_capture_exit(
            name="local", desc="A local group", state="present"
        )

        doapi.assert_not_called()
        assert result["changed"] is False

    def test_updates_description_via_flat_properties_map(self, mocker):
        mocker.patch.object(
            group,
            "getrefs",
            return_value={"message": {"result": {"groups": [EXISTING_GROUP]}}},
        )
        doapi = mocker.patch.object(
            group, "doapi", return_value={"changed": True, "message": ""}
        )

        result = _run_and_capture_exit(
            name="local", desc="new description", state="present"
        )

        doapi.assert_called_once_with(
            "groups/6",
            "PUT",
            MM_PROVIDER,
            {
                "ref": "groups/6",
                "saveComment": "Ansible API",
                "properties": {
                    "name": "local",
                    "description": "new description",
                },
            },
        )
        assert result["changed"] is True
