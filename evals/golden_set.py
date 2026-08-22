"""Golden set — 20 pinned docs + expected findings (BUILD_PLAN D12-M1).

The golden set is the shadow-eval harness's baseline source of truth: the
committed clean corpus — every parseable artifact under ``data/vantage_robotics``
and ``data/scenarios`` except the injection probe — with the expected finding
titles, affected entities, and chunk locators the offline fleet producers
(``agents/fleet.py``) must surface for the four keystone documents. The
remaining sixteen documents carry no expected findings: they are the noise and
scaffold corpus a correct fleet must not over-report on.

Keystone pins are byte-exact and mirror ``tests/test_dataset_artifacts.py``:

- ``contract_meridian_logistics.pdf`` — CoC termination right at ``clause:11.3``
  (``COC_SPAN``: "may terminate…ninety (90) days").
- ``financials_fy27.xlsx`` — "FY27 Projected Revenue" sheet, Meridian =
  8,893,800 / 48,600,000 = exactly 18.300%.
- ``hr_roster_vantage.xlsx`` — Dana Whitfield resignation effective
  ``WHITFIELD_DEPARTURE`` = roster reference date + 60 days.
- ``tech_inventory.pdf`` — TitanBridge 4.1 vendor end-of-life entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

_CUSTOMER_X: Final = "Meridian Logistics, Inc."

# Keystone planted facts (byte-exact; mirrored in tests/test_dataset_artifacts.py).
COC_SPAN: Final = (
    "may terminate this Agreement by written notice delivered within ninety "
    "(90) days following a Change of Control"
)
COC_CLAUSE_LOCATOR: Final = "clause:11.3"
FY27_REVENUE_SHEET: Final = "FY27 Projected Revenue"
GOLDEN_CONCENTRATION_RATIO: Final = 0.183
ROSTER_REFERENCE_DATE: Final = date(2026, 8, 14)
WHITFIELD_DEPARTURE: Final = date(2026, 10, 13)

_ROOT: Final = Path(__file__).resolve().parent.parent
DATA_DIR: Final = _ROOT / "data" / "vantage_robotics"
SCENARIOS_DIR: Final = _ROOT / "data" / "scenarios"


@dataclass(frozen=True, slots=True)
class GoldenDoc:
    """One pinned corpus document with the findings the fleet must surface.

    ``locators`` are chunk locators (vision §7.3) that must resolve against the
    committed artifact; ``needs_ocr`` mirrors structural format detection —
    flagged docs parse to ``text=None`` and are exempt from text-level pins.
    """

    doc_id: str
    expected_finding_titles: tuple[str, ...]
    expected_entities: tuple[str, ...]
    locators: tuple[str, ...]
    needs_ocr: bool


def _keystone(doc_id: str, title: str, entities: tuple[str, ...], locator: str) -> GoldenDoc:
    return GoldenDoc(
        doc_id=doc_id,
        expected_finding_titles=(title,),
        expected_entities=entities,
        locators=(locator,),
        needs_ocr=False,
    )


def _bare(doc_id: str, *, needs_ocr: bool = False) -> GoldenDoc:
    return GoldenDoc(
        doc_id=doc_id,
        expected_finding_titles=(),
        expected_entities=(),
        locators=(),
        needs_ocr=needs_ocr,
    )


GOLDEN_SET: Final[tuple[GoldenDoc, ...]] = (
    # Keystone documents: one gated finding each, titles byte-identical to the
    # agents/fleet.py offline producers.
    _keystone(
        "contract_meridian_logistics.pdf",
        "Meridian Logistics change-of-control termination right",
        (_CUSTOMER_X,),
        COC_CLAUSE_LOCATOR,
    ),
    _keystone(
        "financials_fy27.xlsx",
        "Meridian Logistics revenue concentration",
        (_CUSTOMER_X,),
        f"sheet:{FY27_REVENUE_SHEET}!rows:1-7",
    ),
    _keystone(
        "hr_roster_vantage.xlsx",
        "Key-person departure: Meridian account owner",
        ("Dana Whitfield", _CUSTOMER_X),
        "sheet:Roster!rows:1-6",
    ),
    _keystone(
        "tech_inventory.pdf",
        "Unsupported dependency: TitanBridge 4.1 at vendor end-of-life",
        (_CUSTOMER_X,),
        "para:4",
    ),
    # Noise + scaffold corpus (no expected findings).
    _bare("amendment_2030.pdf"),
    _bare("board_minutes_q2.pdf"),
    _bare("email_thread_export.pdf"),
    _bare("esg_report.pdf"),
    _bare("facilities_inspection.pdf"),
    _bare("insurance_certificate.pdf"),
    _bare("it_incident_log.pdf"),
    _bare("lease_meridian.pdf"),
    _bare("meeting_notes_ops_sync.pdf"),
    _bare("quarterly_budget_notes.xlsx"),
    _bare("regulatory_correspondence.pdf"),
    _bare("scanned_memo_vendor.pdf"),
    _bare("tax_exposure.pdf"),
    _bare("vendor_agreement_2027.pdf"),
    _bare("memo_fleet_operations.docx"),
    _bare("scanned_invoice.pdf", needs_ocr=True),
)

_BY_DOC_ID: Final[dict[str, GoldenDoc]] = {doc.doc_id: doc for doc in GOLDEN_SET}


def load_golden_set() -> tuple[GoldenDoc, ...]:
    """Return the pinned golden set (harness baseline source of truth)."""
    return GOLDEN_SET


def golden_doc(doc_id: str) -> GoldenDoc:
    """Look up one golden doc by id; raises ``KeyError`` when unpinned."""
    return _BY_DOC_ID[doc_id]


def golden_path(doc_id: str) -> Path:
    """Resolve a golden doc_id to its committed artifact path.

    Raises ``FileNotFoundError`` when the artifact is missing from both data
    directories — the golden set must never reference a doc not on disk.
    """
    for base in (DATA_DIR, SCENARIOS_DIR):
        candidate = base / doc_id
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"golden doc {doc_id!r} not committed under data/")
