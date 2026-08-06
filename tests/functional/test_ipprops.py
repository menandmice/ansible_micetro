"""Functional coverage for the `ipprops` module against a live Micetro host.

ipprops sets custom properties on an IP address, but (per its own docs)
those properties must already be defined. The text-typed fixture
property here is created/torn down via a raw API call rather than
`props.py`, since `props.py` has its own, separately-documented bug that
blocks creating text-typed properties on dest=ipaddress (see
test_props.py) - this file is about ipprops.py's behavior, not that one.
"""

import random
import uuid

import pytest

from .helpers import as_bool, uri_check, collect_output


def _free_test_address():
    return "10.0.1.%d" % random.randint(100, 240)


def _define_property_task(name, prop_type):
    return {
        "name": "Define the %s custom property (raw API)" % prop_type,
        "ansible.builtin.uri": {
            "url": "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/1/propertyDefinitions",
            "method": "POST",
            "url_username": "{{ mm_provider.mm_user }}",
            "url_password": "{{ mm_provider.mm_password }}",
            "force_basic_auth": True,
            "body_format": "json",
            "status_code": [201],
            "body": {
                "saveComment": "functional test fixture",
                "propertyDefinition": {
                    "name": name,
                    "type": prop_type,
                    "system": False,
                    "mandatory": False,
                    "readOnly": False,
                    "multiLine": False,
                    "defaultValue": "",
                },
            },
        },
        # Registered (even though nothing here inspects the result) so
        # this raw, non-idempotent call gets the same per-task
        # connection-limit retry every collection-module task gets -
        # see _with_connection_limit_retry in conftest.py.
        "register": "_define_property_result",
    }


def _delete_property_task(name):
    return {
        "name": "Remove the custom property (raw API)",
        "ansible.builtin.uri": {
            "url": (
                "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/1/"
                "propertyDefinitions/" + name
            ),
            "method": "DELETE",
            "url_username": "{{ mm_provider.mm_user }}",
            "url_password": "{{ mm_provider.mm_password }}",
            "force_basic_auth": True,
            "status_code": [204],
        },
        "register": "_delete_property_result",
    }


def test_set_text_property_on_ip_is_idempotent(run_playbook, mm_provider):
    address = _free_test_address()
    prop_name = "claudefuncip%s" % uuid.uuid4().hex[:6]
    ipam_url = "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/" + address

    tasks = [
        _define_property_task(prop_name, "String"),
        {
            "name": "Set the custom property on the address",
            "menandmice.ansible_micetro.ipprops": {
                "state": "present",
                "ipaddress": address,
                "properties": {prop_name: "Reykjavik"},
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "set_result",
        },
        uri_check("Verify property value", ipam_url, "verify_set"),
        {
            "name": "Re-run with the same value (idempotency check)",
            "menandmice.ansible_micetro.ipprops": {
                "state": "present",
                "ipaddress": address,
                "properties": {prop_name: "Reykjavik"},
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        _delete_property_task(prop_name),
        collect_output(
            {
                "set_changed": "set_result.changed | bool",
                "prop_value": (
                    "verify_set.json.result.ipamRecord.customProperties['%s']"
                    % prop_name
                ),
                "noop_changed": "noop_result.changed | bool",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["set_changed"]) is True
    assert output["prop_value"] == "Reykjavik"
    assert as_bool(output["noop_changed"]) is False


@pytest.mark.xfail(
    reason=(
        "Micetro's v2 API stringifies every custom property value on "
        "read regardless of its declared type (confirmed for Boolean "
        "and Integer), but accepts native JSON types on write. "
        "ipprops.py's change-detection compares the requested native "
        "value against that stringified read-back with no "
        "normalization (its str2bool handling only covers lowercase "
        "'true'/'false', not the API's actual '1'/'0'), so it reports "
        "changed=true on every run for any non-string-typed property "
        "even when nothing changed. Filed as a follow-up; this test "
        "documents the bug so it flips to a pass once fixed."
    ),
    strict=True,
)
def test_set_boolean_property_on_ip_is_idempotent(run_playbook, mm_provider):
    address = _free_test_address()
    prop_name = "claudefuncipbool%s" % uuid.uuid4().hex[:6]

    tasks = [
        _define_property_task(prop_name, "Boolean"),
        {
            "name": "Set the custom property on the address",
            "menandmice.ansible_micetro.ipprops": {
                "state": "present",
                "ipaddress": address,
                "properties": {prop_name: True},
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "set_result",
        },
        {
            "name": "Re-run with the same value (idempotency check)",
            "menandmice.ansible_micetro.ipprops": {
                "state": "present",
                "ipaddress": address,
                "properties": {prop_name: True},
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "noop_result",
        },
        _delete_property_task(prop_name),
        collect_output({"noop_changed": "noop_result.changed | bool"}),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["noop_changed"]) is False
