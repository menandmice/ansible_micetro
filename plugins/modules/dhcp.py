#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible DHCP reservation module.

Part of the Men&Mice Ansible integration

Module to manage DHCP reservations in the Men&Mice Suite
  - Set or release a DHCP reservation
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible.utils import unicode
from ansible_collections.ansilabnl.micetro.plugins.module_utils.micetro import (
    doapi,
    get_single_refs,
    get_dhcp_scopes,
)

DOCUMENTATION = r"""
  module: dhcp
  short_description: Manage DHCP reservations on the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Manage DHCP reservations on the Men&Mice Suite
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the reservation.
      type: bool
      required: False
      choices: [ absent, present ]
      default: present
    name:
      description:
        - Name of the reservation
      type: str
      required: True
    ipaddress:
      description:
        - The IP address(es) to make a reservation on.
        - When the IP address is changed a new reservation is made.
        - It is not allowed to make reservations in DHCP blocks.
      type: list
      elements: str
      required: True
    macaddress:
      description: MAC address for the IP address.
      type: str
      required: True
    ddnshost:
      description: The dynamic DNS host to place the entry in.
      type: str
      required: False
    filename:
      description: Filename to place the entry in.
      type: str
      required: False
    servername:
      description: Server to place the entry in.
      type: str
      required: False
    nextserver:
      description: Next server as DHCP option (bootp).
      type: str
      required: False
    deleteunspecified:
      description: Clear properties that are not explicitly set.
      type: bool
      required: False
    mm_provider:
      description: Definition of the Men&Mice suite API mm_provider.
      type: dict
      required: True
      suboptions:
        mm_url:
          description: Men&Mice API server to connect to.
          required: True
          type: str
        mm_user:
          description: userid to login with into the API.
          required: True
          type: str
        mm_password:
          description: password to login with into the API.
          required: True
          type: str
          no_log: True
"""

EXAMPLES = r"""
- name: Add a reservation for an IP address
 ansilabnl.micetro.dhcp:
    state: present
    name: myreservation
    ipaddress: 172.16.17.8
    macaddress: 44:55:66:77:88:99
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost
"""

RETURN = r"""
message:
    description: The output message from the Men&Mice System.
    type: str
    returned: always
"""


def run_module():
    """Run Ansible module."""
    # Define available arguments/parameters a user can pass to the module
    module_args = dict(
        state=dict(
            type="str",
            required=False,
            default="present",
            choices=["absent", "present"],
        ),
        name=dict(type="str", required=True),
        ipaddress=dict(type="list", required=True),
        macaddress=dict(type="str", required=True),
        ddnshost=dict(type="str", required=False, default=""),
        filename=dict(type="str", required=False, default=""),
        servername=dict(type="str", required=False, default=""),
        nextserver=dict(type="str", required=False, default=""),
        deleteunspecified=dict(type="bool", required=False, default=False),
        mm_provider=dict(
            type="dict",
            required=True,
            options=dict(
                mm_url=dict(type="str", required=True, no_log=False),
                mm_user=dict(type="str", required=True, no_log=False),
                mm_password=dict(type="str", required=True, no_log=True),
            ),
        ),
    )

    # Seed the result dict in the object
    # We primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = {"changed": False, "message": ""}

    # The AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    # If the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # Get all API settings
    mm_provider = module.params["mm_provider"]

    for ipaddress in module.params["ipaddress"]:
        # Get the existing reservation for requested IP address
        refs = "IPAMRecords/%s" % ipaddress
        resp = get_single_refs(refs, mm_provider)
        # If the 'invalid' key exists, the request failed.
        if resp.get("invalid", None):
            result.pop("message", None)
            result["warnings"] = resp.get("warnings", None)
            result["changed"] = False
            break

        scopes = get_dhcp_scopes(mm_provider, ipaddress)
        if not scopes:
            errormsg = "No DHCP scope for IP address %s", ipaddress
            module.fail_json(msg=errormsg)

        if resp["ipamRecord"]["dhcpReservations"]:
            # A reservation for this IP address was found
            if module.params["state"] == "present":
                # Reservation wanted, already in place so update
                reservations = resp["ipamRecord"]["dhcpReservations"]
                http_method = "PUT"
                for reservation in reservations:
                    databody = {
                        "ref": reservation["ref"],
                        "saveComment": "Ansible API",
                        "deleteUnspecified": module.params.get(
                            "deleteunspecified", False
                        ),
                        "properties": [
                            {"name": "name", "value": module.params["name"]},
                            {
                                "name": "clientIdentifier",
                                "value": module.params["macaddress"],
                            },
                            {"name": "addresses", "value": ipaddress},
                            {
                                "name": "ddnsHostName",
                                "value": module.params.get("ddnshost", ""),
                            },
                            {
                                "name": "filename",
                                "value": module.params.get("filename", ""),
                            },
                            {
                                "name": "serverName",
                                "value": module.params.get("servername", ""),
                            },
                            {
                                "name": "nextServer",
                                "value": module.params.get("nextserver", ""),
                            },
                        ],
                    }

                    # Check if the requested data is equal to the current data
                    # How lovely: The API returns the IP address as a list, so it seems
                    # logical to offer the IP address as a list as well. But this is
                    # not allowed, IP address needs to be a string. So that needs
                    # to be taken into consideration.
                    change = False
                    for key in databody["properties"]:
                        name = key["name"]
                        val = key["value"]
                        if name == "addresses" and isinstance(
                            val, (str, unicode)
                        ):
                            val = [val]

                        # Check if it is in the current values
                        if val != reservation.get(name, "unknown"):
                            change = True
                            break

                    if change:
                        result["changed"] = True
                        url = "%s" % reservation["ref"]
                        result = doapi(url, http_method, mm_provider, databody)
            else:
                # Delete the reservations. Empty body, as the ref is sufficient
                http_method = "DELETE"
                databody = {"saveComment": "Ansible API"}
                for ref in resp["ipamRecord"]["dhcpReservations"]:
                    if ipaddress in ref["addresses"]:
                        url = ref["ref"]
                        result = doapi(url, http_method, mm_provider, databody)
        else:
            if module.params["state"] == "present":
                # If IP address is a string, turn it into a list, as the API
                # requires that
                if isinstance(ipaddress, (str, unicode)):
                    ipaddress = [ipaddress]

                # No reservation found. Create one. Try this in each scope.
                for scope in scopes:
                    http_method = "POST"
                    url = "%s/DHCPReservations" % scope
                    databody = {
                        "saveComment": "Ansible API",
                        "dhcpReservation": {
                            "name": module.params["name"],
                            "clientIdentifier": module.params["macaddress"],
                            "reservationMethod": "HardwareAddress",
                            "addresses": ipaddress,
                            "ddnsHostName": module.params.get("ddnshost", ""),
                            "filename": module.params.get("filename", ""),
                            "serverName": module.params.get("servername", ""),
                            "nextServer": module.params.get("nextserver", ""),
                        },
                    }

                    # Execute the API
                    result = doapi(url, http_method, mm_provider, databody)
            else:
                result["changed"] = False

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
