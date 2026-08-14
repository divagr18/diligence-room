"""Contract tests for the Day-1 hello agent (BUILD_PLAN D1-M6).

These are structural: they pin the agent's identity, model, and tool surface
without calling Vertex AI (network smoke tests live in scripts/). The JSON
finding output contract referenced by the workstream prompts (D1-M8) will key
off these same identifiers.
"""

from __future__ import annotations

from agents.base_agent import ECHO_TOOL, MODEL_ID, root_agent


class TestHelloAgentContract:
    def test_model_id_is_gemini_35_flash(self) -> None:
        assert MODEL_ID == "gemini-3.5-flash"

    def test_root_agent_identity(self) -> None:
        assert root_agent.name == "diligence_room_hello"
        assert root_agent.model == MODEL_ID

    def test_agent_has_exactly_the_echo_tool(self) -> None:
        assert root_agent.tools == [ECHO_TOOL]

    def test_agent_has_instruction_and_description(self) -> None:
        assert root_agent.instruction
        assert root_agent.description

    def test_echo_returns_verbatim_payload(self) -> None:
        marker = "diligence-room-day1-smoke"
        assert ECHO_TOOL(text=marker) == {"echoed": marker}
