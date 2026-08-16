"""Runtime dispatcher — enforcement layer for agent→data AuthZ (BUILD_PLAN D3-M2).

The dispatcher is the single enforcement point that turns a ``can`` decision
into a raised ``AuthzDenied`` exception and an emitted denial event.
"""

from __future__ import annotations

from typing import Protocol

from identity.authz import Action, AuthzDenied, Resource, can, denial_envelope
from identity.principals import Principal
from runtime.events import EventEnvelope


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def authorize(
    principal: Principal,
    action: Action,
    resource: Resource,
    publisher: _Publisher | None = None,
) -> None:
    """Enforce *principal*'s right to perform *action* on *resource*.

    Returns ``None`` when allowed. When denied, emits a denial event via
    *publisher* (if provided) and raises ``AuthzDenied``.
    """
    allowed, reason = can(principal, action, resource)
    if allowed:
        return
    assert reason is not None  # noqa: S101 — guaranteed by can() contract
    if publisher is not None:
        envelope = denial_envelope(principal, action, resource, reason)
        publisher.publish(envelope)
    raise AuthzDenied(principal, action, resource, reason)


def authorized_read(
    principal: Principal,
    resource: Resource,
    publisher: _Publisher | None = None,
) -> None:
    """Sugar: authorize ``Action.READ`` for *resource*."""
    authorize(principal, Action.READ, resource, publisher=publisher)
