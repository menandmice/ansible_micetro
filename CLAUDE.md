# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An Ansible collection (`menandmice.ansible_micetro`) that manages a Micetro
(Men&Mice / BlueCat) DNS, DHCP and IPAM installation via its REST API
(`mmws/api`). It ships Ansible modules, lookup plugins, and a dynamic
inventory plugin — no standalone application code.

## Commands

Testing/linting is done through `tox` (see `tox.ini`):

```bash
tox -e linters       # black --check, flake8, yamllint, ansible-lint (the full gate)
tox -e black          # auto-format plugins/ with black (line length 80)
tox -e unit           # pytest tests/unit - mocks the HTTP layer, no live server needed
tox -e functional     # pytest tests/functional - real ansible-playbook/-inventory
                      # runs against a live Micetro host; opt-in, not in the default
                      # envlist (see "Testing against a live server" below)
```

Individual tools, if you need to run just one:

```bash
black -l80 --check plugins          # or drop --check to reformat
flake8 plugins                      # max-line-length 160, see [flake8] in tox.ini for ignored codes
yamllint -c .yamllint -s .
ansible-lint docs/examples/play-<name>.yml   # ansible-lint only targets docs/examples/*.yml, not plugins/
pytest tests/unit
pytest tests/functional   # needs live credentials, see below
```

### Testing against a live server

`tests/functional/` runs the real modules/lookups/inventory plugin
through `ansible-playbook`/`ansible-inventory` against an actual Micetro
instance (`tests/unit/` only mocks the HTTP layer). It needs credentials:
either `MM_HOST`/`MM_USER`/`MM_PASSWORD` env vars, or a `local/creds.env`
file at the repo root (`HOST=`/`USERNAME=`/`PASSWORD=`, already
gitignored). With neither present, the whole session is skipped rather
than failing.

These tests mutate real objects on whatever host they're pointed at
(always cleaned up afterward) and log in fresh per module task with no
way to log out (the v2 API has no session/logout endpoint) - a host with
a low per-user concurrent-connection cap can trip transient "Too many
open connections" failures under load. `tests/functional/conftest.py`
retries the specific task that hit this via Ansible's own
`retries`/`until` loop rather than treating it as a real failure.

`.ansible-lint` excludes `plugins/`, `meta/`, and `galaxy.yml` from ansible-lint —
only the example playbooks under `docs/examples/` are linted that way. Python
code style is enforced by `black` + `flake8` instead.

To try modules/plugins locally against a real Micetro instance, copy
`micetro.yml-sample` to `micetro.yml` and adjust `ansible.cfg`'s
`inventory = micetro.yml` (see comments in that file).

## Architecture

- `plugins/module_utils/micetro.py` — the shared API client every module and
  plugin builds on. Key functions:
  - `doapi(url, method, mm_provider, databody)` — the single low-level entry
    point for all HTTP calls to `{mm_url}/mmws/api/{url}`. Basic-auth'd,
    retries up to 5 times with a short sleep on `ConnectionError` (for HA
    failover), and normalizes results into `{"changed": ..., "message": ...}`
    or `{"changed": False, "warnings": ...}` on `HTTPError`.
  - `get_single_refs(objname, mm_provider)` — GET wrapper that unwraps
    `message["result"]`, or returns `{"invalid": True, "warnings": ...}` on
    error. Modules check `resp.get("invalid")` after calling this rather than
    handling exceptions directly.
  - `getrefs` / `get_dhcp_scopes` — thin, task-specific helpers built on `doapi`.
  - `TRUEFALSE` — the API sometimes encodes booleans inverted (`0` = true,
    `1` = false); use this map rather than hardcoding it elsewhere.
  All modules/plugins import from this file via the fully-qualified
  `ansible_collections.menandmice.ansible_micetro.plugins.module_utils.micetro`
  path (required for collections, not a relative import).

- `plugins/modules/*.py` — one module per Micetro object type (`zone`,
  `user`, `group`, `role`, `dnsrecord`, `dhcp`, `dhcpscope`,
  `dhcpscope_info`, `claimip`, `ipprops`, `props`). Every module follows the
  same shape:
  1. `DOCUMENTATION` / `EXAMPLES` / `RETURN` docstrings (standard Ansible
     module doc format — keep these in sync with actual `module_args`).
  2. `run_module()` builds `module_args` with `AnsibleModule`, always
     including an `mm_provider` sub-dict (`mm_url`, `mm_user`,
     `mm_password` with `no_log=True`) — this is the common auth contract
     across the whole collection.
  3. State-management modules (`zone`, `user`, `group`, etc.) take a
     `state: present|absent`, first GET the existing object via
     `get_single_refs`, then branch into PUT/POST (present) or DELETE
     (absent) via `doapi`, mirroring typical Ansible idempotent-CRUD.
  4. `_info` modules (`dhcpscope_info`) are read-only: no `state`, just
     query/filter/sort params and a GET.
  5. `module.check_mode` short-circuits before any mutating API call.

- `plugins/lookup/` (`freeip`, `ipinfo`) — `LookupBase` plugins for use in
  Jinja expressions (e.g. finding/claiming free IPs). Same `mm_provider`
  contract and `doapi`/`TRUEFALSE` usage as modules.

- `plugins/inventory/inventory.py` — dynamic inventory plugin
  (`menandmice.ansible_micetro.inventory`) that populates Ansible inventory
  from Micetro IPAM data; configured via `micetro.yml` (see
  `micetro.yml-sample` and `docs/README_inventory.adoc`).

- `docs/` — Asciidoc sources (one `README_<topic>.adoc` per
  module/plugin/topic) plus `docs/examples/*.yml` example playbooks, which
  double as the ansible-lint fixtures in `tox.ini`. `docs/README.pdf` is a
  generated artifact assembled from the adoc sources via `docs/Makefile`.
  `docs/API_GAP_ASSESSMENT.md` tracks the collection's migration to the
  Micetro v2 REST API (versioned camelCase paths, Bearer session auth) —
  see GitLab issues for current status of that work.

- `tests/unit/` — pytest suite that mocks the HTTP layer
  (`ansible.module_utils.urls.open_url`) to test `module_utils/micetro.py`
  and individual modules in isolation; no live server needed.
  `tests/functional/` runs the real modules/lookups/inventory plugin via
  `ansible-playbook`/`ansible-inventory` subprocesses against a live
  Micetro host — see the "Testing against a live server" note above.
  Both directories register the collection under its FQCN
  (`ansible_collections.menandmice.ansible_micetro...`) via `conftest.py`
  so plugin code imports correctly without a real collection install.

## Conventions worth preserving

- Every module/plugin exposes credentials as a single `mm_provider` dict
  (`mm_url`, `mm_user`, `mm_password`) — never separate top-level args.
- Ref IDs from the v2 API are full, camelCase, self-describing paths like
  `dnsZones/123` or `groups/6` — use them directly as a URL, never
  prepend another type-prefix (`"Groups/%s" % group_ref` was a real,
  now-fixed bug: `group_ref` already contained `groups/6`, producing
  `groups/groups/6`). For a compound association endpoint like
  `/groups/{groupRef}/roles/{roleRef}`, concatenate the two full refs
  directly — `"%s/%s" % (group_ref, role_ref)` naturally produces
  `groups/6/roles/31`, matching the path exactly.
- The `objType` field on association objects (`{"ref": ..., "objType":
  ..., "name": ...}` used when adding/removing group/role/user
  membership) must be the *singular* `ObjectType` enum value (`Group`,
  `Role`, `User`, `DNSZone`, ...), never the plural resource-collection
  name (`Groups`, `Roles`, `Users`) — a mismatch here silently breaks
  membership-diff comparisons rather than erroring.
- Custom properties (and, for `PUT`/update calls generally, the
  `properties` field) are a flat `{name: value}` map in the request
  body, not the old `[{"name": x, "value": y}, ...]` array shape. But
  every custom property value comes back from a `GET` as a **string**
  regardless of its declared type (confirmed for Boolean and Integer,
  not just the obvious String case) — code comparing a requested native
  Python value against a fetched value for idempotency must normalize
  for this or it will report false changes forever. `ipprops.py`
  currently doesn't; see `tests/functional/test_ipprops.py`.
- Bump `version_added` in a module's `DOCUMENTATION`, the collection
  `version` in `galaxy.yml`, and add an entry to `CHANGELOG.md` together
  when releasing a change.
