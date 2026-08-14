"""Agent Registry domain models (BUILD_PLAN D1-M4, vision §7.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class Workstream(StrEnum):
    LEGAL = "legal"
    FINANCE = "finance"
    HR = "hr"
    IP_TECH = "ip_tech"
    TAX = "tax"
    REGULATORY = "regulatory"
    ESG = "esg"
    REAL_ESTATE = "real_estate"


_WORKSTREAM_BY_AGENT_ID: dict[str, Workstream] = {
    workstream.value: workstream for workstream in Workstream
}


def resolve_workstream(agent_id: str) -> Workstream:
    try:
        return _WORKSTREAM_BY_AGENT_ID[agent_id]
    except KeyError:
        raise ValueError(
            f"unknown agent_id {agent_id!r}: expected one of {sorted(_WORKSTREAM_BY_AGENT_ID)}"
        ) from None


@dataclass(frozen=True, slots=True)
class AgentVersion:
    version: str
    model_id: str
    prompt_ref: str
    created_at: datetime
    approved: bool = False
    eval_score: float | None = None
    rollback_target: str | None = None
    changelog: str = ""


@dataclass(frozen=True, slots=True)
class AgentManifest:
    agent_id: str
    name: str
    version: str
    capabilities: tuple[str, ...]
    owner: str
    required_identity: str
    allowed_tools: tuple[str, ...]
    supported_document_types: tuple[str, ...]
    policy_profile: str
    created_at: datetime
    external_communication: Literal["prohibited"] = "prohibited"
    approved: bool = False
    eval_score: float | None = None
    deployment_status: str = "registered"
    rollback_target: str | None = None
    known_limitations: str = ""
    last_security_review: datetime | None = None

    def __post_init__(self) -> None:
        resolve_workstream(self.agent_id)

    @property
    def workstream(self) -> Workstream:
        return resolve_workstream(self.agent_id)
