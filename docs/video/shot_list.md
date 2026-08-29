# Demo Video Shot List — Revision 3 (recording cut)

Supersedes the beat ordering in `docs/timing_sheet.md` for the recorded cut.
The seven locked beats survive intact; Rev. 3 adds a cold open, folds the
architecture diagram into beat 2, and moves Google Cloud console proof forward
so a judge who stops watching early has already seen the deployment evidence.

**Total: 240 s (4:00 hard cap, vision §17).** Narration pace ~2.3 words/s.

## Why the ordering changed

The rubric weights *Demo & Production Readiness* at 30%, and names two things
explicitly: "live unedited demo clarity" and "backend running on Google Cloud
(visible console/dashboard proof)". In the locked sheet both land in beat 7,
after 3:35 of build-up. Devpost's own guidance and the ADK-hackathon winners
converge on front-loading the payoff, so Rev. 3 shows the CRITICAL finding and
the deployed URL inside the first 20 seconds, then earns it back over the
remaining beats.

## Shot table

| # | Beat | Sec | Cume |
|---|---|---|---|
| 0 | Cold open — the conclusion first | 20 | 0:20 |
| 1 | Friction + the twist | 25 | 0:45 |
| 2 | Assemble the fleet + architecture | 20 | 1:05 |
| 3 | Unedited execution on live GCP | 65 | 2:10 |
| 4 | Cross-agent discovery + crash-resume cameo | 40 | 2:50 |
| 5 | Attack the system | 25 | 3:15 |
| 6 | Upgrade, regression, rollback | 20 | 3:35 |
| 7 | Human approval + console proof | 25 | 4:00 |

---

### Beat 0 — Cold open (20 s)

**On screen:** deployed dashboard on `*.run.app`, Findings view, the CRITICAL
Meridian customer-exit finding open. Browser URL bar visible the whole time.

**Narration (~46 w):**
> This is a live deal room running on Google Cloud. One critical finding:
> the target's largest customer can walk away if the deal closes. Four
> specialist agents each found one piece of that. None of them was permitted
> to reach this conclusion alone. Here's how that works.

**Proves:** deployment proof + value proposition, both inside 20 seconds.

---

### Beat 1 — Friction + the twist (25 s)

**On screen:** the Vantage Robotics data room — 20 documents, mixed formats.

**Narration (~57 w):**
> M&A diligence burns analyst-weeks reading vendor documents that are
> deliberately disorganised. The obvious build is a summariser. That is the
> wrong shape. In a real data room the documents are adversaries, the agents
> are principals with identities, and memory is partitioned by policy — not
> by convenience.

**Proves:** Innovation & Operational Utility framing (40%).

---

### Beat 2 — Assemble the fleet + architecture (20 s)

**On screen:** Registry view — 8 agents with versions and approval state.
Cut to `docs/diagram/architecture.svg` for the last 8 s.

**Narration (~46 w):**
> Eight specialists: Legal, Finance, HR, IP and Technology, Tax, Regulatory,
> ESG, Real Estate. Each is a versioned manifest with an approval state and a
> rollback target. Underneath: ADK agents on Vertex AI Agent Engine, Cloud
> Run, Firestore, Pub/Sub, Model Armor, Cloud Trace.

**Proves:** Registry/discovery/versioning + "clean architecture diagram".

---

### Beat 3 — Unedited execution on live GCP (65 s) — ONE CONTINUOUS TAKE

**On screen:** split — terminal left, deployed dashboard right. No cuts.

1. Terminal shows the command and the live target banner
   (`[target] LIVE firestore project=diligence-room-live database=diligence`).
2. Documents ingest: format detection → Gemma sentinel → Model Armor →
   classification → routing.
3. Dashboard findings count climbs 0 → 5 by live polling; no page reload.

**Narration (~105 w):** narrate only what appears; do not pre-announce results.
> This is one take, no cuts. The replay drives the real pipeline against live
> Firestore — the pacing is accelerated, nothing else is. Every document is
> hostile until proven otherwise: format detection, then the Gemma sentinel,
> then Model Armor, then classification and routing to a workstream.
> Findings appear only when an agent can cite an evidence span in a source
> document. Watch the dashboard — that is live Firestore polling, not a
> scripted animation. Five findings, forty-nine events, all of it appended to
> an audit log I can replay.

**Proves:** live unedited demo, async runtime, deployment proof.

---

### Beat 4 — Cross-agent discovery + cameo (40 s)

**On screen:** Legal's change-of-control finding → Gateway decision payload →
Finance returns `18.3%` → Coordinator CRITICAL → trace expanded.
Last 10 s: crash-resume cameo picture-in-picture, bottom right.

**Narration (~92 w):**
> Legal finds a change-of-control termination right for Meridian. It cannot
> read Finance's data — different principal, different partition. So it asks,
> through the Gateway. The policy engine is deny-by-default; this request is
> allowed, but aggregate-only. Finance returns one number — eighteen point
> three percent of projected FY27 revenue — never the underlying model. Only
> once four workstreams independently name the same entity may the Coordinator
> synthesise CRITICAL. Bottom right: I kill an agent mid-run; it resumes from
> its checkpoint and creates no duplicate.

**Proves:** Gateway, identity isolation, multi-agent reasoning, failure tolerance.

---

### Beat 5 — Attack the system (25 s)

**On screen:** Security view — 20/20 blocked scorecard, quarantine feed, then
the denied cross-workstream write.

**Narration (~57 w):**
> Twenty red-team attacks: prompt injection, encoded payloads, exfiltration,
> cross-workspace state mutation. Twenty blocked, zero false positives on a
> twenty-document clean corpus. A poisoned contract instructs Finance to
> approve the deal and export the valuation model. Model Armor quarantines it
> before it ever becomes agent context.

**Proves:** Model Armor, Identity, memory isolation (Fortified Fleet core).

---

### Beat 6 — Upgrade, regression, rollback (20 s)

**On screen:** Registry — Legal v2.4 → v2.5, shadow eval RED, rollback, finding
counts identical after.

**Narration (~46 w):**
> Legal v2.5 ships. The shadow harness replays a golden set against it and
> catches a regression the release notes did not mention. Roll back to v2.4 —
> deal memory intact, finding counts identical. Version and state are separate
> concerns here.

**Proves:** lifecycle maturity, state/version separation.

---

### Beat 7 — Human approval + console proof (25 s)

**On screen:** negotiation draft quoting evidence spans → deal lead approves →
`send_logged`. Then Cloud Console: Cloud Run services, Firestore, Cloud Trace
span for the finding's `audit_trace_id`.

**Narration (~57 w):**
> The fleet drafts the seller request, quoting every evidence span. Sending it
> is the one thing it may not do alone — that needs a human. Approved, and
> logged. Every finding carries a trace id that resolves in Cloud Trace, back
> to the source document. Autonomy where it's safe, a gate where it isn't.

**Proves:** confidence-gated autonomy, compliance, observability, GCP proof.

---

## Recording notes

- Beat 3 is the only beat that must be a single unbroken take. Everything else
  may be re-taken freely.
- Keep the browser URL bar visible in beats 0, 3, 4, 5, 7 — it is the cheapest
  continuous proof that this is a deployed service and not localhost.
- Lower-thirds `cards/b1.png … b7.png` map to beats 1–7; beat 0 runs clean.
- If a take overruns, the sanctioned trim is beat 6 narration, keeping its
  visual (carried over from the locked sheet).
