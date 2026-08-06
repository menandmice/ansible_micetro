"""Functional coverage for the `inventory` dynamic inventory plugin.

The test host has IPAM-tracked ranges but no addresses that are both
Assigned and have a linked DNS host record (inventory.py only surfaces
addresses with `dnsHosts` set), and no DNS server to create one against.
So this covers the structural/no-crash path - the actual replacement for
the removed `command/GetIPAMRecords` endpoint - rather than real host
data, which can't exist on this host.
"""


def test_inventory_runs_and_returns_well_formed_empty_result(
    run_inventory, mm_provider
):
    inventory = run_inventory(mm_provider, ranges=["10.0.1.0/24"])

    assert "_meta" in inventory
    assert "all" in inventory
    # No assigned+DNS-linked addresses exist on this host, so no
    # dynamically-discovered groups beyond the standard "all"/"ungrouped".
    assert set(inventory.keys()) <= {"_meta", "all", "ungrouped"}


def test_inventory_accepts_filters_without_erroring(run_inventory, mm_provider):
    inventory = run_inventory(
        mm_provider,
        ranges=["10.0.1.0/24"],
        filters=[{"location": "nowhere"}],
    )

    assert "_meta" in inventory
