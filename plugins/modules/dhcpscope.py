#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2024, Adam Brauns (@abrauns-silex)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible DHCP Scope module.

Part of the Men&Mice Ansible integration

Module to manage DHCP scope definitions in Micetro
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
  module: dhcpscope
  short_description: Manage DHCP scope(s) in the Micetro
  author:
    - Adam Brauns (@abrauns-silex)
  version_added: "1.0.8"
  description:
    - Create/delete DHCP scope(s) in Micetro.
    - Manage DHCP scope options.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the DHCP scope
      type: str
      choices: [ absent, present ]
      default: present
    name:
      description: DHCP scope name
      type: str
      required: true
    description:
      description: DHCP scope description
      type: str
      default: Managed via Ansible
    enabled:
      description: Whether the DHCP scope is enabled
      type: bool
      default: true
    range_ref:
      description: Range reference for the DHCP scope
      type: str
      required: true
    dhcp_server_refs:
      description: DHCP server reference(s) for the DHCP scope
      type: list
      elements: str
      required: true
    options:
      description:
        - Options for the DHCP scope.
        - The key must be the number option in Micetro.
        - Any values that are passed into a list are combined into a single string
          delimited by a comma.
      type: dict
    save_comment:
      description: Save comment left in Micetro
      type: str
      default: Ansible API
    mm_provider:
      description: Definition of the Micetro API mm_provider.
      type: dict
      required: true
      suboptions:
        mm_url:
          description: Men&Mice API server to connect to.
          type: str
          required: true
        mm_user:
          type: str
          description: userid to login with into the API.
          required: true
        mm_password:
          type: str
          description: password to login with into the API.
          required: true
"""

EXAMPLES = r"""
- name: Manage DHCP scope without options using defaults
  menandmice.ansible_micetro.dhcpscope:
    name: My DHCP Scope
    range_ref: Ranges/1
    dhcp_server_refs:
      - DHCPServers/1
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Remove DHCP scope using defaults
  menandmice.ansible_micetro.dhcpscope:
    state: absent
    name: My DHCP Scope
    range_ref: Ranges/1
    dhcp_server_refs:
      - DHCPServers/1
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Manage DHCP scope with options using defaults
  menandmice.ansible_micetro.dhcpscope:
    state: present
    name: My DHCP Scope
    range_ref: Ranges/1
    dhcp_server_refs:
      - DHCPServers/1
    options:
      3:
        - 1.1.1.1
      51: 172800
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Manage DHCP scope with options using all parameters
  menandmice.ansible_micetro.dhcpscope:
    state: present
    name: My DHCP Scope
    description: DHCP scope description
    enabled: true
    range_ref: Ranges/1
    dhcp_server_refs:
      - DHCPServers/1
    options:
      3:
        - 1.1.1.1
      51: 172800
    save_comment: Ansible API
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost
"""

RETURN = r"""
message:
    description: The output message from Micetro.
    type: str
    returned: always
"""

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.menandmice.ansible_micetro.plugins.module_utils.micetro import (
    doapi,
    get_single_refs
)

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
        name=dict(type="str", required=True),
        description=dict(type="str", required=False, default="Managed via Ansible"),
        enabled=dict(type="bool", required=False, default=True),
        range_ref=dict(type="str", required=True),
        dhcp_server_refs=dict(type="list", required=True, elements="str"),
        options=dict(type="dict", required=False),
        save_comment=dict(type="str", required=False, default="Ansible API"),
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
    result = {"changed": False, "message": "No changes to DHCP scope required"}

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
    state = module.params["state"]
    name = module.params["name"]
    description = module.params["description"]
    enabled = module.params["enabled"]
    range_ref = module.params["range_ref"]
    dhcp_server_refs = module.params["dhcp_server_refs"]
    options = module.params["options"]
    save_comment = module.params["save_comment"]

    for dhcp_server_ref in dhcp_server_refs:

        # Look up DHCP scope
        refs = "DHCPScopes?filter=name=%s%%20AND%%20rangeRef=%s%%20AND%%20dhcpServerRef=%s" % (name, range_ref, dhcp_server_ref)
        resp = get_single_refs(refs, mm_provider)
        if resp.get("invalid", None):
            module.fail_json(
                msg="An error occurred, please try again",
                response=resp
            )

        # Ensure there aren't multiple scopes returned
        total_results = resp["totalResults"]
        if total_results > 1:
            module.fail_json(
                msg="More than one DHCP scope found, unable to take action",
                dhcp_scopes=resp["dhcpScopes"],
                total_results=total_results
            )

        # Ensure DHCP scope is present
        if state == "present":
            present_change_message = "DHCP scope successfully updated"

            # Create the DHCP scope if it is not found
            if total_results == 0:
                url = "DHCPScopes"
                http_method = "POST"
                databody = {
                    "dhcpScope": {
                        "name": name,
                        "rangeRef": range_ref,
                        "dhcpServerRef": dhcp_server_ref,
                        "description": description,
                        "enabled": enabled
                    },
                    "saveComment": save_comment
                }
                api_result = doapi(url, http_method, mm_provider, databody)
                if api_result["changed"]:
                    result.update({
                        "changed": True,
                        "message": present_change_message
                    })

                # Ensure the creation results in one DHCP scope
                resp = get_single_refs(refs, mm_provider)
                total_results = resp["totalResults"]
                if total_results != 1:
                    module.fail_json(
                        msg="Creation of DHCP scope did not produce a DHCP scope, unable to take action",
                        dhcp_scopes=resp["dhcpScopes"],
                        total_results=total_results
                    )

            ref = resp["dhcpScopes"][0]["ref"]
            if options:
                # Format options parameter
                formatted_options = []
                for key, value in options.items():
                    if isinstance(value, list):
                        value = ','.join(map(str, value))
                    formatted_options.append({
                        "option": "::%s" % key,
                        "value": str(value)
                    })

                # Check to see if the options are different
                options_needs_update = False
                url = "%s/Options" % ref
                option_resp = get_single_refs(url, mm_provider)
                for formatted_option in formatted_options:
                    if formatted_option not in option_resp["dhcpOptions"]:
                        options_needs_update = True
                        break

                # Update the options if they are different
                if options_needs_update:
                    http_method = "PUT"
                    databody = {
                        "dhcpOptions": formatted_options,
                        "saveComment": save_comment
                    }
                    api_result = doapi(url, http_method, mm_provider, databody)
                    if api_result["changed"]:
                        result.update({
                            "changed": True,
                            "message": present_change_message
                        })

        # Ensure DHCP scope is absent
        if state == "absent":
            if total_results == 0:
                result["message"] = "DHCP scope is absent"

            else:
                url = resp["dhcpScopes"][0]["ref"]
                http_method = "DELETE"
                api_result = doapi(url, http_method, mm_provider, {})
                if api_result["changed"]:
                    result.update({
                        "changed": True,
                        "message": "DHCP scope successfully removed"
                    })

    # Return collected results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
