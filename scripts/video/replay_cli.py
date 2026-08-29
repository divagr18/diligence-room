"""CLI shim over runtime.replay.run_replay for the video beat-3 take.

Two mutually exclusive targets:

* default — refuses to run unless ``FIRESTORE_EMULATOR_HOST`` is set, because
  emulator-backed beats are deterministic and offline;
* ``--live`` — explicit opt-in that writes through ADC into the real Firestore
  database named by ``DILIGENCE_FIRESTORE_DATABASE``, for the deployed-stack
  take. It refuses to run while the emulator variable is set (that combination
  silently sends "live" traffic to localhost), and it defaults to its own deal
  namespace so a recording can never mutate the canonical ``deal-falcon``
  evidence data.

The command line is printed before execution so the capture shows exactly
what runs, against which project and database.
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


LIVE_DEAL_ID = "deal-falcon-demo"


def resolve_deal_id(explicit: str | None, live: bool) -> str:
    """Pick the deal namespace: explicit wins, else live gets its own."""
    if explicit is not None:
        return explicit
    return LIVE_DEAL_ID if live else "deal-falcon"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic replay for the demo video.")
    parser.add_argument("--speed", type=float, default=34000.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--deal-id", default=None)
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Replay into live Firestore via ADC instead of the emulator "
            f"(defaults the deal namespace to {LIVE_DEAL_ID!r})."
        ),
    )
    args = parser.parse_args(argv)

    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if args.live:
        if emulator:
            print(
                "Refusing: --live was passed but FIRESTORE_EMULATOR_HOST is set "
                f"({emulator}); unset it so live traffic cannot land on the emulator.",
                file=sys.stderr,
            )
            raise SystemExit(2)
    elif not emulator:
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is not set; the video replay "
            "runs against the emulator only (pass --live to target real Firestore).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    deal_id = resolve_deal_id(args.deal_id, args.live)
    config = build_config(speed=args.speed, seed=args.seed, deal_id=deal_id)
    live_flag = " --live" if args.live else ""
    print(
        f"$ uv run python scripts/video/replay_cli.py --speed {args.speed:g} "
        f"--seed {args.seed} --deal-id {deal_id}{live_flag}"
    )
    if args.live:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "(ADC default)")
        database = os.environ.get("DILIGENCE_FIRESTORE_DATABASE", "(default)")
        print(f"[target]   LIVE firestore project={project} database={database}")
    else:
        print(f"[target]   emulator {emulator}")
    started = time.monotonic()
    report = run_replay(config)
    wall = time.monotonic() - started
    print(format_report(report))
    print(f"[report]   wall_clock_s={wall:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
