# CP1 Ruling — GO as planned (BUILD_PLAN D7-M0)

**Date:** 2026-08-17 (executed ahead of the plan's Thu 08-20 slot)
**Decision:** **GO as planned** — full portfolio stays in scope; all eight
workstreams continue on the Rev. 2 parity track (vision §6 rev. 2); the
Day-9 cutline remains the only sanctioned de-scope trigger (vision §24).

## Inputs reviewed

| Evidence | Location | Verdict |
|---|---|---|
| Day-6 gate checklist (7 items) | `docs/evidence/cp1/CHECKPOINT1.md` | all GREEN |
| Quality battery | `docs/evidence/cp1/battery.txt` — 644 passed | GREEN |
| mypy strict / ruff / gitleaks | `docs/evidence/cp1/gates.txt` | GREEN |
| Deep four LIVE (real gemini-3.5-flash, manifest-built agents, evidence-gated findings) | `docs/evidence/d6-live-fleet.txt` — 4/4 PASS, teardown to DELETE_REQUESTED | GREEN |

## Additional input since the evidence pack

Post-checkpoint security review (2026-08-17) found and fixed 8 issues —
sentinel fail-closed tripwire + truncation bypass, evidence-gate AuthZ
(category required, unauthorized citations rejected + audited), factory
version-approval gate, structured duplicate reject, honest live-window env
contract, per-agent fault isolation, and end-to-end red-team pipeline
quarantine coverage. Battery now 659 passed; commits `7f5239a..53be73b`
pushed to `origin/main`. This strengthens, not weakens, the GO basis.

## Ruling details

1. **Portfolio** — stays in scope (no portfolio→roadmap de-scope).
2. **Agents 5–8** (tax, regulatory, esg, real_estate) — remain on scaffolding
   parity with real findings from their own document classes (Day-6 scaffold
   prompts + seed docs landed; live parity exercised on Day 12+).
3. **Deep four** — continue exercising cross-workstream (gateway), escalation
   (Day 7, D7-M6), and failure-tolerance paths.
4. **Day 7 proceeds** — Model Armor core (D7-M1..M3), red-team runner + ledger
   growth to 10 (D7-M4..M5), escalation path (D7-M6), with a small live window
   for one managed-Model-Armor sanitize call (operator-approved).

## Conditions carried forward

- Model Armor managed API is exercised live once (this day's window); the
  offline gate rides the project-rules layer + sentinel tripwire (disclosed
  stand-ins until then).
- Day-9 cutline (vision §24) is unaffected by this ruling.
