"""Crash-resume tests (BUILD_PLAN D9-M3, vision §19.4).

Agent runs checkpoint state transitions to the append-only event log. Killing
a run mid-run and restarting resumes from the last checkpoint without
duplicate findings (idempotency) and without lost work: every completed step
is an event, a checkpointed step is never re-executed, and the step-level
work itself is idempotent via stable finding ids.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from google.cloud import firestore

from agents.fleet import run_workstream_offline
from memory.event_log import EventLog
from memory.findings import FindingsStore
from registry.models import Workstream
from runtime.checkpoint import RunCheckpointer, run_with_checkpoints
from runtime.events import EventType

DEAL = "deal-falcon"
RUN = "day9-crash-resume-run"


class _KillSwitch:
    """Raises exactly once to simulate a mid-run crash, then lets work proceed."""

    def __init__(self) -> None:
        self.armed = True

    def wrap(self, inner: Callable[[], str]) -> Callable[[], str]:
        def guarded() -> str:
            if self.armed:
                self.armed = False
                raise SystemError("simulated mid-run crash")
            return inner()

        return guarded


def _steps(client: firestore.Client) -> list[tuple[str, Callable[[], str]]]:
    return [
        ("legal", lambda: run_workstream_offline(client, DEAL, Workstream.LEGAL)),
        ("finance", lambda: run_workstream_offline(client, DEAL, Workstream.FINANCE)),
        ("hr", lambda: run_workstream_offline(client, DEAL, Workstream.HR)),
    ]


def _finding_count(client: firestore.Client) -> int:
    store = FindingsStore(client)
    return sum(
        len(store.list_for_workstream(DEAL, ws))
        for ws in (Workstream.LEGAL, Workstream.FINANCE, Workstream.HR)
    )


def _checkpoint_steps(client: firestore.Client) -> list[str]:
    import json

    out: list[str] = []
    for record in EventLog(client).events(DEAL):
        if record.type != EventType.RUNNER_CHECKPOINT.value:
            continue
        payload = json.loads(record.payload_json)
        if payload.get("run_id") == RUN:
            out.append(str(payload.get("step_id")))
    return out


class TestCrashResume:
    def test_kill_mid_run_then_resume_completes_without_duplicates(
        self, firestore_client: firestore.Client
    ) -> None:
        kill = _KillSwitch()
        steps = _steps(firestore_client)
        steps[2] = (steps[2][0], kill.wrap(steps[2][1]))

        with pytest.raises(SystemError, match="simulated mid-run crash"):
            run_with_checkpoints(firestore_client, DEAL, RUN, steps, actor="runner")
        assert _finding_count(firestore_client) == 2
        assert _checkpoint_steps(firestore_client) == ["legal", "finance"]

        report = run_with_checkpoints(firestore_client, DEAL, RUN, steps, actor="runner")
        assert report.completed is True
        assert report.skipped == ("legal", "finance")
        assert report.executed == ("hr",)
        assert _finding_count(firestore_client) == 3
        assert _checkpoint_steps(firestore_client) == ["legal", "finance", "hr"]

    def test_completed_run_is_fully_skipped_on_rerun(
        self, firestore_client: firestore.Client
    ) -> None:
        steps = _steps(firestore_client)
        first = run_with_checkpoints(firestore_client, DEAL, RUN, steps, actor="runner")
        assert first.executed == ("legal", "finance", "hr")
        assert first.skipped == ()

        second = run_with_checkpoints(firestore_client, DEAL, RUN, steps, actor="runner")
        assert second.completed is True
        assert second.executed == ()
        assert second.skipped == ("legal", "finance", "hr")
        assert _finding_count(firestore_client) == 3

    def test_distinct_runs_do_not_share_checkpoints(
        self, firestore_client: firestore.Client
    ) -> None:
        steps = _steps(firestore_client)
        run_with_checkpoints(firestore_client, DEAL, RUN, steps, actor="runner")
        checkpointer = RunCheckpointer(firestore_client, DEAL, "another-run")
        assert checkpointer.is_completed("legal") is False

    def test_checkpoint_is_idempotent_per_step(self, firestore_client: firestore.Client) -> None:
        checkpointer = RunCheckpointer(firestore_client, DEAL, RUN)
        seq_first = checkpointer.record("legal", actor="runner")
        events_before = len(EventLog(firestore_client).events(DEAL))
        assert checkpointer.is_completed("legal") is True
        assert checkpointer.is_completed("finance") is False
        assert len(EventLog(firestore_client).events(DEAL)) == events_before
        assert seq_first >= 1
