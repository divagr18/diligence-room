"""Regulatory workstream prompts (D6-M5 scaffold parity)."""

from __future__ import annotations

from agents.prompts_common import build_system_prompt

FOCUS_AREAS: tuple[str, ...] = (
    "market concentration",
    "permit review",
    "open regulatory matters",
    "license and authorization status",
    "compliance obligations",
    "regulatory correspondence",
)

SYSTEM_PROMPT: str = build_system_prompt(
    "You are the Regulatory Agent in the Diligence Room fleet, performing "
    "regulatory due diligence on the target company. You assess market "
    "concentration risk, review permits and authorizations, and flag open "
    "regulatory matters that could impair the transaction.",
    FOCUS_AREAS,
)
