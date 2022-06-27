#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible Zone Management module.

Part of the Men&Mice Ansible integration

Module to manage DNS-Zones in the Men&Mice Suite
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
  module: zone
  short_description: Manage DNS zones in the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Manage DNS zones in the Men&Mice Suite
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the zone.
      type: bool
      required: False
      choices: [ absent, present ]
      default: present
    name:
      description: Name of the zone.
      type: str
      required: True
    nameserver:
      description:
        - Nameserver to define the zone on.
        - Required if I(state=present).
      type: str
      required: False
    authority:
      description: Name of the DNS server that contains the zone or
                   the string C([Active Directory]) if the zone
                   is integrated in the Active Directory.
      type: str
      required: False
    servtype:
      description:
         - Type of the master server.
      type: str
      required: False
      choices: [ master, slave, stub, forward ]
      default: master
    dynamic:
      description: Dynamic DNS zone.
      type: bool
      required: False
      default: False
    masters:
      description: The IP addresses of the master servers if the
                   new zone is not a master zone.
      type: list
      elements: str
      required: False
    adintegrated:
      description: True if the zone is Active Directory integrated.
      type: bool
      required: False
    adreplicationtype:
      description: Type of the AD replication.
      type: str
      required: False
    adpartition:
      description: The AD partition if the zone is Active Directory integrated.
      type: str
      required: False
    customproperties:
      description:
        - Custom properties for the zone.
        - These properties must already exist.
        - See also M(mm_props).
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
- name: Create a new zone
 ansilabnl.micetro.zone:
    state: present
    name: example.com
    nameserver: ns1.example.com
    authority: mmsuite.example.net
    customproperties:
      location: Reykjavik
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Release a zone
 ansilabnl.micetro.zone:
    state: absent
    name: example.com
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
        nameserver=dict(type="str", required=False),
        authority=dict(type="str", required=False),
        servtype=dict(
            type="str",
            required=False,
            default="master",
            choices=["master", "slave", "stub", "forward"],
        ),
        dynamic=dict(type="bool", required=False, default=False),
        masters=dict(type="list", required=False),
        adintegrate=dict(type="bool", required=False),
        adreplicationtype=dict(type="str", required=False),
        adpartition=dict(type="str", required=False),
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

    # Make sure the DNS type is capitalised, as the API requires that
    module.params["servtype"] = module.params["servtype"].capitalize()

    # Get all API settings
    mm_provider = module.params["mm_provider"]

    # Name is required
    if not module.params["name"]:
        module.fail_json(msg="missing required argument: name")

    # Nameserver is required
    if not module.params["nameserver"]:
        module.fail_json(msg="missing required argument: nameserver")

    # Get the existing DNS View for the nameserver
    refs = "DNSViews?dnsServerRef=%s" % module.params.get("nameserver")
    resp = get_single_refs(refs, mm_provider)

    # If the 'invalid' key exists, the request failed.
    if resp.get("invalid", None):
        module.fail_json(
            msg="nameserver does not exist: %s" % module.params["nameserver"]
        )
    # Only the refID is needed, strip the DNSViews/ text
    dnsview_ref = resp["dnsViews"][0]["ref"].replace("DNSViews/", "")

    # Try to get all zone info for this zone on this DNSView
    refs = "DNSZones?filter=%s&dnsViewRef=%s" % (
        module.params.get("name"),
        dnsview_ref,
    )
    resp = get_single_refs(refs, mm_provider)

    # If absent is requested, make a quick delete
    if module.params["state"] == "absent":
        if resp.get("totalResults", 1) == 0:
            # Zone does not exist. Just return
            result["change"] = False
            module.exit_json(**result)

        http_method = "DELETE"
        url = "%s" % resp["dnsZones"][0]["ref"]
        databody = {"saveComment": "Ansible API"}
        result = doapi(url, http_method, mm_provider, databody)
        module.exit_json(**result)

    # Come here the zone needs to be present
    # If the totalResults fiel contains '0', the zone does not exist
    # otherwise it does and needs to be changed.
    if resp.get("totalResults", 1) != 0:
        # Zone exists. Update

        # Create the API call.
        #   `name`        is read-only, so not in the call
        #   `dynamicname` is read-only, so not in the call
        #   `authority`   is read-only, so not in the call
        http_method = "PUT"
        url = "%s" % resp["dnsZone"]["ref"]
        databody = {
            "ref": resp["dnsZone"]["ref"],
            "saveComment": "Ansible API",
            "properties": [
                {"name": "type", "value": module.params["servtype"]}
            ],
        }
        # Add extra parameters, if requested.
        masters = module.params.get("masters", None)
        if module.params["servtype"] != "Master" and masters is not None:
            databody["properties"].append({"name": "masters", "value": masters})
        if module.params.get("adIntegrated"):
            databody["properties"].append(
                {
                    "name": "adIntegrated",
                    "value": module.params.get("adintegrated"),
                }
            )
        if module.params.get("adreplicationtype"):
            databody["properties"].append(
                {
                    "name": "adReplicationType",
                    "value": module.params.get("adreplicationtype"),
                }
            )
        if module.params.get("adpartition"):
            databody["properties"].append(
                {
                    "name": "adPartition",
                    "value": module.params.get("adpartition"),
                }
            )

        # Define all custom properties, if needed
        if module.params.get("customproperties", None):
            for key, val in module.params.get("customproperties").items():
                databody["properties"].append({"name": key, "value": val})

        # Find out if a change is needed
        change = False
        for key in databody["properties"]:
            name = key["name"]
            val = key["value"]

            # Check if it is in the current values, either in the "normal" set or
            # the custom properties
            cur = resp["dnsZone"].get(name, None)
            if not cur:
                # Not found yet, try custumprops
                cur = resp["dnsZone"]["customProperties"].get(name, None)

            # Check if it is in the current values
            if val != cur:
                change = True
                break

        # Execute the API
        if change:
            result = doapi(url, http_method, mm_provider, databody)
    else:
        # Create the API call
        http_method = "POST"
        url = "dnsZones"
        databody = {
            "saveComment": "Ansible API",
            "dnsZone": {
                "name": module.params["name"],
                "dnsViewRef": dnsview_ref,
                "dynamic": module.params["dynamic"],
                "authority": module.params["authority"],
                "type": module.params["servtype"],
            },
        }
        # Add extra parameters, if requested.
        masters = module.params.get("masters", None)
        if module.params["servtype"] != "Master" and masters is not None:
            databody["masters"] = masters
        if module.params.get("adintegrated"):
            databody["dnsZone"]["adIntegrated"] = module.params.get(
                "adintegrated"
            )
        if module.params.get("adreplicationtype"):
            databody["dnsZone"]["adReplicationtype"] = module.params.get(
                "adreplicationtype"
            )
        if module.params.get("adpartition"):
            databody["dnsZone"]["adPartition"] = module.params.get(
                "adpartition"
            )

        # Define all custom properties, if needed
        if module.params.get("customproperties", None):
            props = []
            for key, val in module.params.get("customproperties").items():
                props.append({"name": key, "value": val})
            databody["dnsZone"]["customProperties"] = props

        # Create the zone on the Men&Mice Suite
        result = doapi(url, http_method, mm_provider, databody)

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
