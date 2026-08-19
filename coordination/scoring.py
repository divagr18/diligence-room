"""Red-flag scoring engine (BUILD_PLAN D8-M1, vision §10).

Deterministic, explainable scoring of one finding against the analytical
context gathered around it. Factors (vision §10): severity, confidence,
financial exposure, regulatory implications, number of affected workstreams,
unresolved duration, dependency impact, and evidence quality.

Severity-loyalty: without escalation context a finding's red-flag level is its
own severity; escalation context can raise the level at most ONE step above the
finding's severity (a medium finding can become a high red flag, never
critical). Vision §10 canonical example: Legal HIGH + 18.3% exposure + 0.94
confidence + Legal&Finance affected => CRITICAL, while Legal alone stays HIGH.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from memory.findings import Finding, FindingSeverity


class RedFlagLevel(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_LEVEL_ORDER: Final[tuple[RedFlagLevel, ...]] = (
    RedFlagLevel.INFORMATIONAL,
    RedFlagLevel.LOW,
    RedFlagLevel.MEDIUM,
    RedFlagLevel.HIGH,
    RedFlagLevel.CRITICAL,
)

_SEVERITY_BASE: Final[Mapping[FindingSeverity, float]] = {
    FindingSeverity.INFORMATIONAL: 0.0,
    FindingSeverity.LOW: 8.0,
    FindingSeverity.MEDIUM: 20.0,
    FindingSeverity.HIGH: 40.0,
    FindingSeverity.CRITICAL: 60.0,
}

_CONFIDENCE_WEIGHT: Final[float] = 30.0
_EXPOSURE_CAP: Final[float] = 20.0
_REGULATORY_WEIGHT: Final[float] = 8.0
_WORKSTREAM_WEIGHT: Final[float] = 6.0
_WORKSTREAM_CAP: Final[int] = 3
_DURATION_CAP: Final[float] = 8.0
_DEPENDENCY_WEIGHT: Final[float] = 6.0
_EVIDENCE_WEIGHT: Final[float] = 2.0
_EVIDENCE_CAP: Final[int] = 3

_LADDER: Final[tuple[tuple[float, RedFlagLevel], ...]] = (
    (90.0, RedFlagLevel.CRITICAL),
    (65.0, RedFlagLevel.HIGH),
    (40.0, RedFlagLevel.MEDIUM),
    (20.0, RedFlagLevel.LOW),
)


@dataclass(frozen=True, slots=True)
class ScoringContext:
    """Analytical context layered on top of a finding for red-flag scoring."""

    financial_exposure_pct: float = 0.0
    regulatory_implicated: bool = False
    affected_workstreams: int = 1
    unresolved_days: float = 0.0
    dependency_impacted: bool = False

    def __post_init__(self) -> None:
        if self.financial_exposure_pct < 0:
            raise ValueError(
                f"financial_exposure_pct must be >= 0, got {self.financial_exposure_pct}"
            )
        if self.affected_workstreams < 1:
            raise ValueError(f"affected_workstreams must be >= 1, got {self.affected_workstreams}")
        if self.unresolved_days < 0:
            raise ValueError(f"unresolved_days must be >= 0, got {self.unresolved_days}")


@dataclass(frozen=True, slots=True)
class RedFlag:
    """One scored red flag: numeric score, ladder level, audit rationale."""

    score: float
    level: RedFlagLevel
    rationale: str


def _severity_level(severity: FindingSeverity) -> RedFlagLevel:
    return RedFlagLevel(severity.value)


def _ceiling_for(severity: FindingSeverity) -> RedFlagLevel:
    index = _LEVEL_ORDER.index(_severity_level(severity))
    return _LEVEL_ORDER[min(index + 1, len(_LEVEL_ORDER) - 1)]


def _ladder_level(score: float) -> RedFlagLevel:
    for threshold, level in _LADDER:
        if score >= threshold:
            return level
    return RedFlagLevel.INFORMATIONAL


def score_finding(finding: Finding, context: ScoringContext | None = None) -> RedFlag:
    """Score one finding against the vision §10 factors; fully deterministic."""
    ctx = context if context is not None else ScoringContext()
    exposure = min(ctx.financial_exposure_pct, _EXPOSURE_CAP)
    workstreams_beyond_first = min(max(ctx.affected_workstreams - 1, 0), _WORKSTREAM_CAP)
    duration = min(ctx.unresolved_days, _DURATION_CAP)
    evidence_bonus = min(len(finding.evidence), _EVIDENCE_CAP) * _EVIDENCE_WEIGHT

    score = (
        _SEVERITY_BASE[finding.severity]
        + _CONFIDENCE_WEIGHT * finding.confidence
        + evidence_bonus
        + exposure
        + (_REGULATORY_WEIGHT if ctx.regulatory_implicated else 0.0)
        + _WORKSTREAM_WEIGHT * workstreams_beyond_first
        + duration
        + (_DEPENDENCY_WEIGHT if ctx.dependency_impacted else 0.0)
    )

    escalated = (
        ctx.financial_exposure_pct > 0
        or ctx.regulatory_implicated
        or ctx.affected_workstreams > 1
        or ctx.unresolved_days > 0
        or ctx.dependency_impacted
    )
    if escalated:
        ceiling = _ceiling_for(finding.severity)
        ladder = _ladder_level(score)
        level = min(ladder, ceiling, key=_LEVEL_ORDER.index)
    else:
        level = _severity_level(finding.severity)

    rationale = (
        f"score={score:.2f} level={level.value} | "
        f"severity={finding.severity.value} confidence={finding.confidence:.2f} "
        f"evidence={len(finding.evidence)} "
        f"exposure_pct={ctx.financial_exposure_pct:.1f} "
        f"regulatory={ctx.regulatory_implicated} "
        f"workstreams={ctx.affected_workstreams} "
        f"unresolved_days={ctx.unresolved_days:.1f} "
        f"dependency={ctx.dependency_impacted}"
    )
    return RedFlag(score=score, level=level, rationale=rationale)
