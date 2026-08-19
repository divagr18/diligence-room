# Diligence Room — 14-Day Build Plan (Phase/Module Breakdown)
**Companion to `diligence-room-vision.md` (Rev. 2). All decisions locked 2026-08-14. Day 1 = Fri 2026-08-14 → Day 14 = Thu 2026-08-27.**

## 0. Constants

| | |
|---|---|
| Team | **A (Platform)**: runtime, gateway, identity, infra, deploy, observability, replay, compliance · **B (Fleet)**: agents, memory, armor rules, red-team, dataset, dashboard UI, content |
| Capacity | 6 h/person/day → 12 person-h/day → **168 person-h total** |
| Budget | $170 cloud cap; billing alerts at $85 / $136 / $170 |
| Stack | Python + Google ADK · Vertex AI Agent Engine · FastAPI · Firestore · Pub/Sub · Cloud Run · React (Vite/TS) frontend · OTel → Cloud Trace |

**How to read a day:** each day has **phases** (logical stages, roughly time-boxed). Each phase lists **modules** — atomic build units with an ID (`D3-M2`), owner, concrete deliverable (file/endpoint/test), dependencies, and hours. Every day ends with a **gate**: green → next day; red → apply that day's **If red** action. Never "catch up tomorrow".

**Repo module map** (modules reference these paths):

```
diligence-room/
├── infra/        bootstrap_gcp.py · deploy/ (agent_engine.py, cloud_run.py) · compliance_config/
├── registry/     models.py · store.py · api.py
├── runtime/      deal.py · events.py · runner.py · guards.py · checkpoint.py · replay.py · dlq.py
├── agents/       base_agent.py · tools/ · {legal,finance,hr,ip_tech,tax,regulatory,esg,real_estate}/(agent.py,prompts.py) · coordinator/ · negotiation/
├── memory/       partitions.py · event_log.py · findings.py
├── identity/     principals.py · authz.py · human_authz.py
├── gateway/      app.py · policy.py · decide.py · audit.py
├── ingestion/    pipeline.py · formats.py · parsing.py · sentinel.py · classifier.py · lineage.py
├── armor/        model_armor.py · rules.py · quarantine.py
├── compliance/   regions.py · dlpcfg.py
├── observability/ otel.py · trace_link.py
├── coordination/ scoring.py · escalation.py
├── redteam/      attacks/ (fixtures, 4 class folders) · runner.py · scorecard.py
├── dashboard/    api/ (FastAPI) · web/ (React: views Overview, Finding+Trace, Security, Registry)
├── data/         vantage_robotics/ (synthetic docs) · scenarios/project_falcon.json
├── evals/        golden_set.py · harness.py
└── tests/        test_isolation.py · test_evidence_gate.py · test_guards.py · ...
```

---

## Day 1 — Fri 08-14 · Foundation & deploy skeleton

**Objective:** one ADK agent running asynchronously on Vertex AI Agent Engine, from a reproducible repo, with cost alarms armed.
**Prereqs:** GCP accounts, billing available.

### Phase 1 — Accounts & repo foundations (h 0:00–2:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D1-M1 | GCP bootstrap script | A | `infra/bootstrap_gcp.py`: project verify, billing link, API enable list (Vertex AI, Agent Engine, Model Armor, Firestore, Cloud Run, Pub/Sub, Document AI, DLP, Cloud Trace, KMS), budget alerts via Billing API at $85/$136/$170 | — | 1.0 |
| D1-M2 | Org safety guardrails | A | disable SA key creation, enable Cloud Audit Logs (admin + data access for firestore/storage), org-policy notes in README | D1-M1 | 0.5 |
| D1-M3 | Repo skeleton | A | monorepo layout per module map; `pyproject.toml` (uv), ruff + mypy strict, pre-commit with secrets scan (gitleaks), branch protection, PR template | — | 0.5 |
| D1-M4 | Domain schemas | B | `registry/models.py` (AgentManifest, AgentVersion), `runtime/deal.py` (Deal), `memory/findings.py` (Finding per vision §9 incl. evidence[] contract) as typed dataclasses | — | 1.5 |
| D1-M5 | Firestore layout spec | B | `docs/firestore_layout.md`: `deals/{deal_id}`, `…/findings/{fid}`, `…/events/{eid}`, `registry/agents/{aid}`; indexes needed | D1-M4 | 0.5 |

**Phase exit:** bootstrap script runs clean on a fresh project; schemas pass mypy.

### Phase 2 — Managed-runtime spike (h 2:00–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D1-M6 | ADK hello agent | A | `agents/base_agent.py` v0: minimal ADK Agent on Gemini 3.5 Flash (verify exact Vertex model ID — record it in `docs/model_ids.md`), one echo tool | D1-M1 | 1.5 |
| D1-M7 | Agent Engine deploy + async invoke | A | `infra/deploy/agent_engine.py`: deploy agent, async session invoke test, response assertion; runbook line in README | D1-M6 | 1.5 |
| D1-M8 | Focus-area prompts ×4 | B | `agents/{legal,finance,hr,ip_tech}/prompts.py`: focus areas from vision §5 + JSON finding output contract matching D1-M4 | D1-M4 | 3.0 |

**Phase exit:** `python infra/deploy/agent_engine.py` → deployed agent answers async; prompt files load in agent constructors.

### Phase 3 — Gate (h 5:00–6:00)

- [ ] Re-run deploy from clean env (the Day-14 judge will do a cold clone; start that habit now)
- [ ] Billing alerts visible in Cloud Console (screenshot → `docs/evidence/`)
- [ ] Commit: schemas, bootstrap, deploy script

**If red:** Agent Engine friction → overnight decision: continue managed vs fallback Cloud Run jobs + Firestore memory (boundary-compatible; see risk register).

**Hours:** A 6.0 (M1 1.0 + M2 0.5 + M3 0.5 + M6 1.5 + M7 1.5 + gate 1.0) · B 6.0 (M4 1.5 + M5 0.5 + M8 3.0 + gate 1.0)

---

## Day 2 — Sat 08-15 · Registry + event pipeline

**Objective:** document upload → Pub/Sub event → agent consumes → Firestore state; registry serves 8 manifests.

### Phase 1 — Event bus backbone (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D2-M1 | Event schema + publisher | A | `runtime/events.py`: typed events (`document.ingested`, `finding.created`, `gateway.decision`, `security.event`), envelope `{event_id, deal_id, ts, actor, payload}`, publisher with dedupe key | D1-M1 | 1.5 |
| D2-M2 | Data-room buckets | A | regional Cloud Storage buckets (US + EU pair per vision §7.8), Pub/Sub notifications on object finalize, `docs/deal_provisioning.md` | D1-M1 | 1.0 |
| D2-M3 | Registry store | B | `registry/store.py`: Firestore-backed CRUD for manifests/versions incl. `rollback_target`, `approved`, `eval_score` | D1-M4 | 1.5 |
| D2-M4 | Dataset plan + first docs | B | `data/vantage_robotics/DATASET_PLAN.md` (full seed table from vision §26) + authored `contract_meridian_logistics.pdf` (CoC clause) + `financials_fy27.xlsx` (Customer X = 18.3%) | — | 1.0 |

**Phase exit:** `gcloud storage cp` fires a notification event; registry store unit tests green.

### Phase 2 — Registry API + gateway shell (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D2-M5 | Registry API | B | `registry/api.py` (FastAPI): `POST /agents`, `GET /agents`, `GET /agents/{id}/versions`, `PATCH /agents/{id}/approval`, rollback-target field; all 8 manifests seeded | D2-M3 | 1.5 |
| D2-M6 | Deal workspace + docs 3–4 draft | B | Deal "Project Falcon" record in Firestore; HR roster + IP/tech docs drafted (content finalized Day 4) | D1-M4 | 1.0 |
| D2-M7 | Gateway service shell | A | `gateway/app.py` (FastAPI) on Cloud Run via `infra/deploy/cloud_run.py`: `/healthz`, caller-identity header middleware, request logging | D1-M3 | 1.5 |
| D2-M8 | Audit writer | A | `gateway/audit.py`: append-only decision/event records to Firestore events collection | D2-M1 | 1.0 |

**Phase exit:** registry endpoints live (curl demo); gateway shell responds with caller identity captured.

### Phase 3 — Integration + gate (h 5:00–6:00)

- [ ] Upload D2-M4 contract → bucket notification → event published → hello agent consumes → deal-state doc written
- [ ] Registry lists all 8 agents with versions and approval fields
- [ ] Commit + push

**If red:** eventing flaky → switch ingestion trigger to Cloud Run job polling (keep Pub/Sub for agent-to-agent); record deviation.

**Hours:** A 6.0 (M1 1.5 + M2 1.0 + M7 1.5 + M8 1.0 + gate 1.0) · B 6.0 (M3 1.5 + M4 1.0 + M5 1.5 + M6 1.0 + gate 1.0)

---

## Day 3 — Sun 08-16 · Identity + memory partitions

**Objective:** provable isolation — Legal ⊬ Finance, Finance ⊬ HR — with logged denials; first real finding with resolvable evidence.

### Phase 1 — Identity plane (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D3-M1 | Agent principals | A | `identity/principals.py`: per-workstream service identities (`legal-agent@{deal}` …), manifest→identity binding; bootstrap extension provisions them | D1-M2 | 1.5 |
| D3-M2 | Agent→data AuthZ | A | `identity/authz.py`: `can(identity, action, resource)` evaluated against ACL matrix (vision §7.4); enforced in runtime dispatcher before any read; denials emit events | D3-M1, D2-M1 | 1.0 |
| D3-M3 | Memory partitions | B | `memory/partitions.py`: Memory Bank namespace = `org/deal/workstream`; identical partition key in Firestore; helper `get_partition(deal_id, workstream)` | D1-M5 | 2.5 |

**Phase exit:** identity exists per agent; unauthorized read raises typed `AuthzDenied` with event emitted.

### Phase 2 — Event log, findings writer, dataset (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D3-M4 | Append-only event log | A | `memory/event_log.py`: immutable writer, monotonic seq, read API; every D2-M1 event lands here | D2-M1 | 1.5 |
| D3-M5 | Negative isolation suite | A | `tests/test_isolation.py`: Legal⊬Finance, Finance⊬HR, HR⊬valuation, cross-deal read — each asserts denial + audit event; wired to CI | D3-M2 | 2.0 |
| D3-M6 | Findings writer v1 | B | `memory/findings.py`: create/update finding within partition; evidence list structurally required (enforcement logic Day 9) | D3-M3 | 1.5 |
| D3-M7 | Dataset: key-person | B | finalize HR doc (VP responsible for Customer X leaving in 60 days); verify 18.3% figure consistent across financials | D2-M4 | 1.0 |

**Phase exit:** isolation suite green in CI; findings writer creates a partitioned finding.

### Phase 3 — First real finding + gate (h 5:00–6:00)

- [ ] Legal agent processes `contract_meridian_logistics.pdf` → finding with **evidence span pointing at the CoC clause text**
- [ ] Negative tests demonstrated on camera (footage reusable for the video's isolation proof)

**If red:** partition leakage → stop all downstream work; isolation is keystone.

**Hours:** A 6.0 (M1 1.5 + M2 1.0 + M4 1.5 + M5 2.0) · B 6.0 (M3 2.5 + M6 1.5 + M7 1.0 + finding smoke 1.0)

---

## Day 4 — Mon 08-17 · Ingestion + Gemma sentinel

**Objective:** mixed bundle auto-routes end-to-end; Gemma sentinel visible in traces (bonus model locked).

### Phase 1 — Parse backbone (h 0:00–2:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D4-M1 | Format detection | A | `ingestion/formats.py`: MIME + structural sniff (native PDF / scanned / XLSX / DOCX / image / eml) | D2-M1 | 0.5 |
| D4-M2 | Document AI parsing | A | `ingestion/parsing.py`: OCR + text/table extraction wrappers; chunk extraction per doc class (vision §7.3 chunking) | D4-M1 | 1.5 |
| D4-M3 | Dataset: IP doc + contradiction pair | B | `tech_inventory.pdf` (Customer X subsystem on unsupported vendor component) + `vendor_agreement_2027.pdf`; amendment authored but held for Day 5 | D2-M4 | 2.0 |

**Phase exit:** all four format classes parse to text + metadata.

### Phase 2 — Sentinel + classification (h 2:00–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D4-M4 | **Gemma sentinel** | A | `ingestion/sentinel.py`: Gemma (Vertex endpoint or containerized on Cloud Run) doing (1) `pre_classify(doc)`, (2) `mark_pii_spans(doc)` → DLP routing hint, (3) `injection_tripwire(doc)`; decisions emitted as span attributes + events; Flash invoked only for cleared docs (cost gate) | D4-M2 | 3.0 |
| D4-M5 | Classifier/router | B | `ingestion/classifier.py`: Flash-based doc_type + workstream routing using sentinel hints; routing decision event | D4-M4 | 2.0 |
| D4-M6 | Lineage | B | `ingestion/lineage.py`: checksum + version chain (amendment links to original); duplicate suppression | D4-M2 | 1.0 |

**Phase exit:** sentinel spans appear in local trace run; classifier routes a labeled test set ≥90%.

### Phase 3 — Pipeline wiring + gate (h 5:00–6:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D4-M7 | Pipeline assembly | B | `ingestion/pipeline.py`: detect → parse → sentinel → classify → (PII? mark for DLP Day 11) → route event to workstream runtime | D4-M1…M6 | 1.0 |
| D4-M8 | Mixed-bundle test | Both | native PDF + scanned PDF + XLSX + DOCX → all route correctly; PII doc flagged; sentinel visible in Cloud Trace | D4-M7 | 1.0 each |

**Gate:** mixed bundle green; sentinel model labeled in traces.
**If red:** Gemma serving friction → hosted Gemma API call instead of endpoint; bonus still earned, decision documented.

**Hours:** A 6.0 (M1 0.5 + M2 1.5 + M4 3.0 + M8 1.0) · B 6.0 (M3 2.0 + M5 2.0 + M6 1.0 + M7 1.0)

---

## Day 5 — Tue 08-18 · Gateway policy engine

**Objective:** Legal asks Finance, gets 18.3% — governed; direct cross-workstream access denied and logged.

### Phase 1 — Policy model + protocol (h 0:00–2:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D5-M1 | Policy objects | A | `gateway/policy.py`: `PolicyRule {subject_workstream, target_workstream, purposes[], response_shape: aggregate_only \| none, rate_limit}`; Firestore-backed | D3-M1 | 1.5 |
| D5-M2 | Cross-workstream query protocol | B | `agents/tools/gateway_query.py`: tool `ask_agent(target_ws, question, purpose)`; message schema; Legal prompt hook: on CoC finding → ask Finance revenue share | D3-M6 | 2.0 |

**Phase exit:** policy rules load from Firestore; tool callable in agent sandbox.

### Phase 2 — Decision engine + finance tuning (h 2:00–4:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D5-M3 | Decide() | A | `gateway/decide.py`: evaluate request → ALLOW/DENY + machine-readable reason enum (`AGGREGATE_PERMITTED`, `RAW_MODEL_PROHIBITED`, `WORKSTREAM_BOUNDARY`, …); rate-limit counters | D5-M1 | 2.0 |
| D5-M4 | Aggregate enforcement | A | response filter: Finance returns scalar aggregates only; raw valuation/model artifacts never cross; unit test with extraction attempt | D5-M3 | 1.5 |
| D5-M5 | Finance tuning + amendment | B | Finance prompt tuned for revenue-concentration queries; `amendment_2030.pdf` authored and lineage-linked to D4-M3 exclusivity doc | D4-M3 | 2.5 |

**Phase exit:** decide() returns reasoned verdicts for 6 scripted requests (3 allow, 3 deny).

### Phase 3 — Governed E2E + gate (h 4:30–6:00)

- [ ] Legal CoC finding triggers `ask_agent(finance, …)` → Gateway **ALLOW** (`AGGREGATE_PERMITTED`) → `18.3%` recorded in finding context
- [ ] Scripted direct read of Finance workspace by Legal identity → **DENY** + audit event
- [ ] Debug listing shows both decisions (seeds Security view)

**If red:** protocol mismatch → hardcode Legal→Finance corridor tonight; generalize Day 8.

**Hours:** A 6.0 (M1 1.5 + M3 2.0 + M4 1.5 + gate 1.0) · B 6.0 (M2 2.0 + M5 2.5 + gate 1.0 + buffer 0.5)

---

## Day 6 — Wed 08-19 · Fleet-out + runtime hardening ⚠ (Checkpoint-1 eve)

**Objective:** all 8 agents registered; deep four produce independent findings; runtime survives malformed events.

### Phase 1 — Scaffolding + reliability (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D6-M1 | Agent factory | B | `agents/base_agent.py` v1: instantiate ADK agent from manifest — identity binding, memory partition, tool set (`data-room-read` scoped, `finding-create`, `gateway-query`), model config, output contract | D5-M2 | 1.5 |
| D6-M2 | Retry + idempotency | A | `runtime/runner.py`: dispatch with retry/backoff, idempotency key = event hash, bounded attempts | D3-M4 | 1.5 |
| D6-M3 | Dead-letter queue | A | `runtime/dlq.py`: DLQ topic after max retries, redrive script, DLQ event type | D6-M2 | 1.0 |

**Phase exit:** factory spins up 2 different agents from manifests; retry/idempotency unit tests green.

### Phase 2 — Fleet online (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D6-M4 | Deep three online | B | Finance, HR, IP/Tech agents via factory against seeded docs; each writes ≥1 real finding | D6-M1 | 2.0 |
| D6-M5 | Four scaffolds | B | Tax, Regulatory, ESG, Real Estate: manifest + focus prompt + seed doc each + registered | D6-M1 | 1.5 |
| D6-M6 | Malicious batch #1 | A | `redteam/attacks/injection/` ×2, `/exfiltration/` ×2, `/injection/obfuscated/` ×1 fixtures + `expected.yaml` (expected: quarantined, reason) | D4-M7 | 1.5 |
| D6-M7 | Failure drill | A | push malformed doc event → DLQ catch → no crash, no partial state | D6-M3 | 1.0 |

**Phase exit:** 8 agents registered; DLQ drill green.

### Phase 3 — Gate + evidence (h 5:00–6:00)

- [ ] Deep four: independent findings present in their partitions
- [ ] Capture evidence artifacts for Checkpoint 1 → `docs/evidence/cp1/`

**If red:** proceed to Checkpoint 1 decisions first thing Day 7 — no delay.

**Hours:** A 6.0 (M2 1.5 + M3 1.0 + M6 1.5 + M7 1.0 + gate 1.0) · B 6.0 (M1 1.5 + M4 2.0 + M5 1.5 + gate 1.0)

---

## Day 7 — Thu 08-20 · ⚠ CHECKPOINT 1 + Model Armor

**Objective:** poisoned documents never reach agent context; red-team runner exists; escalation fires on critical.

### Phase 0 — Checkpoint 1 (h 0:00–1:00, both)

| ID | Module | Owner | Deliverable | h |
|---|---|---|---|---|
| D7-M0 | CP1 decision | Both | Review Day-6 gate evidence against checklist → `docs/decisions/cp1.md`: GO as planned / portfolio→roadmap / agents 5–8→scaffolding parity | 0.5 each |

### Phase 1 — Armor core (h 1:00–3:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D7-M1 | Model Armor client | A | `armor/model_armor.py`: template config (prompt-injection, exfiltration detectors), `sanitize(text)` wrapper, latency/cost logging | D1-M1 | 1.5 |
| D7-M2 | Project rules | A | `armor/rules.py`: custom layer — mailto/link exfil patterns, fake-authority claims, cross-workstream mutating verbs, "ignore previous instructions" variants | D7-M1 | 1.0 |
| D7-M3 | Quarantine store | B | `armor/quarantine.py`: quarantined-doc collection (never routed to runtime), doc status update, `security.event` emission | D2-M1 | 1.5 |

**Phase exit:** one poisoned fixture quarantined with reason codes.

### Phase 2 — Red-team v1 + escalation (h 3:30–5:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D7-M4 | Red-team runner v0 | B | `redteam/runner.py`: feed fixture doc through ingestion → assert result vs `expected.yaml` → result row | D7-M3 | 1.5 |
| D7-M5 | Attack ledger: 5 new | B | authority-forgery ×1 (injection), state-mutation ×1 (cross-workstream), privilege-escalation ×1 (cross-workstream), tool-poisoning ×1, cross-deal probe ×1 → ledger 10 (injection 4, exfil 2, cross-ws 2, poison/cross-deal 2) | D7-M4 | 1.5 |
| D7-M6 | Escalation path | A | `coordination/escalation.py`: critical finding → deal-lead notification event + dashboard-readable inbox entry | D3-M6 | 1.5 |

**Phase exit:** runner produces pass/fail rows for all 10 fixtures.

### Phase 3 — Batch verification + gate (h 5:30–6:00)

- [ ] All malicious batch #1 quarantined **before** agent context; security events on feed
- [ ] Escalation event fires for a forced critical finding

**If red:** Armor API friction → custom-rules-only screening tonight; API retry Day 8 first task.

**Hours:** A 6.0 (CP1 0.5 + M1 1.5 + M2 1.0 + M6 1.5 + batch verify 1.5) · B 6.0 (CP1 0.5 + M3 1.5 + M4 1.5 + M5 1.5 + gate 1.0)

---

## Day 8 — Fri 08-21 · Coordinator + red-flag engine

> **Progress note (pulled forward, end of Day 7):** D8-M4 dashboard backend APIs
> (read-only demo data plane, `b9e85f7`) and D11-M1 + D11-M4..M7 web shell (four
> views; Deal Room Ledger design contract + executable contract QA) were delivered
> early. The document viewer (vision §15.2 — finding evidence opens the served
> source at the located PDF page / XLSX sheet+row) was delivered in the Day-7
> finalise (`a02eb0a`, `130fb1a`, `dc68a23`; receipt `docs/evidence/finalise-day7.txt`).
> D8-M1..M3 plus D8-M4 role filtering are built below.

**Objective:** the **keystone** — CRITICAL finding emerges *only* from multi-agent synthesis; dashboard APIs serve it.

### Phase 1 — Scoring + human AuthZ (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D8-M1 | Red-flag scoring | B | `coordination/scoring.py`: severity × confidence × financial exposure × affected-workstreams × unresolved-duration → score + level + rationale; deterministic, unit-tested | D7-M6 | 2.5 |
| D8-M2 | Human→agent-output AuthZ | A | `identity/human_authz.py`: roles (deal_lead, junior_legal, outside_counsel, hr_analyst) → visibility matrix; filter middleware for dashboard API | D3-M2 | 2.5 |

**Phase exit:** scoring unit tests green; role filter demo (junior_legal sees Legal findings, not valuation).

### Phase 2 — Keystone synthesis + APIs (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D8-M3 | Coordinator agent | B | `agents/coordinator/`: consumes multi-workstream findings → combined finding CRITICAL-001 (Customer X: contract × revenue × key-person × tech) with links to all contributors | D8-M1 | 2.5 |
| D8-M4 | Dashboard backend APIs | A | `dashboard/api/`: `GET /deals/{id}/summary`, `/findings`, `/findings/{fid}` (evidence + audit_trace_id + contributors), `/security/events`, role-filtered via D8-M2 | D8-M2 | 2.5 |

**Phase exit:** CRITICAL-001 exists with 4 contributor links; APIs return it complete.

### Phase 3 — Keystone E2E + gate (h 5:00–6:00)

- [ ] Replay seeded chain: Legal CoC → gateway 18.3% → HR key-person → IP/Tech risk → Coordinator CRITICAL-001 → escalation
- [ ] Verify: removing any single workstream input prevents the CRITICAL synthesis (proof it's not a single-agent result)
- [ ] APIs return complete finding payload with all links

**If red:** synthesis weak → tighten coordinator prompt tonight only; scoring stays deterministic. Keystone is never de-scoped.

**Hours:** A 6.0 (M2 2.5 + M4 2.5 + gate 1.0) · B 6.0 (M1 2.5 + M3 2.5 + gate 1.0)

---

## Day 9 — Sat 08-22 · Failure tolerance ✂ CUTLINE-1

**Objective:** loop guard, evidence gate, crash-resume all demonstrable — the architectural-discipline answer. CUTLINE-1 ruling at hour 4.

### Phase 1 — Guards & evidence gate (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D9-M1 | Loop guard | A | `runtime/guards.py`: max iterations, tool-call budget, wall-clock + token budgets per run; on trip → checkpoint + terminate + `run_bounds_exceeded` event; `tests/test_guards.py` with runaway-prompt fixture | D6-M2 | 2.5 |
| D9-M2 | Evidence gate | B | `memory/findings.py` enforcement: each evidence span must resolve to a parsed chunk (span lookup at write time); failure → reject with `evidence_unresolvable` + event; confidence < threshold caps status at `candidate`; `tests/test_evidence_gate.py` with fabricated citations | D4-M2 | 2.5 |

**Phase exit:** guard trips on runaway fixture; fabricated citation rejected.

### Phase 2 — Crash-resume + negotiation start (h 2:30–4:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D9-M3 | Crash-resume | A | `runtime/checkpoint.py`: state transitions to event log; kill mid-run → restart → complete without duplicate findings (idempotency asserted in test) | D9-M1, D3-M4 | 1.5 |
| D9-M4 | Negotiation core | B | `agents/negotiation/`: draft generator from critical finding + approval state machine (`draft → pending_approval → approved → send_logged`) | D8-M3 | 1.5 |

**Phase exit:** kill-resume test green; negotiation draft generated from CRITICAL-001.

### Phase 3 — ✂ CUTLINE-1 ruling (h 4:00–4:30, both)

| ID | Module | Owner | Deliverable | h |
|---|---|---|---|---|
| D9-M5 | Cutline ruling | Both | D9-M1..M4 green by hour 4? → Negotiation full spec (redlines, seller requests, counterparty questions). Red → stays minimal (draft + approve + logged send). Record `docs/decisions/cutline1.md` | 0.5 each |

### Phase 4 — Gate (h 4:30–6:00)

- [ ] Runaway prompt trips loop guard; event visible in feed
- [ ] Fabricated citation rejected by evidence gate
- [ ] Kill mid-run → resume → same deal state, zero duplicates
- [ ] Approval state machine transitions logged

**If red:** CP2 effectively moves up; freeze scope now, spend Day 10 closing gaps.

**Hours:** A 6.0 (M1 2.5 + M3 1.5 + ruling 0.5 + gate polish 1.5) · B 6.0 (M2 2.5 + M4 1.5 + ruling 0.5 + gate polish 1.5)

---

## Day 10 — Sun 08-23 · Observability

**Objective:** any finding traceable source-doc → … → finding in Cloud Trace + dashboard data model.

### Phase 1 — Tracer backbone (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D10-M1 | OTel core | A | `observability/otel.py`: OTel SDK, OTLP → Cloud Trace exporter, service names per component | D1-M1 | 1.5 |
| D10-M2 | Stage instrumentation | A | spans with GenAI semantic-convention attributes (`gen_ai.*`) across ingestion, sentinel, armor, agent runs, gateway decisions | D10-M1 | 1.0 |
| D10-M3 | Trace-view data model | B | `dashboard/api` serializer: finding graph (docs → agents → gateway requests → finding) for the Finding+Trace view | D8-M4 | 2.5 |

**Phase exit:** spans from one document flow visible in Cloud Trace.

### Phase 2 — Trace linking + attack wave 2 (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D10-M4 | Finding ↔ trace link | A | `observability/trace_link.py`: `audit_trace_id` resolves to Cloud Trace; span links from ingestion span to finding span | D10-M2 | 2.5 |
| D10-M5 | Malicious batch #2 + noise | B | injection variants ×2, exfiltration variant ×1, privilege-escalation ×1 in `redteam/attacks/` with `expected.yaml` → ledger 14 (injection 6, exfil 3, cross-ws 3, poison/cross-deal 2); noise docs ×3 (email export, scan, junk spreadsheet) for dataset realism | D7-M4 | 2.5 |

**Phase exit:** CRITICAL-001's `audit_trace_id` resolves; batch #2 fixtures run.

### Phase 3 — Gate (h 5:00–6:00)

- [ ] Open CRITICAL-001 → walk full span chain in Cloud Trace AND in trace-view payload
- [ ] Attack ledger at 14 with expected results

**If red:** trace gaps → add missing span wrappers only; never fake a trace.

**Hours:** A 6.0 (M1 1.5 + M2 1.0 + M4 2.5 + gate 1.0) · B 6.0 (M3 2.5 + M5 2.5 + gate 1.0)

---

## Day 11 — Mon 08-24 · Dashboard + compliance plane

**Objective:** 4 views live on Cloud Run; CMEK/VPC-SC/DLP/region controls demonstrable in Cloud Console.

### Phase 1 — Shell + compliance foundation (h 0:00–2:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D11-M1 | Web shell | B | `dashboard/web/` (Vite React+TS): routing for 4 views, API client, Cloud Run deploy via `infra/deploy/cloud_run.py`, auth stub | D8-M4 | 1.5 |
| D11-M2 | Region verification | A | `compliance/regions.py`: assert buckets/Firestore/Cloud Run locations match deal's declared regions; report output | D2-M2 | 1.0 |
| D11-M3 | CMEK | A | Cloud KMS keyrings per region; Firestore + Storage CMEK applied via `infra/compliance_config/`; verify key-access entries in Cloud Audit Logs | D1-M2 | 1.0 |

**Phase exit:** deployed dashboard serves shell views; KMS keys visible.

### Phase 2 — Views + controls (h 2:00–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D11-M4 | Overview view | B | deal health, counters, workstream progress bars, agents active, security counter | D11-M1 | 1.0 |
| D11-M5 | Finding+Trace view | B | finding list → detail drawer: evidence spans w/ source links, contributors, confidence, trace timeline from D10-M3 | D11-M1 | 1.75 |
| D11-M6 | Security view | B | quarantines, denials, gateway decisions, red-team scorecard slot (data Day 12) | D11-M1 | 0.75 |
| D11-M7 | Registry view | B | agents, versions, approval badges, upgrade/rollback buttons → registry API | D11-M1 | 0.75 |
| D11-M8 | VPC-SC | A | service perimeter around Agent Engine/Vertex, Storage, Firestore, Memory Bank; egress rules; violation attempt logged | D11-M3 | 1.5 |
| D11-M9 | DLP on HR path | A | `compliance/dlpcfg.py`: inspection template, trigger on PII-flagged docs (sentinel hint from D4-M4), redact/tokenize before agent context; HR doc demo | D4-M4 | 1.5 |

**Phase exit:** all 4 views render real data; VPC-SC violation test logged.

### Phase 3 — Console footage + gate (h 5:00–6:00)

- [ ] Every demo beat reproducible on deployed dashboard URL
- [ ] Record Cloud Console footage: CMEK keys, VPC-SC perimeter, DLP job, region fields → `docs/evidence/deployment/` (this IS the video's deployment-proof material)

**If red:** view incomplete → Registry view degrades to read-only table first; never cut Finding+Trace.

**Hours:** A 6.0 (M2 1.0 + M3 1.0 + M8 1.5 + M9 1.5 + footage 1.0) · B 6.0 (M1 1.5 + M4 1.0 + M5 1.75 + M6 0.75 + M7 0.75 + gate 0.25)

---

## Day 12 — Tue 08-25 · Versioning + Red-Team suite ⚠ CHECKPOINT 2 (hard)

**Objective:** upgrade→regression→rollback with memory intact; 20/4 scorecard live; approval beat end-to-end. Then: freeze.

### Phase 1 — Golden set + attack wave 3 (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D12-M1 | Golden set | A | `evals/golden_set.py`: ~20 pinned docs + expected findings (incl. known CoC clause pattern) | D4-M7 | 1.0 |
| D12-M2 | Shadow harness | A | `evals/harness.py`: run candidate agent version over golden set, diff findings vs baseline → regression report | D12-M1 | 1.5 |
| D12-M3 | Attack wave 3 (complete 20) | B | +injection ×2, +exfiltration ×2, +cross-workstream ×1, +poisoning ×1 (6 new fixtures + expected.yaml) → **final ledger 20 = injection ×8, exfiltration ×5, cross-workstream ×4, tool-poisoning/cross-deal ×3** | D10-M5 | 2.5 |

**Phase exit:** harness flags a deliberately broken agent version; ledger = 20.

### Phase 2 — Rollback + scorecard (h 2:30–4:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D12-M4 | Upgrade + rollback | A | publish Legal v2.5 (deliberate CoC-prompt regression) → shadow eval RED → rollback via registry API (`rollback_target`) → runtime reconnects same memory; Registry view reflects state | D12-M2 | 2.0 |
| D12-M5 | Scorecard | B | `redteam/scorecard.py`: aggregate runner results per class → Security view (honest numbers, shown as-is) | D12-M3 | 1.0 |
| D12-M6 | Negotiation completion | B | per CUTLINE-1 ruling: full spec (redlines/seller requests/counterparty questions) or minimal; dashboard approve button → `send_logged` event | D9-M4 | 1.0 |

**Phase exit:** rollback preserves memory (finding counts identical before/after); approval beat works.

### Phase 3 — ⚠ CHECKPOINT 2 (h 4:30–5:15, both)

| ID | Module | Owner | Deliverable | h |
|---|---|---|---|---|
| D12-M7 | Keystone audit | Both | Verify keystone set item-by-item (Customer X finding · quarantine beat · DENY beat · isolation tests · evidence gate + loop guard · deployment proof). ANY red → **hard feature freeze**: Days 13–14 = polish + recording only. Record `docs/decisions/cp2.md` | 0.5 each |

### Phase 4 — Gate (h 5:15–6:00)

- [ ] Rollback demo repeatable twice
- [ ] Scorecard renders 20-attack results
- [ ] Approval beat: draft → human approve → logged send, visible in Finding view and event log

**If red:** freeze already triggered by CP2; fix only what blocks the video.

**Hours:** A 6.0 (M1 1.0 + M2 1.5 + M4 2.0 + CP2 0.5 + gate 1.0) · B 6.0 (M3 2.5 + M5 1.0 + M6 1.0 + CP2 0.5 + gate 1.0)

---

## Day 13 — Wed 08-26 · Replay + rehearsals + content

**Objective:** the 14-day scenario runs deterministically in ≤4 min on deployed infra; blog live; README + diagram done.

### Phase 1 — Replay runner (h 0:00–2:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D13-M1 | Scenario file | A | `data/scenarios/project_falcon.json`: timestamped event timeline Days 1–14 (uploads, findings, attacks, amendment, upgrade/rollback) mirroring vision §16 | D4-M7 | 1.5 |
| D13-M2 | Replay engine | A | `runtime/replay.py`: inject scenario at accelerated clock into the real pipeline (all processing genuine); deterministic seed; run_id stamped into traces | D13-M1 | 1.0 |
| D13-M3 | Blog post | B | public post (dev.to/Medium): architecture, the twist, what broke, hackathon-purpose language (required for +0.2); URL saved to `docs/submission.md` | — | 2.5 |

**Phase exit:** one complete replay run finishes < 4 min wall-clock.

### Phase 2 — Rehearsals + docs (h 2:30–5:00)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D13-M4 | Dress rehearsals ×3 | A | timed runs vs vision §17 beat table; fix ONLY blocking issues; `docs/timing_sheet.md` locked (beat → seconds) | D13-M2 | 2.5 |
| D13-M5 | Architecture diagram | B | Excalidraw/Mermaid render of vision §22 (not ASCII) → README + video asset | D11-M5 | 1.0 |
| D13-M6 | README v1 | B | overview, diagram, quickstart (bootstrap script), credentials, stack table, license, evaluation section pointing at `evals/` | D13-M5 | 1.5 |

**Phase exit:** timing sheet locked; README renders cleanly.

### Phase 3 — Gate (h 5:00–6:00)

- [ ] Full scenario ≤ 4:00, deterministic across 2 consecutive runs
- [ ] Gemma sentinel verified live (bonus item checked): spans present + cost-reduction number captured for README
- [ ] Blog URL public/indexable (not unlisted)

**If red:** timing overrun → trim beat-5 narration (upgrade/rollback), keep the visual.

**Hours:** A 6.0 (M1 1.5 + M2 1.0 + M4 2.5 + gate 1.0) · B 6.0 (M3 2.5 + M5 1.0 + M6 1.5 + gate 1.0)

---

## Day 14 — Thu 08-27 · Record + submit

**Objective:** video captured, submission airtight, submitted before deadline.

### Phase 1 — Recording (h 0:00–4:00, B-led)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D14-M1 | Video recording | B | 4-min video per timing sheet: 30 s friction+twist open → beats 1–7; replay segment recorded as ONE unedited take (terminal + dashboard side by side); deployment footage from D11 evidence | D13-M4 | 3.5 |
| D14-M2 | Submission checklist run | A | repo public · license · gitleaks secrets scan clean · clean-clone reproducible setup verified · deployment proof present · video link · form answers mapped to the three weighted criteria + bonus items | D13-M6 | 3.5 |

**Phase exit:** video exported; checklist fully green.

### Phase 2 — Publish + closeout (h 4:00–5:30)

| ID | Module | Owner | Deliverable | Deps | h |
|---|---|---|---|---|---|
| D14-M3 | Social post | B | X/LinkedIn post: project highlight + video/blog links + `#AllThingsAgenticHackathon` (required) | D14-M1 | 1.0 |
| D14-M4 | Cost report + teardown | A | actual spend table (vs $60–120 estimate) in README appendix; tear down non-essential endpoints; keep demo env alive through judging | D14-M2 | 1.5 |

**Phase exit:** post published; idle endpoints down.

### Phase 3 — Final review + submit (h 5:30–6:00, both)

- [ ] Watch video once, end-to-end, as a judge: friction stated? twist stated? keystone visible? deployment proven?
- [ ] Submit form; save confirmation.

**Hours:** A 6.0 (M2 3.5 + M4 1.5 + review 1.0) · B 6.0 (M1 3.5 + M3 1.0 + review 1.0 + buffer 0.5)

---

# Cutline & budget summary

## Cutline table

| Cutline | When | Trigger | Effect |
|---|---|---|---|
| Checkpoint 1 | Day 7 AM | Day-6 gate red | Portfolio → roadmap; agents 5–8 → scaffolding parity |
| CUTLINE-1 | Day 9 h4 | Guards/evidence-gate/crash-resume red | Negotiation Agent → minimal (draft + approve + logged send) |
| Checkpoint 2 | Day 12 h4:30 | Any keystone item red | Hard feature freeze; polish + record only |

**Keystone set (never cut):** Customer X cross-workstream finding · Model Armor quarantine beat · Identity DENY beat · memory-isolation negative tests · evidence gate + loop guard · deployment proof.

## Attack ledger progression (20 attacks / 4 classes)

| Day | Added | Cumulative (injection / exfil / cross-ws / poison·cross-deal) | Total |
|---|---|---|---|
| 6 | injection ×2, exfil ×2, obfuscated-injection ×1 | 3 / 2 / 0 / 0 | 5 |
| 7 | authority-forgery ×1, state-mutation ×1, priv-esc ×1, tool-poisoning ×1, cross-deal probe ×1 | 4 / 2 / 2 / 2 | 10 |
| 10 | injection ×2, exfil ×1, priv-esc ×1 | 6 / 3 / 3 / 2 | 14 |
| 12 | injection ×2, exfil ×2, cross-ws ×1, poisoning ×1 | **8 / 5 / 4 / 3** | 20 |

## Bonus points tracker (+0.6 committed)

| Item | Points | Built | Verified |
|---|---|---|---|
| Gemma ingestion sentinel | +0.2 | Day 4 (D4-M4) | Day 13 gate |
| Blog post (public, hackathon language) | +0.2 | Day 13 (D13-M3) | Day 13 gate |
| Social post + hashtag | +0.2 | Day 14 (D14-M3) | submit-time check |

## Cost guardrails ($170)

- Billing alerts $85 / $136 / $170 (D1-M1). Event/replay-triggered execution only — no 24/7 polling.
- Gemma sentinel gates Flash usage (cheap model first). Batched eval windows.
- Teardown idle endpoints after recording (D14-M4).
- Projected $60–120; actuals reported in README appendix.

## Risk register (top 5)

| Risk | Likelihood | Mitigation |
|---|---|---|
| Feature-parity ambition exceeds velocity | High | Cutline table pre-agreed; keystone protected; CP1 forces honesty Day 7 |
| Managed Agent Engine/Memory Bank API friction | Medium | Day-1 spike gates the decision; fallback Cloud Run jobs + Firestore memory is boundary-compatible |
| Video overrun/flakiness | Medium | Replay = deterministic; timing sheet locked Day 13; beat 2 = single continuous take |
| Cost overrun | Low | Alerts + triggered execution + Flash-only + projected headroom |
| Dashboard bottleneck (B overloaded Day 11) | Medium | Day-8 APIs pre-built; Registry view degrades to read-only first; A absorbs overflow |
