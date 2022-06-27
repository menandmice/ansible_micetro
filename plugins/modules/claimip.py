#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible Claim IP address module.

Part of the Men&Mice Ansible integration

Module to claim IP addresses in DHCP in the Men&Mice Suite
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansilabnl.micetro.plugins.module_utils.micetro import (
    doapi,
    get_single_refs,
)

DOCUMENTATION = r"""
  module: claimip
  short_description: Claim IP addresses in DHCP in the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Claim IP addresses in DHCP in the Men&Mice Suite.
    - These addresses can not be in a DHCP range.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the claim.
      type: bool
      required: False
      choices: [ absent, present ]
      default: present
    ipaddress:
      description: The IP address(es) to work on.
      type: list
      required: True
      elements: str
    customproperties:
      description:
        - Custom properties for the IP address.
        - These properties must already exist.
        - See also M(mm_props)
      seealso: See also M(mm_props)
      type: dict
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
- name: Claim IP address
 ansilabnl.micetro.claimip:
    state: present
    ipaddress: 172.16.12.14
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Release claim on IP addresses
 ansilabnl.micetro.claimip:
    state: present
    ipaddress:
      - 172.16.12.14
      - 172.16.12.15
      - 172.16.12.16
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

STATEBOOL = {"present": True, "absent": False}


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
        ipaddress=dict(type="list", required=True),
        customproperties=dict(type="dict", required=False),
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
        # Get the IP address and find the reference
        # If the 'invalid' key exists, the request failed.
        refs = "IPAMRecords/%s" % ipaddress
        resp = get_single_refs(refs, mm_provider)
        if resp.get("invalid", None):
            result.pop("message", None)
            result["warnings"] = resp.get("warnings", None)
            result["changed"] = False
            break

        ipaddr_ref = resp["ipamRecord"]["addrRef"]
        curclaim = resp["ipamRecord"]["claimed"]

        # Set the claim for the IP address
        statebool = STATEBOOL[module.params["state"]]
        if curclaim != statebool:
            http_method = "PUT"
            url = ipaddr_ref
            databody = {
                "ref": ipaddr_ref,
                "saveComment": "Ansible API",
                "properties": {"claimed": statebool},
            }

            # Define all custom properties, if needed
            if module.params.get("customproperties", None):
                for key, val in module.params.get("customproperties").items():
                    databody["properties"][key] = val

            # Execute the API
            result = doapi(url, http_method, mm_provider, databody)
        else:
            result["message"] = "No claim change for %s" % ipaddress

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
