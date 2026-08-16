"""Document classifier + workstream router (BUILD_PLAN D4-M5).

Routing decisions are pure: no event emission here — the pipeline owns the
``document.routed`` event. ``FakeClassifier`` is the deterministic offline
decision engine; ``FlashClassifier`` is the guarded live client
(gemini-3.5-flash is served only at location=global, see docs/model_ids.md).
"""

from __future__ import annotations

import json
import os
from typing import Any, Final, Protocol

from ingestion.models import ClassHint, RouteDecision
from ingestion.sentinel import injection_markers

FLASH_MODEL_ID: Final[str] = "gemini-3.5-flash"
_FLASH_FLAG = "DILIGENCE_FLASH_CLASSIFIER_ENABLED"

WORKSTREAMS: frozenset[str] = frozenset(
    {"legal", "finance", "hr", "ip_tech", "tax", "regulatory", "esg", "real_estate"}
)


class Classifier(Protocol):
    def classify(self, document_id: str, text: str, hint: ClassHint | None) -> RouteDecision: ...


_DOC_TYPE_WORKSTREAM: dict[str, str | None] = {
    "contract": "legal",
    "license_agreement": "legal",
    "financial_statement": "finance",
    "invoice": "finance",
    "hr_roster": "hr",
    "tech_inventory": "ip_tech",
    "tax_notice": "tax",
    "regulatory_filing": "regulatory",
    "esg_report": "esg",
    "lease": "real_estate",
    "correspondence": None,
}

_DOC_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "contract": (
        "master services agreement",
        "agreement",
        "clause",
        "termination right",
        "indemnification",
        "settlement",
        "legal counsel",
        "governed by",
    ),
    "license_agreement": ("software license", "licensor", "licensee", "exclusivity"),
    "financial_statement": (
        "revenue",
        "earnings",
        "projection",
        "ebitda",
        "gross-margin",
        "concentration",
    ),
    "invoice": ("invoice", "amount due", "remittance"),
    "hr_roster": (
        "roster",
        "resignation",
        "employee",
        "departure",
        "key-person",
        "human resources",
        "succession",
    ),
    "tech_inventory": (
        "asset inventory",
        "end-of-life",
        "component",
        "runtime migration",
        "subsystem",
        "open-source",
    ),
    "tax_notice": (
        "irs",
        "transfer pricing",
        "withholding",
        "franchise tax",
        "deferred tax",
        "apportionment",
        "tax counsel",
    ),
    "regulatory_filing": (
        "regulatory filing",
        "agency",
        "compliance report",
        "corrective action",
        "audit response",
        "comment period",
    ),
    "esg_report": ("emissions", "sustainability", "esg", "carbon", "renewable"),
    "lease": ("lease", "premises", "landlord", "tenant", "zoning", "title report"),
    "correspondence": ("memo", "regarding", "meeting notes", "subject:"),
}

_EVIDENCE_WORKSTREAM: dict[str, tuple[str, ...]] = {
    "ip_tech": ("fleet", "subsystem", "engineering", "maintenance", "component"),
    "finance": ("payment", "remittance", "revenue", "invoice"),
    "hr": ("employee", "roster"),
    "legal": ("clause", "agreement"),
}


def _score_doc_types(lowered: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
        score = sum(lowered.count(keyword) for keyword in keywords)
        if score:
            scores[doc_type] = scores.get(doc_type, 0) + score
    return scores


def _evidence_workstream(lowered: str) -> str | None:
    hits = {
        workstream: sum(lowered.count(keyword) for keyword in keywords)
        for workstream, keywords in _EVIDENCE_WORKSTREAM.items()
    }
    hits = {workstream: count for workstream, count in hits.items() if count}
    if not hits:
        return None
    return max(hits, key=lambda workstream: hits[workstream])


class FakeClassifier:
    """Deterministic offline classifier/router."""

    def classify(self, document_id: str, text: str, hint: ClassHint | None) -> RouteDecision:
        markers = injection_markers(text)
        if markers:
            return RouteDecision(
                document_id=document_id,
                doc_type="other",
                workstream=None,
                confidence=0.99,
                reasons=(f"injection_guard:{','.join(markers)}",),
            )
        lowered = text.lower()
        scores = _score_doc_types(lowered)
        reasons: list[str] = []
        if hint is not None:
            reasons.append(f"hint:{hint.label}")
        if not scores:
            if hint is not None and hint.label == "other":
                reasons.append("hint_agreement")
            return RouteDecision(
                document_id=document_id,
                doc_type="other",
                workstream=None,
                confidence=0.0,
                reasons=tuple(reasons or ("no evidence",)),
            )
        doc_type = max(scores, key=lambda label: scores[label])
        if doc_type == "correspondence":
            workstream = _evidence_workstream(lowered)
        else:
            workstream = _DOC_TYPE_WORKSTREAM[doc_type]
        confidence = min(1.0, 0.5 + 0.05 * min(scores[doc_type], 6))
        if hint is not None:
            if hint.label == doc_type:
                confidence = min(1.0, confidence + 0.15)
                reasons.append("hint_agreement")
            else:
                reasons.append(f"hint_disagrees:{hint.label}")
        reasons.append(f"evidence:{doc_type}")
        return RouteDecision(
            document_id=document_id,
            doc_type=doc_type,
            workstream=workstream,
            confidence=round(confidence, 3),
            reasons=tuple(reasons),
        )


def _parse_route_json(raw: str) -> dict[str, object] | None:
    text = raw.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        text = text[newline + 1 :] if newline != -1 else ""
        if text.endswith("```"):
            text = text[:-3]
    try:
        data = json.loads(text.strip())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class FlashClassifier:
    """Live Flash classifier behind the --confirm-live style env flag."""

    def __init__(self) -> None:
        if os.environ.get(_FLASH_FLAG) != "1":
            raise RuntimeError("FlashClassifier disabled: set DILIGENCE_FLASH_CLASSIFIER_ENABLED=1")
        if not os.environ.get("GOOGLE_CLOUD_PROJECT") or not os.environ.get(
            "GOOGLE_CLOUD_LOCATION"
        ):
            raise RuntimeError(
                "FlashClassifier requires GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION"
            )
        from google import genai

        self._client = genai.Client(vertexai=True)
        self._model_id = FLASH_MODEL_ID

    def classify(self, document_id: str, text: str, hint: ClassHint | None) -> RouteDecision:
        hint_note = (
            f"A cheap sentinel pre-classified this as {hint.label} "
            f"({hint.rationale}). Use it as a hint only.\n\n"
            if hint is not None
            else ""
        )
        prompt = (
            "Route this due-diligence document. Reply with ONLY a JSON object: "
            '{"doc_type": str, "workstream": one of legal|finance|hr|ip_tech|tax|'
            "regulatory|esg|real_estate or null when unclassifiable/junk, "
            '"confidence": 0.0-1.0, "reasons": [str]}\n\n'
            f"{hint_note}DOCUMENT TEXT:\n{text[:12000]}"
        )
        response = self._client.models.generate_content(model=self._model_id, contents=prompt)
        raw: Any = getattr(response, "text", "") or ""
        data = _parse_route_json(str(raw))
        if data is None:
            return RouteDecision(
                document_id=document_id,
                doc_type="other",
                workstream=None,
                confidence=0.0,
                reasons=("parse_error",),
            )
        workstream = data.get("workstream")
        normalized = (
            str(workstream) if isinstance(workstream, str) and workstream in WORKSTREAMS else None
        )
        confidence = data.get("confidence")
        raw_reasons = data.get("reasons")
        reasons = (
            tuple(str(item) for item in raw_reasons if isinstance(item, str))
            if isinstance(raw_reasons, list)
            else ()
        )
        return RouteDecision(
            document_id=document_id,
            doc_type=str(data.get("doc_type", "other")),
            workstream=normalized,
            confidence=float(confidence) if isinstance(confidence, int | float) else 0.0,
            reasons=reasons or ("flash",),
        )
