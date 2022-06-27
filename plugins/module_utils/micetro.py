#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
# All imports
import time
from ansible.errors import AnsibleError
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


def doapi(url, method, mm_provider, databody):
    """Run an API call.

    Parameters:
        - url          -> Relative URL for the API entry point
        - method       -> The API method (GET, POST, DELETE,...)
        - mm_provider     -> Needed credentials for the API mm_provider
        - databody     -> Data needed for the API to perform the task

    Returns:
        - The response from the API call
        - The Ansible result dict

    When connection errors arise, there will be a multiple of tries,
    each a couple of seconds apart, this to handle high-availability
    """
    headers = {"Content-Type": "application/json"}
    apiurl = "%s/mmws/api/%s" % (mm_provider["mm_url"], url)
    result = {}

    # Maximum and current number of tries to connect to the Men&Mice API
    maxtries = 5
    tries = 0

    while tries <= 4:
        tries += 1
        try:
            resp = open_url(
                apiurl,
                method=method,
                force_basic_auth=True,
                url_username=mm_provider["mm_user"],
                url_password=mm_provider["mm_password"],
                data=json.dumps(databody),
                validate_certs=False,
                headers=headers,
            )

            # Response codes of the API are:
            #  - 200 => All OK, data returned in the body
            #  - 204 => All OK, no data returned in the body
            #  - *   => Something is wrong, error data in the body
            # But sometimes there is a situation where the response code
            # was 201 and with data in the body, so that is picked up as well

            # Get all API data and format return message
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
            result["changed"] = True
        except HTTPError as err:
            errbody = json.loads(err.read().decode())
            result["changed"] = False
            result["warnings"] = "%s: %s (%s)" % (
                err.msg,
                errbody["error"]["message"],
                errbody["error"]["code"],
            )
        except URLError as err:
            raise AnsibleError(
                "Failed lookup url for %s : %s" % (apiurl, to_native(err))
            )
        except SSLValidationError as err:
            raise AnsibleError(
                "Error validating the server's certificate for %s: %s"
                % (apiurl, to_native(err))
            )
        except ConnectionError as err:
            if tries == maxtries:
                raise AnsibleError(
                    "Error connecting to %s: %s" % (apiurl, to_native(err))
                )
            # There was a connection error, wait a little and retry
            time.sleep(0.25)

        if result.get("message", "") == "No Content":
            result["message"] = ""

        return result


def getrefs(objtype, mm_provider):
    """Get all objects of a certain type.

    Parameters
        - objtype  -> Object type to get all refs for (User, Group, ...)
        - mm_provider -> Needed credentials for the API mm_provider

    Returns:
        - The response from the API call
        - The Ansible result dict
    """
    return doapi(objtype, "GET", mm_provider, {})


def get_single_refs(objname, mm_provider):
    """Get all information about a single object.

    Parameters
        - objname  -> Object name to get all refs for (IPAMRecords/172.16.17.201)
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

    return "Unknow error"


def get_dhcp_scopes(mm_provider, ipaddress):
    """Given an IP Address, find the DHCP scopes."""
    url = "Ranges?filter=%s" % ipaddress

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
