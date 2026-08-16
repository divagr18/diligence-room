# Diligence Room

**A zero-trust runtime for autonomous institutional agent fleets, demonstrated through M&A due diligence.**

> Documents are adversaries, agents are principals, and memory is partitioned by policy — not convenience.

Built for the **AllThingsAgentic Hackathon** (Fortified Enterprise Fleet track) on the Google Gemini Enterprise Agent Platform: Python + Google ADK, Vertex AI Agent Engine, Gemini 3.5 Flash, Firestore, Pub/Sub, Cloud Run, Model Armor, Cloud Trace.

- Specification: [`diligence-room-vision.md`](diligence-room-vision.md)
- Day-by-day build plan: [`BUILD_PLAN.md`](BUILD_PLAN.md)

## Repository layout

```
diligence-room/
├── infra/          GCP bootstrap, deployment scripts, compliance config
├── registry/       Agent Registry (manifests, versions, approval, rollback)
├── runtime/        Deal runtime (events, guards, checkpoints, replay, DLQ)
├── agents/         ADK agent fleet (8 workstreams + coordinator + negotiation)
├── memory/         Partitioned memory (org/deal/workstream), event log, findings
├── identity/       Zero-trust agent principals + agent→data / human→output AuthZ
├── gateway/        Agent Gateway policy engine (the build-not-buy)
├── ingestion/      Format detection → parsing → Gemma sentinel → classification
├── armor/          Model Armor client, project rules, quarantine store
├── compliance/     Region pinning, DLP config
├── observability/  OTel GenAI semantic conventions → Cloud Trace
├── coordination/   Red-flag scoring, escalation
├── redteam/        20-attack red-team suite + scorecard
├── dashboard/      FastAPI backend + React frontend (4 views)
├── data/           Synthetic Acme Robotics dataset + replay scenarios
├── evals/          Golden set + shadow evaluation harness
└── tests/          Isolation, evidence-gate, guards, and unit tests
```

## Quickstart

```bash
# 1. Install dependencies (Python 3.11, uv)
uv sync

# 2. Bootstrap the GCP project (project create, billing link, APIs,
#    staging bucket, budget alerts at $85/$136/$170)
uv run python infra/bootstrap_gcp.py

# 3. Apply org-safety guardrails (audit logs, SA-key policy)
uv run python infra/guardrails.py

# 4. Deploy the ADK agent to Vertex AI Agent Engine and invoke it asynchronously
uv run python infra/deploy/agent_engine.py deploy
uv run python infra/deploy/agent_engine.py invoke
```

Credentials: the scripts use **Application Default Credentials** —

```bash
gcloud auth login
gcloud auth application-default login
```

(No service-account keys are ever created — see *Security posture* below.)

## Runbook (Day 1)

| Step | Command | Expected |
|---|---|---|
| Environment check | `uv sync` | lock resolves, deps install (dev group included by default) |
| Lint/type gate | `uv run pre-commit run --all-files` | all hooks pass |
| GCP bootstrap | `uv run python infra/bootstrap_gcp.py` | APIs enabled, budgets listed |
| Guardrails | `uv run python infra/guardrails.py` | auditConfigs applied |
| Deploy | `uv run python infra/deploy/agent_engine.py deploy` | reasoningEngines resource name printed |
| Async invoke | `uv run python infra/deploy/agent_engine.py invoke` | asserted response from deployed agent |

## Runbook (Day 2 — offline against the Firestore emulator)

| Step | Command | Expected |
|---|---|---|
| Event bus + audit + store tests | `uv run pytest tests/test_events.py tests/test_gateway_audit.py tests/test_registry_store.py` | green against local emulator |
| Registry seed + API | `uv run pytest tests/test_registry_api.py` | 8-agent seed, approval PATCH, 409/404/422 |
| Dataset artifacts | `uv run python scripts/author_dataset.py` | deterministic PDF/XLSX artifacts regenerated |
| Data-room plan (dry run) | `uv run python infra/data_room.py --deal-id deal-falcon --project-number 910285417505 --dry-run` | prints full gcloud plan, executes nothing |
| Gateway shell | `uv run pytest tests/test_gateway_app.py tests/test_cloud_run_plan.py` | healthz/whoami/caller capture + write-only deploy gate |
| **Offline gate (S8)** | `uv run pytest tests/test_e2e_offline.py` | full chain green; see `docs/deal_provisioning.md` |

The live runbook (bucket creation, Cloud Run deploy, verification curls) is
in [`docs/deal_provisioning.md`](docs/deal_provisioning.md) and is guarded by
`--confirm-live` on every deploy script.

## Runbook (Day 4 — ingestion + Gemma sentinel, offline)

| Step | Command | Expected |
|---|---|---|
| Format detection | `uv run pytest tests/test_formats.py` | native/scanned PDF, XLSX, DOCX, EML, image sniffed structurally |
| Parse + chunk | `uv run pytest tests/test_parsing.py tests/test_chunking.py` | text + tables + clause locators; scans honest (`text=None`, `needs_ocr`) |
| Lineage | `uv run pytest tests/test_lineage.py` | sha256 NEW / SUPPRESSED / NEW_VERSION against the emulator |
| Sentinel + cost gate | `uv run pytest tests/test_sentinel.py` | tripwire short-circuits before downstream calls; `FakeSentinel` offline |
| Router | `uv run pytest tests/test_classifier.py` | labeled set ≥ 90% accuracy; junk/injection never route |
| Tracing | `uv run pytest tests/test_tracing.py` | sentinel span labeled `gen_ai.request.model` via in-memory exporter |
| Pipeline + consumer hook | `uv run pytest tests/test_pipeline.py tests/test_consumer.py` | `document.parsed` / `document.routed` events; Day-2 contract green |
| **Mixed-bundle gate (D4-M8)** | `uv run pytest tests/test_mixed_bundle.py` | full bundle routes/flags/events/spans; dup suppressed |

Live calls (Gemma sentinel, Flash classifier, Document AI) are flag-gated
(`DILIGENCE_GEMMA_ENABLED`, `DILIGENCE_FLASH_CLASSIFIER_ENABLED`,
`DILIGENCE_DOCAI_ENABLED`) and exercised only inside the live evidence
window; the Gemma serving decision is recorded in
[`docs/decisions/gemma-serving.md`](docs/decisions/gemma-serving.md).

## Security posture (Day-1 guardrails)

- **No service-account keys are created anywhere in this project.** All tooling authenticates with
  `gcloud auth application-default login` (ADC) or workload identity on Cloud Run / Agent Engine.
- **Cloud Audit Logs:** Admin Activity is always on. Data Access logs (ADMIN_READ, DATA_READ,
  DATA_WRITE) are explicitly enabled for Firestore (configured via `datastore.googleapis.com`)
  and Cloud Storage (`storage.googleapis.com`).
- **Billing guardrails:** budgets alert at 50% / 80% / 100% of the $170 hard cap.
- **Repository:** hosted privately at `github.com/divagr18/diligence-room` with
  branch protection on `main` (force-push/deletion blocked, admins enforced);
  made public at submission per the hackathon checklist (Day 14, D14-M2).

### Org-policy deviations (standalone billing account)

This project runs under a standalone Google Cloud account (no Cloud Organization node), so
org-scope constraints cannot be applied:

| Desired control | Org mechanism | Status here |
|---|---|---|
| Disable SA key creation | `iam.disableServiceAccountKeyCreation` (org/folder only) | **Deviation** — enforced by convention: zero SA keys, ADC/workload identity only; audited via Cloud Audit Logs |
| Org policy constraints | Organization Policy Service | N/A without org node |
| Branch protection | GitHub repo setting (not org policy) | **Applied** — `main` protected (enforce admins, no force-push/delete) on the private repo |

These deviations are recorded deliberately and will be revisited if the project moves under an
organization.

## License

Apache 2.0 (see `LICENSE` — added at submission, Day 14).
