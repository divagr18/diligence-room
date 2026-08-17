# Firestore Layout (BUILD_PLAN D1-M5)

Structured state lives in Firestore; the event log is the source of truth and
findings are materialized projections of it (vision §7.3 Memory Implementation).
This spec is the contract for `registry/store.py` (D2-M3) and the Day-3 memory
partitions (D3-M3).

## Collections

### `deals/{deal_id}` — Deal document (`runtime.deal.Deal`)

| Field | Type | Notes |
|---|---|---|
| deal_id | string | equals document id |
| name | string | e.g. `Project Falcon` |
| target | string | e.g. `Acme Robotics` |
| deal_type | string | `Acquisition` |
| regions | array\<string\> | e.g. `["US","EU"]` — drives region pinning (§7.8) |
| expected_window_days | int | |
| policy_profile_id | string | |
| status | string | `active` / `closed` / `aborted` |
| created_at | timestamp | |

### `deals/{deal_id}/findings/{finding_id}` — Finding (`memory.findings.Finding`)

| Field | Type | Notes |
|---|---|---|
| finding_id | string | equals document id |
| deal_id | string | denormalized for index queries |
| workstream | string | `legal` … `real_estate` |
| title / summary | string | |
| severity | string | informational/low/medium/high/critical |
| confidence | number | [0, 1] |
| status | string | candidate/validated/open/resolved/dismissed |
| evidence | array\<map\> | each: `{verbatim_span, document_id, chunk_ref}` — required non-empty (§19.2) |
| source_documents | array\<string\> | |
| related_findings | array\<string\> | finding ids |
| affected_entities | array\<string\> | |
| questions | array\<string\> | |
| owner | string | agent principal, e.g. `legal-agent@deal-falcon` |
| audit_trace_id | string \| null | Cloud Trace linkage (Day 10) |
| created_at / updated_at | timestamp | |

### `deals/{deal_id}/events/{event_id}` — append-only event log (Day 2/3)

Envelope `{event_id, deal_id, ts, seq, actor, type, payload_json}`. Writes are
append-only; `seq` is monotonic per deal (D3-M4). Immutable by convention and
later retention policy (§7.8). Documents also store `dedupe_key` — the
envelope's idempotency key for append deduplication (D6-M2).

### `deals/{deal_id}/gateway_policy/{rule_id}` — gateway policy rule (Day 5, D5-M1)

| Field | Type | Notes |
|---|---|---|
| rule_id | string | `{subject}->{target}`, e.g. `legal->finance` |
| subject_workstream / target_workstream | string | `Workstream` values |
| purposes | array\<string\> | allow-list; empty = no purpose grants |
| response_shape | string | `aggregate_only` / `none` |
| rate_limit | int | max ALLOWs per rolling hour; 0 = unlimited |

Deny-default: a missing rule denies (`NO_POLICY`). Seeded corridor: `legal->finance`
with purposes `revenue_concentration`, `change_of_control_exposure`,
`aggregate_only`, rate limit 10.

### `deals/{deal_id}/gateway_rate/{rule_id}` — rolling-hour rate counter (Day 5, D5-M3)

| Field | Type | Notes |
|---|---|---|
| window_start | string | ISO timestamp truncated to the hour |
| count | int | ALLOWs consumed in the window; transactional increment |

### `deals/{deal_id}/documents/{document_id}` — ingestion lineage (Day 4, D4-M6; Day 5, D5-M5)

| Field | Type | Notes |
|---|---|---|
| document_id / deal_id / logical_key | string | |
| checksum | string | sha256 of content |
| version | int | continues prior chains (`chains_from`, `link_supersedes`) |
| supersedes | string \| null | prior document id or logical key |
| ingested_at | string | ISO timestamp |
| status | string | `new` / `suppressed` / `new_version` |
| security_status | string \| absent | `quarantined` when blocked by the tripwire or armor screen (Day 7, D7-M3); absent when cleared |

### `deals/{deal_id}/quarantined/{document_id}` — quarantine record (Day 7, D7-M3)

Written when a document is blocked before routing (sentinel tripwire or armor
screen). Quarantined documents never reach agent context.

| Field | Type | Notes |
|---|---|---|
| deal_id / document_id | string | |
| checksum | string | sha256 of the blocked content |
| version | int | lineage version at block time |
| layer | string | `sentinel_tripwire` / `model_armor` |
| reason_codes | array\<string\> | sentinel patterns or armor reason codes |
| rule_ids | array\<string\> | project-rule ids (armor layer) |
| security_status | string | always `quarantined` |
| ts | string | ISO timestamp |

### `deals/{deal_id}/inbox/{finding_id}` — deal-lead inbox entry (Day 7, D7-M6)

Dashboard-readable notification written when a critical finding escalates
(vision §10). One entry per escalated finding, keyed by finding id.

| Field | Type | Notes |
|---|---|---|
| kind | string | `escalation` |
| finding_id / title / owner | string | |
| severity / workstream | string | `critical` / emitting workstream |
| message | string | deal-lead notification text |
| status | string | `open` |
| created_at | string | ISO timestamp |

### `agents/{agent_id}` — AgentManifest (`registry.models.AgentManifest`)

Physical path note: the registry module stores manifests in the top-level
`agents` collection (parallel to `deals/{deal_id}`). The earlier notation
`registry/agents/{agent_id}` is a 3-segment path, which Firestore treats as a
subcollection — documents require an even segment count — so the top-level
`agents` collection is the physical home for manifests.

| Field | Type | Notes |
|---|---|---|
| agent_id / name / version | string | current version |
| capabilities | array\<string\> | |
| owner / required_identity / policy_profile | string | |
| allowed_tools | array\<string\> | |
| supported_document_types | array\<string\> | |
| external_communication | string | always `prohibited` |
| approved | bool | |
| eval_score | number \| null | |
| deployment_status | string | `registered` / `deployed` / `deprecated` |
| rollback_target | string \| null | version string |
| known_limitations | string | |
| last_security_review | timestamp \| null | |
| created_at | timestamp | |

### `agents/{agent_id}/versions/{version}` — AgentVersion

| Field | Type |
|---|---|
| version / model_id / prompt_ref / changelog | string |
| approved | bool |
| eval_score | number \| null |
| rollback_target | string \| null |
| created_at | timestamp |

## Partition key mapping (Day 3 bridge)

Memory partition key `organization/deal/workstream` maps 1:1 onto these paths:
findings are always read/written under a single deal document scope and carry
an explicit `workstream` field; cross-workstream reads go through the Gateway,
never through a Firestore query (D3-M2 enforces, D3-M5 negative-tests).

## Required composite indexes

| Collection | Fields | Purpose |
|---|---|---|
| `findings` | `deal_id ASC, workstream ASC, status ASC, severity DESC` | workstream dashboards |
| `findings` | `deal_id ASC, status ASC, updated_at DESC` | open-items feed |
| `findings` | `deal_id ASC, severity DESC, confidence DESC` | escalation ordering (Day 8) |
| `events` | `deal_id ASC, seq ASC` | ordered replay / materialization |
| `agents` | `approved ASC, deployment_status ASC` | registry listing (D2-M5) |

Single-field indexes on `severity`, `status`, `workstream`, `approved` are
auto-created by Firestore.

## Workstream partitions (Day 3)

Memory Bank namespaces data per vision §7.3 as **organization/deal/workstream**.
The three-part key maps onto the Firestore document path

    deals/{deal_id}/workstreams/{ws}

where `{ws}` is a `Workstream` value (`legal`, `finance`, … `real_estate`).
Workstream-scoped data lives in the `items` subcollection beneath this document:

    deals/{deal_id}/workstreams/{ws}/items/{item_id}

The existing `findings` and `events` collections remain deal-scoped
(`deals/{deal_id}/findings/…`, `deals/{deal_id}/events/…`) and are not nested
under workstream partitions — cross-workstream queries route through the
Gateway policy engine, never through direct Firestore fan-out.
