# Deal Provisioning (BUILD_PLAN D2-M2)

Per-deal data-room bucket provisioning with Pub/Sub notifications for
object-finalize events. Buckets are created as **US + EU regional pairs**
per vision §7.8 (region pinning), and every upload fires an
`OBJECT_FINALIZE` notification to the shared `deal-events` Pub/Sub topic
for downstream ingestion.

## Provisioning sequence

For each deal, the following resources are created in order:

1. **Pub/Sub topic** `deal-events` (project-level, created once). Every
   data-room bucket publishes to this single topic on object finalize.

2. **US bucket** — `diligence-room-dataroom-{deal_id}-us` in
   `us-central1`, uniform bucket-level access enabled.

3. **EU bucket** — `diligence-room-dataroom-{deal_id}-eu` in
   `europe-west1`, uniform bucket-level access enabled.

4. **IAM grant** — `roles/pubsub.publisher` granted on the `deal-events`
   topic to the Google Cloud Storage service agent
   (`service-{project_number}@gs-project-accounts.iam.gserviceaccount.com`).
   Without this grant, GCS cannot publish bucket notifications.

5. **Notifications** — one `OBJECT_FINALIZE` notification per bucket,
   wired to `deal-events`. Any `gcloud storage cp` or console upload
   into either bucket fires a message consumed by the ingestion pipeline
   (Day 4, D4-M1…M7).

All steps are idempotent: the script checks for existing resources via
describe/list before creating, so re-runs are safe.

## LIVE-GATE RUNBOOK

When GCP access is available (project `diligence-room` restored or
freshly created), run these commands in order to fully provision the
platform and verify end-to-end:

```bash
# 1. Restore the deleted project (if applicable).
gcloud projects undelete diligence-room

# 2. Bootstrap: APIs, billing, staging bucket, budget alerts.
uv run python infra/bootstrap_gcp.py

# 2b. Create the Firestore database (NOT auto-created after undelete/new project).
gcloud firestore databases create --project=diligence-room --location=nam5

# 3. Org-safety guardrails (audit logs, SA-key policy).
uv run python infra/guardrails.py

# 4. Provision per-deal data-room buckets + notifications.
uv run python infra/data_room.py \
    --deal-id deal-falcon \
    --project-number 910285417505 \
    --confirm-live

# 5. Seed the agent registry (8 manifests).
uv run python registry/seed.py --confirm-live

# 6. Deploy Cloud Run services (gateway + dashboard).
uv run python infra/deploy/cloud_run.py --confirm-live

# 7. Upload a test document to the US data-room bucket.
gcloud storage cp \
    data/acme_robotics/contract_customer_x.pdf \
    gs://diligence-room-dataroom-deal-falcon-us/

# 8. Verify the deployed services respond.
# Note: use /health on Cloud Run — Google Frontend answers /healthz itself at
# the edge before the container sees it (the app serves both routes).
curl https://<gateway-url>/health
curl https://<gateway-url>/whoami
```

The `--confirm-live` flag on `data_room.py`, `seed.py`, and `cloud_run.py` is
a deliberate write-only guard: running without it (and without `--dry-run`)
exits immediately with a refusal message.

## Day-4 live evidence window (D4-M8 gate, short window)

Day 4 is built offline-first; the live window exists only to capture the
phase-exit evidence "sentinel model labeled in traces" + a real mixed-bundle
run, then tear down (Phase-A pattern). Estimated cost < $1.

```bash
# 1. Restore the project (DELETE_REQUESTED is recoverable ~30 days).
gcloud projects undelete diligence-room
gcloud projects describe diligence-room --format="value(lifecycleState)"  # ACTIVE

# 2. Re-apply bootstrap (idempotent) — recreates the deleted budget alerts.
uv run python infra/bootstrap_gcp.py
uv run python infra/guardrails.py

# 3. Firestore must exist after undelete (check before creating).
gcloud firestore databases describe --project=diligence-room \
  || gcloud firestore databases create --project=diligence-room --location=nam5

# 4. Re-provision the data room + registry.
uv run python infra/data_room.py --deal-id deal-falcon \
    --project-number 910285417505 --confirm-live
uv run python registry/seed.py --confirm-live

# 5. Live gate runner (Step-10 artifact): pulls deal-events, downloads the
#    uploaded bundle from the US bucket, runs the REAL pipeline —
#    gemini-3.5-flash (location=global) + hosted Gemma sentinel — and
#    exports OTel spans to Cloud Trace. Env for the window:
#      GOOGLE_GENAI_USE_VERTEXAI=TRUE  GOOGLE_CLOUD_LOCATION=global
#      DILIGENCE_FLASH_CLASSIFIER_ENABLED=1
#      DILIGENCE_GEMMA_ENABLED=1       GOOGLE_API_KEY=<AI-Studio key, env only>
#      DILIGENCE_DOCAI_ENABLED=1  (optional; needs a us OCR processor —
#      if provisioning friction appears, scanned docs route honestly with
#      needs_ocr and the evidence file records the skip; BUILD_PLAN red path)
uv run python scripts/run_d4_live_gate.py --deal-id deal-falcon --confirm-live

# 6. Capture evidence AS IT HAPPENS -> docs/evidence/d4-live-gate.txt
#    (events in Firestore, span ids + Cloud Trace console URLs, per-doc
#    routing table, provenance notes for anything recovered after the fact).

# 7. Tear down: budget + project (buckets/processors/registry all go with it).
#    Capture receipt -> docs/evidence/d4-teardown.txt, confirm DELETE_REQUESTED.
```

## Offline substitutes

The live Day-2 gate was executed successfully on 2026-08-16 (see
`docs/evidence/d2-live-gate.txt`) and the project was torn down again
afterwards (`docs/evidence/d2-teardown.txt`, recoverable via
`gcloud projects undelete diligence-room`). The offline equivalents below
remain the development-time contract:

| Live activity | Offline substitute |
|---|---|
| End-to-end pipeline on GCP | [`tests/test_e2e_offline.py`](../tests/test_e2e_offline.py) — full pipeline exercised against the local Firestore emulator (see [`tests/conftest.py`](../tests/conftest.py) for the emulator fixture) |
| Bucket provisioning plan | [`tests/test_data_room_plan.py`](../tests/test_data_room_plan.py) — pure planning logic unit-tested; `--dry-run` prints the full gcloud command sequence |
| Bootstrap API enablement | [`tests/test_bootstrap_plan.py`](../tests/test_bootstrap_plan.py) — service-enablement diff and budget-argument construction |

The emulator fixture in `tests/conftest.py` starts a local Firestore
emulator on a free port (session-scoped), sets `FIRESTORE_EMULATOR_HOST`,
and yields a per-test project ID to ensure isolation without cleanup.

## Offline gate (Day-2 gate substitute)

`tests/test_e2e_offline.py` proves the full Day-2 chain against the emulator
with zero live GCP calls:

1. registry seeded with all 8 workstream agents (`registry/seed.py`);
2. Project Falcon deal workspace provisioned (`runtime/deal_workspace.py`);
3. a simulated `OBJECT_FINALIZE` notification for
   `contract_customer_x.pdf` in the falcon US bucket is parsed into a
   `document.ingested` envelope (`runtime/bucket_notify.py`);
4. the envelope crosses the event bus (`runtime/events.py` InMemoryPublisher)
   and is drained by a consumer into the append-only audit log
   (`gateway/audit.py`, seq 1 assigned transactionally);
5. the deal document is readable and the registry API serves the 8-agent
   fleet.

A second test proves duplicate notifications are idempotent (same seq, one
document). When the live gate runs, this file is the acceptance contract the
live flow must match.
