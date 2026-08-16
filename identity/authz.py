"""Agent→data authorization policy (BUILD_PLAN D3-M2, vision §7.4).

Defines the ACL matrix mapping document categories to owning workstreams,
the resource path parser (two grammars), the policy decision function
``can``, and the denial-event envelope builder.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from identity.principals import Principal
from registry.models import Workstream
from runtime.events import EventEnvelope, EventType, new_event


class Action(StrEnum):
    """Operations a principal can attempt on a resource."""

    READ = "read"


# ── ACL matrix (locked) ────────────────────────────────────────────────────

CATEGORY_OWNERS: Final[Mapping[str, Workstream]] = {
    "contracts": Workstream.LEGAL,
    "litigation": Workstream.LEGAL,
    "financials": Workstream.FINANCE,
    "projections": Workstream.FINANCE,
    "valuation": Workstream.FINANCE,
    "rosters": Workstream.HR,
    "payroll": Workstream.HR,
    "compensation": Workstream.HR,
    "patents": Workstream.IP_TECH,
    "licenses": Workstream.IP_TECH,
    "tech-inventory": Workstream.IP_TECH,
    "tax-filings": Workstream.TAX,
    "regulatory": Workstream.REGULATORY,
    "esg": Workstream.ESG,
    "leases": Workstream.REAL_ESTATE,
}

_FULL_GRAMMAR_PREFIX: Final[str] = "deals/"


# ── Resource ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Resource:
    """A document resource addressed by deal, workstream, category, and name."""

    deal_id: str
    workstream: Workstream | None
    category: str
    name: str

    def __post_init__(self) -> None:
        if self.category not in CATEGORY_OWNERS:
            raise ValueError(
                f"unknown category {self.category!r}: expected one of {sorted(CATEGORY_OWNERS)}"
            )


def parse_resource(raw: str, deal_id: str | None = None) -> Resource:
    """Parse a resource path into a ``Resource``.

    Accepts two grammars:
    - Full: ``deals/{deal_id}/workstreams/{ws}/{category}/{name}``
    - Bare: ``{category}/{name}`` (requires *deal_id* parameter)
    """
    if raw.startswith(_FULL_GRAMMAR_PREFIX):
        return _parse_full_grammar(raw)
    return _parse_bare_grammar(raw, deal_id)


def _parse_full_grammar(raw: str) -> Resource:
    parts = raw.split("/", 5)
    # deals / {deal_id} / workstreams / {ws} / {category} / {name}
    if len(parts) < 6:
        raise ValueError(f"malformed full resource path: {raw!r}")
    resource_deal_id = parts[1]
    try:
        workstream = Workstream(parts[3])
    except ValueError:
        raise ValueError(f"unknown workstream {parts[3]!r} in resource path") from None
    category = parts[4]
    name = parts[5]
    return Resource(
        deal_id=resource_deal_id,
        workstream=workstream,
        category=category,
        name=name,
    )


def _parse_bare_grammar(raw: str, deal_id: str | None) -> Resource:
    if deal_id is None:
        raise ValueError("deal_id is required for bare resource paths")
    parts = raw.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"malformed bare resource path: {raw!r}")
    category = parts[0]
    name = parts[1]
    return Resource(
        deal_id=deal_id,
        workstream=None,
        category=category,
        name=name,
    )


# ── Denial types ───────────────────────────────────────────────────────────


class DenialReason(StrEnum):
    """Why an authorization was denied."""

    cross_deal = "cross_deal"
    workstream_boundary = "workstream_boundary"


class AuthzDenied(Exception):
    """Raised when a principal is denied access to a resource."""

    def __init__(
        self,
        principal: Principal,
        action: Action,
        resource: Resource,
        reason: DenialReason,
    ) -> None:
        self.principal = principal
        self.action = action
        self.resource = resource
        self.reason = reason
        super().__init__(
            f"authz denied: {reason.value} ({principal.name} {action.value} {resource.category})"
        )


# ── Policy decision ────────────────────────────────────────────────────────


def can(
    principal: Principal,
    action: Action,
    resource: Resource,
) -> tuple[bool, DenialReason | None]:
    """Decide whether *principal* may perform *action* on *resource*.

    Cross-deal is checked first (precedence over workstream boundary).
    """
    if resource.deal_id != principal.deal_id:
        return (False, DenialReason.cross_deal)
    if CATEGORY_OWNERS[resource.category] is not principal.workstream:
        return (False, DenialReason.workstream_boundary)
    return (True, None)


# ── Denial event builder ──────────────────────────────────────────────────


def denial_envelope(
    principal: Principal,
    action: Action,
    resource: Resource,
    reason: DenialReason,
    now: datetime | None = None,
) -> EventEnvelope:
    """Build a SECURITY_EVENT envelope recording an authorization denial."""
    ws_segment = resource.workstream.value if resource.workstream is not None else "-"
    resource_path = (
        f"deals/{resource.deal_id}/workstreams/{ws_segment}/{resource.category}/{resource.name}"
    )
    return new_event(
        deal_id=resource.deal_id,
        actor=principal.name,
        event_type=EventType.SECURITY_EVENT,
        payload={
            "decision": "deny",
            "identity": principal.name,
            "action": action.value,
            "resource": resource_path,
            "reason": reason.value,
        },
        now=now,
    )
