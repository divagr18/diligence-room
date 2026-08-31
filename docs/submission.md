---
submission_id: diligence-room-project-falcon
project: Project Falcon
hackathon: AllThingsAgentic Hackathon
track: Fortified Enterprise Fleet
blog_url: https://dev.to/divagr/zero-trust-agent-fleets
visibility: public
blog_draft: docs/blog/draft.md
blog_language: hackathon-purpose (created for the AllThingsAgentic Hackathon, bonus +0.2)
---

# Diligence Room (Project Falcon)

![Diligence Room Architecture](https://raw.githubusercontent.com/divagr18/diligence-room/main/docs/diagram/architecture.png)

## Inspiration

### The Problem in M&A Diligence
Corporate acquisitions force deal teams to review more than 10,000 pages of unvetted documents under tight deadlines: scanned contracts, severance memos, cap tables, and financial models.

The worst risks hide in the gaps between disciplines:
- **Legal** finds a Change-of-Control clause in Section 11.3 of a contract with Meridian Logistics.
- **Finance** calculates that Customer X provides 18.3% of projected cash flow.
- **HR** finds that the account lead for Meridian is resigning.
- **IP/Tech** finds that a core software dependency (TitanBridge 4.1) reaches End-of-Life.

Read alone, each note looks minor. **Together, they prove the target will likely lose its primary customer right after the acquisition closes.** In traditional deal rooms, isolated teams miss this connection until it is too late to renegotiate price.

### The Unlikely Hero: The Deal-Room Analyst
Junior transaction analysts spend days cross-referencing contradictory PDFs. Diligence Room gives them an autonomous agent fleet that works around the clock, discovers connected risks, proves every fact with exact text quotes, and halts before taking external actions.

### The Twist: Documents Are Adversaries
Most AI systems trust uploaded files. In an M&A transaction, **documents are untrusted, potentially hostile inputs**. Sellers can upload prompt injections, exfiltration traps, or deceptive summaries.

Diligence Room enforces **Zero-Trust rules**:
1. **Documents are adversaries:** All text must pass a four-layer screening gauntlet (Format Detection -> Chunk Parsing -> Gemma 4 Sentinel -> Model Armor) before entering agent context.
2. **Agents are principals:** Each agent runs with its own identity, read scope, and write bounds.
3. **Memory is partitioned by policy:** Legal cannot open raw financial ledgers; Finance cannot view HR files.

---

## What it does

Diligence Room runs autonomous, zero-trust diligence on M&A targets:

### 1. Autonomous Ingestion and Screening
When a user uploads a file to Cloud Storage, Pub/Sub triggers the pipeline. A lightweight **Gemma 4 Sentinel** (`gemma-4-26b-a4b-it`) and Google Cloud **Model Armor** (`diligence-room-d7`) quarantine prompt injections, exfiltration lures, and PII before worker agents can read them.

### 2. Eight Specialist Agents
Eight domain agents (**Legal, Finance, HR, IP/Tech, Tax, Regulatory, ESG, Real Estate**) analyze documents within strict boundaries using **Gemini 3.5 Flash** on Vertex AI.

### 3. Governed Agent Gateway
The Agent Gateway blocks unauthorized cross-agent reads. When Legal asks Finance for customer revenue exposure, the Gateway returns only an aggregate number (`18.3%`), keeping raw financial spreadsheets private.

### 4. Coordination Keystone and Risk Synthesis
In **Project Falcon** (evaluating target **Vantage Robotics, Inc.**), the Coordinator monitors the deal graph. When four separate agents identify risks on the same counterparty, the Coordinator synthesizes CRITICAL finding `b093295dab91`: _"Compound Customer-Exit Exposure Threatens Deal Economics."_ If any single workstream is missing, the Coordinator refuses to synthesize the finding.

### 5. Write-Time Evidence Gate
The evidence gate blocks hallucinations. An agent cannot save a finding unless every quoted `verbatim_span` matches the source document text word for word.

### 6. Human Approval Gate
The Negotiation agent drafts contract remedies and price cuts from critical findings, then stops at an explicit gate: `draft -> pending_approval -> [STOPS FOR HUMAN REVIEW] -> approved -> send_logged`. The Deal Lead must approve any draft before it leaves the deal room.

### 7. Executive Dashboard and Audit Traces
A 5-view web console links every finding back to its source document and execution span in **Google Cloud Trace**.

---

## How we built it

We built Diligence Room natively on the **Gemini Enterprise Agent Platform (GEAP)**. It was created for the **AllThingsAgentic Hackathon** in the **Fortified Enterprise Fleet** track:

| GEAP Pillar | Technology | Implementation Details |
|---|---|---|
| **Discovery & Lifecycle** | **Agent Registry** | All 8 specialist agents publish official A2A cards via [infra/agent_registry.py](https://github.com/divagr18/diligence-room/blob/main/infra/agent_registry.py). `gcloud agent-registry agents list` discovers all agents. Firestore tracks semantic versions and rollback targets. |
| **Core Execution** | **Agent Runtime** / Vertex AI Agent Engine | Long-running asynchronous execution runs as a Google ADK reasoning engine (`projects/378831539922/locations/us-central1/reasoningEngines/7141202128323739648`) with retries and dead-letter queues. |
| **Long-Term State** | **Memory Bank** | Decoupled processes run `recall("Meridian")` to fetch verified counterparty facts weeks later without direct database imports. |
| **Zero-Trust Access** | **Agent Identity** | Each workstream uses a separate IAM identity; negative isolation prevents unauthorized reads (`Legal ⊬ Finance`, `Finance ⊬ HR`). |
| **Routing & Policy** | **Agent Gateway** | Deny-default router on Cloud Run returns machine-readable verdicts (`allow/aggregate_permitted`, `deny/no_policy`) and aggregate-only data. |
| **Inline Guardrails** | **Model Armor** | Managed template (`diligence-room-d7`) and custom project rules fail closed on unparseable outputs to quarantine attacks. |
| **Observability & Tracing** | **Agent Observability** | OpenTelemetry GenAI spans stream to Google Cloud Trace; every finding carries a durable `audit_trace_id`. |
| **Foundation Models** | **Gemini 3.5 Flash & Gemma 4** | Gemini 3.5 Flash handles domain reasoning; `gemma-4-26b-a4b-it` serves as the Tier-1 Ingestion Sentinel. |
| **Compliance Plane** | **Cloud KMS & DLP** | Customer-managed keys (CMEK) protect data in US and EU; Cloud DLP inspects HR files; zero service account keys. |

---

## Challenges we ran into

1. **Guardrails Failing Open:** Early testing showed that unrecognized guardrail responses were treated as safe. We rewrote the Model Armor client to **fail closed** on any non-standard response.
2. **Inconsistent Entity Names:** Models generated slight variations of corporate names (e.g. _"Meridian Logistics"_ vs _"Meridian Logistics, Inc. account"_), which broke multi-agent convergence. We enforced strict entity schemas in tool parameters instead of relying on fuzzy matching.
3. **Cross-Region Latency:** Running agents across different regions slowed down execution. Moving active Firestore databases and Cloud Run services to `asia-south1` cut round-trip latency from 834 ms to 156 ms, dropping total deal replay time from 262s to 57s.
4. **Runaway Tool Loops:** Complex edge cases caused early prototypes to loop repeatedly. We added the [Loop Guard](https://github.com/divagr18/diligence-room/blob/main/runtime/guards.py) with hard limits on iterations, tool calls, token usage, and time.
5. **Mid-Run Container Crashes:** When cloud workers restart mid-run, they can duplicate findings. We added state checkpoints and idempotency keys to ensure restarted runs create **zero duplicate findings**.

---

## Accomplishments that we're proud of

- **1,103 Automated Tests Passing:** 100% pass rate across unit, integration, isolation, and evidence-gate test suites.
- **Mypy Strict Typing:** 0 type errors across 209 Python files.
- **20/20 Red-Team Attacks Blocked:** 100% containment across 4 attack types (8 injections, 5 exfiltrations, 4 cross-workstream leaks, 3 poisoning attempts).
- **0.0% False Positive Rate:** Processed 20 clean data-room documents with zero false alarms.
- **49-Event Deterministic Replay:** Replays 14 simulated deal days in **under 4 minutes** (seed 42).
- **143 Audited Deal Events:** Preserves an immutable event ledger in Firestore.
- **$170 Cloud Budget Guardrail:** Kept cloud spend within budget with alerts at 50%, 80%, and 100%.

---

## What we learned

1. **Enforce Security in Code, Not Prompts:** You cannot prompt-engineer safety into enterprise workflows; you must enforce boundaries through identity checks, network policy, and write-time schema validation.
2. **Tiered Models Save Money:** Placing a small Gemma 4 sentinel in front of Gemini 3.5 Flash cut token waste on junk and hostile files by 74%.
3. **Separate State from Agent Code:** Storing deal findings separately from agent manifests allows instant rollbacks without wiping deal memory.
4. **Keep Humans in the Loop:** Autonomous agents should draft remedies, but a human must approve every real-world action.

---

## What's next for Dilligence Room

1. **Portfolio Risk Clustering:** Compare risk graphs across multiple deals to spot shared supplier risks across private equity portfolios.
2. **Automated Seller Q&A Lists:** Turn missing evidence gaps into prioritized question lists for sellers.
3. **Enterprise Connectors:** Connect directly to SAP, NetSuite, Intralinks, and Datasite data rooms.
4. **Antitrust Filing Drafts:** Turn market-share findings into draft regulatory filings.

---

## Bonus Developer Contributions (+0.6 Points)

1. **Additional Google AI Model: Gemma 4 Ingestion Sentinel (+0.2 Bonus):** Integrated `gemma-4-26b-a4b-it` via Gemini Developer API for Tier-1 zero-shot prompt injection detection ([ingestion/sentinel.py](https://github.com/divagr18/diligence-room/blob/main/ingestion/sentinel.py), live proof in [docs/evidence/gemma-live.txt](https://github.com/divagr18/diligence-room/blob/main/docs/evidence/gemma-live.txt)).
2. **Public Technical Blog Post (+0.2 Bonus):** Published live at [divagr.com/blog/zero-trust-agent-fleets](https://divagr.com/blog/zero-trust-agent-fleets) (draft in [docs/blog/draft.md](https://github.com/divagr18/diligence-room/blob/main/docs/blog/draft.md)), containing required hackathon-purpose language.
3. **Public Social Media Promotion (+0.2 Bonus):** Shared publicly on X at [x.com/divagr1925/status/2094503795086725497](https://x.com/divagr1925/status/2094503795086725497) with `#AllThingsAgenticHackathon`.

---

## Project Links & Live Endpoints

- **Demo Video Walkthrough:** [YouTube (4-Minute Full Replay)](https://youtu.be/oCu2HfN85Ec)
- **Technical Blog Post:** [divagr.com/blog/zero-trust-agent-fleets](https://divagr.com/blog/zero-trust-agent-fleets)
- **Public Social Post:** [X / Twitter (@divagr1925)](https://x.com/divagr1925/status/2094503795086725497)
- **Hosted Dashboard (Web UI):** [diligence-room-dashboard...run.app](https://diligence-room-dashboard-378831539922.asia-south1.run.app)
- **Hosted Agent Gateway:** [gateway...run.app](https://gateway-378831539922.asia-south1.run.app)
- **Deployed Agent Runtime:** `projects/378831539922/locations/us-central1/reasoningEngines/7141202128323739648`
- **Cloud Trace Sample:** [Cloud Trace `d77658309933cf2ff4a5d336e9960a64`](https://console.cloud.google.com/traces/list?project=diligence-room-live&tid=d77658309933cf2ff4a5d336e9960a64)
- **Architecture Diagram:** [High-Res Vector SVG](https://raw.githubusercontent.com/divagr18/diligence-room/main/docs/diagram/architecture.png) (PNG: [High-Res PNG](https://raw.githubusercontent.com/divagr18/diligence-room/main/docs/diagram/architecture.png))
- **Code Repository:** [github.com/divagr18/diligence-room](https://github.com/divagr18/diligence-room)

