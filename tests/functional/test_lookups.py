"""Functional coverage for the `freeip` and `ipinfo` lookup plugins."""

from .helpers import collect_output


def test_freeip_returns_an_address_in_the_requested_network(
    run_playbook, mm_provider
):
    tasks = [
        {
            "name": "Look up a free IP in the test subnet",
            "ansible.builtin.set_fact": {
                "free_ip": (
                    "{{ lookup('menandmice.ansible_micetro.freeip', "
                    "mm_provider, '10.0.1.0/24') }}"
                )
            },
        },
        collect_output({"free_ip": "free_ip"}),
    ]

    output = run_playbook(tasks, mm_provider)

    assert output["free_ip"].startswith("10.0.1.")


def test_ipinfo_returns_record_for_known_address(run_playbook, mm_provider):
    tasks = [
        {
            # ipinfo.py's own docs specify query(), not lookup(), for
            # accessing the result as a structured dict.
            "name": "Look up info for a known-tracked address",
            "ansible.builtin.set_fact": {
                "ip_info": (
                    "{{ query('menandmice.ansible_micetro.ipinfo', "
                    "mm_provider, '10.0.1.50') }}"
                )
            },
        },
        collect_output(
            {
                "address": "ip_info.address",
                "claimed": "ip_info.claimed | bool",
            }
        ),
    ]

    output = run_playbook(tasks, mm_provider)

    assert output["address"] == "10.0.1.50"
    # Not asserting a specific claimed state - other tests in this suite
    # toggle it - just that the lookup returns a real record shape.
    assert output["claimed"] in (True, False)
