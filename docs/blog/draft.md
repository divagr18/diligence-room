---
title: "Teaching an Agent Fleet to Distrust Documents: Zero-Trust M&A Diligence on Google Cloud"
description: "How we built a zero-trust runtime for eight autonomous due-diligence agents on the Google Gemini Enterprise Agent Platform, and what broke along the way."
tags: allthingsagentichackathon, gemini, ai-agents, google-cloud, multi-agent-systems
published: false
canonical_url: https://divagr.com/blog/zero-trust-agent-fleets
---

# Teaching an Agent Fleet to Distrust Documents: Zero-Trust M&A Diligence on Google Cloud

## TL;DR

Diligence Room is an enterprise zero-trust runtime for autonomous multi-agent fleets, demonstrated through a high-stakes M&A due diligence scenario on a synthetic robotics company, Vantage Robotics (investigated under the deal name **Project Falcon**). Eight specialist agents analyze a hostile, unvetted data room under strict information barriers, running the entire transaction from initial document upload to executive risk synthesis as a deterministic replay in under four minutes. 

The architecture rests on three foundational reframings: **documents are adversaries, agents are principals, and memory is partitioned by policy rather than convenience.** 

It was created for the AllThingsAgentic Hackathon, in the Fortified Enterprise Fleet track, on the Google Gemini Enterprise Agent Platform.

---

## 2:00 AM in the Virtual Data Room

Picture an M&A war room at 2:00 AM, two days before signing. 

The seller has uploaded 10,000 pages of unvetted documents: scanned PDF contracts, cap tables, severance agreements, and financial spreadsheets. A transaction analyst must answer one question: *what in this room threatens the deal?*

The worst risks hide in the gaps between disciplines:
- In `02_Contracts/`, Legal finds a Change-of-Control clause in Section 11.3 of a contract with Meridian Logistics.
- In `04_Financials/`, Finance models cash flows and finds Customer X accounts for **18.3% of projected revenue**.
- In `07_HR/`, HR finds that **Dana Whitfield, the primary account director for Meridian, is resigning**.
- In `09_Technology/`, an engineer finds that a core middleware package (**TitanBridge 4.1**) reaches End-of-Life.

Read alone, each note looks routine. **Together, they prove the target will lose its primary customer immediately after closing.**

In human deal rooms, separate teams miss this connection because they work in silos. Monolithic "chat with your docs" bots also fail: they lose track of facts across long prompts, invent numbers, and fall for prompt injections hidden in invoices.

We did not build a chatbot. We built an **autonomous agent fleet that works while the deal team sleeps**—screening threats, enforcing strict boundaries, and proving every factual claim against exact text quotes before a human signs a deal.

---

## The Twist

**Documents are adversaries. Agents are principals. Memory is partitioned by policy, not convenience.**

Every design choice in Diligence Room follows from these three rules:

1. **Documents are adversaries:** In M&A deals, you cannot trust vendor files. Every uploaded document is an unvetted input. It must pass a four-layer screening gauntlet before any text enters an agent's reasoning context.
2. **Agents are principals:** Specialist agents (Legal, Finance, HR, IP/Tech, Tax, Regulatory, ESG, Real Estate) do not share one large context window. Each runs under its own identity with restricted read scopes and write bounds.
3. **Memory is partitioned by policy:** Financial models never cross into HR's workspace. When Legal needs revenue numbers, it cannot browse the financial model; it queries the Agent Gateway, which returns only an aggregate number under strict policy rules.

---

## Architecture: The Four Layers of Defense

Between an untrusted vendor document and an executive deal finding sits an uncompromising chain of gates:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE FOUR-LAYER SCREENING GAUNTLET                     │
│                                                                             │
│   Hostile Upload (PDF / XLSX / DOCX)                                        │
│          │                                                                  │
│          ▼                                                                  │
│   [ LAYER 1: GEMMA 4 SENTINEL ] ──► Quarantines prompt injections & attacks │
│          │ (Passed)                                                         │
│          ▼                                                                  │
│   [ LAYER 2: MODEL ARMOR API ]  ──► Managed threat & jailbreak detection    │
│          │ (Passed)                                                         │
│          ▼                                                                  │
│   [ LAYER 3: AGENT GATEWAY ]    ──► Deny-default cross-agent policy routing │
│          │ (Governed)                                                       │
│          ▼                                                                  │
│   [ LAYER 4: EVIDENCE GATE ]    ──► Write-time exact substring verification │
│          │ (Validated)                                                      │
│          ▼                                                                  │
│   [ IMMUTABLE DEAL FINDING ]                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 1: The Gemma Sentinel (Cost & Ingestion Gate)
Before invoking premium models, every document chunk passes through `gemma-4-26b-a4b-it` on the Gemini Developer API. The sentinel acts as an inline tripwire: detecting direct adversarial prompt injections, identifying sensitive PII markers, and assigning pre-classification confidence hints. Poisoned text is quarantined immediately at zero significant token cost.

### Layer 2: Model Armor API (Managed Perimeter)
Documents cleared by the sentinel enter Google Cloud's Model Armor template (`diligence-room-d7`) alongside custom project inspection rules. Across a 20-attack red-team ledger (direct injections, data exfiltration lures, cross-workstream leakage, and tool poisoning), **100% of attacks were quarantined before reaching agent context**, with a 0% false-positive rate across clean deal documents.

### Layer 3: The Agent Gateway (Deny-Default Policy Router)
When the Legal Agent needs to verify whether Meridian Logistics is a material customer, it cannot open Finance's data room. Instead, it dispatches a structured query to the Agent Gateway on Cloud Run. The Gateway verifies the identity policy:
- `legal -> finance (revenue_concentration)`: **ALLOW / aggregate_permitted** → returns scalar `18.3%`.
- `hr -> finance (raw_payroll_export)`: **DENY / no_policy** → blocked and logged as an auditable security event.

### Layer 4: The Evidence Gate (Anti-Hallucination Wall)
Large language models love to sound confident when inventing citations. Diligence Room eliminates hallucinated deal findings at the database write boundary: when an agent calls `finding_create`, the evidence gate verifies that every single quoted `verbatim_span` exists as an exact, byte-for-byte substring within the cited document chunk. If a model fabricates a quote, the write is aborted with `evidence_unresolvable` and flagged in the audit trace.

---

## The Coordination Keystone: Project Falcon's Defining Moment

The true power of this architecture culminates in the discovery of compound deal risk during **Project Falcon**:

1. **Legal Agent** ingests `contracts/contract_meridian_logistics.pdf`, identifies the 90-day Change-of-Control clause in Section 11.3, and logs a HIGH finding backed by verbatim text.
2. Through the **Agent Gateway**, Legal requests customer concentration from Finance, receiving the verified aggregate of **18.3% FY27 projected revenue**.
3. **HR Agent** scans executive departure agreements and logs the resignation of Dana Whitfield (Meridian account owner).
4. **IP/Tech Agent** flags that the robotics control stack relies on TitanBridge 4.1, which reaches EOL before the contract renewal date.

Independently, none of the four specialist agents is authorized to declare a deal-killing emergency. But the **Coordinator Keystone** evaluates multi-agent convergence across the deal graph. Recognizing four independent, evidence-backed signals converging on a single corporate counterparty, the Coordinator synthesizes finding `b093295dab91`: 
> **CRITICAL: Compound Customer-Exit Exposure Threatens Deal Economics.**

If any single specialist workstream is removed, or if any evidence span fails verification, the Coordinator refuses to synthesize the finding. It is structurally immune to single-agent hallucination.

---

## Human Approval is a Gate, Not a Formality

Once a critical exposure is identified, the Negotiation Agent drafts specific remedy proposals (such as seller indemnities, escrow holdbacks, or pre-closing customer waivers).

Crucially, **the agent cannot send these remedies to the seller on its own.**

The negotiation engine operates on an explicit state machine:
`draft → pending_approval → [HALTED FOR HUMAN REVIEW] → approved → send_logged`

The transition from `pending_approval` to `approved` requires cryptographic human-to-output authorization signed by the Deal Lead in the executive dashboard. Nothing leaves the virtual deal room without human consent.

---

## What Broke, and What We Built About It

The hackathon judging rubric challenges builders to confront real-world multi-agent failures. During development, four critical failure modes broke our system—and each yielded an essential architectural defense:

### 1. The Runaway Tool Loop
*What broke:* Early in testing, an edge-case contract clause caused a specialist agent to loop continuously across ten tool calls, draining tokens and freezing execution.  
*The defense:* We engineered the **Loop Guard** (`runtime/guards.py`). Every agent execution is governed by hard ceilings on iteration count, tool-call budgets, token consumption, and per-step wall-clock timeouts. Exceeding any threshold gracefully halts the agent, saves an execution checkpoint, and logs a `run.bounds_exceeded` receipt.

### 2. The Subtle Hallucination
*What broke:* An agent generated a plausible finding regarding an environmental indemnification clause, citing a page number but slightly paraphrasing the text.  
*The defense:* We built the write-time **Evidence Gate** (`memory/findings.py`). Paraphrased or unresolvable citations are rejected at write time, an `evidence.rejected` event is recorded, and low-confidence findings remain capped at `candidate` status so they never trigger autonomous escalations.

### 3. The Mid-Run Container Crash
*What broke:* In distributed cloud environments, containers restart unexpectedly. A worker crash mid-diligence left incomplete records and duplicate findings upon reboot.  
*The defense:* We implemented **Crash-Resume & Idempotency** (`runtime/checkpoint.py`). Execution states are committed transactionally to an append-only event log. When a crashed worker restarts, it resumes directly from its last checkpoint. Idempotency keys guarantee that restarted jobs produce **zero duplicate findings**.

### 4. The Regressed Agent Deployment
*What broke:* Deploying an updated Legal prompt (v2.5.0) caused subtle classification regressions on complex indemnities.  
*The defense:* We built the **Registry Rollback** mechanism (`registry/`). When shadow evaluations on our 20-document golden set detected the regression, we executed an instant rollback to v2.4.0. Because memory and findings live in partitioned deal storage rather than agent code, deal state survived completely intact.

---

## Built on the Gemini Enterprise Agent Platform (GEAP)

Diligence Room was built natively from day one on Google Cloud's **Gemini Enterprise Agent Platform (GEAP)**, unifying seven enterprise agent pillars into a cohesive, zero-trust architecture:

- **Discovery & Lifecycle (Agent Registry):** All eight specialist agents are published as official A2A Agent Cards (`infra/agent_registry.py`), discoverable via `gcloud agent-registry agents list`. Firestore provides enterprise semantic versioning, approval state, and instant live rollback targets.
- **Core Execution (Agent Runtime / Vertex AI Agent Engine):** Long-running, asynchronous background execution deployed as a Google ADK reasoning engine (`projects/378831539922/locations/us-central1/reasoningEngines/7141202128323739648`) with automated retries and dead-letter queues.
- **Long-Term State (Memory Bank & Partitioned Firestore):** Persistent counterparty memory that survives across multi-week sessions. Decoupled processes can invoke `recall("Meridian")` to retrieve verified deal knowledge without database dependencies, backed by append-only transactional event streams.
- **Zero-Trust Access (Agent Identity):** Cryptographic per-workstream IAM principals with enforced negative isolation (`Legal ⊬ Finance`, `Finance ⊬ HR`, cross-deal isolation) and strict agent→data / human→output AuthZ.
- **Routing & Policy (Agent Gateway):** A high-performance deny-default policy engine on Cloud Run that validates cross-workstream queries, enforces machine-readable verdicts (`allow/aggregate_permitted`, `deny/no_policy`), and returns aggregate-only projections.
- **Inline Guardrails (Model Armor):** Managed security template (`diligence-room-d7`) combined with project inspection rules. Built with a strict **fail-closed architecture** to quarantine prompt injections and jailbreaks before model invocation.
- **Telemetry & Tracing (Agent Observability):** OpenTelemetry GenAI semantic-convention spans streamed to Google Cloud Trace, linking source document chunks to executive findings through durable `audit_trace_id` headers.
- **Foundation Models (Google ADK & Gemini 3.5 Flash):** Google ADK (`google-adk` 2.7.0) powers the 8-agent reasoning fleet with Gemini 3.5 Flash on Vertex AI (`global` location) for structured domain extraction.
- **Tier-1 Ingestion Sentinel (Gemma 4):** `gemma-4-26b-a4b-it` on the Gemini Developer API serves as a low-cost, zero-shot tripwire for adversarial injection screening and PII hints.
- **Compliance & Sovereignty Plane:** Cloud KMS Customer-Managed Encryption Keys (CMEK) across US & EU (`deal-falcon-primary`), Cloud DLP inspect templates for HR salary masking, and zero service-account keys (ADC & Workload Identity only).

---

## Demo & Verification

- **Repository:** [github.com/divagr18/diligence-room](https://github.com/divagr18/diligence-room)
- **Live Dashboard:** [diligence-room-dashboard](https://diligence-room-dashboard-378831539922.asia-south1.run.app)
- **Hosted Gateway:** [gateway-edge](https://gateway-378831539922.asia-south1.run.app)
- **Demo Walkthrough:** [YouTube (4-Minute Full Replay)](https://youtu.be/oCu2HfN85Ec) (VIDEO LINK)

---

## Closing Thought

Autonomous AI agents do not need to be unconstrained black boxes. When built on zero-trust foundations—where documents are treated as adversaries, agents operate under strict isolation, and humans retain the ultimate approval keys—agent fleets can transform the most complex enterprise workflows into defensible, transparent, and auditable outcomes.

