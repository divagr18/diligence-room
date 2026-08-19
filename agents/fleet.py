"""Deep-four fleet findings — offline deterministic producers (BUILD_PLAN D6-M4).

Each deep workstream (legal, finance, hr, ip_tech) extracts exactly one
finding fact from its seeded document using a genuine verbatim span, then
writes it through the same evidence-gated finding-create path the live model
uses (``agents/tools/finding_create.py``). This module is the offline proof
that the write path produces one gated finding per workstream; the live path
(scripts/run_d6_live_fleet.py) replaces the extractor with the real Flash
agent while keeping the identical evidence gate and partition write.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from google.cloud import firestore

from agents.tools.data_room_read import DatasetDocSource, DocSource
from agents.tools.finding_create import make_finding_create
from agents.tools.gateway_query import OfflineFinanceResponder
from identity.principals import principal_for
from ingestion.chunking import chunk
from ingestion.models import ParsedDoc
from ingestion.parsing import LocalParser
from registry.models import Workstream

DEEP_WORKSTREAM_DOCUMENTS: Final[Mapping[Workstream, str]] = {
    Workstream.LEGAL: "contract_meridian_logistics.pdf",
    Workstream.FINANCE: "financials_fy27.xlsx",
    Workstream.HR: "hr_roster_vantage.xlsx",
    Workstream.IP_TECH: "tech_inventory.pdf",
}

DEEP_WORKSTREAM_CATEGORIES: Final[Mapping[Workstream, str]] = {
    Workstream.LEGAL: "contracts",
    Workstream.FINANCE: "financials",
    Workstream.HR: "rosters",
    Workstream.IP_TECH: "tech-inventory",
}

_CUSTOMER_X = "Meridian Logistics, Inc."


@dataclass(frozen=True, slots=True)
class WorkstreamFact:
    """One extracted finding fact with its verbatim evidence span."""

    title: str
    summary: str
    severity: str
    confidence: float
    document_id: str
    verbatim_span: str
    chunk_ref: str | None
    affected_entities: tuple[str, ...]


def _line_containing(parsed: ParsedDoc, marker: str) -> str:
    assert parsed.text is not None
    for line in parsed.text.split("\n"):
        if marker in line:
            return line
    raise ValueError(f"marker {marker!r} not found in {parsed.document_id}")


def _legal_fact(parsed: ParsedDoc) -> WorkstreamFact:
    target = next(c for c in chunk(parsed) if c.locator == "clause:11.3")
    return WorkstreamFact(
        title="Meridian Logistics change-of-control termination right",
        summary=(
            "Section 11.3 of the Meridian Logistics master services agreement "
            "grants either party a termination right within 90 days of a change "
            "of control — triggered by the proposed acquisition."
        ),
        severity="high",
        confidence=0.9,
        document_id=parsed.document_id,
        verbatim_span=target.text,
        chunk_ref="clause:11.3",
        affected_entities=(_CUSTOMER_X,),
    )


def _finance_fact(parsed: ParsedDoc) -> WorkstreamFact:
    share = OfflineFinanceResponder().compute_share().value
    return WorkstreamFact(
        title="Meridian Logistics revenue concentration",
        summary=(f"Meridian Logistics represents {share:.1f}% of projected FY27 revenue."),
        severity="medium",
        confidence=0.95,
        document_id=parsed.document_id,
        verbatim_span=_line_containing(parsed, "Meridian Logistics"),
        chunk_ref=None,
        affected_entities=(_CUSTOMER_X,),
    )


def _hr_fact(parsed: ParsedDoc) -> WorkstreamFact:
    return WorkstreamFact(
        title="Key-person departure: Meridian account owner",
        summary=(
            "Dana Whitfield (VP Customer Success), owner of the Meridian "
            "Logistics relationship, resigns effective 60 days from the roster "
            "reference date."
        ),
        severity="medium",
        confidence=0.9,
        document_id=parsed.document_id,
        verbatim_span=_line_containing(parsed, "Whitfield"),
        chunk_ref=None,
        affected_entities=("Dana Whitfield", _CUSTOMER_X),
    )


def _ip_tech_fact(parsed: ParsedDoc) -> WorkstreamFact:
    return WorkstreamFact(
        title="Unsupported dependency: TitanBridge 4.1 at vendor end-of-life",
        summary=(
            "The Meridian-serving fleet-orchestration subsystem runs on "
            "TitanBridge 4.1, vendor end-of-life with no support contract; "
            "migration is estimated at 9-12 months."
        ),
        severity="high",
        confidence=0.9,
        document_id=parsed.document_id,
        verbatim_span=_line_containing(parsed, "TitanBridge 4.1"),
        chunk_ref=None,
        affected_entities=(_CUSTOMER_X,),
    )


_EXTRACTORS: Final[Mapping[Workstream, Callable[[ParsedDoc], WorkstreamFact]]] = {
    Workstream.LEGAL: _legal_fact,
    Workstream.FINANCE: _finance_fact,
    Workstream.HR: _hr_fact,
    Workstream.IP_TECH: _ip_tech_fact,
}


def extract_fact(workstream: Workstream, parsed: ParsedDoc) -> WorkstreamFact:
    return _EXTRACTORS[workstream](parsed)


def stable_finding_id(deal_id: str, workstream: Workstream, fact: WorkstreamFact) -> str:
    """Content-derived finding id so reruns hit the duplicate guard."""
    digest_input = "|".join(
        (deal_id, workstream.value, fact.document_id, fact.title, fact.verbatim_span)
    )
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]


def run_workstream_offline(
    client: firestore.Client,
    deal_id: str,
    workstream: Workstream,
    doc_source: DocSource | None = None,
    now: datetime | None = None,
) -> str:
    """Run one deep workstream's offline finding pass; return the finding id."""
    source = doc_source if doc_source is not None else DatasetDocSource()
    document_name = DEEP_WORKSTREAM_DOCUMENTS[workstream]
    blob = source.read(document_name)
    if blob is None:
        raise FileNotFoundError(f"seeded document {document_name!r} not found")
    parsed = LocalParser().parse(blob, document_name, deal_id)
    if parsed.text is None:
        raise ValueError(f"{document_name!r} needs OCR; offline producer cannot extract")
    fact = extract_fact(workstream, parsed)
    principal = principal_for(workstream, deal_id)
    tool = make_finding_create(principal, client, source, now=now)
    payload = {
        "finding_id": stable_finding_id(deal_id, workstream, fact),
        "title": fact.title,
        "summary": fact.summary,
        "severity": fact.severity,
        "confidence": fact.confidence,
        "evidence": [
            {
                "verbatim_span": fact.verbatim_span,
                "document_id": fact.document_id,
                "category": DEEP_WORKSTREAM_CATEGORIES[workstream],
                "chunk_ref": fact.chunk_ref,
            }
        ],
        "source_documents": [fact.document_id],
        "affected_entities": list(fact.affected_entities),
        "questions": [],
    }
    result = tool(finding_json=json.dumps(payload))
    if result["decision"] != "created":
        raise RuntimeError(f"finding rejected for {workstream.value}: {result}")
    return str(result["finding_id"])
