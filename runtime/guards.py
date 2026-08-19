"""Loop guard — bounded agent runs (BUILD_PLAN D9-M1, vision §19.2).

Each agent run is bounded: max iterations, max tool-call budget, max
wall-clock per step, and a token budget. A run that exceeds bounds is
terminated (the guard raises inside the loop), its partial state is
checkpointed, and the event is logged as ``run.bounds_exceeded`` (visible in
the Security view). This is the architectural-discipline answer to *what
happens if a worker agent loops?*
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from runtime.events import EventEnvelope, EventType, new_event

_T = TypeVar("_T")


class TripReason(StrEnum):
    ITERATIONS = "iterations_exceeded"
    TOOL_CALLS = "tool_calls_exceeded"
    WALL_CLOCK = "wall_clock_exceeded"
    TOKENS = "token_budget_exceeded"


class LoopGuardTripped(Exception):
    """Raised inside a bounded run at the moment a bound is exceeded."""

    def __init__(self, reason: TripReason, detail: str) -> None:
        super().__init__(f"loop guard tripped: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class RunBounds:
    """Per-run limits (vision §19.2): iterations, tool calls, wall-clock, tokens."""

    max_iterations: int
    max_tool_calls: int
    max_step_wall_clock_s: float
    token_budget: int

    def __post_init__(self) -> None:
        if self.max_iterations <= 0:
            raise ValueError(f"max_iterations must be > 0, got {self.max_iterations}")
        if self.max_tool_calls <= 0:
            raise ValueError(f"max_tool_calls must be > 0, got {self.max_tool_calls}")
        if self.max_step_wall_clock_s <= 0:
            raise ValueError(f"max_step_wall_clock_s must be > 0, got {self.max_step_wall_clock_s}")
        if self.token_budget <= 0:
            raise ValueError(f"token_budget must be > 0, got {self.token_budget}")


class LoopGuard:
    """Run-level counters that raise the moment any bound is exceeded."""

    def __init__(self, bounds: RunBounds, now: Callable[[], float] = time.monotonic) -> None:
        self._bounds = bounds
        self._now = now
        self.iterations = 0
        self.tool_calls = 0
        self.tokens = 0
        self.last_state: Mapping[str, object] = {}
        self._step_started_at: float | None = None

    def begin_step(self, state: Mapping[str, object] | None = None) -> None:
        """Start the next iteration; trips on iteration or step wall-clock overrun."""
        stamp = self._now()
        if (
            self._step_started_at is not None
            and stamp - self._step_started_at > self._bounds.max_step_wall_clock_s
        ):
            raise LoopGuardTripped(
                TripReason.WALL_CLOCK,
                f"step exceeded {self._bounds.max_step_wall_clock_s}s wall-clock budget",
            )
        if self.iterations >= self._bounds.max_iterations:
            raise LoopGuardTripped(
                TripReason.ITERATIONS,
                f"run exceeded {self._bounds.max_iterations} iterations",
            )
        self.iterations += 1
        if state is not None:
            self.last_state = dict(state)
        self._step_started_at = stamp

    def record_tool_call(self) -> None:
        """Register one executed tool call; trips when the budget is exhausted."""
        if self.tool_calls >= self._bounds.max_tool_calls:
            raise LoopGuardTripped(
                TripReason.TOOL_CALLS,
                f"run exceeded {self._bounds.max_tool_calls} tool calls",
            )
        self.tool_calls += 1

    def record_tokens(self, tokens: int) -> None:
        """Add model-token usage; trips once the cumulative budget is exceeded."""
        self.tokens += tokens
        if self.tokens > self._bounds.token_budget:
            raise LoopGuardTripped(
                TripReason.TOKENS,
                f"run exceeded {self._bounds.token_budget} token budget",
            )


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


@dataclass(frozen=True, slots=True)
class BoundedOutcome(Generic[_T]):
    """One bounded run's outcome: completion, trip reason, counters, partial state."""

    completed: bool
    trip_reason: TripReason | None
    result: _T | None
    iterations: int
    tool_calls: int
    tokens: int
    partial_state: Mapping[str, object]


def run_bounded(
    work: Callable[[LoopGuard], _T],
    bounds: RunBounds,
    publisher: _Publisher | None = None,
    deal_id: str | None = None,
    actor: str | None = None,
    checkpoint_sink: Callable[[Mapping[str, object]], object] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> BoundedOutcome[_T]:
    """Run *work* under *bounds*; on trip, checkpoint partial state + log the event."""
    guard = LoopGuard(bounds, now=now)
    try:
        result = work(guard)
    except LoopGuardTripped as tripped:
        partial: dict[str, object] = dict(guard.last_state)
        if checkpoint_sink is not None:
            checkpoint_sink(partial)
        if publisher is not None and deal_id is not None and actor is not None:
            publisher.publish(
                new_event(
                    deal_id,
                    actor,
                    EventType.RUN_BOUNDS_EXCEEDED,
                    {
                        "reason": tripped.reason.value,
                        "detail": tripped.detail,
                        "iterations": guard.iterations,
                        "tool_calls": guard.tool_calls,
                        "tokens": guard.tokens,
                        "partial_state": partial,
                    },
                )
            )
        return BoundedOutcome(
            completed=False,
            trip_reason=tripped.reason,
            result=None,
            iterations=guard.iterations,
            tool_calls=guard.tool_calls,
            tokens=guard.tokens,
            partial_state=partial,
        )
    return BoundedOutcome(
        completed=True,
        trip_reason=None,
        result=result,
        iterations=guard.iterations,
        tool_calls=guard.tool_calls,
        tokens=guard.tokens,
        partial_state={},
    )
