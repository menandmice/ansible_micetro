#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2020-2022, Men&Mice
# GNU General Public License v3.0
# see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt
#
# python 3 headers, required if submitting to Ansible
"""Ansible lookup plugin.

Lookup plugin for finding information about an IP address
in the Men&Mice Suite.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type
from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible_collections.ansilabnl.micetro.plugins.module_utils.micetro import (
    doapi,
)

DOCUMENTATION = r"""
    lookup: ipinfo
    author: Ton Kersten <t.kersten@atcomputing.nl> for Men&Mice
    version_added: "2.7"
    short_description: Find information of an IP address
    description:
      - This lookup collects info of an IP address
    options:
      mm_provider:
        description: Definition of the Men&Mice suite API mm_provider
        type: dict
        required: True
        suboptions:
          mm_url:
            description: Men&Mice API server to connect to
            required: True
            type: str
          mm_user:
            description: userid to login with into the API
            required: True
            type: str
          mm_password:
            description: password to login with into the API
            required: True
            type: str
            no_log: True
      ipaddress:
        description:
          - The IP address that is examined
        type: str
        required: True
"""

EXAMPLES = r"""
- name: Find all info for IP 172.16.17.2
  debug:
    msg: "Info for IP: {{ lookup('ansilabnl.micetro.ipinfo', mm_provider, '172.16.17.2') }}"
  vars:
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd

- name: Get DHCP reservations for 172.16.17.2
  debug:
        msg: "{{ ipinfo['dhcpReservations'] }}"
  vars:
    mm_provider:
      mm_url: http://mmsuite.example.net
      mm_user: apiuser
      mm_password: apipasswd
    ipinfo: "{{ query('ansilabnl.micetro.ipinfo', mm_provider, '172.16.17.2') }}"
"""

RETURN = r"""
_list:
  description: A dict containing all results
  fields:
    0: IP address(es)
"""


class LookupModule(LookupBase):
    """Extension to the base looup."""

    def run(self, terms, variables=None, **kwargs):
        """Variabele terms contains a list with supplied parameters.

        - mm_provider  -> Definition of the Men&Mice suite API mm_provider
        - IPAddress -> The IPAddress to examine
        """
        # Sufficient parameters
        if len(terms) < 2:
            raise AnsibleError(
                "Insufficient parameters. Need at least: mm_url, mm_user, mm_password and IPAddress."
            )

        # Get the parameters
        mm_provider = terms[0]
        ipaddress = terms[1].strip()

        # Call the API to find info
        http_method = "GET"
        url = "%s/%s" % ("IPAMRecords", ipaddress)
        databody = {}
        result = doapi(url, http_method, mm_provider, databody)

        # An error occured?
        if result.get("warnings", None):
            raise AnsibleError(result.get("warnings"))

        if isinstance(result, dict):
            return result["message"]["result"]["ipamRecord"]
        return result
