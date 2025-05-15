#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Adam Brauns (@abrauns-silex)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible DHCP Scope info module.

Part of the Men&Mice Ansible integration

Module to get information on DHCP scope definitions in Micetro
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
  module: dhcpscope_info
  short_description: Gather information about DHCP scopes in Micetro
  author:
    - Adam Brauns (@abrauns-silex)
  version_added: "1.0.13"
  description:
    - Retrieves information about DHCP scopes from the Micetro system using the Men&Mice API.
    - Supports filtering by name, sorting, and optionally gathering scope options.
  notes:
    - When in check mode, this module does not make changes and returns the current state.
    - The module requires a valid Micetro API endpoint and credentials.
  options:
    limit:
      description:
        - Maximum number of DHCP scopes to return.
        - Must be a positive integer.
      type: int
      required: false
    mm_provider:
      description: Configuration details for connecting to the Micetro API.
      type: dict
      required: true
      suboptions:
        mm_url:
          description: URL of the Men&Mice API server (e.g., https://micetro.example.com).
          type: str
          required: true
        mm_user:
          description: Username for API authentication.
          type: str
          required: true
        mm_password:
          description: Password for API authentication.
          type: str
          required: true
    format_options:
      description: Whether to include DHCP scope options in the response.
      type: bool
      required: false
      default: true
    gather_options:
      description: Whether to include DHCP scope options in the response.
      type: bool
      required: false
      default: true
    name:
      description:
        - The name of the DHCP scope to filter by (optional).
        - If not provided, all scopes matching other criteria are returned.
      type: str
      required: false
    search_method:
      description:
        - Method to use when filtering by name.
        - C(exact) matches the exact name, C(contains) matches any part, C(starts_with) matches the beginning, C(ends_with) matches the end.
      type: str
      required: false
      default: "exact"
      choices: ["exact", "contains", "starts_with", "ends_with"]
    sort_by:
      description: Field to sort the results by.
      type: str
      required: false
      default: "name"
      choices: ["name", "ref", "rangeRef", "dhcpServerRef", "superscope", "description", "available"]
    sort_order:
      description: Order in which to sort the results.
      type: str
      required: false
      default: "Ascending"
      choices: ["Ascending", "Descending"]
"""

EXAMPLES = r"""
- name: Get all DHCP scope(s)
  menandmice.ansible_micetro.dhcpscope_info:
    mm_provider:
      mm_url: https://micetro.example.com
      mm_user: apiuser
      mm_password: apipass

- name: Get DHCP scope(s) by name
  menandmice.ansible_micetro.dhcpscope_info:
    name: my-dhcp-scope
    mm_provider:
      mm_url: https://micetro.example.com
      mm_user: apiuser
      mm_password: apipass

- name: Get DHCP scope(s) without options
  menandmice.ansible_micetro.dhcpscope_info:
    name: my-dhcp
    gather_options: false
    search_method: contains
    mm_provider:
      mm_url: https://micetro.example.com"
      mm_user: apiuser
      mm_password: apipass
"""

RETURN = r"""
dhcp_scopes:
  description: List of DHCP scope objects returned from Micetro
  type: list
  returned: success
  sample:
    - name: 192.168.1.0/24
      ref: DHCPScopes/123
      rangeRef: Ranges/456
      dhcpServerRef: DHCPServers/789
      options:
        - option: 3
          value: 192.168.1.1
        - option: 51
          value: 691200
total_results:
  description: Total number of DHCP scopes matching the criteria
  type: int
  returned: success
  sample: 1
message:
  description: Status message about the operation
  type: str
  returned: always
  sample: Returned 1 DHCP scope(s)
"""

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.menandmice.ansible_micetro.plugins.module_utils.micetro import (
    get_single_refs
)


def validate_params(module):
    """Validate module parameters"""
    if module.params["limit"] and module.params["limit"] < 0:
        module.fail_json(msg="limit parameter must be a positive integer")

    if module.params["name"] and len(module.params["name"]) > 255:
        module.fail_json(msg="name parameter is too long (max 255 characters)")

    return


def run_module():
    """Run Ansible module."""
    # Define available arguments/parameters a user can pass to the module
    module_args = dict(
        limit=dict(type="int", required=False),
        mm_provider=dict(
            type="dict",
            required=True,
            options=dict(
                mm_url=dict(type="str", required=True, no_log=False),
                mm_user=dict(type="str", required=True, no_log=False),
                mm_password=dict(type="str", required=True, no_log=True),
            ),
        ),
        format_options=dict(type="bool", required=False, default=True),
        gather_options=dict(type="bool", required=False, default=True),
        name=dict(type="str", required=False),
        search_method=dict(
            type="str",
            required=False,
            default="exact",
            choices=["exact", "contains", "starts_with", "ends_with"]
        ),
        sort_by=dict(
            type="str",
            required=False,
            default="name",
            choices=["name", "ref", "rangeRef", "dhcpServerRef", "superscope", "description", "available"]
        ),
        sort_order=dict(
            type="str",
            required=False,
            default="Ascending",
            choices=["Ascending", "Descending"]
        )
    )

    # Seed the result dict in the object
    # We primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = {"changed": False, "message": "Returned 0 DHCP scope(s)"}

    # The AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    # Ensure parameters are valid
    validate_params(module)

    # If the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # Filter search values
    search_method_map = {
        "exact": "",
        "contains": "@",
        "starts_with": "^",
        "ends_with": "$"
    }

    # Gather all module parameters
    limit = module.params["limit"]
    mm_provider = module.params["mm_provider"]
    gather_options = module.params["gather_options"]
    name = module.params["name"]
    format_options = module.params["format_options"]
    search_method = search_method_map[module.params["search_method"]]
    sort_by = module.params["sort_by"]
    sort_order = module.params["sort_order"]

    # Generate URL for API call
    query = ["DHCPScopes?"]
    if name:
        query.append('filter=name=%s"%s"' % (search_method, name.replace(" ", "%20")))

    if limit:
        query.append("limit=%s" % (limit))

    if sort_by:
        query.append("sortBy=%s" % (sort_by))

    if sort_order:
        query.append("sortOrder=%s" % (sort_order))

    refs = "&".join(query)

    # Perform initial search
    resp = get_single_refs(refs, mm_provider)
    if resp.get("invalid", None):
        module.fail_json(
            msg="An error occurred during the initial search, please try again",
            response=resp
        )

    # Update the results based on the API call
    result.update({
        "dhcp_scopes": resp["dhcpScopes"],
        "total_results": resp["totalResults"],
        "message": "Returned %s DHCP scope(s)" % len(resp["dhcpScopes"])
    })

    # Gather the DHCP scope options
    if gather_options:
        for dhcp_scope in result["dhcp_scopes"]:
            refs = "%s/Options" % dhcp_scope["ref"]
            resp = get_single_refs(refs, mm_provider)
            if resp.get("invalid", None):
                module.fail_json(
                    msg="An error occurred while getting the DHCP scope options, please try again",
                    response=resp
                )

            option_list = resp.get("dhcpOptions", [])
            if format_options:
                for option in option_list:
                    option["option"] = option["option"].replace("::", "")
            dhcp_scope.update({"options": option_list})

    # Return collected results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
