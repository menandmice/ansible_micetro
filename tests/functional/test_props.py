"""Functional coverage for the `props` module against a live Micetro host.

Uses dest=ipaddress (-> ipamRecords propertyDefinitions) since the test
host has real tracked IP ranges but no DNS/DHCP servers to hang a
`dest=zone`/`dest=dnsserver` property off of.

Uses proptype=yesno (Boolean) rather than text for most cases: the
ipamRecords propertyDefinitions backend on this server rejects
cloudTags/listItems (which props.py used to send unconditionally for
proptype=text) with a WSDL-layer error - props.py now skips those
fields for dest=ipaddress specifically (issue #14). See
test_text_property_on_ipaddress_dest_is_actually_created below for
that path.
"""

import uuid

import pytest

from .helpers import as_bool, collect_output, uri_check


def test_props_create_update_delete(run_playbook, mm_provider):
    prop_name = "claudefunc%s" % uuid.uuid4().hex[:8]
    prop_def_url = (
        "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/1/propertyDefinitions/"
        + prop_name
    )

    tasks = [
        {
            "name": "Create custom property definition",
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "present",
                "proptype": "yesno",
                "dest": "ipaddress",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", prop_def_url, "verify_created"),
        {
            "name": "Update to mandatory",
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "present",
                "proptype": "yesno",
                "dest": "ipaddress",
                "mandatory": True,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "update_result",
        },
        uri_check("Verify updated", prop_def_url, "verify_updated"),
        {
            "name": "Delete custom property definition",
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "absent",
                "dest": "ipaddress",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        # This endpoint returns 400 "Unknown property", not 404, once
        # the property definition is gone.
        uri_check(
            "Verify gone",
            prop_def_url,
            "verify_gone",
            status_code=[200, 400, 404],
        ),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_name": (
                    "verify_created.json.result.propertyDefinition.name"
                ),
                "created_mandatory": (
                    "verify_created.json.result.propertyDefinition.mandatory | bool"
                ),
                "update_changed": "update_result.changed | bool",
                "updated_mandatory": (
                    "verify_updated.json.result.propertyDefinition.mandatory | bool"
                ),
                "delete_changed": "delete_result.changed | bool",
                "gone_status": "verify_gone.status | int",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert output["created_name"] == prop_name
    assert as_bool(output["created_mandatory"]) is False
    assert as_bool(output["update_changed"]) is True
    assert as_bool(output["updated_mandatory"]) is True
    assert as_bool(output["delete_changed"]) is True
    assert int(output["gone_status"]) in (400, 404)


def test_text_property_on_ipaddress_dest_is_actually_created(
    run_playbook, mm_provider
):
    prop_name = "claudefunctext%s" % uuid.uuid4().hex[:8]
    prop_def_url = (
        "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/1/propertyDefinitions/"
        + prop_name
    )

    tasks = [
        {
            "name": "Create a text custom property definition",
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "present",
                "proptype": "text",
                "dest": "ipaddress",
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check(
            "Verify created",
            prop_def_url,
            "verify_created",
            status_code=[200, 400],
        ),
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_status": "verify_created.status | int",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    # The module reports success and the property never actually exists.
    assert as_bool(output["create_changed"]) is True
    assert int(output["created_status"]) == 200


@pytest.mark.parametrize(
    "dest,resource_type",
    [
        ("dnsrecord", "dnsRecords"),
        ("changerequest", "changeRequests"),
    ],
)
def test_new_dest_types_from_issue_8(
    run_playbook, mm_provider, dest, resource_type
):
    """Regression coverage for issue #8: DEST2URL originally didn't cover
    these two. Unlike most of the *other* object types that also expose
    a propertyDefinitions endpoint (roles, users, groups, folders, DHCP
    scopes/groups/pools, AD sites/forests, ...), these two are
    confirmed live to actually accept custom property creation - see
    test_props.py's module docstring and props.py's DESTTYPES comment
    for the full list of object types that were tried and rejected."""
    prop_name = "claudefunc%s%s" % (dest, uuid.uuid4().hex[:6])
    prop_def_url = (
        "{{ mm_provider.mm_url }}/mmws/api/v2/%s/1/propertyDefinitions/%s"
        % (resource_type, prop_name)
    )

    tasks = [
        {
            "name": "Create custom property definition on dest=%s" % dest,
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "present",
                "proptype": "yesno",
                "dest": dest,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "create_result",
        },
        uri_check("Verify created", prop_def_url, "verify_created"),
        {
            "name": "Delete custom property definition",
            "menandmice.ansible_micetro.props": {
                "name": prop_name,
                "state": "absent",
                "dest": dest,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "delete_result",
        },
        collect_output(
            {
                "create_changed": "create_result.changed | bool",
                "created_name": (
                    "verify_created.json.result.propertyDefinition.name"
                ),
                "delete_changed": "delete_result.changed | bool",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["create_changed"]) is True
    assert output["created_name"] == prop_name
    assert as_bool(output["delete_changed"]) is True
