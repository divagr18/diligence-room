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

# 3. Org-safety guardrails (audit logs, SA-key policy).
uv run python infra/guardrails.py

# 4. Provision per-deal data-room buckets + notifications.
uv run python infra/data_room.py \
    --deal-id deal-falcon \
    --project-number 910285417505 \
    --confirm-live

# 5. Seed the agent registry (8 manifests).
uv run python registry/seed.py

# 6. Deploy Cloud Run services (gateway + dashboard).
uv run python infra/deploy/cloud_run.py --confirm-live

# 7. Upload a test document to the US data-room bucket.
gcloud storage cp \
    data/acme_robotics/contract_customer_x.pdf \
    gs://diligence-room-dataroom-deal-falcon-us/

# 8. Verify the deployed services respond.
curl https://<gateway-url>/healthz
curl https://<gateway-url>/whoami
curl https://<gateway-url>/agents
```

The `--confirm-live` flag on both `data_room.py` and `cloud_run.py` is a
deliberate write-only guard: running without it (and without `--dry-run`)
exits immediately with a refusal message.

## Offline substitutes

The GCP project is currently torn down (deliberate teardown; recoverable via
`gcloud projects undelete diligence-room`), so live verification is paused.
The following provide offline equivalents until the live gate runs:

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
