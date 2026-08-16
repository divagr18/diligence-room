"""Aggregate-response enforcement (BUILD_PLAN D5-M4, vision §7.5).

Finance answers crossing the gateway must be scalar aggregates. Structural
and keyword markers detect table dumps, customer listings, and valuation-model
internals — in responses AND questions — and block them with
RAW_MODEL_PROHIBITED. Question screening is content-based and purpose-
independent: policy reads the declared purpose, never the question text.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final

from gateway.decide import DecisionReason
from gateway.policy import ResponseShape

_VALID_UNITS: Final[tuple[str, ...]] = ("percent", "usd", "count")


class ExtractionBlocked(Exception):
    """Raised when content would leak raw model artifacts across the gateway."""

    def __init__(self, reason: DecisionReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"extraction blocked ({reason.value}): {detail}")


@dataclass(frozen=True, slots=True)
class AggregateAnswer:
    """One scalar aggregate computed by a target workstream."""

    metric: str
    value: float
    unit: str
    source_document: str
    basis: str

    def __post_init__(self) -> None:
        if self.unit not in _VALID_UNITS:
            raise ValueError(f"unknown unit {self.unit!r}: expected one of {_VALID_UNITS}")
        if not math.isfinite(self.value):
            raise ValueError(f"aggregate value must be finite, got {self.value!r}")


def render_aggregate(answer: AggregateAnswer) -> str:
    """Render a scalar aggregate as the only shapes allowed to cross."""
    if answer.unit == "percent":
        return f"{answer.value:.1f}%"
    if answer.unit == "usd":
        return f"${answer.value:,.0f}"
    return str(int(answer.value))


_RESPONSE_MARKERS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\|"), "table pipe"),
    (re.compile(r"[^\n]*\t[^\n]*\t"), "tab-separated columns"),
    (
        re.compile(r"(?i)\b(dcf|discount rate|terminal growth|valuation model)\b"),
        "valuation-model internals",
    ),
    (
        re.compile(
            r"(?i)\b(each customer|every customer|all customers|by customer"
            r"|row by row|line item|itemized)\b"
        ),
        "multi-entity listing",
    ),
)

_QUESTION_MARKERS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (
        re.compile(
            r"(?i)\b(full valuation model|valuation model|dcf|discount rate"
            r"|terminal growth|assumptions)\b"
        ),
        "model artifact request",
    ),
    (
        re.compile(
            r"(?i)\b(every customer|each customer|all customers|list .*customer"
            r"|itemized|row by row|line item|dump)\b"
        ),
        "bulk-listing request",
    ),
)

_NUMERIC_LINE = re.compile(r"^\s*[\$\d,.\s]{6,}\s*$")
_NUMERIC_DUMP_LINES = 3


def _is_numeric_dump(text: str) -> bool:
    hits = sum(1 for line in text.splitlines() if _NUMERIC_LINE.match(line))
    return hits >= _NUMERIC_DUMP_LINES


def enforce_response_shape(text: str, shape: ResponseShape) -> str:
    """Return *text* if it may cross under *shape*; raise ExtractionBlocked."""
    if shape is ResponseShape.NONE:
        raise ExtractionBlocked(DecisionReason.RAW_MODEL_PROHIBITED, "response_shape is none")
    stripped = text.strip()
    for pattern, label in _RESPONSE_MARKERS:
        if pattern.search(stripped):
            raise ExtractionBlocked(DecisionReason.RAW_MODEL_PROHIBITED, label)
    if _is_numeric_dump(stripped):
        raise ExtractionBlocked(DecisionReason.RAW_MODEL_PROHIBITED, "multi-row numeric dump")
    return stripped


def screen_question(question: str) -> None:
    """Block questions that request raw artifacts regardless of purpose."""
    for pattern, label in _QUESTION_MARKERS:
        if pattern.search(question):
            raise ExtractionBlocked(DecisionReason.RAW_MODEL_PROHIBITED, label)
