---
submission_id: diligence-room-project-falcon
project: Project Falcon
hackathon: AllThingsAgentic Hackathon
track: Fortified Enterprise Fleet
blog_url: https://dev.to/diligence-room/project-falcon-fortified-deal-fleet-xxxx
visibility: public
blog_draft: docs/blog/draft.md
blog_language: hackathon-purpose (created for the AllThingsAgentic Hackathon, bonus +0.2)
---

# Project Falcon: Diligence Room

Copy the sections below into the submission form fields.

## Summary (form: project description)

**Diligence Room is a Fortified Enterprise Agentic Fleet for M&A due
diligence.** Its eight specialist agents cover Legal, Finance, HR, IP/Tech,
Tax, Regulatory, ESG, and Real Estate. They investigate a target in parallel,
make governed handoffs when another discipline is needed, and build an
auditable picture of deal risk.

In **Project Falcon**, the fleet investigates the synthetic **Vantage
Robotics, Inc.** data room. Legal finds a Meridian change-of-control right;
Finance finds 18.3% FY27 revenue concentration; HR finds the Meridian account
owner is leaving; and IP/Tech finds an end-of-life dependency. The Coordinator
can synthesize those independently evidenced signals into one CRITICAL
customer-exit exposure that no single specialist is allowed to create. It
escalates that conclusion to the deal lead, then stops at a human approval
gate. Twenty red-team attacks are blocked before reaching agent context.

Everything runs live on Google Cloud: Cloud Run (gateway + dashboard),
Agent Runtime / Vertex AI Agent Engine (deployed ADK agent), Firestore (partitioned memory + event
log), Pub/Sub (event bus), Model Armor (managed screening), Cloud KMS + DLP
(compliance plane), Cloud Trace (OpenTelemetry GenAI spans).

- Hosted dashboard: https://diligence-room-dashboard-378831539922.asia-south1.run.app
- Hosted gateway: https://gateway-378831539922.asia-south1.run.app
- Repository: https://github.com/divagr18/diligence-room
- Demo video: VIDEO LINK (added at submission; ≤4 min, English)

## Why a fleet

Project Falcon is built for a task that does not fit into one chat window. It
catalogs specialist agents for reuse, delegates work across isolated
workstreams, preserves state through a crash, and gives the auditor a complete
decision trail. Legal, Finance, HR, and IP/Tech must independently surface
linked signals before the Coordinator can create the CRITICAL finding. No
worker can make that conclusion alone.

**The Unlikely Hero is the deal-room analyst.** This person sits between an
untrusted vendor data room and senior reviewers. They need more than document
summaries. They need connected risk, source evidence, and clear ownership. The
fleet handles mechanical triage and cross-referencing. The analyst retains the
external negotiation approval, while the auditor can inspect every access
decision, evidence span, safety verdict, and finding.

## How the fleet operates

### Discovery & Lifecycle (Agent Registry)

All eight agents are published into the **Gemini Enterprise Agent Platform
Agent Registry** as A2A agent cards (`infra/agent_registry.py`), so the fleet is
discoverable across the organisation: `gcloud agent-registry agents list` returns
all eight projected as read-only Agents. Cards are derived from the Firestore
manifests, never restated, so the two cannot drift, and each card's published URL
resolves — the gateway serves it at `GET /agents/{agent_id}`.

Our own registry (`registry/`) stays the lifecycle layer on top: semantic
versions, approval state, eval scores and rollback targets, none of which the
platform registry models. Live proof: a deliberately broken Legal v2.5 was
published, caught by the shadow harness, and rolled back to 2.4.0 with memory
intact.

### Core Execution & State (Agent Runtime + Memory Bank)

Long-running asynchronous execution on Agent Runtime / Vertex AI Agent Engine
(the platform renamed Agent Engine to Agent Runtime; the API resource is still
`ReasoningEngine` for backwards compatibility). Deployed resource
`projects/378831539922/locations/us-central1/reasoningEngines/7141202128323739648`,
async invoke verified.

**Memory Bank** (`memory/memory_bank.py`) attaches to that runtime instance and
holds durable memory about counterparties, so a session opened weeks later starts
knowing what the fleet learned. The coordinator writes one memory when it
synthesises the CRITICAL finding; `recall("Meridian")` from a separate process —
one that never imports Firestore — returns the 18.3% concentration, the Section
11.3 change-of-control right and the four-workstream convergence. That is the
cross-session claim, checked rather than asserted.

Firestore keeps what it is good at: partitions `org / deal / workstream` with an
append-only event log (143 audited events live) and crash-resume checkpoints. A restarted run creates no
duplicate findings. Retry and idempotency keys, plus a dead-letter queue,
handle malformed events.

### Security & Governance (Agent Identity + Agent Gateway + Model Armor)

- **Agent Identity**: per-workstream principals with zero-trust AuthZ;
  negative isolation proven live (Legal ⊬ Finance, Finance ⊬ HR, cross-deal
  reads denied with audit events).
- **Agent Gateway**: a deny-default policy engine with machine-readable
  verdicts. A Legal request to Finance for `revenue_concentration` receives
  `allow / aggregate_permitted`. An unauthorized route receives
  `deny / no_policy`. Raw financial models never cross workstream boundaries.
- **Model Armor**: managed template (`diligence-room-d7`, prompt-injection +
  jailbreak at MEDIUM_AND_ABOVE, malicious-URI) + project rules + quarantine
  store; it fails closed on unparseable verdicts. A poisoned fixture returned
  `MATCH_FOUND pi_and_jailbreak` and was quarantined before agent context.

### Telemetry (Agent Observability)

OpenTelemetry GenAI semantic-convention spans exported to Cloud Trace across
ingestion, sentinel, armor, agent runs, and gateway decisions. Every finding
carries an `audit_trace_id` that resolves in Cloud Trace. The trace connects
the source document to the resulting finding.

### Compliance, data sovereignty, security posture

CMEK keyrings + keys in US and EU (`deal-falcon-primary`), DLP inspect
template on the HR path, region pinning (US+EU declared per deal), retention,
Cloud Audit Logs with data access enabled, zero service-account keys (ADC +
workload identity only), budget guardrails ($170 cap; alerts 50/80/100%).
VPC-SC perimeter config committed and shape-tested; application recorded as a
documented deviation on a standalone (no-org) account.

## The deal in action

M&A diligence is parallel, adversarial, and cross-functional. The eight
workstreams read separate document categories under separate identities, so no
single agent sees the whole deal. Legal finds the change-of-control clause and
asks Finance for a permitted aggregate. Finance returns `18.3%`, not the raw
model. The Coordinator creates a CRITICAL finding only when all four required
workstreams identify the same entity. If one contributor is missing, it
refuses to synthesize.

The executive dashboard exposes this in five views: Overview (workstream
coverage and the escalation inbox), Findings and finding detail (evidence
spans, the finding graph, and the audit trace), Documents (every file in the
data room with the workstream it was routed to, the routing confidence, and
whether it was quarantined), Security (the red-team scorecard and the
quarantine table, where each blocked payload is openable), and Registry
(agent versions, approval state, eval scores).

Every upload is treated as hostile input until it passes format detection,
parsing, the Gemma sentinel, and Model Armor. In the live scenario, an upload
triggers Pub/Sub processing, four evidence-gated findings, a denied access
attempt, CRITICAL synthesis `b093295dab91`, a security response that blocks
20 red-team attacks, and a final human approval for the negotiation.

## Architecture

Strict separation of concerns: ingestion / sentinel / armor / fleet / gateway
/ coordination / dashboard are independently testable modules (1,103 tests;
mypy strict on 209 files). Failure tolerance is tested, not claimed: loop
guard (runaway-agent fixture), evidence gate (fabricated citations rejected),
crash-resume (a restarted run creates no duplicates), DLQ + redrive, deny-default
gateway, aggregate-only response filter, rollback with memory preserved.
State lives in Firestore with transactional sequence numbers. Tools are scoped
per principal. The deterministic replay engine runs the 49-event scenario
through the real pipeline in under four minutes and produces identical results
across consecutive runs.

## Live project

The dashboard and gateway run on Cloud Run in `asia-south1`, with a second
region in `us-central1`. The deployed ADK
agent runs on Agent Runtime / Vertex AI Agent Engine. Cloud Trace records the
agent and gateway
spans. The [architecture diagram](diagram/architecture.svg),
[deployment receipts](evidence/live-deployment.txt), and
[provisioning guide](deal_provisioning.md) explain how the system is deployed
and reproduced.

## Submission form answers

- **Project start date:** 2026-08-14. First commit `D1-M3: repo skeleton` at
  2026-08-14 23:57 IST; 166 commits over the eighteen days to submission.
- **Google SDK used:** Google ADK (`google-adk` 2.7.0) for the agent fleet, and
  the Google GenAI SDK (`google-genai` 2.18.1) for the Gemini 3.5 Flash and
  Gemma calls. Agent Runtime deployment goes through
  `google-cloud-aiplatform` 1.163.0 with the `[adk,agent_engines]` extras.
- **Models:** `gemini-3.5-flash` on Vertex AI (served from the `global`
  location) for the eight workstream agents and the routing classifier;
  `gemma-4-26b-a4b-it` on the Gemini Developer API for the ingestion sentinel.
- **Pre-existing or third-party code:** none. Every line of first-party code in
  this repository was written during the submission period. The project depends
  only on published open-source packages, declared in `pyproject.toml` and
  `dashboard/web/package.json` and used under their own licences; no code was
  copied from another project, and no prior work was carried in. The dataset is
  synthetic and generated by `scripts/author_dataset.py` - no external corpus.

## Technologies used

Python 3.11 · Google ADK · Agent Runtime / Vertex AI Agent Engine ·
Gemini 3.5 Flash · Gemma
(sentinel, bonus model) · FastAPI · React + Vite + TypeScript · Firestore ·
Pub/Sub · Cloud Run · Cloud Storage · Model Armor · Cloud DLP · Cloud KMS
(CMEK) · Cloud Trace (OpenTelemetry GenAI semantic conventions) · uv ·
pre-commit (ruff, mypy strict, gitleaks).

## Data sources

Fully synthetic, authored deterministically for this project: the Vantage
Robotics data room (scripts/author_dataset.py), the 20-document golden set,
the 20-attack red-team fixture ledger, and the 49-event Project Falcon
scenario. No real company data, no real PII.

## Findings & learnings

1. Managed guardrails can fail open. Our first live Model Armor call exposed
   a response-mapping bug; the client now fails closed on any unrecognizable
   verdict.
2. LLM entity naming is a coordination hazard. One agent's "Meridian
   Logistics, Inc. account" broke strict convergence; fixed via a canonical
   entity contract in the finding tool spec, not fuzzy matching.
3. Undeleted GCP projects leave zombies. The (default) Firestore database
   was unservable after project undelete; we shipped an env-driven client
   factory routing live traffic to a named database.
4. Cost gates work. Gemma sentinel before premium Flash calls kept the whole
   build under a $170 budget.
5. Deployment packaging drifts silently. The Agent Runtime remote
   requirements lagged module-level imports until a live container failed to
   start.

## Additional project materials

- Blog post: draft ready at [`docs/blog/draft.md`](blog/draft.md). Publish it
  publicly, replace the placeholder `blog_url` in the frontmatter, and retain
  the sentence that it was created for the AllThingsAgentic Hackathon before
  claiming this bonus.
- Social post: publish publicly with `#AllThingsAgenticHackathon`, then add
  the final post URL to the submission form before claiming this bonus.
- Additional Google AI model integrated: **Gemma 4** ingestion sentinel,
  `gemma-4-26b-a4b-it` (`ingestion/sentinel.py`). Verified live: it classifies
  the Meridian termination clause as `contract` at 0.98 confidence with a
  model-written rationale, and tripwires a direct prompt injection. Evidence in
  [`evidence/gemma-live.txt`](evidence/gemma-live.txt), which also records that
  the recorded replay path uses the deterministic sentinel tier for timing.

## Spin-up instructions

Start with README Quickstart: `uv sync`, `uv run python
infra/bootstrap_gcp.py`, `uv run pytest`, and `npm --prefix dashboard/web run
build`. Then follow `docs/deal_provisioning.md` to provision Firestore,
data-room buckets, the registry, and Cloud Run services.

## Innovation & Operational Utility

Project Falcon turns four separate diligence signals into one decision that a
single agent cannot safely reach. The result is useful to the deal team: a
clear, evidence-backed account of why a customer relationship could affect
deal economics, with the human retaining control of the final negotiation.

## Architectural Discipline & Tech Stack

The fleet separates ingestion, safety screening, specialist agents, the
gateway, memory, coordination, and the dashboard. Each component is testable
on its own. Firestore stores durable state, the gateway limits what agents can
ask of one another, and Cloud Trace links a finding back to its source and
execution path.

## Demo & Production Readiness

The hosted dashboard and gateway are live on Google Cloud. The public demo
shows the running system process a document, make a governed cross-workstream
request, block an unauthorized request, create the CRITICAL finding, and show
the supporting Cloud Run, Agent Runtime, and Cloud Trace resources.
