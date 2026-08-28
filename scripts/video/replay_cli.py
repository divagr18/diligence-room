"""CLI shim over runtime.replay.run_replay for the video beat-3 take.

Refuses to run unless ``FIRESTORE_EMULATOR_HOST`` is set: video beats are
emulator-backed by design (deterministic, offline, real pipeline below the
pacing seam). The command line is printed before execution so the capture
shows exactly what runs.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence

from runtime.replay import DEFAULT_SCENARIO_PATH, ReplayConfig, ReplayReport, run_replay


def build_config(speed: float, seed: int, deal_id: str) -> ReplayConfig:
    return ReplayConfig(
        scenario_path=DEFAULT_SCENARIO_PATH,
        deal_id=deal_id,
        seed=seed,
        speed=speed,
    )


def format_report(report: ReplayReport) -> str:
    lines = (
        f"[report]   run_id={report.run_id}",
        f"[report]   events_injected={report.events_injected}",
        f"[report]   findings_created={report.findings_created}",
        f"[report]   duration_s={report.duration_s:.2f} (<240s budget)",
        f"[report]   deterministic={report.deterministic}",
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic replay for the demo video.")
    parser.add_argument("--speed", type=float, default=34000.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--deal-id", default="deal-falcon")
    args = parser.parse_args(argv)

    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is not set; the video replay "
            "runs against the emulator only.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    config = build_config(speed=args.speed, seed=args.seed, deal_id=args.deal_id)
    print(
        f"$ uv run python scripts/video/replay_cli.py --speed {args.speed:g} "
        f"--seed {args.seed} --deal-id {args.deal_id}"
    )
    started = time.monotonic()
    report = run_replay(config)
    wall = time.monotonic() - started
    print(format_report(report))
    print(f"[report]   wall_clock_s={wall:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
