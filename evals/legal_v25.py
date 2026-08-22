"""Legal v2.5 — the deliberate CoC regression candidate (BUILD_PLAN D12-M4).

The shadow harness's RED case: ``broken_legal_fact`` reproduces the Legal
producer with the CoC title and summary intentionally weakened — "termination"
drops from the title and the "90 days" notice window drops from the summary —
exactly the weakening Legal v2.5 publishes. The pinned golden finding no
longer matches, so ``evals.harness.run_harness`` reports the CoC doc as
missing while the weakened finding surfaces as an unpinned ``new`` title.
Every workstream but legal stays on the baseline producer, so the candidate
diff isolates the Legal regression.

This module also owns the demo wiring for the upgrade/rollback beat:
``publish_legal_v25`` registers the candidate in the Agent Registry
(unapproved, ``rollback_target`` pre-declared at 2.4.0), and
``extractor_from_registry`` selects the legal fact producer from the live
manifest version — v2.5.0 runs ``broken_legal_fact``, the rolled-back
2.4.0 runs the baseline fleet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from agents.fleet import WorkstreamFact, extract_fact
from evals.golden_set import COC_CLAUSE_LOCATOR
from evals.harness import Extractor
from ingestion.chunking import chunk
from ingestion.models import ParsedDoc
from registry.models import AgentManifest, AgentVersion, Workstream
from registry.store import AgentRegistryStore

_CUSTOMER_X: Final = "Meridian Logistics, Inc."

LEGAL_V25_VERSION: Final = "2.5.0"
KNOWN_GOOD_LEGAL_VERSION: Final = "2.4.0"
LEGAL_V25_CHANGELOG: Final = "CoC prompt regression (deliberate D12-M4 eval demo)"


def broken_legal_fact(parsed: ParsedDoc) -> WorkstreamFact:
    """Legal CoC fact with "termination" and "90 days" dropped from title/summary."""
    target = next(c for c in chunk(parsed) if c.locator == COC_CLAUSE_LOCATOR)
    return WorkstreamFact(
        title="Meridian Logistics change-of-control clause noted",
        summary=(
            "Section 11.3 of the Meridian Logistics master services agreement "
            "references a change-of-control provision; flagged for follow-up."
        ),
        severity="high",
        confidence=0.9,
        document_id=parsed.document_id,
        verbatim_span=target.text,
        chunk_ref=COC_CLAUSE_LOCATOR,
        affected_entities=(_CUSTOMER_X,),
    )


def legal_v25_extract_fact(workstream: Workstream, parsed: ParsedDoc) -> WorkstreamFact:
    """Candidate extractor: Legal v2.5 for legal, baseline producers elsewhere."""
    if workstream is Workstream.LEGAL:
        return broken_legal_fact(parsed)
    return extract_fact(workstream, parsed)


def publish_legal_v25(store: AgentRegistryStore, now: datetime | None = None) -> AgentManifest:
    """Publish the Legal v2.5 regression candidate into the registry.

    Registers the version record (changelog names the deliberate weakening)
    and points the legal manifest at it, unapproved, with the known-good
    version pre-declared as ``rollback_target`` — the sanctioned direct-store
    publish path (plan §10). Returns the updated manifest.
    """
    stamp = now if now is not None else datetime.now(UTC)
    return store.publish_version(
        "legal",
        AgentVersion(
            version=LEGAL_V25_VERSION,
            model_id="gemini-3.5-flash",
            prompt_ref="agents.legal.prompts:SYSTEM_PROMPT",
            created_at=stamp,
            approved=False,
            rollback_target=KNOWN_GOOD_LEGAL_VERSION,
            changelog=LEGAL_V25_CHANGELOG,
        ),
    )


def extractor_from_registry(store: AgentRegistryStore) -> Extractor:
    """Fleet extractor selected by the live legal manifest version.

    v2.5.0 runs ``broken_legal_fact`` for the legal workstream; any other
    version (notably the rolled-back known-good one) runs the baseline
    fleet. Every workstream but legal always runs the baseline producers.
    """
    if store.get_manifest("legal").version == LEGAL_V25_VERSION:
        return legal_v25_extract_fact
    return extract_fact
