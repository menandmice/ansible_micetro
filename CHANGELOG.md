# Changelog

- spenney, agudgeirsson - 2026-08-24 - Version 2.0.0
  * Migrated the collection to the Micetro v2 REST API: versioned
    camelCase endpoints and Bearer session-token auth in
    `module_utils.micetro`, replacing the unversioned PascalCase/
    Basic-Auth API and the `ansible.errors` import that broke on
    ansible-core 2.21+
  * Added the `dhcpsuperscope`, `dhcpaddresspool`, `dhcpgroup`, and
    `dnsrecords` (bulk DNS record creation) modules as first-class
    DHCP/DNS sub-objects
  * Added a unit test suite (`tests/unit`) and a functional test suite
    (`tests/functional`) that runs the real modules/lookups/inventory
    plugin against a live Micetro host, and ran it against a live
    server to find and fix further bugs
  * Expanded `props.py`'s supported `dest` types to `dnsrecord` and
    `changerequest`, the two additional object types confirmed to
    actually support custom properties
  * Fixed several bugs found while migrating: `dhcp.py` couldn't import
    at all (dead `ansible.utils.unicode` reference), `group.py`'s
    `state: absent`/`present` logic always missed existing groups,
    `zone.py` referenced a nonexistent response key, and more
  * Fixed `dhcpaddresspool.py` sending a read-only `name` field and an
    unneeded `dhcpScopeRef` on create, which made every pool creation
    fail outright; `name` is no longer a module option since the API
    never allowed setting it
  * Fixed `dhcp.py` always sending `ddnsHostName`/`filename`/`serverName`/
    `nextServer` even when unset, which MS DHCP servers reject outright
    ([MM-31019](https://bluecatnetworks.atlassian.net/browse/MM-31019))
  * Fixed the `ipinfo` lookup plugin returning a bare dict instead of a
    list, which broke `query()`
  * Fixed `props.py` sending unsupported `cloudTags`/`listItems` and
    swallowing create/update failures
  * Fixed `ipprops.py` reporting `changed=true` forever for non-string
    custom properties
  * Added support for view-disambiguated zone names
    (`"zonename (viewname)"`) in `dnsrecord.py`'s/`dnsrecords.py`'s
    `dnszone` filter, for BIND servers with multiple views sharing a
    zone name ([PM-9770](https://bluecatnetworks.atlassian.net/browse/PM-9770))
  * Added `descr`/`adintegrate` aliases to keep backwards compatibility
    with existing playbooks
  * Cached Micetro session tokens on disk across module tasks in the
    same playbook run
  * Fixed `ansible.cfg`'s `[inventory] enable_plugins` missing `yaml`/
    `ini`, which silently broke static inventory files once the config
    file was actually being loaded
  * Added a GitHub Actions workflow to publish to Ansible Galaxy
    automatically on tag push

- abrauns-silex - 2025-05-14 - Version 1.0.14
  * Fixed a minor bug when a dhcpscope contains a space in `dhcpscope` and `dhcpscope_info`

- abrauns-silex - 2025-04-08 - Version 1.0.13
  * Added dhcpscope_info module

- TonK - 2024-08-16 - Version 1.0.12
  * Fix "Primary" or "Master" API naming scheme by Andrew McCann

- TonK - 2024-08-16 - Version 1.0.11
  * Fix multiple domain bug as suggested by Andrew McCann
    in issue 8

- TonK - 2024-08-13 - Version 1.0.10
  * Added primary zone check as suggested by Andrew McCann
    in issue 7

- abrauns-silex - 2024-07-29 - Version 1.0.9
  * Minor improvements to error handling for the dhcpscope module

- abrauns-silex - 2024-07-23 - Version 1.0.8
  * Added dhcpscope module

- TonK - 2023-07-06 - Version 1.0.7
  * Fixed a syntax error in `user.py`
  * Changed `mmsuite` to `micetro`
  * Changed 'Men&Mice Suite' into 'Micetro' globally
  * Set the copyright year to 2023

- TonK - 2023-07-06 - Version 1.0.6
  * Fixed issue 2 (hb9hnt - Beni)
    Removing user from "All users" group is not allowed
  * Fixed issue 3 (hb9hnt - Beni)
    Allow for usernames with non ASCII characters (UTF8)

- TonK - 2022-05-31
  * Initial conversion of the loose modules to a collection
