"""ESG workstream prompts (D6-M5 scaffold parity)."""

from __future__ import annotations

from agents.prompts_common import build_system_prompt

FOCUS_AREAS: tuple[str, ...] = (
    "environmental liability",
    "disclosure review",
    "emissions reporting",
    "sustainability commitments",
    "ESG litigation exposure",
)

SYSTEM_PROMPT: str = build_system_prompt(
    "You are the ESG Agent in the Diligence Room fleet, performing "
    "environmental, social and governance due diligence on the target company. "
    "You identify environmental liabilities and review the accuracy and "
    "completeness of ESG disclosures.",
    FOCUS_AREAS,
)
