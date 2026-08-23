# Timing Sheet, 4-Minute Demo Video (D13-M4)

Status: LOCKED. Locked 2026-08-23 after three timed dress rehearsals at HEAD `a178b6d`.

Hard constraint from vision §17: 240 seconds (4:00) total. The video opens with the
friction + twist framing and proves Google Cloud deployment with a console shot. Beat 3
below is one unedited replay take, terminal and dashboard side by side, timed through
`runtime/replay.py` wall-clock; every other beat is narration plus footage, timed by
stopwatch. CP2 freeze is active (`docs/decisions/cp2.md`), so rehearsals fix only
blocking issues. Three runs found none.

## Locked beat table

Beat numbers 1 through 7 here map to vision §17 beat numbers 0 through 6, in order.

| Beat | Title | Seconds |
|---|---|---|
| 1 | Friction + twist | 30 |
| 2 | Assemble the fleet | 20 |
| 3 | Unedited execution, replay take with terminal + dashboard side-by-side | 60 |
| 4 | Cross-agent discovery | 40 |
| 5 | Attack the system | 30 |
| 6 | Upgrade + rollback | 25 |
| 7 | Human approval + audit | 35 |

Total: 30 + 20 + 60 + 40 + 30 + 25 + 35 = 240 s, exactly the 4:00 budget.

## How the numbers were measured

- **Replay wall-clock (beat 3):** `runtime/replay.py` `run_replay` against the Firestore
  emulator, fresh deal namespace per run, seed 42, speed 1000. The accelerated clock
  compresses only the pacing of the 14-day scenario timeline, the same seam as
  `tests/test_replay.py`, so all processing stays genuine: ingestion, Gemma sentinel
  tripwire, Model Armor project rules, routing, evidence-gated findings, coordinator
  synthesis, registry upgrade/rollback, and the human-approval negotiation. Wall-clock
  is `ReplayReport.duration_s` from `time.monotonic`.
- **Manual narration:** each beat's locked narration script read aloud at voiceover pace
  (about 2.3 words per second), timed by stopwatch, rounded to 0.1 s.
- **Spare budget:** the gap between measured totals and 240 s is silent footage: dashboard
  walk-up, trace expansion in the Findings view, the 10 s kill-and-resume cameo folded
  into beat 4 (vision §19.4), the side-by-side framing of beat 3, and the CMEK / VPC-SC /
  region console shots in beat 7.

Locked narration seconds per beat, from the final rehearsal: 22.1, 12.0, 19.0, 15.1,
13.2, 10.1, 16.9 (sum 108.4 s of spoken word inside the 240 s budget). Every figure
sits under its beat's allocation in the locked table.

## Dress rehearsal log

All runs on 2026-08-23 at HEAD `a178b6d`, emulator-backed, fully offline. Every run
injected all 49 scenario events, created the 5 golden-set findings, and was
deterministic under `run_id` `replay-bdd640fb0667` (seed 42).

| Run | Replay wall-clock, beat 3 (s) | Narration, all beats (s) | Measured total (s) | Headroom vs 240 (s) |
|---|---|---|---|---|
| R1 | 2.05 | 112.3 | 114.4 | 125.6 |
| R2 | 1.17 | 109.8 | 111.0 | 129.0 |
| R3 | 0.95 | 108.4 | 109.4 | 130.6 |

Rehearsal notes:

- R1 ran cold (first emulator boot of the session) and still cleared the budget by more
  than two minutes, so beat 3's 60 s allocation holds with a wide margin.
- R2 and R3 tightened narration only. No blocking issues surfaced, so nothing was cut
  and no feature work was touched, per the CP2 freeze.
- The plan §10 contingency (trim beat 5 upgrade/rollback narration, keep the visual) was
  never needed: beat 6 measured 10.1 s spoken against its 25 s allocation.

## Lock rationale

Every beat's measured actual cleared its locked allocation in all three rehearsals.
Beat 3's replay wall-clock peaked at 2.05 s against its 60 s allocation, total spoken
narration peaked at 112.3 s against the 240 s budget, and every per-beat narration
figure above sits under its own beat's allocation. The locked allocation matches the
vision §17 table exactly, so recording follows this sheet with no re-timing. If a
recording take overruns, the only sanctioned trim is beat 6's narration
(upgrade/rollback), keeping its visual.
