"""Diligence Room fleet agents (BUILD_PLAN D1-M6 v0 + D6-M1 factory).

Two layers live here:

1. The Day-1 hello agent (``root_agent``) on Gemini 3.5 Flash with a single
   echo tool — the Vertex AI Agent Engine deploy smoke spike.
2. The Day-6 agent factory (``build_agent_from_manifest``) that instantiates
   the workstream fleet from registry manifests: identity binding, the
   memory/finding/gateway toolset, model config from the approved version, and
   the workstream system prompt (which embeds the finding JSON contract).
"""

from __future__ import annotations

import importlib
from typing import Any, Protocol

from google.adk.agents import Agent
from google.cloud import firestore

from agents.tools.data_room_read import DocSource, make_data_room_read
from agents.tools.finding_create import make_finding_create
from agents.tools.gateway_query import (
    LocalGatewayClient,
    OfflineFinanceResponder,
    gateway_query_tool,
)
from identity.principals import Principal, bind_manifest
from registry.models import Workstream
from registry.store import AgentRegistryStore

MODEL_ID = "gemini-3.5-flash"

_ECHO_MARKER = "echoed"


def echo(text: str) -> dict[str, str]:
    """Echo the provided text back verbatim.

    Args:
        text: The exact text to echo back.

    Returns:
        A dict with the echoed text under the 'echoed' key.
    """
    return {_ECHO_MARKER: text}


ECHO_TOOL = echo

_INSTRUCTION = """\
You are the Diligence Room hello agent, a deployment smoke-test agent.

Your only capability is the `echo` tool. When the user asks you to echo
something, call the `echo` tool with the exact text they provided, then report
the echoed text back in your final answer. Never paraphrase or modify the text.
"""


root_agent: Agent = Agent(
    name="diligence_room_hello",
    model=MODEL_ID,
    description=("Day-1 smoke-test agent proving the ADK-to-Agent-Engine deploy path."),
    instruction=_INSTRUCTION,
    tools=[ECHO_TOOL],
)


class EventPublisher(Protocol):
    """Minimal publish surface for security-event emission (audit trail)."""

    def publish(self, event: Any) -> str: ...


def _resolve_prompt_ref(prompt_ref: str) -> str:
    """Resolve ``"agents.<ws>.prompts:SYSTEM_PROMPT"`` to the prompt string."""
    module_path, _, attribute = prompt_ref.partition(":")
    if not module_path or not attribute:
        raise ValueError(f"malformed prompt_ref {prompt_ref!r}")
    module = importlib.import_module(module_path)
    prompt = getattr(module, attribute)
    if not isinstance(prompt, str):
        raise ValueError(f"prompt_ref {prompt_ref!r} did not resolve to a string")
    return prompt


def build_agent_from_manifest(
    client: firestore.Client,
    agent_id: str,
    deal_id: str,
    publisher: EventPublisher,
    doc_source: DocSource,
) -> Agent:
    """Instantiate one workstream ADK agent from its registry manifest.

    Performs zero-trust wiring: binds the manifest to a deal-scoped principal,
    enforces the approval gate, wires the scoped toolset (data-room-read,
    finding-create, gateway-query), selects the model from the approved
    version, and loads the workstream system prompt.
    """
    store = AgentRegistryStore(client)
    manifest = store.get_manifest(agent_id)
    if not manifest.approved:
        raise ValueError(f"agent {agent_id!r} is not approved")

    version = store.get_version(agent_id, manifest.version)
    principal: Principal = bind_manifest(manifest, deal_id)
    instruction = _resolve_prompt_ref(version.prompt_ref)

    data_room_tool = make_data_room_read(principal, publisher, doc_source)
    finding_tool = make_finding_create(principal, client, doc_source)
    gateway_client = LocalGatewayClient(
        client=client, responders={Workstream.FINANCE: OfflineFinanceResponder()}
    )
    ask_tool = gateway_query_tool(principal, deal_id, gateway_client)

    return Agent(
        name=manifest.agent_id,
        model=version.model_id,
        description=manifest.name,
        instruction=instruction,
        tools=[data_room_tool, finding_tool, ask_tool],
    )
