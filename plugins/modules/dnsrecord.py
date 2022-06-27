#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
"""Ansible DNS Record Management module.

Part of the Men&Mice Ansible integration

Module to manage DNS entries for IP addresses in the Men&Mice Suite
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
  module: dnsrecord
  short_description: Manage DNS records in the Men&Mice Suite
  author:
    - Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
  version_added: "2.7"
  description:
    - Manage DNS records in the Men&Mice Suite.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
    - As it is very common in DNS to have multiple entries with the same name,
      there is no possibility to change a record, the only way is to add the
      new record with the updated data and remove the old one after that.
  options:
    state:
        description: The state of the properties.
        type: bool
        required: False
        choices: [ absent, present ]
        default: present
    name:
      description:
        - The name of the DNS record.
        - Can either be partially or fully qualified.
      type: str
      required: True
    data:
      description:
          - The data that is added to the DNS record
          - The record data is a space-separated list
            when the resource type is one of
            MX, SRV, NAPTR, CAA, CERT, HINFO, TLSA
          - For MX and SRV the hostname should be the short
            name and not the FQDN
      type: str
      required: True
    dnszone:
      description: The DNS zone where the action should take place.
      type: str
      required: True
    rrtype:
      description: Resource Record Type for this DNS record.
      type: str
      required: False
      default: A
      choices: [
                A, AAAA, CNAME, CAA, DNAME,
                DLV, DNSKEY, DS, HINFO,
                LOC, MX, NAPTR, NS,
                NSEC3PARAM, PTR, RP, SOA,
                SPF, SRV, SSHFP, TLSA, TXT
      ]
    ttl:
      description: The Time-To-Live of the DNS record.
      type: int
      required: False
      default: 0 (Same as zone)
    comment:
      description:
        - Comment string for the record.
        - Note that only records in static DNS zones can have a comment string
      type: str
      required: False
    enabled:
      description:
        - True if the record is enabled.
        - If the record is disabled the value is false
      type: bool
      required: False
      default: False
    aging:
      description:
        - The aging timestamp of dynamic records in AD integrated zones.
        - Hours since January 1, 1601, UTC.
        - Providing a non-zero value creates a dynamic record.
      type: int
      required: False
      default: 0
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
- name: Set DNS record in zone for a defined name
 ansilabnl.micetro.dnsrecord:
    state: present
    name: beatles
    data: 172.16.17.2
    rrtype: A
    dnszone: example.net.
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Set PTR record in zone for a defined name
 ansilabnl.micetro.dnsrecord:
    state: present
    name: "2.17.16.172.in-addr.arpa."
    data: beatles.example.net.
    rrtype: PTR
    dnszone: "17.16.172.in-addr.arpa."
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost

- name: Set MX record
 ansilabnl.micetro.dnsrecord:
    state: present
    name: beatles
    rrtype: MX
    dnszone: example.net.
    data: "10 ringo"
    ttl: 86400
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

# Define all available Resource Record types
RRTYPES = [
    "A",
    "AAAA",
    "CNAME",
    "CAA",
    "DNAME",
    "DLV",
    "DNSKEY",
    "DS",
    "HINFO",
    "LOC",
    "MX",
    "NAPTR",
    "NS",
    "NSEC3PARAM",
    "PTR",
    "RP",
    "SOA",
    "SPF",
    "SRV",
    "SSHFP",
    "TLSA",
    "TXT",
]

# Resource types with tab seperation in the data field.
RRTYPES_TAB = ["MX", "SRV", "NAPTR", "CAA", "CERT", "HINFO", "TLSA"]


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
        data=dict(type="str", required=True),
        ttl=dict(type="int", required=False, default=0),
        comment=dict(type="str", required=False),
        enabled=dict(type="bool", required=False, default=True),
        aging=dict(type="int", required=False, default=0),
        dnszone=dict(type="str", required=True),
        rrtype=dict(type="str", required=False, default="A", choices=RRTYPES),
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

    # Get the data field and make it tabbed when needed
    rrname = module.params.get("name").strip()
    rrdata = module.params.get("data").strip()
    rrtype = module.params.get("rrtype").strip().upper()
    if rrtype in RRTYPES_TAB:
        rrdata = "\t".join(rrdata.split())
    # Zone MUST end with a '.' and I can imagine that this
    # is forgotten
    rrzone = module.params.get("dnszone").strip()
    if rrzone[-1] != ".":
        rrzone += "."

    # Try to get all name of DNS Zone info
    refs = "DNSZones?filter=%s" % rrzone
    zoneresp = get_single_refs(refs, mm_provider)
    if zoneresp.get("totalResults", 1) == 0:
        # Zone does not exists
        module.fail_json(msg="DNS Zone '%s' does not exist" % rrzone)

    # find the correct zone from the returned group (could be more then one)
    zoneref = None
    if len(zoneresp["dnsZones"]) == 1:
        zoneref = zoneresp["dnsZones"][0]["ref"]
    else:
        for zr in zoneresp["dnsZones"]:
            if zr["name"] == rrzone:
                zoneref = zr["ref"]
                break

    # And try to get the DNS record with this data
    # DNSRecords?filter=name=host2 and type=A and data=192.168.10.11
    # name and data are required, type defaults to A (so all fields are
    # always available). All spaces are translated into '%20'
    # (hex code for space) and tabs are replaced with '\\t' to ensure
    # the tabs reach the API ad '\t'.
    refs = "%s/DNSRecords?filter=name=%s and type=%s and data=%s" % (
        zoneref,
        rrname,
        rrtype,
        rrdata,
    )
    refs = refs.replace(" ", "%20").replace("\t", "\\t")
    iparesp = get_single_refs(refs, mm_provider)

    # It could be that the result is empty. This sometimes happens when
    # a record is stored with just the name and not the FQDN. This depends on
    # the recordtype
    rrname = module.params.get("name")
    if len(iparesp.get("dnsRecords", [])) == 0:
        rrname = rrname.split(".")[0]
        refs = "%s/DNSRecords?filter=name=%s and type=%s and data=%s" % (
            zoneref,
            rrname,
            rrtype,
            rrdata,
        )
        refs = refs.replace(" ", "%20").replace("\t", "\\t")
        iparesp = get_single_refs(refs, mm_provider)

    # If more then one result was found
    if iparesp.get("totalResults", 1) > 1:
        for res in iparesp["dnsRecords"]:
            # Is it the correct record type, if not, remove it
            if res["type"] != rrtype:
                iparesp["dnsRecords"].remove(res)
                iparesp["totalResults"] -= 1

    # If absent is requested, make a quick delete
    if module.params["state"] == "absent":
        if iparesp.get("totalResults", 1) == 0:
            # DNS record does not exist. Just return
            result["change"] = False
            module.exit_json(**result)

        # It does exist. Delete it
        http_method = "DELETE"
        url = "%s" % iparesp["dnsRecords"][0]["ref"]
        databody = {"saveComment": "Ansible API"}
        result = doapi(url, http_method, mm_provider, databody)
        module.exit_json(**result)

    # Come here the DNS record should be present
    # Check if the complete record is already present?
    if iparesp.get("totalResults", 1) == 0:
        # No record file. Always add it
        add = True
    else:
        # A similar record is found, check if it is exactly the same.
        if "." in rrdata:
            rrdatashort = rrdata.split(".")[0]
        else:
            rrdatashort = rrdata
        add = False
        add = add or (iparesp["dnsRecords"][0]["name"] != rrname)
        add = add or (iparesp["dnsRecords"][0]["type"] != rrtype)
        add = add or (
            (iparesp["dnsRecords"][0]["data"] != rrdata)
            and (iparesp["dnsRecords"][0]["data"] != rrdatashort)
        )

    if add:
        # Absent, create
        http_method = "POST"
        url = "DNSRecords"
        databody = {
            "saveComment": "Ansible API",
            "dnsRecords": [
                {
                    "name": rrname,
                    "type": rrtype,
                    "data": rrdata,
                    "comment": module.params.get("comment", ""),
                    "enabled": module.params.get("enabled"),
                    "aging": module.params.get("aging", 0),
                    "dnsZoneRef": zoneref,
                }
            ],
        }
        if module.params.get("ttl"):
            databody["dnsRecords"][0]["ttl"] = str(module.params.get("ttl"))

        result = doapi(url, http_method, mm_provider, databody)
        # When an IP address has status 'claimed', it cannot be assigned a
        # DNS record. The 'errors' field shows this.
        if result["message"]["result"]["errors"]:
            result["warnings"] = result["message"]["result"]["errors"]
            result.pop("message", None)
    else:
        result = {"changed": False, "message": ""}

    # return collected results
    module.exit_json(**result)


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
