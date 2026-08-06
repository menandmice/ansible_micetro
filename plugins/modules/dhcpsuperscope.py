#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, BlueCat Networks
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible DHCP Superscope module.

Part of the Men&Mice Ansible integration

Module to manage DHCP superscopes in Micetro
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
  module: dhcpsuperscope
  short_description: Manage DHCP superscope(s) in the Micetro
  author:
    - BlueCat Networks
  version_added: "1.0.15"
  description:
    - Create/delete DHCP superscope(s) in Micetro.
    - A DHCP superscope groups one or more DHCP scopes under a single
      DHCP server so they can be managed together.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the DHCP superscope
      type: str
      choices: [ absent, present ]
      default: present
    name:
      description: DHCP superscope name
      type: str
      required: true
    description:
      description: DHCP superscope description
      type: str
      default: Managed via Ansible
    dhcp_server_ref:
      description: DHCP server reference that will own the superscope
      type: str
      required: true
    dhcp_scope_refs:
      description:
        - References of DHCP scopes to place in the superscope on creation.
        - Only used when creating a new superscope; ignored for updates.
      type: list
      elements: str
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
- name: Manage DHCP superscope using defaults
  menandmice.ansible_micetro.dhcpsuperscope:
    name: My DHCP Superscope
    dhcp_server_ref: dhcpServers/1
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Manage DHCP superscope with initial scopes
  menandmice.ansible_micetro.dhcpsuperscope:
    name: My DHCP Superscope
    description: Superscope description
    dhcp_server_ref: dhcpServers/1
    dhcp_scope_refs:
      - dhcpScopes/1
      - dhcpScopes/2
    save_comment: Ansible API
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Remove DHCP superscope
  menandmice.ansible_micetro.dhcpsuperscope:
    state: absent
    name: My DHCP Superscope
    dhcp_server_ref: dhcpServers/1
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
    get_single_refs,
)


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
        description=dict(
            type="str", required=False, default="Managed via Ansible"
        ),
        dhcp_server_ref=dict(type="str", required=True),
        dhcp_scope_refs=dict(type="list", required=False, elements="str"),
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
    result = {
        "changed": False,
        "message": "No changes to DHCP superscope required",
    }

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

    # Gather all module parameters
    mm_provider = module.params["mm_provider"]
    state = module.params["state"]
    name = module.params["name"]
    description = module.params["description"]
    dhcp_server_ref = module.params["dhcp_server_ref"]
    dhcp_scope_refs = module.params["dhcp_scope_refs"]
    save_comment = module.params["save_comment"]

    # Ensure DHCP server reference is present
    resp = get_single_refs(dhcp_server_ref, mm_provider)
    if resp.get("invalid", None):
        module.fail_json(
            msg="DHCP server reference not found, please try again",
            dhcp_server_ref=dhcp_server_ref,
            response=resp,
        )

    # Look up the superscope
    refs = 'dhcpSuperscopes?filter=name="%s"%%20AND%%20dhcpServerRef=%s' % (
        name.replace(" ", "%20"),
        dhcp_server_ref,
    )
    resp = get_single_refs(refs, mm_provider)
    if resp.get("invalid", None):
        module.fail_json(
            msg="An error occurred, please try again", response=resp
        )

    # Ensure no more than one DHCP superscope is returned
    total_results = resp["totalResults"]
    if total_results > 1:
        module.fail_json(
            msg="More than one DHCP superscope found, unable to take action",
            response=resp,
        )

    # Ensure DHCP superscope is present
    if state == "present":
        if total_results == 0:
            # Create the DHCP superscope
            url = "dhcpSuperscopes"
            http_method = "POST"
            databody = {
                "superscope": {
                    "name": name,
                    "description": description,
                    "dhcpServerRef": dhcp_server_ref,
                },
                "saveComment": save_comment,
            }
            if dhcp_scope_refs:
                databody["dhcpScopeRefs"] = dhcp_scope_refs

            api_result = doapi(url, http_method, mm_provider, databody)
            if api_result.get("warnings", None):
                module.fail_json(
                    msg="Failed to create DHCP superscope, please try again",
                    response=api_result,
                )

            if api_result["changed"]:
                result.update(
                    {
                        "changed": True,
                        "message": "DHCP superscope successfully created",
                    }
                )
        else:
            # Superscope exists; update name/description if changed
            superscope = resp["superscopes"][0]
            change = False
            if superscope["name"] != name:
                change = True
            if superscope["description"] != description:
                change = True

            if change:
                url = superscope["ref"]
                http_method = "PUT"
                databody = {
                    "ref": superscope["ref"],
                    "saveComment": save_comment,
                    "properties": {
                        "name": name,
                        "description": description,
                    },
                }
                api_result = doapi(url, http_method, mm_provider, databody)
                if api_result.get("warnings", None):
                    module.fail_json(
                        msg="Failed to update DHCP superscope, please try again",
                        response=api_result,
                    )

                result.update(
                    {
                        "changed": True,
                        "message": "DHCP superscope successfully updated",
                    }
                )

    # Ensure DHCP superscope is absent
    if state == "absent":
        if total_results == 0:
            result["message"] = "DHCP superscope is absent"
        else:
            url = resp["superscopes"][0]["ref"]
            http_method = "DELETE"
            api_result = doapi(url, http_method, mm_provider, {})
            if api_result["changed"]:
                result.update(
                    {
                        "changed": True,
                        "message": "DHCP superscope successfully removed",
                    }
                )

    # Return collected results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
