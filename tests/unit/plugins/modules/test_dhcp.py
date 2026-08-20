"""Unit tests for plugins/modules/dhcp.py."""

import pytest

from ansible_collections.menandmice.ansible_micetro.plugins.modules import (
    dhcp,
)
from .utils import AnsibleExitJson, exit_json, set_module_args

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

IP = "172.16.17.8"
SCOPE_REF = "dhcpScopes/1"

EXISTING_RESERVATION = {
    "ref": "dhcpReservations/9",
    "name": "old",
    "clientIdentifier": "00:00:00:00:00:00",
    "addresses": [IP],
}


@pytest.fixture(autouse=True)
def _patch_exit_json(monkeypatch):
    monkeypatch.setattr(dhcp.AnsibleModule, "exit_json", exit_json)


def _run_and_capture_exit(**module_args):
    set_module_args(
        dict(
            mm_provider=MM_PROVIDER,
            name="myreservation",
            ipaddress=IP,
            macaddress="44:55:66:77:88:99",
            **module_args,
        )
    )
    with pytest.raises(AnsibleExitJson) as exc:
        dhcp.run_module()
    return exc.value.args[0]


def _get_single_refs_side_effect(reservations=None, invalid=False):
    def _side_effect(objname, _mm_provider):
        assert objname == "ipamRecords/%s" % IP
        if invalid:
            return {"invalid": True, "warnings": "not found"}
        return {"ipamRecord": {"dhcpReservations": reservations or []}}

    return _side_effect


class TestPresentCreate:
    def test_creates_without_optional_fields(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(),
        )
        mocker.patch.object(
            dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF]
        )
        doapi = mocker.patch.object(
            dhcp, "doapi", return_value={"changed": True, "message": ""}
        )

        result = _run_and_capture_exit(state="present")

        doapi.assert_called_once_with(
            "%s/dhcpReservations" % SCOPE_REF,
            "POST",
            MM_PROVIDER,
            {
                "saveComment": "Ansible API",
                "dhcpReservation": {
                    "name": "myreservation",
                    "clientIdentifier": "44:55:66:77:88:99",
                    "reservationMethod": "HardwareAddress",
                    "addresses": [IP],
                },
            },
        )
        assert result["changed"] is True

    def test_creates_with_optional_fields(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(),
        )
        mocker.patch.object(
            dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF]
        )
        doapi = mocker.patch.object(
            dhcp, "doapi", return_value={"changed": True, "message": ""}
        )

        _run_and_capture_exit(
            state="present",
            ddnshost="host.example.com",
            filename="pxelinux.0",
            servername="tftp.example.com",
            nextserver="10.0.0.5",
        )

        sent_body = doapi.call_args[0][3]
        assert sent_body["dhcpReservation"]["ddnsHostName"] == (
            "host.example.com"
        )
        assert sent_body["dhcpReservation"]["filename"] == "pxelinux.0"
        assert sent_body["dhcpReservation"]["serverName"] == (
            "tftp.example.com"
        )
        assert sent_body["dhcpReservation"]["nextServer"] == "10.0.0.5"

    def test_fails_when_no_scope_found(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[])
        doapi = mocker.patch.object(dhcp, "doapi")

        set_module_args(
            dict(
                mm_provider=MM_PROVIDER,
                name="myreservation",
                ipaddress=IP,
                macaddress="44:55:66:77:88:99",
                state="present",
            )
        )
        with pytest.raises(SystemExit):
            dhcp.run_module()

        doapi.assert_not_called()

    def test_returns_warnings_when_ip_invalid(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(invalid=True),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(dhcp, "doapi")

        result = _run_and_capture_exit(state="present")

        doapi.assert_not_called()
        assert result["changed"] is False
        assert result["warnings"] == "not found"


class TestPresentUpdate:
    def test_updates_when_changed(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                reservations=[EXISTING_RESERVATION]
            ),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(
            dhcp, "doapi", return_value={"changed": True, "message": ""}
        )

        result = _run_and_capture_exit(state="present")

        doapi.assert_called_once_with(
            "dhcpReservations/9",
            "PUT",
            MM_PROVIDER,
            {
                "ref": "dhcpReservations/9",
                "saveComment": "Ansible API",
                "deleteUnspecified": False,
                "properties": {
                    "name": "myreservation",
                    "clientIdentifier": "44:55:66:77:88:99",
                    "addresses": IP,
                },
            },
        )
        assert result["changed"] is True

    def test_noop_when_nothing_changed(self, mocker):
        matching = dict(
            EXISTING_RESERVATION,
            name="myreservation",
            clientIdentifier="44:55:66:77:88:99",
        )
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(reservations=[matching]),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(dhcp, "doapi")

        result = _run_and_capture_exit(state="present")

        doapi.assert_not_called()
        assert result["changed"] is False

    def test_update_does_not_send_unset_optional_fields(self, mocker):
        # Regression test: sending ddnsHostName (or the other optional
        # fields) unconditionally makes MS DHCP servers reject the whole
        # request, even when the caller never asked to set them.
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                reservations=[EXISTING_RESERVATION]
            ),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(
            dhcp, "doapi", return_value={"changed": True, "message": ""}
        )

        _run_and_capture_exit(state="present")

        sent_properties = doapi.call_args[0][3]["properties"]
        for field in ("ddnsHostName", "filename", "serverName", "nextServer"):
            assert field not in sent_properties


class TestAbsent:
    def test_deletes_when_reservation_exists(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(
                reservations=[EXISTING_RESERVATION]
            ),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(
            dhcp, "doapi", return_value={"changed": True, "message": ""}
        )

        result = _run_and_capture_exit(state="absent")

        doapi.assert_called_once_with(
            "dhcpReservations/9",
            "DELETE",
            MM_PROVIDER,
            {"saveComment": "Ansible API"},
        )
        assert result["changed"] is True

    def test_noop_when_reservation_does_not_exist(self, mocker):
        mocker.patch.object(
            dhcp,
            "get_single_refs",
            side_effect=_get_single_refs_side_effect(),
        )
        mocker.patch.object(dhcp, "get_dhcp_scopes", return_value=[SCOPE_REF])
        doapi = mocker.patch.object(dhcp, "doapi")

        result = _run_and_capture_exit(state="absent")

        doapi.assert_not_called()
        assert result["changed"] is False
