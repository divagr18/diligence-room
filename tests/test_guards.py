"""Loop guard tests (BUILD_PLAN D9-M1, vision §19.2).

Each agent run is bounded: max iterations, max tool-call budget, max
wall-clock per step, and a token budget. A run that exceeds bounds is
terminated (it never loops forever), its partial state is checkpointed, and
the event is logged as ``run.bounds_exceeded`` — the architectural-discipline
answer to *what happens if a worker agent loops?*
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from runtime.events import EventEnvelope, EventType, InMemoryPublisher
from runtime.guards import (
    BoundedOutcome,
    LoopGuard,
    LoopGuardTripped,
    RunBounds,
    TripReason,
    run_bounded,
)

_BOUNDS = RunBounds(
    max_iterations=10,
    max_tool_calls=5,
    max_step_wall_clock_s=1.0,
    token_budget=100,
)


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def advance(self, seconds: float) -> None:
        self.t += seconds

    def __call__(self) -> float:
        return self.t


class TestRunBoundsValidation:
    def test_non_positive_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            RunBounds(max_iterations=0, max_tool_calls=1, max_step_wall_clock_s=1.0, token_budget=1)
        with pytest.raises(ValueError, match="max_tool_calls"):
            RunBounds(max_iterations=1, max_tool_calls=0, max_step_wall_clock_s=1.0, token_budget=1)
        with pytest.raises(ValueError, match="max_step_wall_clock_s"):
            RunBounds(max_iterations=1, max_tool_calls=1, max_step_wall_clock_s=0.0, token_budget=1)
        with pytest.raises(ValueError, match="token_budget"):
            RunBounds(max_iterations=1, max_tool_calls=1, max_step_wall_clock_s=1.0, token_budget=0)


class TestBoundedRuns:
    def test_within_bounds_completes(self) -> None:
        def work(guard: LoopGuard) -> str:
            for i in range(3):
                guard.begin_step({"iteration": i})
                guard.record_tool_call()
                guard.record_tokens(10)
            return "finished"

        outcome = run_bounded(work, _BOUNDS)
        assert outcome.completed is True
        assert outcome.trip_reason is None
        assert outcome.result == "finished"
        assert outcome.iterations == 3
        assert outcome.tool_calls == 3
        assert outcome.tokens == 30

    def test_runaway_loop_is_terminated_at_iteration_bound(self) -> None:
        def work(guard: LoopGuard) -> None:
            i = 0
            while True:
                guard.begin_step({"iteration": i})
                i += 1

        outcome = run_bounded(
            work,
            RunBounds(
                max_iterations=3,
                max_tool_calls=100,
                max_step_wall_clock_s=100.0,
                token_budget=10_000,
            ),
        )
        assert outcome.completed is False
        assert outcome.trip_reason is TripReason.ITERATIONS
        assert outcome.iterations == 3

    def test_tool_call_budget_trips(self) -> None:
        def work(guard: LoopGuard) -> None:
            guard.begin_step()
            for _ in range(10):
                guard.record_tool_call()

        outcome = run_bounded(
            work,
            RunBounds(
                max_iterations=10,
                max_tool_calls=2,
                max_step_wall_clock_s=100.0,
                token_budget=10_000,
            ),
        )
        assert outcome.completed is False
        assert outcome.trip_reason is TripReason.TOOL_CALLS
        assert outcome.tool_calls == 2

    def test_wall_clock_per_step_trips(self) -> None:
        clock = _FakeClock()

        def work(guard: LoopGuard) -> None:
            guard.begin_step({"step": 0})
            clock.advance(5.0)
            guard.begin_step({"step": 1})

        outcome = run_bounded(work, _BOUNDS, now=clock)
        assert outcome.completed is False
        assert outcome.trip_reason is TripReason.WALL_CLOCK

    def test_token_budget_trips(self) -> None:
        def work(guard: LoopGuard) -> None:
            guard.begin_step()
            guard.record_tokens(60)
            guard.record_tokens(60)

        outcome = run_bounded(
            work,
            RunBounds(
                max_iterations=10,
                max_tool_calls=10,
                max_step_wall_clock_s=100.0,
                token_budget=100,
            ),
        )
        assert outcome.completed is False
        assert outcome.trip_reason is TripReason.TOKENS
        assert outcome.tokens == 120


class TestGuardDirectly:
    def test_guard_raises_when_iterations_exhausted(self) -> None:
        guard = LoopGuard(_BOUNDS)
        for _ in range(_BOUNDS.max_iterations):
            guard.begin_step()
        with pytest.raises(LoopGuardTripped):
            guard.begin_step()


class TestTripHandling:
    def test_trip_checkpoints_partial_state_and_emits_event(self) -> None:
        checkpoints: list[Mapping[str, object]] = []
        publisher = InMemoryPublisher()

        def work(guard: LoopGuard) -> None:
            for i in range(10):
                guard.begin_step({"iteration": i})

        outcome = run_bounded(
            work,
            RunBounds(
                max_iterations=2,
                max_tool_calls=10,
                max_step_wall_clock_s=100.0,
                token_budget=100,
            ),
            publisher=publisher,
            deal_id="deal-falcon",
            actor="worker-agent@deal-falcon",
            checkpoint_sink=checkpoints.append,
        )
        assert outcome.completed is False
        assert checkpoints, "partial state must be checkpointed on trip"
        assert checkpoints[-1]["iteration"] == 1
        assert outcome.partial_state["iteration"] == 1
        types = [EventEnvelope.from_json(p).type for p in publisher.published]
        assert EventType.RUN_BOUNDS_EXCEEDED in types

    def test_trip_without_publisher_returns_outcome_quietly(self) -> None:
        def work(guard: LoopGuard) -> None:
            while True:
                guard.begin_step()

        outcome = run_bounded(
            work,
            RunBounds(
                max_iterations=1,
                max_tool_calls=1,
                max_step_wall_clock_s=1.0,
                token_budget=1,
            ),
        )
        assert outcome.completed is False
        assert outcome.trip_reason is TripReason.ITERATIONS

    def test_completed_run_has_empty_partial_state(self) -> None:
        outcome = run_bounded(lambda guard: "ok", _BOUNDS)
        assert isinstance(outcome, BoundedOutcome)
        assert outcome.trip_reason is None
        assert dict(outcome.partial_state) == {}
