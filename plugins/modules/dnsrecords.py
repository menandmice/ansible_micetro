#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, BlueCat Networks
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible Bulk DNS Record Management module.

Part of the Men&Mice Ansible integration

Module to create multiple DNS records in one zone with a single API call
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
  module: dnsrecords
  short_description: Create multiple DNS records in one zone in a single API call
  author:
    - BlueCat Networks
  version_added: "1.0.15"
  description:
    - Create multiple DNS records in the same DNS zone with a single API call.
    - The v2 API's C(POST /dnsRecords) accepts an array of records scoped to
      one zone; this module batches that the way
      M(menandmice.ansible_micetro.dnsrecord) can't (one record per call,
      and therefore one API round-trip per record).
    - Only creation is supported - the API has no bulk-delete endpoint, so
      removing many records offers no advantage over
      M(menandmice.ansible_micetro.dnsrecord) in a loop.
    - Records already present (matched the same way
      M(menandmice.ansible_micetro.dnsrecord) does - name, type and data)
      are skipped rather than recreated.
    - If any record in the batch fails to create, the module fails and
      reports the per-record error messages. Records that succeeded in
      the same batch are I(not) rolled back - the API has no batch-undo.
  notes:
    - When in check mode, this module pretends to have done things
      and returns C(changed = True).
  options:
    dnszone:
      description:
        - The DNS zone all records in this call are created in.
        - If a BIND server has several views with the same zone name in
          each, disambiguate with the Management Console's own display
          format, C(zonename (viewname)), e.g. V(example.com (internal)).
      type: str
      required: true
    records:
      description: The DNS records to create.
      type: list
      elements: dict
      required: true
      suboptions:
        name:
          description:
            - The name of the DNS record.
            - Can either be partially or fully qualified.
          type: str
          required: true
        data:
          description:
            - The data that is added to the DNS record.
            - The record data is a space-separated list when the resource
              type is one of MX, SRV, NAPTR, CAA, CERT, HINFO, TLSA.
            - For MX and SRV the hostname should be the short name and not
              the FQDN.
          type: str
          required: true
        rrtype:
          description: Resource Record Type for this DNS record.
          type: str
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
        comment:
          description:
            - Comment string for the record.
            - Note that only records in static DNS zones can have a
              comment string.
          type: str
        enabled:
          description: True if the record is enabled.
          type: bool
          default: true
        aging:
          description:
            - The aging timestamp of dynamic records in AD integrated zones.
            - Hours since January 1, 1601, UTC.
            - Providing a non-zero value creates a dynamic record.
          type: int
          default: 0
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
          description: userid to login with into the API.
          type: str
          required: true
        mm_password:
          description: password to login with into the API.
          type: str
          required: true
          no_log: true
"""

EXAMPLES = r"""
- name: Create several DNS records in one zone with a single API call
  menandmice.ansible_micetro.dnsrecords:
    dnszone: example.net.
    records:
      - name: host1
        data: 172.16.17.10
      - name: host2
        data: 172.16.17.11
      - name: mail
        data: "10 mailhost"
        rrtype: MX
        ttl: 86400
    mm_provider:
      mm_url: http://micetro.example.net
      mm_user: apiuser
      mm_password: apipasswd
  delegate_to: localhost
"""

RETURN = r"""
message:
    description: The output message from the Men&Mice System.
    type: str
    returned: always
created:
    description: References of the DNS records actually created (records
                 that already existed are skipped, not re-created).
    type: list
    returned: always
"""

# All imports
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.menandmice.ansible_micetro.plugins.module_utils.micetro import (
    doapi,
    get_single_refs,
    resolve_dns_zone_ref,
)

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


def _normalize_record(record):
    """Apply the same name/data/type normalization dnsrecord.py does."""
    rrname = record["name"].strip()
    rrdata = record["data"].strip()
    rrtype = record["rrtype"].strip().upper()
    if rrtype in RRTYPES_TAB:
        rrdata = "\t".join(rrdata.split())
    return rrname, rrdata, rrtype


def _record_already_exists(zoneref, rrname, rrdata, rrtype, mm_provider):
    """Same existence check dnsrecord.py does: exact name/type/data
    match, falling back to a short (unqualified) name lookup - some
    record types are stored under just the name, not the FQDN.
    """
    refs = "%s/dnsRecords?filter=name=%s and type=%s and data=%s" % (
        zoneref,
        rrname,
        rrtype,
        rrdata,
    )
    refs = refs.replace(" ", "%20").replace("\t", "\\t")
    resp = get_single_refs(refs, mm_provider)

    if len(resp.get("dnsRecords", [])) == 0:
        rrname_short = rrname.split(".")[0]
        refs = "%s/dnsRecords?filter=name=%s and type=%s and data=%s" % (
            zoneref,
            rrname_short,
            rrtype,
            rrdata,
        )
        refs = refs.replace(" ", "%20").replace("\t", "\\t")
        resp = get_single_refs(refs, mm_provider)

    if len(resp.get("dnsRecords", [])) == 0:
        return False

    rrdatashort = rrdata.split(".")[0] if "." in rrdata else rrdata
    for candidate in resp["dnsRecords"]:
        if candidate["type"] != rrtype:
            continue
        if candidate["name"] != rrname:
            continue
        if candidate["data"] in (rrdata, rrdatashort):
            return True
    return False


def run_module():
    """Run Ansible module."""
    module_args = dict(
        dnszone=dict(type="str", required=True),
        records=dict(
            type="list",
            elements="dict",
            required=True,
            options=dict(
                name=dict(type="str", required=True),
                data=dict(type="str", required=True),
                rrtype=dict(type="str", default="A", choices=RRTYPES),
                ttl=dict(type="int"),
                comment=dict(type="str"),
                enabled=dict(type="bool", default=True),
                aging=dict(type="int", default=0),
            ),
        ),
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

    result = {
        "changed": False,
        "message": "No DNS records needed creating",
        "created": [],
    }

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if module.check_mode:
        module.exit_json(changed=True, message="", created=[])

    mm_provider = module.params["mm_provider"]

    zoneinfo = resolve_dns_zone_ref(module.params["dnszone"], mm_provider)
    if zoneinfo.get("invalid"):
        module.fail_json(msg=zoneinfo["warnings"])
    zoneref = zoneinfo["ref"]

    to_create = []
    for record in module.params["records"]:
        rrname, rrdata, rrtype = _normalize_record(record)
        if _record_already_exists(zoneref, rrname, rrdata, rrtype, mm_provider):
            continue

        entry = {
            "name": rrname,
            "type": rrtype,
            "data": rrdata,
            "comment": record.get("comment") or "",
            "enabled": record["enabled"],
            "aging": record["aging"],
        }
        if record.get("ttl"):
            entry["ttl"] = str(record["ttl"])
        to_create.append(entry)

    if not to_create:
        module.exit_json(**result)

    # dnsZoneRef at this (batch) level - confirmed live - scopes every
    # record in the array to the same zone; the single-record
    # dnsrecord.py instead puts it inside its one-item array, which the
    # API also accepts, but the array form is the documented shape for
    # a multi-record POST.
    databody = {
        "saveComment": "Ansible API",
        "dnsZoneRef": zoneref,
        "dnsRecords": to_create,
    }
    api_result = doapi("dnsRecords", "POST", mm_provider, databody)
    if api_result.get("warnings"):
        module.fail_json(msg=api_result["warnings"])

    presult = api_result["message"]["result"]
    errors = presult.get("errors", [])
    # Confirmed live: a failed record's entry in objRefs is a sentinel
    # ("unknown/0"), not a real ref - and "errors" is a compact list of
    # only the failure messages (not index-aligned with the submitted
    # records), but each message names the offending record by name.
    created = [
        ref
        for ref in presult.get("objRefs", [])
        if not ref.startswith("unknown/")
    ]

    if errors:
        module.fail_json(
            msg="One or more DNS records failed to create: %s"
            % "; ".join(errors),
            errors=errors,
            created=created,
            changed=bool(created),
        )

    module.exit_json(
        changed=True,
        message="%d DNS record(s) created" % len(created),
        created=created,
    )


def main():
    """Start here."""
    run_module()


if __name__ == "__main__":
    main()
