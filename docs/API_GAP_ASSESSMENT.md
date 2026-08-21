# Micetro 26.1.0 API Gap Assessment

Assessment date: 2026-08-06. Compares the current `menandmice.ansible_micetro`
collection against the live Micetro 26.1.0 REST API
(`https://api.menandmice.com/26.1.0/`, OpenAPI spec at
`https://api.menandmice.com/26.1.0/swagger.json`) and SOAP API
(`https://api.menandmice.com/26.1.0/SOAP.html`).

## Headline finding: the collection targets a retired API generation

Every module builds URLs against a **legacy, unversioned, PascalCase** API
(`DNSZones`, `DHCPScopes`, `IPAMRecords`, `Users`, `Roles`,
`command/GetIPAMRecords`, `%s/1/PropertyDefinitions/%s`) using **HTTP Basic
Auth on every call**. The 26.1.0 spec documents a different generation:
versioned `/mmws/api/v2/...`, **camelCase** resources (`dnsZones`,
`dhcpScopes`, `ipamRecords`), a uniform `Bearer` session-token model
(`POST /micetro/sessions` → token), and object schemas that dropped the old
`properties: [{name, value}]` array in favor of typed fields plus a
`customProperties` map. Basic Auth isn't listed as a supported security
scheme in the current spec — only `Bearer token`.

This should be fixed before any new-feature work: it's not "some fields are
missing," it's "this collection may be speaking a dialect the server no
longer understands."

## 1. Deprecate / rewrite (broken or obsolete against current API)

| Item | Evidence | Why it needs to change |
|---|---|---|
| `module_utils/micetro.py: doapi()` — Basic Auth on every request | `force_basic_auth=True`, credentials on every call | v2 security scheme is `Bearer` session token only, via `POST /micetro/sessions`. Needs a session-token auth path (with re-login on expiry) instead of per-call Basic Auth. |
| Unversioned, PascalCase endpoint strings everywhere (`"DNSZones"`, `"Users"`, `"Roles"`, `"IPAMRecords/%s"`, `"DHCPScopes"`, `"Groups"`, `"DNSViews?..."`, `"DNSRecords"`) | Used in `zone.py`, `user.py`, `group.py`, `role.py`, `dnsrecord.py`, `dhcp.py`, `claimip.py`, `ipprops.py`, `lookup/ipinfo.py` | v2 paths are camelCase and versioned: `/dnsZones`, `/users`, `/roles`, `/ipamRecords/{addrRef}`, `/dhcpScopes`, `/groups`, `/dnsViews`, `/dnsRecords`. Every URL builder in the collection needs updating. |
| `inventory/inventory.py` — `url = "command/GetIPAMRecords"` (line ~274) | | There is **no `/command/*` namespace at all** in the v2 spec — a REST-over-SOAP-RPC shim from the old API, almost certainly gone. Must be rewritten to use `/ranges` + `/ranges/{rangeRef}/ipamRecords`. |
| `props.py` — `"%s/1/PropertyDefinitions/%s" % (DEST2URL[...], ...)` (lines ~236-317) | | v2 uses a uniform `/{resourceType}/{ref}/propertyDefinitions/{property}` sub-resource on every object type — no `/1/` segment. `DEST2URL` (`dnsserver`, `dhcpserver`, `zone`, `iprange`, `ipaddress`, `device`, `interface`, `cloudnet`, `cloudaccount`) is also missing several now-supported types (see §2). |
| `dhcp.py` — `from ansible.utils import unicode` (line ~21, used at ~241/266) | | `ansible.utils.unicode` doesn't exist in any Ansible release the collection claims to support (`requires_ansible: >=2.9.10`). **This module cannot import today.** Fix regardless of the API-version work. |
| `lookup/freeip.py` — `"%s/NextFreeAddress" % ref` (PascalCase, line ~200) | | v2 equivalent is `/ranges/{rangeRef}/nextFreeAddress` (camelCase). v2 also adds a scope-aware sibling, `/dhcpScopes/{ref}/nextFreeReservationAddress`, worth using when claiming for DHCP reservations. |
| Custom-property/body shape: `databody["properties"] = [{"name": x, "value": y}, ...]` | `zone.py`, `dhcpscope.py`, `group.py`, `role.py`, `user.py` | Confirmed against the `DHCPScope`/`DNSZone` v2 schemas: no `properties` array anymore. Built-in fields are plain object properties; custom properties are a dedicated `customProperties` map (`CustomPropertyMap`). Every module's request-body construction needs to change shape, not just endpoint. |
| `addressSpaces` concept (assumed flat/single IPAM) | Spec text: *"Gets organizations (deprecated, use GetOrganizations instead)"* | Multi-tenant model moved to `/organizations`. Nothing in the collection is organization-aware. |
| Minor inconsistency | `zone.py` mixes `"DNSZones"`/`"DNSViews"` (PascalCase, GET) with `"dnsZones"` (lowercase, POST at line ~326) | Looks like an abandoned partial migration already in the code — clean up as part of the rewrite. |

## 2. New capabilities in 26.1.0 with zero coverage today

**DHCP** (biggest expansion — today's `dhcp.py`/`dhcpscope.py` treat DHCP as
"scopes with inline options" only):
- DHCP Superscopes as real CRUD objects (`/dhcpSuperscopes`) — today's
  `dhcpscope.py` only takes a `superscope` name string.
- DHCP Groups, Address Pools, Exclusions as first-class sub-objects
  (`/dhcpGroups`, `/dhcpAddressPools`, `/dhcpExclusions`), each with their own
  options/property-definitions/access/history.
- DHCP failover relationships (`/dhcpServers/{ref}/failoverRelationships`) —
  no HA/failover support exists.
- DHCP policies + policy enforcement (`.../policies`,
  `.../policyEnforcement`).
- DHCP leases — get/add/release (`/dhcpScopes/{ref}/leases`) — only
  reservations are managed today, not live leases.
- DHCP class names / vendor & user classes / subclasses — no coverage.
- Reservations can be owned by a server, group, or scope in v2
  (`{ownerRef}/dhcpReservations`); `dhcp.py` only knows scope-owned
  reservations.

**DNS:**
- DNS Generate Directives (BIND `$GENERATE`-style) —
  `/dnsZones/{ref}/generateDirectives`.
- Zone/server-level Options (`/dnsZones/{ref}/options`,
  `/dnsServers/{ref}/options`) — `zone.py` only sets a handful of top-level
  fields.
- DNSSEC key storage providers (`/dnsZones/{ref}/keyStorageProviders`) — no
  DNSSEC support.
- Related-record linkage (A/AAAA ↔ PTR) via
  `/dnsRecords/{ref}/relatedDnsRecords`.
- Bulk record creation — `POST /dnsRecords` accepts an array; today's module
  is one-record-per-call.

**IPAM / Ranges:**
- Range statistics, address blocks, available address blocks, subranges
  (`/ranges/{ref}/statistics|addressBlocks|availableAddressBlocks|subranges`)
  — natural fit for an `_info` module.
- IPAM record ping (`POST /ipamRecords/{ref}/ping`) — no live-reachability
  check today.

**Governance / access control:**
- Change Requests / approval workflow (`/changeRequests`) — lets automation
  submit changes for human approval instead of applying directly. Likely the
  highest-value single addition for regulated environments.
- Per-object fine-grained ACLs — every resource type exposes
  `GET/PUT .../access`; no access-control management exists today.
- Per-object event history/audit — `.../history` on every type; no auditing
  module exists.

**Infrastructure objects with no representation:**
- Active Directory: `/adForests`, `/adSites`, `/adSiteLinks` (today `zone.py`
  only has flat `adintegrated`/`adpartition` booleans).
- Cloud: `/cloudNetworks`, `/cloudServiceAccounts` — Azure/AWS/NS1/Akamai
  account sync and VNet/VPC import as ranges. `props.py`'s `DEST2URL` already
  anticipates `cloudnet`/`cloudaccount` property-definition support, but no
  module manages the cloud objects themselves.
- Devices & Interfaces (`/devices`, `/interfaces`).
- Appliances (`/appliances`, `+supportInfo`).
- Folders (`/folders`) — hierarchical grouping for zones/scopes/ranges.
- Organizations (`/organizations`) — multi-tenant replacement for deprecated
  `addressSpaces`.
- Reporting (`/reportDefinitions`, `/reportSources`, `/reports` incl. file
  export).
- System/ops: `/micetro` (install info), `/micetro/licenseKeys`,
  `/micetro/logFiles`, `/micetro/systemSettings` — could back a
  `micetro_info`/`micetro_settings` module.

## Recommended sequencing

1. **Foundation fix** (blocking, no new features): rework
   `module_utils/micetro.py` for versioned camelCase paths + Bearer session
   auth, fix the `customProperties`/field-shape change, and port every
   existing module 1:1 to its current capability. This alone fixes the
   almost-certainly-broken current state and the dead `dhcp.py` import.
2. **Capability expansion** (net-new modules/lookups), roughly in priority
   order: Change Requests (approval workflow), DHCP object graph
   (superscopes/groups/pools/leases/failover/policies), Folders +
   Organizations, per-object access/history, then Cloud/AD/Devices/Reporting/
   System as lower-priority additions.
