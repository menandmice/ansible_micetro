#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, BlueCat Networks
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible DHCP Group module.

Part of the Men&Mice Ansible integration

Module to manage DHCP groups in Micetro
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
  module: dhcpgroup
  short_description: Manage DHCP group(s) in the Micetro
  author:
    - BlueCat Networks
  version_added: "2.0.0"
  description:
    - Create/delete DHCP group(s) in Micetro.
    - A DHCP group is a first-class sub-object owned by a DHCP server or
      a DHCP scope, and can itself own DHCP reservations or nest further
      groups.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description: The state of the DHCP group
      type: str
      choices: [ absent, present ]
      default: present
    name:
      description: DHCP group name
      type: str
      required: true
    owner_ref:
      description:
        - Reference of the DHCP server or DHCP scope that owns this group.
      type: str
      required: true
    parent_ref:
      description:
        - Reference of a parent DHCP group to nest this group under.
        - Only used when creating a new group; ignored for updates.
      type: str
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
- name: Manage a DHCP group owned by a DHCP server
  menandmice.ansible_micetro.dhcpgroup:
    name: My DHCP Group
    owner_ref: dhcpServers/1
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Manage a nested DHCP group owned by a DHCP scope
  menandmice.ansible_micetro.dhcpgroup:
    name: My Nested DHCP Group
    owner_ref: dhcpScopes/1
    parent_ref: dhcpGroups/1
    save_comment: Ansible API
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Remove a DHCP group
  menandmice.ansible_micetro.dhcpgroup:
    state: absent
    name: My DHCP Group
    owner_ref: dhcpServers/1
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
        owner_ref=dict(type="str", required=True),
        parent_ref=dict(type="str", required=False),
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
    result = {"changed": False, "message": "No changes to DHCP group required"}

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
    owner_ref = module.params["owner_ref"]
    parent_ref = module.params["parent_ref"]
    save_comment = module.params["save_comment"]

    # Ensure the owner reference is present
    resp = get_single_refs(owner_ref, mm_provider)
    if resp.get("invalid", None):
        module.fail_json(
            msg="Owner reference not found, please try again",
            owner_ref=owner_ref,
            response=resp,
        )

    # Ensure the parent group reference is present, if requested
    if parent_ref:
        resp = get_single_refs(parent_ref, mm_provider)
        if resp.get("invalid", None):
            module.fail_json(
                msg="Parent group reference not found, please try again",
                parent_ref=parent_ref,
                response=resp,
            )

    # Find the DHCP group amongst the owner's groups
    resp = get_single_refs("%s/dhcpGroups" % owner_ref, mm_provider)
    if resp.get("invalid", None):
        module.fail_json(
            msg="An error occurred, please try again", response=resp
        )

    group = None
    for candidate in resp["dhcpGroups"]:
        if candidate["name"] == name:
            group = candidate
            break

    # Ensure DHCP group is present
    if state == "present":
        if group is None:
            # Create the DHCP group
            url = "%s/dhcpGroups" % owner_ref
            http_method = "POST"
            dhcp_group = {"name": name, "ownerRef": owner_ref}
            if parent_ref:
                dhcp_group["parentRef"] = parent_ref
            databody = {
                "dhcpGroup": dhcp_group,
                "saveComment": save_comment,
            }

            api_result = doapi(url, http_method, mm_provider, databody)
            if api_result.get("warnings", None):
                module.fail_json(
                    msg="Failed to create DHCP group, please try again",
                    response=api_result,
                )

            if api_result["changed"]:
                result.update(
                    {
                        "changed": True,
                        "message": "DHCP group successfully created",
                    }
                )
        else:
            # Group exists, found by matching name, so there is nothing
            # left to update: name is the lookup key and the API doesn't
            # expose any other mutable field on a DHCP group (no
            # description, and parentRef/ownerRef are create-only).
            result["message"] = "DHCP group is present"

    # Ensure DHCP group is absent
    if state == "absent":
        if group is None:
            result["message"] = "DHCP group is absent"
        else:
            url = group["ref"]
            http_method = "DELETE"
            api_result = doapi(
                url, http_method, mm_provider, {"saveComment": save_comment}
            )
            if api_result["changed"]:
                result.update(
                    {
                        "changed": True,
                        "message": "DHCP group successfully removed",
                    }
                )

    # Return collected results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
