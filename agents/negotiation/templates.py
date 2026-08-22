"""Deterministic negotiation artifact templates (BUILD_PLAN D12-M6, vision §11).

Three renderers — clause redline, seller request, and counterparty
clarification questions (a three-question bank). Every renderer is pure
string composition over the finding the evidence gate already verified:

- every ``evidence.verbatim_span`` is quoted verbatim with its source
  document (and locator when recorded),
- every affected entity is named,
- the proposed frame / request / questions derive from the finding's own
  title, summary, and entities.

No model call anywhere: the human approval gate behind ``drafts.py``
reviews exactly what the evidence gate verified — nothing more is
invented between the two.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from memory.findings import Evidence, Finding

_EVIDENCE_LABEL: Final[str] = "Grounding evidence (verbatim, verified at write time)"
_APPROVAL_NOTE: Final[str] = (
    "Prepared by the negotiation agent from verified evidence. Human approval "
    "is required before anything leaves the room (vision §11)."
)
_NO_ENTITIES: Final[str] = "none recorded"

_QUESTION_BANK: Final[tuple[str, str, str]] = (
    "Please confirm whether {entities} remains bound by the provision quoted "
    "below as of the signing date, and identify every amendment, side letter, "
    "waiver, or consent touching it.",
    "Please state the current status of the matter described in the quoted "
    "provision — notices given, consents obtained, and obligations still "
    "outstanding — as it concerns {entities}.",
    "Please clarify whether a change of control would trigger any notice, "
    "consent, filing, or termination obligation under the quoted provision, "
    "for {entities}, and on what timeline.",
)


def _locator(entry: Evidence) -> str:
    return f" [{entry.chunk_ref}]" if entry.chunk_ref else ""


def _evidence_lines(evidence: Sequence[Evidence]) -> tuple[str, ...]:
    return tuple(
        f"- {entry.document_id}{_locator(entry)}: “{entry.verbatim_span}”" for entry in evidence
    )


def _entities(finding: Finding) -> str:
    return ", ".join(finding.affected_entities) if finding.affected_entities else _NO_ENTITIES


def _header(finding: Finding, artifact: str) -> str:
    return "\n".join(
        (
            f"{artifact} — {finding.title}",
            f"Finding: {finding.finding_id} · Severity: {finding.severity.value} · "
            f"Confidence: {finding.confidence:.0%}",
            f"Affected entities: {_entities(finding)}",
        )
    )


def _footer(lines: Sequence[str]) -> str:
    return "\n".join((*lines, "", _APPROVAL_NOTE))


def render_redline(finding: Finding) -> str:
    """Proposed clause redline: quotes every evidence span and proposes a
    protective frame scoped to the finding and its affected entities."""
    frame = (
        "Proposed frame:\n"
        f"Qualify or strike the provision quoted above so that “{finding.title}” is "
        f"addressed for {_entities(finding)}: {finding.summary} Any revision must "
        "preserve the rights and notice periods captured in the quoted spans, and "
        "require written notice to the buyer before exercise."
    )
    return "\n".join(
        (
            _header(finding, "PROPOSED CLAUSE REDLINE"),
            "",
            f"{_EVIDENCE_LABEL}:",
            *_evidence_lines(finding.evidence),
            "",
            _footer(frame.split("\n")),
        )
    )


def render_seller_request(finding: Finding) -> str:
    """Seller request: a formal written-request frame over the same quoted
    evidence, naming the affected entities the request concerns."""
    frame = (
        "Request to seller:\n"
        f"We request written confirmation and supporting documentation regarding: "
        f"{finding.summary} The request concerns {_entities(finding)} and relies on "
        "the provisions quoted below; please supply the underlying agreements, any "
        "amendments, waivers, or consents, and the current status of the matter."
    )
    return "\n".join(
        (
            _header(finding, "SELLER REQUEST"),
            "",
            f"{_EVIDENCE_LABEL}:",
            *_evidence_lines(finding.evidence),
            "",
            _footer(frame.split("\n")),
        )
    )


def render_clarification_questions(finding: Finding) -> str:
    """Counterparty clarification questions: the three-question bank, each
    parameterized by the finding, each grounded in the quoted evidence."""
    entities = _entities(finding)
    questions = tuple(
        f"Q{i}. {template.format(entities=entities)}\n    In reference to: {finding.title}"
        for i, template in enumerate(_QUESTION_BANK, start=1)
    )
    return "\n".join(
        (
            _header(finding, "CLARIFICATION QUESTIONS FOR COUNTERPARTY"),
            "",
            *questions,
            "",
            f"{_EVIDENCE_LABEL}:",
            *_evidence_lines(finding.evidence),
            "",
            _APPROVAL_NOTE,
        )
    )
