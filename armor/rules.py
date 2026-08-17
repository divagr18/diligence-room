"""Model Armor project rules (BUILD_PLAN D7-M2, vision §7.6).

Deterministic custom screening layer on top of the managed Model Armor API:
stable, audited rule ids across the Day-7 attack classes (exfiltration links,
authority forgery, cross-workstream state mutation and privilege escalation,
ignore-instruction variants, tool poisoning, cross-deal probing). Runs offline,
must stay precision-tuned against the committed clean dataset
(``tests/test_armor_rules.py``), and catches the attack shapes the sentinel
tripwire is not designed to see.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

RULE_EXFIL_MAILTO: Final[str] = "exfil.mailto"
RULE_EXFIL_LINK: Final[str] = "exfil.link"
RULE_AUTHORITY_FORGERY: Final[str] = "authority.forgery"
RULE_CROSS_WS_MUTATION: Final[str] = "cross_ws.mutation"
RULE_CROSS_WS_ESCALATION: Final[str] = "cross_ws.privilege_escalation"
RULE_IGNORE_VARIANTS: Final[str] = "injection.ignore_variants"
RULE_TOOL_POISONING: Final[str] = "poisoning.tool"
RULE_CROSS_DEAL_PROBE: Final[str] = "cross_deal.probe"

_REASON_CODES: Final[Mapping[str, str]] = {
    RULE_EXFIL_MAILTO: "exfiltration",
    RULE_EXFIL_LINK: "exfiltration",
    RULE_AUTHORITY_FORGERY: "authority_forgery",
    RULE_CROSS_WS_MUTATION: "cross_workstream_mutation",
    RULE_CROSS_WS_ESCALATION: "privilege_escalation",
    RULE_IGNORE_VARIANTS: "ignore_instructions",
    RULE_TOOL_POISONING: "tool_poisoning",
    RULE_CROSS_DEAL_PROBE: "cross_deal_probe",
}


@dataclass(frozen=True, slots=True)
class RuleHit:
    """One project-rule detection with its auditable identity."""

    rule_id: str
    reason_code: str
    pattern: str


_PROJECT_RULES: Final[tuple[tuple[str, str, re.Pattern[str]], ...]] = (
    (RULE_EXFIL_MAILTO, "mailto exfiltration link", re.compile(r"mailto:", re.IGNORECASE)),
    (
        RULE_EXFIL_LINK,
        "exfiltration-intent link or known-bad domain",
        re.compile(
            r"\b(?:upload|exfiltrate|post|push|mirror|sync|copy|send)\b[\s\S]{0,80}https?://"
            r"|https?://[^\s]*(?:attacker|evil|exfil|drop|leak)[^\s]*",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_AUTHORITY_FORGERY,
        "forged authority claim or faked approval",
        re.compile(
            r"\b(?:i am|i'm|this is|acting as|speaking as|signed[, ]+|as the)\s+"
            r"(?:the\s+)?(?:system\s+administrator|administrator|admin|root(?:\s+user)?"
            r"|deal\s+lead|compliance\s+officer|policy\s+owner|system\s+prompt)\b"
            r"|\b(?:the\s+)?(?:acquisition|transaction|deal|merger|transfer)\s+"
            r"(?:has\s+been|is|was)\s+(?:already\s+|fully\s+)?(?:approved|cleared|waived)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_CROSS_WS_MUTATION,
        "imperative mutation of another workstream's state",
        re.compile(
            r"\b(?:mark|set|update|change|delete|dismiss|close|resolve|overwrite|alter)\b"
            r"[\s\S]{0,80}\b(?:legal|finance|hr|ip[ &_]*tech|tax|regulatory|esg|real[ _]estate)\b"
            r"[\s\S]{0,60}\b(?:findings?|records?|rosters?|state|status|severit(?:y|ies)"
            r"|scores?|items|partitions?|data)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_CROSS_WS_ESCALATION,
        "permission override or privilege escalation directive",
        re.compile(
            r"\b(?:override|bypass|escalate|elevate|grant|extend)\b[\s\S]{0,60}"
            r"\b(?:your\s+|the\s+|agent\s+)?(?:permissions?|privileges?|restrictions?|controls?"
            r"|boundar(?:y|ies)|access(?:\s+(?:rights?|level|scope|restrictions?))?)\b"
            r"|\byou\s+are\s+(?:now\s+)?(?:authorized|permitted|granted)\s+to\b",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_IGNORE_VARIANTS,
        "ignore/override-policy instruction variant",
        re.compile(
            r"\b(?:override|disregard|ignore|forget|suspend)\b[\s\S]{0,45}"
            r"\b(?:polic(?:y|ies)|rules?|guidelines|guardrails|directives|instructions"
            r"|system\s+prompt)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_TOOL_POISONING,
        "tool-call poisoning directive",
        re.compile(
            r"\bwhen\s+(?:you\s+)?(?:calling|invoking|using|running)\b[\s\S]{0,60}"
            r"\b(?:a\s+|the\s+)?(?:tool|function|finding_create|data_room_read|ask_agent)\b"
            r"|\b(?:attach|include|append|hide)\b[\s\S]{0,60}\b(?:to|in)\s+(?:the\s+)?"
            r"(?:request|payload|tool\s+call)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RULE_CROSS_DEAL_PROBE,
        "cross-deal reconnaissance",
        re.compile(
            r"\bdeal-[a-z]+\b"
            r"|\b(?:list|read|merge|access|copy|browse|enumerate)\b[\s\S]{0,60}"
            r"\b(?:other|another|sibling|prior|previous|all)\s+deals?\b",
            re.IGNORECASE,
        ),
    ),
)


def screen_project_rules(text: str) -> tuple[RuleHit, ...]:
    """Screen *text* against every project rule; one hit per rule, rule order."""
    hits: list[RuleHit] = []
    for rule_id, label, pattern in _PROJECT_RULES:
        if pattern.search(text):
            hits.append(RuleHit(rule_id=rule_id, reason_code=_REASON_CODES[rule_id], pattern=label))
    return tuple(hits)
