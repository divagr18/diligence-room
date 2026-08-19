# CUTLINE-1 Ruling — full negotiation spec proceeds (BUILD_PLAN D9-M5)

**Date:** 2026-08-20 (executed ahead of the plan's Sat 08-22 slot, same as
the pulled-forward Day-8 execution)
**Decision:** All four Day-9 failure-tolerance gates are GREEN well inside
the hour-4 bound, so **the full negotiation spec (redline templates, seller
requests, counterparty questions) proceeds as the Day-12 completion target
(D12-M6)**. Day 9 delivered the core configuration — draft generation +
approval state machine + logged send — which satisfies both cutline branches,
so nothing built is thrown away either way (vision §11, §24).

## Gate evidence

| Gate | Module | Evidence | Verdict |
|---|---|---|---|
| D9-M1 loop guard | `runtime/guards.py` | 10/10 — runaway terminated at bounds, partial state checkpointed, `run.bounds_exceeded` logged | GREEN |
| D9-M2 evidence gate | `agents/tools/finding_create.py` | fabricated spans rejected `evidence_unresolvable` + logged; 0.75 candidate cap; capped findings never auto-escalate | GREEN |
| D9-M3 crash-resume | `runtime/checkpoint.py` | 4/4 — kill→resume completes with zero duplicate findings; checkpoints live in the append-only log | GREEN |
| D9-M4 negotiation core | `agents/negotiation/drafts.py` | 20/20 — full approval chain; every off-chain edge refused; sends only from `approved` | GREEN |

Full battery: 886 passed · mypy strict 170 files clean · ruff check + format
clean (receipt: `docs/evidence/d9-offline-gate.txt`).

## Ruling details

1. **Negotiation scope** — Day-12 target is the full spec: clause redlines,
   seller requests, counterparty clarification questions (D12-M6), building on
   the Day-9 core (confidence-gated drafts, stable draft ids, the
   draft→pending_approval→approved→send_logged state machine, auditable
   `negotiation.transition` events).
2. **No de-scope** — the minimal branch (draft + approval + logged send) is
   already delivered and stays as the floor; the Day-12 work extends it.
3. **Carried conditions** — external sends remain log-only until the deployed
   channel work; nothing leaves the room without human approval at any scope.
