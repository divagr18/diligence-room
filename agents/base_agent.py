"""Diligence Room hello agent v0 (BUILD_PLAN module D1-M6).

Minimal ADK agent on Gemini 3.5 Flash with a single echo tool. Its purpose is
to spike the Vertex AI Agent Engine deployment path (infra/deploy/agent_engine.py)
before any domain logic exists. Later revisions grow into the agent factory
(D6-M1) that instantiates the eight workstream agents from registry manifests.
"""

from __future__ import annotations

from google.adk.agents import Agent

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
