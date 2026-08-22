# CP2 Ruling — GO (BUILD_PLAN D12-M7)

**Date:** 2026-08-23 (Day 12, gate window)
**Decision:** **GO** — keystone set verified item-by-item, all seven GREEN at HEAD
`fda0f5e`; Day 13 proceeds on schedule. The hard-freeze clause below was evaluated and
**not triggered** (no RED item).
**Evidence receipt:** [`docs/evidence/d12-checkpoint2.txt`](../evidence/d12-checkpoint2.txt)
(every count re-run at HEAD and transcribed as printed; lesson from `f9ba043`).

## Keystone audit — item by item

Per vision §24 and the BUILD_PLAN cutline table the keystone set is never cut: Customer X cross-workstream finding ·
Model Armor quarantine beat · Identity DENY beat · memory-isolation negative tests ·
evidence gate + loop guard · deployment proof. Each item re-verified at `fda0f5e`.

| # | Keystone item | Verdict | Evidence at HEAD (all commands re-run, offline emulator) |
|---|---|---|---|
| 1 | Customer X cross-workstream finding | **GREEN** | `tests/test_coordinator.py` — 10 passed. CRITICAL emerges only from multi-workstream synthesis (legal × finance × hr × ip_tech); removing any single deep workstream refuses synthesis; a tampered evidence span refuses. Dashboard serves SYN-001 with full trace + synthesis graph (`tests/test_dashboard_api.py`, inside the 158-passed Day-12 surface run). |
| 2 | Model Armor quarantine beat | **GREEN** | `tests/test_quarantine.py tests/test_pipeline.py` — 20 passed. Quarantine record write, lineage `security_status` flip, armor blocks after classify → quarantine + security event, never routed. Live shell served 20 quarantined records at `/api/security`. |
| 3 | Identity DENY beat | **GREEN** | `tests/test_gateway_e2e.py tests/test_gateway_decide.py tests/test_authz.py tests/test_human_authz.py` — 154 passed. Deny-default seed, rolling rate limit, direct read of a linked finding denied (`"decision": "deny"` audited), role-scoped human output AuthZ. |
| 4 | Memory-isolation negative tests | **GREEN** | `tests/test_isolation.py tests/test_partitions.py` — 142 passed. Cross-partition reads refused; no deal/workstream leakage. Independently re-proven by the rollback demo: registry versioning never reaches `deals/{id}/findings/{fid}`. |
| 5 | Evidence gate | **GREEN** | `tests/test_evidence_gate.py tests/test_tool_finding_create.py` — 21 passed. Category required, uncited claims rejected, candidate cap (0.75) enforced. The CP2 approval-beat finding itself was created through this same evidence-gated `finding_create` path (`decision=created`). |
| 6 | Loop guard | **GREEN** | `tests/test_guards.py tests/test_crash_resume.py` — 14 passed. Runaway worker terminated at the iteration bound, partial state checkpointed, `run.bounds_exceeded` logged; crash-resume restores from checkpoint. The architectural-discipline answer (vision §19) stands. |
| 7 | Deployment proof | **GREEN** | `tests/test_dashboard_deploy.py tests/test_cloud_run_plan.py tests/test_data_room_plan.py tests/test_registry_server.py` — 30 passed. Cloud Run + data-room plans shape-valid, write-only gate refuses without `--confirm-live`. Frontend proven live: `npm run build` clean (275.21 kB JS) and `node qa-contract.mjs` ALL PASS against the running dev shell (API on emulator). Live deploys remain flag-gated; offline proof is the gate (doctrine §1). |

## Day-12 gate checks (plan §9)

The four verifiable checkbox items are GREEN, transcript-verified in the receipt (the
fifth checkbox — recording `cp2.md`, noting HARD FREEZE if any item is red — is this file,
with the freeze clause stated below):

1. **Rollback demo repeatable twice — GREEN.** `scripts/run_d12_rollback_evidence.py`
   ran the full beat twice on isolated emulator projects. Both rounds:
   seed 8 manifests → publish Legal v2.5.0 (`approved=False`, `rollback_target=2.4.0`) →
   harness **RED** (`missing=['contract_meridian_logistics.pdf']`) → rollback to 2.4.0 →
   harness **GREEN** (`missing=[]`, `downgraded=0`).
2. **Scorecard renders the 20-attack results — GREEN.** `GET /api/security` with a live
   emulator client ran the real ledger: `total_blocked=20`, `quarantined=20`, groups
   Prompt Injection 8/8, Exfiltration 5/5, Cross-Workstream Leak 4/4, Tool Poisoning /
   Cross-Deal 3/3. No smoothing; Security view compiles into the production bundle and
   passes the design contract (`qa-contract.mjs`).
3. **Approval beat — GREEN.** Draft → human approve → logged send over HTTP:
   `POST /api/negotiation/drafts` → `pending_approval`, approve by
   `deal-lead@deal-falcon` → `approved`, send → `send_logged`. Visible in Finding-view
   input (`GET /api/negotiation?finding_id=…` lists the draft at `send_logged`) and in the
   deal event log: 4 `negotiation.transition` events, final row `to_state=send_logged`.
4. **Battery + build — GREEN.** `uv run pytest tests/ -q` 1047 passed, 2 warnings in
   26.21s; `uv run mypy .` clean in 198 source files; `uv run ruff check .` all passed;
   `uv run ruff format --check .` 212 files formatted; `npm run build` clean.

## Deliberate regression flow (recorded, as required)

The Day-12 versioning story is proven with a real regression, not a simulated one:

1. **Publish:** Legal v2.5.0 registered unapproved with `rollback_target=2.4.0`; its
   producer is the deliberately weakened `_legal_fact` (title without "termination right",
   summary without "90 days").
2. **RED:** the shadow harness (strict exact diff on title + severity + affected_entities
   against the 20-doc golden set) fails the candidate: the CoC pin is missing
   (`contract_meridian_logistics.pdf`).
3. **Findings survived:** rollback touches only the registry manifest. Finding counts were
   identical before/after in both rounds:
   `{'legal': 1, 'finance': 1, 'hr': 1, 'ip_tech': 1}` — memory is
   `deals/{id}/findings/{fid}` partitioned, not version-bound.
4. **GREEN:** the restored 2.4.0 fleet re-runs the harness green in a fresh deal; the
   pinned CoC finding is regenerated by the baseline producer.

## Freeze clause (standing)

Per plan §9 and the BUILD_PLAN cutline table (vision §24): **if any keystone item is RED, hard feature freeze —
Days 13-14 become polish + recording only.** All seven items are GREEN, so the clause is
not triggered; it remains the standing rule for any later regression before submission.

## Inputs reviewed

| Evidence | Location | Verdict |
|---|---|---|
| CP2 gate battery + live-shell transcripts | `docs/evidence/d12-checkpoint2.txt` | GREEN |
| Registry rollback receipt (D12-M4) | `docs/evidence/d12-registry-rollback.txt` | GREEN |
| CUTLINE-1 ruling (negotiation full spec delivered) | `docs/decisions/cutline1.md` | honored |
| Commits `f9ba043..fda0f5e` (7): corpus → golden set → harness → ledger 20 → rollback → scorecard → negotiation | `git log` | GREEN |
