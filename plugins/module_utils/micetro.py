#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2023, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
# All imports

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import time
from ansible.module_utils._text import to_native
from ansible.module_utils.connection import ConnectionError
from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils.urls import open_url, SSLValidationError

try:
    from ansible.utils_utils.common import json
except ImportError:
    import json

# The API sometimes has another concept of true and false than Python
# does, so 0 is true and 1 is false.
TRUEFALSE = {
    True: 0,
    False: 1,
}

# Base path for the versioned, camelCase Micetro REST API (v2). See
# docs/API_GAP_ASSESSMENT.md for why this replaced the old unversioned,
# PascalCase API.
API_BASE = "mmws/api/v2"

# Cache of active session tokens, keyed by (mm_url, mm_user), so a single
# module/lookup run doesn't log in again for every API call it makes.
_SESSIONS = {}


class MicetroAPIError(Exception):
    """Raised when the Micetro API can't be reached or returns a fatal error.

    Deliberately not ansible.errors.AnsibleError: this file is imported by
    both controller-side plugins (lookup, inventory) and Ansible modules,
    and modules execute inside the AnsiballZ zip sandbox on the target.
    Importing ansible.errors at module scope there conflicts with the
    bundled, restricted copy of ansible.module_utils._internal on current
    ansible-core releases. Controller-side callers that want the usual
    Ansible-formatted error output should catch this and re-raise as
    AnsibleError themselves.
    """


def _login(mm_provider):
    """Create a new API session and return its token."""
    apiurl = "%s/%s/micetro/sessions" % (mm_provider["mm_url"], API_BASE)
    try:
        resp = open_url(
            apiurl,
            method="POST",
            data=json.dumps(
                {
                    "loginName": mm_provider["mm_user"],
                    "password": mm_provider["mm_password"],
                },
                ensure_ascii=False,
            ).encode("utf8"),
            validate_certs=False,
            headers={"Content-Type": "application/json"},
        )
        body = json.loads(resp.read().decode("utf8"))
    except HTTPError as err:
        raise MicetroAPIError(
            "Failed to authenticate to %s: %s"
            % (mm_provider["mm_url"], to_native(err))
        )
    except (URLError, SSLValidationError) as err:
        raise MicetroAPIError(
            "Failed to reach %s: %s" % (mm_provider["mm_url"], to_native(err))
        )
    return body["result"]["session"]


def _session_token(mm_provider, force=False):
    """Return a cached session token, logging in first if needed."""
    key = (mm_provider["mm_url"], mm_provider["mm_user"])
    if force or key not in _SESSIONS:
        _SESSIONS[key] = _login(mm_provider)
    return _SESSIONS[key]


def doapi(url, method, mm_provider, databody):
    """Run an API call.

    Parameters:
        - url          -> Relative URL for the API entry point
        - method       -> The API method (GET, POST, DELETE,...)
        - mm_provider  -> Needed credentials for the API mm_provider
        - databody     -> Data needed for the API to perform the task

    Returns:
        - The response from the API call
        - The Ansible result dict

    When connection errors arise, there will be a multiple of tries,
    each a couple of seconds apart, this to handle high-availability.
    A single re-login (and retry) is attempted on an expired/invalid
    session (HTTP 401) before giving up.
    """
    apiurl = "%s/%s/%s" % (mm_provider["mm_url"], API_BASE, url)

    maxtries = 5
    relogged_in = False

    for tries in range(1, maxtries + 1):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % _session_token(mm_provider),
        }
        try:
            resp = open_url(
                apiurl,
                method=method,
                data=json.dumps(databody, ensure_ascii=False).encode("utf8"),
                validate_certs=False,
                headers=headers,
            )
        except HTTPError as err:
            if err.code == 401 and not relogged_in:
                # Session expired or was invalidated; log in again once
                # and retry this same call.
                relogged_in = True
                _session_token(mm_provider, force=True)
                continue
            errbody = json.loads(err.read().decode())
            return {
                "changed": False,
                "warnings": "%s: %s (%s)"
                % (
                    err.msg,
                    errbody["error"]["message"],
                    errbody["error"]["code"],
                ),
            }
        except URLError as err:
            raise MicetroAPIError(
                "Failed lookup url for %s : %s" % (apiurl, to_native(err))
            )
        except SSLValidationError as err:
            raise MicetroAPIError(
                "Error validating the server's certificate for %s: %s"
                % (apiurl, to_native(err))
            )
        except ConnectionError as err:
            if tries == maxtries:
                raise MicetroAPIError(
                    "Error connecting to %s: %s" % (apiurl, to_native(err))
                )
            # There was a connection error, wait a little and retry
            time.sleep(0.25)
            continue

        # Response codes of the API are:
        #  - 200 => All OK, data returned in the body
        #  - 204 => All OK, no data returned in the body
        #  - *   => Something is wrong, error data in the body
        # But sometimes there is a situation where the response code
        # was 201 and with data in the body, so that is picked up as well
        result = {"changed": True}
        response = resp.read()
        if resp.code == 200:
            # 200 => Data in the body
            # Sometimes (older Python) the data is not a string but a
            # byte array.
            if isinstance(response, bytes):
                response = response.decode("utf8")
            result["message"] = json.loads(response)
        elif resp.code == 201:
            # 201 => Sometimes data in the body??
            try:
                result["message"] = json.loads(response)
            except ValueError:
                result["message"] = ""
        else:
            # No response from API (204 => No data)
            try:
                result["message"] = resp.reason
            except AttributeError:
                result["message"] = ""

        if result.get("message", "") == "No Content":
            result["message"] = ""

        return result


def getrefs(objtype, mm_provider):
    """Get all objects of a certain type.

    Parameters
        - objtype  -> Object type to get all refs for (users, groups, ...)
        - mm_provider -> Needed credentials for the API mm_provider

    Returns:
        - The response from the API call
        - The Ansible result dict
    """
    return doapi(objtype, "GET", mm_provider, {})


def get_single_refs(objname, mm_provider):
    """Get all information about a single object.

    Parameters
        - objname  -> Object name to get all refs for (ipamRecords/172.16.17.201)
        - mm_provider -> Needed credentials for the API mm_provider

    Returns:
        - The response from the API call
        - The Ansible result dict
    """
    resp = doapi(objname, "GET", mm_provider, {})
    if resp.get("message"):
        return resp["message"]["result"]

    if resp.get("warnings"):
        resp["invalid"] = True
        return resp

    return "Unknown error"


def get_dhcp_scopes(mm_provider, ipaddress):
    """Given an IP Address, find the DHCP scopes."""
    url = "ranges?filter=%s" % ipaddress

    # Get the information of this IP range.
    # I'm not sure if an IP address can be part of multiple DHCP
    # scopes, but in the API it's defined as a list, so find them all.
    resp = doapi(url, "GET", mm_provider, {})

    # Gather all DHCP scopes for this IP address
    scopes = []
    if resp:
        for dhcpranges in resp["message"]["result"]["ranges"]:
            for scope in dhcpranges["dhcpScopes"]:
                scopes.append(scope["ref"])

    # Return all scopes
    return scopes
