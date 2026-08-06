"""Unit tests for the v2 API foundation in module_utils/micetro.py.

Covers session-token login/caching, the Bearer auth header, the
single-relogin-then-retry behavior on an expired session (HTTP 401),
and the camelCase v2 endpoint paths used by getrefs()/get_dhcp_scopes().
"""

import io
import json

import pytest
from ansible.module_utils.six.moves.urllib.error import HTTPError

from ansible_collections.menandmice.ansible_micetro.plugins.module_utils import (
    micetro,
)


@pytest.fixture(autouse=True)
def _clear_session_cache():
    """Every test starts with no cached session tokens."""
    micetro._SESSIONS.clear()
    yield
    micetro._SESSIONS.clear()


MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}


class FakeResponse:
    """Minimal stand-in for what open_url() returns."""

    def __init__(self, code, body):
        self.code = code
        self.reason = "No Content"
        self._body = body.encode("utf8") if isinstance(body, str) else body

    def read(self):
        return self._body


def _http_error(code, error_body):
    body = json.dumps(error_body).encode("utf8")
    return HTTPError(
        "http://micetro.example.net/mmws/api/v2/whatever",
        code,
        "error",
        {},
        io.BytesIO(body),
    )


def _session_body(token="tok-123"):
    return json.dumps({"result": {"session": token}})


class TestLogin:
    def test_login_returns_token_and_uses_loginname_field(self, mocker):
        open_url = mocker.patch.object(
            micetro, "open_url", return_value=FakeResponse(201, _session_body())
        )

        token = micetro._login(MM_PROVIDER)

        assert token == "tok-123"
        _, kwargs = open_url.call_args
        sent = json.loads(kwargs["data"].decode("utf8"))
        assert sent == {"loginName": "apiuser", "password": "apipasswd"}
        assert open_url.call_args[0][0] == (
            "http://micetro.example.net/mmws/api/v2/micetro/sessions"
        )

    def test_login_http_error_raises_micetro_api_error(self, mocker):
        mocker.patch.object(
            micetro,
            "open_url",
            side_effect=_http_error(
                401, {"error": {"message": "bad creds", "code": 1}}
            ),
        )

        with pytest.raises(micetro.MicetroAPIError):
            micetro._login(MM_PROVIDER)


class TestSessionToken:
    def test_caches_token_across_calls(self, mocker):
        open_url = mocker.patch.object(
            micetro, "open_url", return_value=FakeResponse(201, _session_body())
        )

        first = micetro._session_token(MM_PROVIDER)
        second = micetro._session_token(MM_PROVIDER)

        assert first == second == "tok-123"
        assert open_url.call_count == 1

    def test_force_bypasses_cache(self, mocker):
        open_url = mocker.patch.object(
            micetro, "open_url", return_value=FakeResponse(201, _session_body())
        )

        micetro._session_token(MM_PROVIDER)
        micetro._session_token(MM_PROVIDER, force=True)

        assert open_url.call_count == 2

    def test_different_providers_get_separate_sessions(self, mocker):
        mocker.patch.object(
            micetro, "open_url", return_value=FakeResponse(201, _session_body())
        )
        other_provider = dict(MM_PROVIDER, mm_user="otheruser")

        micetro._session_token(MM_PROVIDER)
        micetro._session_token(other_provider)

        assert len(micetro._SESSIONS) == 2


class TestDoapi:
    def test_get_success_returns_message_and_changed(self, mocker):
        mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body()),
                FakeResponse(200, json.dumps({"result": {"groups": []}})),
            ],
        )

        result = micetro.doapi("groups", "GET", MM_PROVIDER, {})

        assert result == {
            "changed": True,
            "message": {"result": {"groups": []}},
        }

    def test_sends_bearer_token_and_v2_base_path(self, mocker):
        open_url = mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body("abc")),
                FakeResponse(200, json.dumps({"result": {}})),
            ],
        )

        micetro.doapi("groups", "GET", MM_PROVIDER, {})

        request_call = open_url.call_args_list[1]
        assert (
            request_call[0][0]
            == "http://micetro.example.net/mmws/api/v2/groups"
        )
        assert request_call[1]["headers"]["Authorization"] == "Bearer abc"

    def test_204_no_content_becomes_empty_message(self, mocker):
        mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body()),
                FakeResponse(204, ""),
            ],
        )

        result = micetro.doapi("groups/4", "DELETE", MM_PROVIDER, {})

        assert result == {"changed": True, "message": ""}

    def test_http_error_returns_warnings_without_raising(self, mocker):
        mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body()),
                _http_error(
                    404, {"error": {"message": "not found", "code": 42}}
                ),
            ],
        )

        result = micetro.doapi("groups/999", "GET", MM_PROVIDER, {})

        assert result["changed"] is False
        assert "not found" in result["warnings"]
        assert "42" in result["warnings"]

    def test_401_triggers_single_relogin_then_retries_successfully(
        self, mocker
    ):
        open_url = mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body("first-token")),
                _http_error(
                    401,
                    {"error": {"message": "Missing Session ID.", "code": 5002}},
                ),
                FakeResponse(201, _session_body("second-token")),
                FakeResponse(200, json.dumps({"result": {"ok": True}})),
            ],
        )

        result = micetro.doapi("groups", "GET", MM_PROVIDER, {})

        assert result == {"changed": True, "message": {"result": {"ok": True}}}
        assert open_url.call_count == 4
        last_request_headers = open_url.call_args_list[-1][1]["headers"]
        assert last_request_headers["Authorization"] == "Bearer second-token"

    def test_persistent_401_does_not_loop_forever(self, mocker):
        mocker.patch.object(
            micetro,
            "open_url",
            side_effect=[
                FakeResponse(201, _session_body("first-token")),
                _http_error(
                    401,
                    {"error": {"message": "Missing Session ID.", "code": 5002}},
                ),
                FakeResponse(201, _session_body("second-token")),
                _http_error(
                    401,
                    {"error": {"message": "Missing Session ID.", "code": 5002}},
                ),
            ],
        )

        result = micetro.doapi("groups", "GET", MM_PROVIDER, {})

        # Only relogs in once; the second 401 is reported, not retried again.
        assert result["changed"] is False
        assert "Missing Session ID" in result["warnings"]


class TestGetrefsAndFriends:
    def test_getrefs_uses_get_and_passed_objtype(self, mocker):
        doapi = mocker.patch.object(
            micetro, "doapi", return_value={"message": {}}
        )

        micetro.getrefs("groups", MM_PROVIDER)

        doapi.assert_called_once_with("groups", "GET", MM_PROVIDER, {})

    def test_get_single_refs_unwraps_result(self, mocker):
        mocker.patch.object(
            micetro,
            "doapi",
            return_value={"message": {"result": {"groups": []}}},
        )

        result = micetro.get_single_refs("groups", MM_PROVIDER)

        assert result == {"groups": []}

    def test_get_single_refs_marks_warnings_invalid(self, mocker):
        mocker.patch.object(micetro, "doapi", return_value={"warnings": "boom"})

        result = micetro.get_single_refs("groups/999", MM_PROVIDER)

        assert result["invalid"] is True

    def test_get_dhcp_scopes_uses_lowercase_ranges_endpoint(self, mocker):
        doapi = mocker.patch.object(
            micetro,
            "doapi",
            return_value={
                "message": {
                    "result": {
                        "ranges": [
                            {"dhcpScopes": [{"ref": "dhcpScopes/1"}]},
                        ]
                    }
                }
            },
        )

        scopes = micetro.get_dhcp_scopes(MM_PROVIDER, "172.16.17.2")

        doapi.assert_called_once_with(
            "ranges?filter=172.16.17.2", "GET", MM_PROVIDER, {}
        )
        assert scopes == ["dhcpScopes/1"]
