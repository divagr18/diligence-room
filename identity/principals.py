"""Zero-trust agent principal bindings (BUILD_PLAN D3-M1).

Parses and constructs agent identity strings of the form
``{workstream}-agent@{deal_id}``, validates deal-id format, and
binds a seeded ``AgentManifest`` to a concrete deal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from registry.models import AgentManifest, Workstream

DEAL_PLACEHOLDER: Final[str] = "deal"

_DEAL_ID_RE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9-]*")
_AGENT_SUFFIX: Final[str] = "-agent"


@dataclass(frozen=True, slots=True)
class Principal:
    """Identifies one workstream agent scoped to one deal."""

    workstream: Workstream
    deal_id: str

    @property
    def name(self) -> str:
        return f"{self.workstream.value}-agent@{self.deal_id}"


def _validate_deal_id(deal_id: str) -> None:
    if not deal_id or not _DEAL_ID_RE.fullmatch(deal_id):
        raise ValueError(f"deal_id {deal_id!r} must match ^[a-z][a-z0-9-]*$")


def _coerce_workstream(workstream: Workstream | str) -> Workstream:
    if isinstance(workstream, Workstream):
        return workstream
    return Workstream(workstream)


def principal_for(workstream: Workstream | str, deal_id: str) -> Principal:
    """Construct a Principal, validating deal_id format."""
    _validate_deal_id(deal_id)
    return Principal(workstream=_coerce_workstream(workstream), deal_id=deal_id)


def parse_identity(identity: str) -> Principal:
    """Parse ``{workstream}-agent@{deal_id}`` back into a Principal."""
    if "@" not in identity:
        raise ValueError(f"malformed identity {identity!r}: missing '@' separator")
    prefix, _, deal_id = identity.partition("@")
    if not prefix.endswith(_AGENT_SUFFIX):
        raise ValueError(
            f"malformed identity {identity!r}: expected '{_AGENT_SUFFIX}' suffix before '@'"
        )
    ws_value = prefix[: -len(_AGENT_SUFFIX)]
    try:
        workstream = Workstream(ws_value)
    except ValueError:
        raise ValueError(f"unknown workstream {ws_value!r} in identity {identity!r}") from None
    if not deal_id:
        raise ValueError(f"empty deal_id in identity {identity!r}")
    return Principal(workstream=workstream, deal_id=deal_id)


def bind_manifest(manifest: AgentManifest, deal_id: str) -> Principal:
    """Bind a seeded manifest template to a concrete deal id.

    The manifest's ``required_identity`` must follow the binding template
    ``{agent_id}-agent@deal`` (where ``deal`` is the placeholder).
    """
    expected = f"{manifest.agent_id}{_AGENT_SUFFIX}@{DEAL_PLACEHOLDER}"
    if manifest.required_identity != expected:
        raise ValueError(
            f"required_identity {manifest.required_identity!r} does not "
            f"match binding template {expected!r}"
        )
    return principal_for(manifest.workstream, deal_id)
