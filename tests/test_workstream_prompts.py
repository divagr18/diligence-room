"""Contract tests for the four deep-workstream prompts (BUILD_PLAN D1-M8).

Verifies: focus areas match vision §5, and the JSON finding output contract
keys exactly match the Finding schema (memory.findings.Finding) so agent output
can be constructed without field translation.
"""

from __future__ import annotations

import dataclasses

from agents.finance import prompts as finance_prompts
from agents.hr import prompts as hr_prompts
from agents.ip_tech import prompts as ip_tech_prompts
from agents.legal import prompts as legal_prompts
from agents.prompts_common import FINDING_JSON_CONTRACT
from memory.findings import Finding

RUNTIME_OWNED_FIELDS = frozenset(
    {
        "finding_id",
        "deal_id",
        "workstream",
        "status",
        "owner",
        "created_at",
        "updated_at",
        "audit_trace_id",
        "related_findings",
    }
)
AGENT_OWNED_FIELDS = {field.name for field in dataclasses.fields(Finding)} - RUNTIME_OWNED_FIELDS

WORKSTREAM_MODULES = {
    "legal": legal_prompts,
    "finance": finance_prompts,
    "hr": hr_prompts,
    "ip_tech": ip_tech_prompts,
}

MANDATORY_FOCUS_TERMS = {
    "legal": ("change-of-control", "termination rights", "indemnities"),
    "finance": ("recurring vs non-recurring revenue", "customer concentration"),
    "hr": ("key-person dependency", "retention risk"),
    "ip_tech": ("open-source licenses", "unsupported infrastructure"),
}


class TestFocusAreas:
    def test_each_workstream_has_focus_areas(self) -> None:
        for workstream, module in WORKSTREAM_MODULES.items():
            assert module.FOCUS_AREAS, f"{workstream} has no focus areas"

    def test_mandatory_terms_present_verbatim(self) -> None:
        for workstream, terms in MANDATORY_FOCUS_TERMS.items():
            joined = " ".join(WORKSTREAM_MODULES[workstream].FOCUS_AREAS)
            for term in terms:
                assert term in joined, f"{workstream} missing focus term {term!r}"


class TestFindingContract:
    def test_contract_names_every_agent_owned_field(self) -> None:
        for field_name in AGENT_OWNED_FIELDS:
            assert field_name in FINDING_JSON_CONTRACT, (
                f"finding JSON contract missing field {field_name!r}"
            )

    def test_each_system_prompt_embeds_the_contract(self) -> None:
        for workstream, module in WORKSTREAM_MODULES.items():
            assert FINDING_JSON_CONTRACT in module.SYSTEM_PROMPT, (
                f"{workstream} system prompt must embed the finding contract"
            )

    def test_each_system_prompt_is_substantial(self) -> None:
        for workstream, module in WORKSTREAM_MODULES.items():
            assert len(module.SYSTEM_PROMPT) > 500, f"{workstream} prompt too thin"
