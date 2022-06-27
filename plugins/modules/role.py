#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible role module.

Part of the Men&Mice Ansible integration

Module to manage roles in the Men&Mice Suite.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansilabnl.micetro.plugins.module_utils.micetro import (
    doapi,
    getrefs,
)

DOCUMENTATION = r"""
  module: role
  short_description: Manage roles on the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Manage roles on a Men&Mice Suite installation
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description:
        - Should the role exist or not.
      type: str
      required: False
      choices: [ absent, present ]
      default: present
    name:
      description:
        - Name of the role to create, remove or modify.
      type: str
      required: True
      aliases: [ role ]
    descr:
      description: Description of the role.
      required: False
      type: str
    users:
      description: List of users to add to this role.
      type: list
      required: False
    groups:
      description: List of groups to add to this role.
      type: list
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
- name: Add the 'local' role
 ansilabnl.micetro.role:
    name: local
    desc: A local role
    state: present
    users:
      - johndoe
    groups:
      - my_local_group
  mm_provider:
    mm_url: http://mmsuite.example.net
    mm_user: apiuser
    mm_password: apipasswd
  delegate_to: localhost

- name: Remove the 'local' role
 ansilabnl.micetro.role:
    name: local
    state: absent
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost
"""

RETURN = r"""
message:
    description: The output message from the Men&Mice Suite.
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
        name=dict(type="str", required=True, aliases=["role"]),
        desc=dict(type="str", required=False),
        users=dict(type="list", required=False),
        groups=dict(type="list", required=False),
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
    # Se primarily care about changed and state
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

    # Get all roles from the Men&Mice server, start with Roles url
    state = module.params["state"]

    # Get list of all roles in the system
    resp = getrefs("Roles", mm_provider)
    if resp.get("warnings", None):
        module.fail_json(msg="Collecting roles: %s" % resp.get("warnings"))
    roles = resp["message"]["result"]["roles"]

    # If users are requested, get all users
    if module.params["users"]:
        resp = getrefs("Users", mm_provider)
        if resp.get("warnings", None):
            module.fail_json(msg="Collecting users: %s" % resp.get("warnings"))
        users = resp["message"]["result"]["users"]

    # If groups are requested, get all groups
    if module.params["groups"]:
        resp = getrefs("Groups", mm_provider)
        if resp.get("warnings", None):
            module.fail_json(msg="Collecting groups: %s" % resp.get("warnings"))
        groups = resp["message"]["result"]["groups"]

    # Setup loop vars
    role_exists = False
    role_ref = ""

    # Check if the role already exists
    for role in roles:
        if role["name"] == module.params["name"]:
            role_exists = True
            role_ref = role["ref"]
            role_data = role
            break

    # If requested state is "present"
    if state == "present":
        # Check if all requested users exist
        if module.params["users"]:
            # Create a list with all names, for easy checking
            names = []
            for user in users:
                names.append(user["name"])

            # Check all requested names against the names list
            for name in module.params["users"]:
                if name not in names:
                    module.fail_json(
                        msg="Requested a non existing user: %s" % name
                    )

        # Check if all requested groups exist
        if module.params["groups"]:
            # Create a list with all names, for easy checking
            names = []
            for grp in groups:
                names.append(grp["name"])

            # Check all requested names against the names list
            for name in module.params["groups"]:
                if name not in names:
                    module.fail_json(
                        msg="Requested a non existing group: %s" % name
                    )

        # Create a list of wanted users
        wanted_users = []
        if module.params["users"]:
            for user in users:
                if user["name"] in module.params["users"]:
                    # This user is wanted
                    wanted_users.append(
                        {
                            "ref": user["ref"],
                            "objType": "Users",
                            "name": user["name"],
                        }
                    )

        # Create a list of wanted groups
        wanted_groups = []
        if module.params["groups"]:
            for group in groups:
                if group["name"] in module.params["groups"]:
                    # This group is wanted
                    wanted_groups.append(
                        {
                            "ref": group["ref"],
                            "objType": "Groups",
                            "name": group["name"],
                        }
                    )

        if role_exists:
            # Role already present, just update.
            http_method = "PUT"
            url = "Roles/%s" % role_ref
            databody = {
                "ref": role_ref,
                "saveComment": "Ansible API",
                "properties": [
                    {"name": "name", "value": module.params["name"]},
                    {"name": "description", "value": module.params["desc"]},
                ],
            }

            # Now figure out if users or groups need to be added or deleted
            # The ones in the playbook are in `wanted_(users|groups)`
            # and the roles ref is in `role_ref` and all roles data is
            # in `role_data`.

            # Add or delete a role to or from a group
            # API call with PUT or DELETE
            # http://mandm.example.net/mmws/api/Groups/6/Roles/31
            databody = {"saveComment": "Ansible API"}
            for thisgrp in wanted_groups + role_data["groups"]:
                http_method = ""
                if (thisgrp in wanted_groups) and (
                    thisgrp not in role_data["groups"]
                ):
                    # Wanted but not yet present.
                    http_method = "PUT"
                elif (thisgrp not in wanted_groups) and (
                    thisgrp in role_data["groups"]
                ):
                    # Present, but not wanted
                    http_method = "DELETE"

                # Execute wanted action
                if http_method:
                    url = "%s/%s" % (thisgrp["ref"], role_ref)
                    result = doapi(url, http_method, mm_provider, databody)
                    result["changed"] = True

            # Add or delete a role to or from a user
            # API call with PUT or DELETE
            # http://mandm.example.net/mmws/api/Users/31/Roles/2
            for thisuser in wanted_users + role_data["users"]:
                http_method = ""
                if (thisuser in wanted_users) and (
                    thisuser not in role_data["users"]
                ):
                    # Wanted but not yet present.
                    http_method = "PUT"
                elif (thisuser not in wanted_users) and (
                    thisuser in role_data["users"]
                ):
                    # Present, but not wanted
                    http_method = "DELETE"

                # Execute wanted action
                if http_method:
                    url = "%s/%s" % (thisuser["ref"], role_ref)
                    result = doapi(url, http_method, mm_provider, databody)
                    result["changed"] = True

            # Check idempotency
            change = False
            if role_data["name"] != module.params["name"]:
                change = True
            if role_data["description"] != module.params["desc"]:
                change = True

            if change:
                result = doapi(url, http_method, mm_provider, databody)
            result["changed"] = change
        else:
            # Role not present, create
            http_method = "POST"
            url = "Roles"
            databody = {
                "saveComment": "Ansible API",
                "role": {
                    "name": module.params["name"],
                    "description": module.params["desc"],
                    "users": wanted_users,
                    "groups": wanted_groups,
                    "builtIn": False,
                },
            }
            result = doapi(url, http_method, mm_provider, databody)
            if result.get("warnings", None):
                module.fail_json(msg=result.get("warnings"))
            role_ref = result["message"]["result"]["ref"]

    # If requested state is "absent"
    if state == "absent":
        if role_exists:
            # Role present, delete
            http_method = "DELETE"
            url = "Roles/%s" % role_ref
            databody = {"saveComment": "Ansible API"}
            result = doapi(url, http_method, mm_provider, databody)
        else:
            # Role not present, done
            result["changed"] = False

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
