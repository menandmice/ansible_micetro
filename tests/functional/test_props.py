"""Functional coverage for the `props` module against a live Micetro host.

Uses dest=ipaddress (-> ipamRecords propertyDefinitions) since the test
host has real tracked IP ranges but no DNS/DHCP servers to hang a
`dest=zone`/`dest=dnsserver` property off of.

Uses proptype=yesno (Boolean) rather than text: text-type properties
make props.py send cloudTags/listItems fields, which the ipamRecords
propertyDefinitions backend on this server rejects with a WSDL-layer
error. props.py doesn't check for warnings on that call either, so it
silently reports changed=false/ok instead of failing - see the
functional-testing follow-up filed for this.
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


@pytest.mark.xfail(
    reason=(
        "props.py unconditionally adds cloudTags/listItems to the "
        "request body whenever proptype=text, regardless of dest. This "
        "server's ipamRecords propertyDefinitions backend rejects "
        "cloudTags with a WSDL-layer 400 for dest=ipaddress. Worse, "
        "props.py never checks doapi()'s `warnings` key on that create "
        "call, so it reports changed=false/ok instead of failing - the "
        "module silently no-ops instead of erroring. Filed as a "
        "follow-up; this test documents the bug so it flips to a pass "
        "once fixed."
    ),
    strict=True,
)
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
