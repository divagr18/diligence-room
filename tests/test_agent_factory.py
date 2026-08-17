"""Agent factory tests (BUILD_PLAN D6-M1, scenario S4).

The factory instantiates ADK agents from registry manifests: identity binding
(manifest -> principal), memory-scoped tools (data-room-read, finding-create,
gateway-query), model config from the approved version, and the workstream
system prompt embedding the finding contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.agents import Agent
from google.cloud import firestore

from agents.base_agent import build_agent_from_manifest
from agents.prompts_common import FINDING_JSON_CONTRACT
from agents.tools.data_room_read import DatasetDocSource
from memory.event_log import EventLog
from registry.seed import seed_registry
from registry.store import AgentRegistryStore
from runtime.events import EventEnvelope

DEAL = "deal-falcon"


class _LogPublisher:
    def __init__(self, client: firestore.Client) -> None:
        self._log = EventLog(client)
        self.published: list[EventEnvelope] = []

    def publish(self, event: EventEnvelope) -> str:
        self.published.append(event)
        self._log.append(event)
        return event.event_id


def _tool_by_name(agent: Agent, name: str) -> Any:
    matches = [tool for tool in agent.tools if getattr(tool, "__name__", "") == name]
    assert len(matches) == 1, f"expected exactly one tool named {name!r}"
    return matches[0]


class TestFactory:
    def test_builds_two_distinct_agents(self, firestore_client: firestore.Client) -> None:
        seed_registry(AgentRegistryStore(firestore_client))
        publisher = _LogPublisher(firestore_client)
        legal = build_agent_from_manifest(
            firestore_client, "legal", DEAL, publisher, DatasetDocSource()
        )
        finance = build_agent_from_manifest(
            firestore_client, "finance", DEAL, publisher, DatasetDocSource()
        )
        assert legal.name == "legal"
        assert finance.name == "finance"
        assert legal.name != finance.name
        assert legal.model == "gemini-3.5-flash"
        assert finance.model == "gemini-3.5-flash"

    def test_agent_has_all_three_tools(self, firestore_client: firestore.Client) -> None:
        seed_registry(AgentRegistryStore(firestore_client))
        publisher = _LogPublisher(firestore_client)
        agent = build_agent_from_manifest(
            firestore_client, "legal", DEAL, publisher, DatasetDocSource()
        )
        names = {getattr(tool, "__name__", "") for tool in agent.tools}
        assert names == {"data_room_read", "finding_create", "ask_agent"}

    def test_prompt_embeds_finding_contract(self, firestore_client: firestore.Client) -> None:
        seed_registry(AgentRegistryStore(firestore_client))
        publisher = _LogPublisher(firestore_client)
        agent = build_agent_from_manifest(
            firestore_client, "legal", DEAL, publisher, DatasetDocSource()
        )
        instruction = agent.instruction
        assert isinstance(instruction, str)
        assert FINDING_JSON_CONTRACT in instruction

    def test_identity_binding_scopes_reads(self, firestore_client: firestore.Client) -> None:
        seed_registry(AgentRegistryStore(firestore_client))
        publisher = _LogPublisher(firestore_client)
        legal = build_agent_from_manifest(
            firestore_client, "legal", DEAL, publisher, DatasetDocSource()
        )
        read_tool = _tool_by_name(legal, "data_room_read")
        allowed = read_tool(category="contracts", name="contract_customer_x.pdf")
        denied = read_tool(category="financials", name="financials_fy27.xlsx")
        assert allowed["decision"] == "allow"
        assert denied["decision"] == "deny"
        assert denied["reason"] == "workstream_boundary"

    def test_unknown_agent_raises(self, firestore_client: firestore.Client) -> None:
        seed_registry(AgentRegistryStore(firestore_client))
        publisher = _LogPublisher(firestore_client)
        from registry.store import AgentNotFoundError

        with pytest.raises(AgentNotFoundError):
            build_agent_from_manifest(
                firestore_client, "astrology", DEAL, publisher, DatasetDocSource()
            )

    def test_unapproved_manifest_rejected(self, firestore_client: firestore.Client) -> None:
        store = AgentRegistryStore(firestore_client)
        seed_registry(store)
        store.update_approval("legal", approved=False)
        publisher = _LogPublisher(firestore_client)
        with pytest.raises(ValueError, match="not approved"):
            build_agent_from_manifest(
                firestore_client, "legal", DEAL, publisher, DatasetDocSource()
            )
