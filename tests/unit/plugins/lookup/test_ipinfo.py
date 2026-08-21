"""Unit tests for plugins/lookup/ipinfo.py."""

import pytest
from ansible.errors import AnsibleError

from ansible_collections.menandmice.ansible_micetro.plugins.lookup import (
    ipinfo,
)

MM_PROVIDER = {
    "mm_url": "http://micetro.example.net",
    "mm_user": "apiuser",
    "mm_password": "apipasswd",
}

IPAMRECORD = {
    "addrRef": "ipamRecords/158",
    "address": "192.168.15.3",
    "claimed": True,
}


def test_run_returns_a_list_containing_the_ipam_record(mocker):
    # Regression test: Ansible lookup plugins must return a list - run()
    # used to return the bare dict, which query() rejects outright with
    # "returned <class 'dict'> instead of <class 'list'>".
    mocker.patch.object(
        ipinfo,
        "doapi",
        return_value={"message": {"result": {"ipamRecord": IPAMRECORD}}},
    )

    result = ipinfo.LookupModule().run([MM_PROVIDER, "192.168.15.3"])

    assert isinstance(result, list)
    assert result == [IPAMRECORD]


def test_raises_on_api_warnings(mocker):
    mocker.patch.object(
        ipinfo,
        "doapi",
        return_value={"warnings": "not found"},
    )

    with pytest.raises(AnsibleError):
        ipinfo.LookupModule().run([MM_PROVIDER, "192.168.15.3"])


def test_raises_when_too_few_terms_given():
    with pytest.raises(AnsibleError):
        ipinfo.LookupModule().run([MM_PROVIDER])
