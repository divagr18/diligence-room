"""Crash-resume — resumable runs over the event log (BUILD_PLAN D9-M3, vision §19.4).

Agent runs checkpoint state transitions to the append-only event log. Kill a
process mid-run, restart, and the run resumes from the last checkpoint: a
checkpointed step is never re-executed, so no finding is created twice and no
work is lost. The event log itself is the checkpoint store — durable,
append-only, auditable.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, TypeVar

from google.cloud import firestore

from memory.event_log import EventLog
from runtime.events import EventType, new_event

_T = TypeVar("_T")

_CHECKPOINT_KIND: Final[str] = EventType.RUNNER_CHECKPOINT.value


@dataclass(frozen=True, slots=True)
class RunReport:
    """Resume semantics for one run: which steps executed vs were skipped."""

    run_id: str
    executed: tuple[str, ...]
    skipped: tuple[str, ...]
    completed: bool


class RunCheckpointer:
    """Checkpoints run state transitions into the append-only event log."""

    def __init__(self, client: firestore.Client, deal_id: str, run_id: str) -> None:
        self._log = EventLog(client)
        self._deal_id = deal_id
        self.run_id = run_id

    def is_completed(self, step_id: str) -> bool:
        """True when *step_id* already has a checkpoint event for this run."""
        for record in self._log.events(self._deal_id):
            if record.type != _CHECKPOINT_KIND:
                continue
            payload = json.loads(record.payload_json)
            if payload.get("run_id") == self.run_id and payload.get("step_id") == step_id:
                return True
        return False

    def record(self, step_id: str, actor: str, now: datetime | None = None) -> int:
        """Append the checkpoint event for *step_id*; returns its log seq."""
        event = new_event(
            self._deal_id,
            actor,
            EventType.RUNNER_CHECKPOINT,
            {"run_id": self.run_id, "step_id": step_id},
            now=now,
        )
        return self._log.append(event)


def run_with_checkpoints(
    client: firestore.Client,
    deal_id: str,
    run_id: str,
    steps: Sequence[tuple[str, Callable[[], _T]]],
    actor: str,
    now: datetime | None = None,
) -> RunReport:
    """Run ordered steps, checkpointing each completion to the event log.

    A step whose checkpoint already exists is skipped (never re-executed); a
    step that raises propagates the failure before its checkpoint is written,
    so a restart resumes exactly at that step without duplicates.
    """
    checkpointer = RunCheckpointer(client, deal_id, run_id)
    executed: list[str] = []
    skipped: list[str] = []
    for step_id, step in steps:
        if checkpointer.is_completed(step_id):
            skipped.append(step_id)
            continue
        step()
        checkpointer.record(step_id, actor, now=now)
        executed.append(step_id)
    return RunReport(
        run_id=run_id,
        executed=tuple(executed),
        skipped=tuple(skipped),
        completed=True,
    )
