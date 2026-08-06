"""Unit tests for plugins/modules/props.py's dest-type mapping.

Regression coverage for issue #8: DEST2URL originally covered only 9 of
the object types Micetro's v2 API exposes a propertyDefinitions
sub-resource for. Confirmed live against a real server, most of the
others (roles, users, groups, folders, DHCP scopes/groups/pools, AD
forests/sites, ...) reject custom property creation outright - the API
path existing doesn't mean the object type accepts custom properties.
Only dnsRecords and changeRequests actually do, alongside the original
9, and DEST2URL/DESTTYPES should reflect exactly that verified set.
"""

from ansible_collections.menandmice.ansible_micetro.plugins.modules import props


def test_desttypes_and_dest2url_are_in_sync():
    assert set(props.DESTTYPES) == set(props.DEST2URL.keys())


def test_dest2url_matches_the_verified_working_set():
    expected = {
        "dnsserver": "dnsServers",
        "dhcpserver": "dhcpServers",
        "zone": "dnsZones",
        "iprange": "ranges",
        "ipaddress": "ipamRecords",
        "device": "devices",
        "interface": "interfaces",
        "cloudnet": "cloudNetworks",
        "cloudaccount": "cloudServiceAccounts",
        "dnsrecord": "dnsRecords",
        "changerequest": "changeRequests",
    }

    assert props.DEST2URL == expected
