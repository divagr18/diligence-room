# Checkpoint 1 — Day-6 gate evidence (BUILD_PLAN Phase 3)

Checkpoint-1 eve gate decisions are recorded Day 7 AM per BUILD_PLAN; this
pack captures the Day-6 evidence that feeds them.

## Gate checklist

| Gate item | Status | Evidence |
|---|---|---|
| Deep four produce independent findings, each in its own partition | GREEN (offline deterministic) | `tests/test_deep_four.py` (8 tests) — `gates.txt` |
| Deep four produce independent findings (LIVE, real Flash, manifest-built agents) | GREEN (4/4) | `../d6-live-fleet.txt` |
| All eight workstream agents registered | GREEN | `tests/test_agent_factory.py` + seed (`total manifests=8` live) |
| Agent factory instantiates from manifests (identity bind, toolset, model from approved version) | GREEN | `tests/test_agent_factory.py` (6 tests) |
| Retry + idempotency runner | GREEN | `tests/test_runner.py` (8 tests) |
| Failure drill: malformed event -> DLQ, no crash, no partial state | GREEN | `tests/test_failure_drill.py` (4 tests) — `gates.txt` |
| Red-team batch #1 fixtures trip the sentinel layer | GREEN | `tests/test_redteam_fixtures.py` (10 tests) — `gates.txt` |

## Quality battery (this checkpoint)

- `battery.txt`: `644 passed, 2 warnings in 18.31s`
- mypy --strict over 16 packages: `Success: no issues found in 138 source files`
- pre-commit (ruff check / ruff format / mypy strict / gitleaks): all Passed

## Live window

`../d6-live-fleet.txt`: real gemini-3.5-flash agent loops for legal, finance,
hr, ip_tech built from registry manifests; 4/4 produced evidence-gated findings;
project torn down to `DELETE_REQUESTED` (verified 2026-08-17T08:56:59Z UTC).

## Honest stand-ins carried forward

- Gemma sentinel + Model Armor + Document AI remain offline/red-path until their
  dedicated live days (Day 7 Armor, DLP/OCR later); disclosed in each evidence file.
- The offline deep-four producers (`agents/fleet.py`) are the deterministic proof
  of the write path; the live window proves the same path with the real model.
