#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible group module.

Part of the Men&Mice Ansible integration

Module to manage groups in the Men&Mice Suite.
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
  module: group
  short_description: Manage groups on the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Manage groups on a Men&Mice Suite installation
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    state:
      description:
        - Should the group exist or not.
      type: str
      required: False
      choices: [ absent, present ]
      default: present
    name:
      description:
        - Name of the group to create, remove or modify.
      type: str
      required: True
      aliases: [ group ]
    descr:
      description: Description of the group.
      required: False
      type: str
    users:
      description: List of users to add to this group.
      type: list
      required: False
    roles:
      description: List of roles to add to this group.
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
- name: Add the 'local' group
 ansilabnl.micetro.group:
    name: local
    desc: A local group
    state: present
    users:
      - johndoe
    roles:
      - IPAM Administrators (built-in)
  mm_provider:
    mm_url: http://mmsuite.example.net
    mm_user: apiuser
    mm_password: apipasswd
  delegate_to: localhost

- name: Remove the 'local' group
 ansilabnl.micetro.group:
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
        name=dict(type="str", required=True, aliases=["group"]),
        desc=dict(type="str", required=False),
        users=dict(type="list", required=False),
        roles=dict(type="list", required=False),
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

    # Get all groups from the Men&Mice server, start with Groups url
    state = module.params["state"]

    # If users are requested, get all users
    users = []
    if module.params.get("users", None):
        resp = getrefs("Users", mm_provider)
        if resp.get("warnings", None):
            module.fail_json(msg="Collecting users: %s" % resp.get("warnings"))
        users = resp["message"]["result"]["users"]

    # Get list of all groups in the system
    groups = []
    if module.params.get("groups", None):
        resp = getrefs("Groups", mm_provider)
        if resp.get("warnings", None):
            module.fail_json(msg="Collecting groups: %s" % resp.get("warnings"))
        groups = resp["message"]["result"]["groups"]

    # If roles are requested, get all roles
    roles = []
    if module.params.get("roles", None):
        resp = getrefs("Roles", mm_provider)
        if resp.get("warnings", None):
            module.fail_json(msg="Collecting roles: %s" % resp.get("warnings"))
        roles = resp["message"]["result"]["roles"]

    # Setup loop vars
    group_exists = False
    group_ref = ""

    # Check if the group already exists
    for group in groups:
        if group["name"] == module.params["name"]:
            group_exists = True
            group_ref = group["ref"]
            group_data = group
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

        # Check if all requested roles exist
        if module.params["roles"]:
            # Create a list with all names, for easy checking
            names = []
            for role in roles:
                names.append(role["name"])

            # Check all requested names against the names list
            for name in module.params["roles"]:
                if name not in names:
                    module.fail_json(
                        msg="Requested a non existing role: %s" % name
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

        # Create a list of wanted roles
        wanted_roles = []
        if module.params["roles"]:
            for role in roles:
                if role["name"] in module.params["roles"]:
                    # This role is wanted
                    wanted_roles.append(
                        {
                            "ref": role["ref"],
                            "objType": "Roles",
                            "name": role["name"],
                        }
                    )
        if group_exists:
            # Group already present, just update.
            http_method = "PUT"
            url = "Groups/%s" % group_ref
            databody = {
                "ref": group_ref,
                "saveComment": "Ansible API",
                "properties": [
                    {"name": "name", "value": module.params["name"]},
                    {"name": "description", "value": module.params["desc"]},
                ],
            }
            result = doapi(url, http_method, mm_provider, databody)

            # Now figure out if users or roles need to be added or deleted
            # The ones in the playbook are in `wanted_(users|roles)`
            # and the groups ref is in `group_ref` and all groups data is
            # in `group_data`.

            # Add or delete a role to or from a group
            # API call with PUT or DELETE
            # http://mandm.example.net/mmws/api/Groups/6/Roles/31
            databody = {"saveComment": "Ansible API"}
            for thisrole in wanted_roles + group_data["roles"]:
                http_method = ""
                if (thisrole in wanted_roles) and (
                    thisrole not in group_data["roles"]
                ):
                    # Wanted but not yet present.
                    http_method = "PUT"
                elif (thisrole not in wanted_roles) and (
                    thisrole in group_data["roles"]
                ):
                    # Present, but not wanted
                    http_method = "DELETE"

                # Execute wanted action
                if http_method:
                    url = "%s/%s" % (group_ref, thisrole["ref"])
                    result = doapi(url, http_method, mm_provider, databody)
                    result["changed"] = True

            # Add or delete a group to or from a user
            # API call with PUT or DELETE
            # http://mandm.example.net/mmws/api/Users/31/Groups/2
            for thisuser in wanted_users + group_data["groupMembers"]:
                http_method = ""
                if (thisuser in wanted_users) and (
                    thisuser not in group_data["groupMembers"]
                ):
                    # Wanted but not yet present.
                    http_method = "PUT"
                elif (thisuser not in wanted_users) and (
                    thisuser in group_data["groupMembers"]
                ):
                    # Present, but not wanted
                    http_method = "DELETE"

                # Execute wanted action
                if http_method:
                    url = "%s/%s" % (group_ref, thisuser["ref"])
                    result = doapi(url, http_method, mm_provider, databody)
                    result["changed"] = True

            # Check idempotency
            change = False
            if group_data["name"] != module.params["name"]:
                change = True
            if group_data["description"] != module.params["desc"]:
                change = True

            if change:
                result = doapi(url, http_method, mm_provider, databody)
            result["changed"] = change
        else:
            # Group not present, create
            http_method = "POST"
            url = "Groups"
            databody = {
                "saveComment": "Ansible API",
                "group": {
                    "name": module.params["name"],
                    "description": module.params["desc"],
                    "groupMembers": wanted_users,
                    "roles": wanted_roles,
                    "builtIn": False,
                },
            }
            result = doapi(url, http_method, mm_provider, databody)
            if result.get("warnings", None):
                module.fail_json(msg=result.get("warnings"))
            group_ref = result["message"]["result"]["ref"]

    # If requested state is "absent"
    if state == "absent":
        if group_exists:
            # Group present, delete
            http_method = "DELETE"
            url = "Groups/%s" % group_ref
            databody = {"saveComment": "Ansible API"}
            result = doapi(url, http_method, mm_provider, databody)
        else:
            # group not present, done
            result["changed"] = False

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
