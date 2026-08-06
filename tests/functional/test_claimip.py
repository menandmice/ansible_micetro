"""Functional coverage for the `claimip` module against a live Micetro host.

Uses a real, currently-free address inside the test host's tracked
10.0.1.0/24 subnet (there's no DHCP server on this host, but claimip
only needs an IPAM-tracked range, not a DHCP scope).
"""

import random

from .helpers import as_bool, uri_check, collect_output


def _free_test_address():
    # Avoid .0/.255 and stay clear of low addresses that might be in use.
    return "10.0.1.%d" % random.randint(100, 240)


def test_claim_then_release(run_playbook, mm_provider):
    address = _free_test_address()
    ipam_url = "{{ mm_provider.mm_url }}/mmws/api/v2/ipamRecords/" + address

    tasks = [
        uri_check("Verify address starts unclaimed", ipam_url, "before"),
        {
            "name": "Claim the address",
            "menandmice.ansible_micetro.claimip": {
                "state": "present",
                "ipaddress": address,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "claim_result",
        },
        uri_check("Verify claimed", ipam_url, "after_claim"),
        {
            "name": "Release the address",
            "menandmice.ansible_micetro.claimip": {
                "state": "absent",
                "ipaddress": address,
                "mm_provider": "{{ mm_provider }}",
            },
            "register": "release_result",
        },
        uri_check("Verify released", ipam_url, "after_release"),
        collect_output(
            {
                "was_claimed_before": "before.json.result.ipamRecord.claimed | bool",
                "claim_changed": "claim_result.changed | bool",
                "is_claimed_after_claim": (
                    "after_claim.json.result.ipamRecord.claimed | bool"
                ),
                "release_changed": "release_result.changed | bool",
                "is_claimed_after_release": (
                    "after_release.json.result.ipamRecord.claimed | bool"
                ),
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert as_bool(output["was_claimed_before"]) is False
    assert as_bool(output["claim_changed"]) is True
    assert as_bool(output["is_claimed_after_claim"]) is True
    assert as_bool(output["release_changed"]) is True
    assert as_bool(output["is_claimed_after_release"]) is False
