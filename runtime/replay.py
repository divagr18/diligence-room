"""Accelerated-clock replay engine (BUILD_PLAN D13-M2, vision §16).

Replays a timestamped scenario (``data/scenarios/project_falcon.json``) into
the **real** pipeline at an accelerated clock — only the pacing between
events is compressed (``delta / speed``), never the processing: uploads and
attacks run through ``ingest_blob``, findings through the evidence-gated
fleet producers and coordinator synthesis, upgrade/rollback through the
registry, negotiation through the approval state machine (per-type injection
lives in ``runtime.replay_engine``).

Determinism: events replay in timestamp order, ``run_id`` derives from the
seed alone, and every finding/draft id is content-derived — two runs with
the same seed against fresh deal namespaces produce identical findings. The
``run_id`` is stamped into the ``replay.run`` / ``replay.event`` spans that
parent every pipeline span. Fully offline: emulator-backed Firestore, no
network egress; each run targets a fresh deal namespace.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from google.cloud import firestore
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.tracing import setup_tracing, stage_span, tracer_from
from runtime.replay_engine import ReplayEngine

_ROOT: Final = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIO_PATH: Final = _ROOT / "data" / "scenarios" / "project_falcon.json"
_RUN_ID_PREFIX: Final = "replay-"


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """One accelerated replay: which scenario, which deal, how fast."""

    scenario_path: Path
    deal_id: str = "deal-falcon"
    seed: int = 42
    speed: float = 100.0
    client: firestore.Client | None = None

    def __post_init__(self) -> None:
        if self.speed <= 0:
            raise ValueError(f"speed must be positive, got {self.speed}")


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """Outcome of one replay run.

    ``deterministic`` confirms the run-time invariants held: the scenario was
    already timestamp-ordered as written and every event was injected.
    """

    run_id: str
    events_injected: int
    findings_created: int
    duration_s: float
    deterministic: bool


def derive_run_id(seed: int) -> str:
    """Derive the replay run id from the seed alone (deterministic)."""
    rng = random.Random(seed)
    return f"{_RUN_ID_PREFIX}{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _load_scenario(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("scenario root must be a JSON object")
    raw_events = envelope.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("scenario envelope must contain an 'events' list")
    events: list[dict[str, Any]] = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise ValueError("every scenario event must be a JSON object")
        events.append(raw)
    return envelope, events


def run_replay(
    config: ReplayConfig,
    *,
    sleep: Callable[[float], None] = time.sleep,
    span_exporter: SpanExporter | None = None,
) -> ReplayReport:
    """Replay the scenario at ``speed``x clock into the real pipeline.

    ``sleep`` paces the timeline (delta / speed) and is injectable so tests
    can mock the clock; everything below the pacing seam is genuine.
    ``span_exporter`` is the live/test seam for trace inspection.
    """
    started = time.monotonic()
    envelope, events = _load_scenario(config.scenario_path)
    ordered = sorted(events, key=lambda event: _parse_ts(str(event["ts"])))
    client = config.client if config.client is not None else firestore.Client()
    run_id = derive_run_id(config.seed)
    provider = setup_tracing(
        service_name="diligence-room-replay",
        exporter=span_exporter if span_exporter is not None else InMemorySpanExporter(),
    )
    tracer = tracer_from(provider)
    engine = ReplayEngine(client, config.deal_id, tracer, run_id)
    base_ts = _parse_ts(str(envelope["base_ts"])) if ordered else _parse_ts("1970-01-01T00:00:00Z")
    engine.prepare(base_ts)
    previous: datetime | None = None
    run_attributes: dict[str, str | int | float | bool] = {
        "replay.run_id": run_id,
        "replay.scenario": str(envelope.get("scenario_id", "")),
        "replay.deal": config.deal_id,
        "replay.seed": config.seed,
        "replay.speed": config.speed,
    }
    with stage_span(tracer, "replay.run", links=None, **run_attributes):
        for event in ordered:
            stamp = _parse_ts(str(event["ts"]))
            if previous is not None:
                sleep(max(0.0, (stamp - previous).total_seconds() / config.speed))
            previous = stamp
            engine.inject(event, stamp)
    return ReplayReport(
        run_id=run_id,
        events_injected=engine.events_injected,
        findings_created=engine.findings_created,
        duration_s=time.monotonic() - started,
        deterministic=ordered == events and engine.events_injected == len(ordered),
    )
