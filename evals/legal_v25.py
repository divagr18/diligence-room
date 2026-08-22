"""Legal v2.5 — the deliberate CoC regression candidate (BUILD_PLAN D12-M4 prep).

The shadow harness's RED case: ``broken_legal_fact`` reproduces the Legal
producer with the CoC title and summary intentionally weakened — "termination"
drops from the title and the "90 days" notice window drops from the summary —
exactly the weakening Legal v2.5 publishes. The pinned golden finding no
longer matches, so ``evals.harness.run_harness`` reports the CoC doc as
missing while the weakened finding surfaces as an unpinned ``new`` title.
Every workstream but legal stays on the baseline producer, so the candidate
diff isolates the Legal regression.
"""

from __future__ import annotations

from typing import Final

from agents.fleet import WorkstreamFact, extract_fact
from evals.golden_set import COC_CLAUSE_LOCATOR
from ingestion.chunking import chunk
from ingestion.models import ParsedDoc
from registry.models import Workstream

_CUSTOMER_X: Final = "Meridian Logistics, Inc."


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
