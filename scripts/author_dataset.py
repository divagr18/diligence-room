"""Deterministic synthetic dataset generator (BUILD_PLAN D2-M4 + D2-M6 drafts).

Produces the committed dataset artifacts carrying the keystone demo facts:

- ``contract_customer_x.pdf`` — Acme Robotics master services agreement with
  Meridian Logistics (Customer X), including the change-of-control
  termination right at clause 11.3.
- ``financials_fy27.xlsx`` — projected FY27 revenue by customer, where
  Meridian Logistics is exactly 18.300% of the total.
- ``hr_roster_acme.xlsx`` — DRAFT roster (finalized D3-M7) with Dana
  Whitfield's resignation dated roster-date + 60 days.
- ``tech_inventory.pdf`` — DRAFT asset inventory (finalized D4-M3) with the
  TitanBridge 4.1 end-of-life dependency.

All writers are deterministic (pinned metadata timestamps, no formulas, no
runtime clock reads) so regeneration yields identical content; the tests in
tests/test_dataset_artifacts.py pin the planted facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from openpyxl import Workbook

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "acme_robotics"

_PINNED_DATE = datetime(2026, 7, 1, 9, 0, 0)
_PINNED_DATE_UTC = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)

_ROSTER_DATE = date(2026, 8, 14)
_WHITFIELD_DEPARTURE = _ROSTER_DATE + timedelta(days=60)

_SECTION_FONT_SIZE = 11
_LINE_HEIGHT = 6


@dataclass(frozen=True)
class _CustomerRevenue:
    customer: str
    segment: str
    revenue: int


_CUSTOMER_REVENUES: tuple[_CustomerRevenue, ...] = (
    _CustomerRevenue("Meridian Logistics, Inc.", "Enterprise Logistics", 8_893_800),
    _CustomerRevenue("Halbrook Manufacturing", "Manufacturing", 12_400_000),
    _CustomerRevenue("Cascade Retail Group", "Retail", 9_850_000),
    _CustomerRevenue("Public Sector & Municipal", "Public Sector", 8_106_200),
    _CustomerRevenue("Other (43 accounts)", "Mixed", 9_350_000),
)
_TOTAL_REVENUE = 48_600_000


def _contract_paragraphs() -> list[tuple[str, str]]:
    intro = (
        'This Master Services Agreement (this "Agreement") is entered into as of '
        'July 1, 2026 (the "Effective Date") by and between Acme Robotics, Inc., a '
        "Delaware corporation with its principal place of business at 400 Industrial "
        'Way, Pittsburgh, Pennsylvania ("Provider"), and Meridian Logistics, Inc., '
        "a New York corporation with its principal place of business at 12 Harbor "
        'Row, New York, New York ("Customer"). Provider and Customer are each a '
        '"Party" and together the "Parties".'
    )
    sections: list[tuple[str, str]] = [
        ("1. Definitions", "Capitalized terms have the meanings given in this Section 1."),
        (
            "2. Services",
            "Provider shall deliver the autonomous fleet orchestration services, "
            "maintenance, and support described in the applicable statements of work.",
        ),
        (
            "3. Fees and Payment",
            "Customer shall pay the fees set forth in each statement of work within "
            "thirty (30) days of invoice. Late amounts accrue interest at 1.5% per month.",
        ),
        (
            "4. Term",
            "The initial term of this Agreement is three (3) years from the Effective "
            "Date, renewing for successive one (1) year periods unless terminated earlier.",
        ),
        (
            "5. Confidentiality",
            "Each Party shall protect the other Party's confidential information using "
            "at least reasonable care and shall not disclose it except as required here.",
        ),
        (
            "6. Intellectual Property",
            "Provider retains all right, title, and interest in its pre-existing "
            "technology. Customer retains all right, title, and interest in its data.",
        ),
        (
            "7. Warranties; Disclaimer",
            "Provider warrants that the services will be performed in a professional "
            'manner. EXCEPT AS EXPRESSLY STATED, THE SERVICES ARE PROVIDED "AS IS".',
        ),
        (
            "8. Limitation of Liability",
            "Neither Party is liable for indirect or consequential damages. Provider's "
            "aggregate liability does not exceed fees paid in the twelve (12) months "
            "preceding the claim.",
        ),
        (
            "9. Indemnification",
            "Each Party shall indemnify the other against third-party claims arising "
            "from its negligence or willful misconduct.",
        ),
        (
            "10. Assignment",
            "Neither Party may assign this Agreement without the other Party's prior "
            "written consent, except to a successor in a permitted transaction under "
            "Section 11.",
        ),
        (
            "11. Change of Control",
            "The provisions of this Section 11 govern the effect of a Change of Control "
            "on this Agreement.",
        ),
    ]
    clause_11_1 = (
        '11.1 Definition. "Change of Control" means, with respect to a Party, any '
        "transaction or series of related transactions by which a Person or group of "
        "Persons acquires, directly or indirectly, ownership or control of more than "
        "fifty percent (50%) of the voting securities of such Party, or all or "
        "substantially all of its assets, including by merger, acquisition, or sale."
    )
    clause_11_2 = (
        "11.2 Notice. A Party that enters into a definitive agreement that would "
        "result in a Change of Control shall promptly notify the other Party in writing."
    )
    clause_11_3 = (
        "11.3 Termination Right. Either Party may terminate this Agreement by written "
        "notice delivered within ninety (90) days following a Change of Control of the "
        "other Party, effective on the date specified in such notice."
    )
    section_12 = (
        "12. General Provisions",
        "This Agreement is governed by the laws of the State of Delaware, without "
        "regard to conflict of laws principles. This Agreement is the entire agreement "
        "of the Parties regarding its subject matter and supersedes all prior "
        "agreements and understandings.",
    )
    paragraphs: list[tuple[str, str]] = [("", intro)]
    paragraphs.extend(sections)
    paragraphs.append(("", clause_11_1))
    paragraphs.append(("", clause_11_2))
    paragraphs.append(("", clause_11_3))
    paragraphs.append(section_12)
    return paragraphs


def write_contract_customer_x(path: Path) -> None:
    """Write the deterministic Meridian Logistics master services agreement."""
    pdf = FPDF()
    pdf.creation_date = _PINNED_DATE_UTC
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(
        0,
        10,
        "MASTER SERVICES AGREEMENT",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "", _SECTION_FONT_SIZE)
    for heading, body in _contract_paragraphs():
        if heading:
            pdf.set_font("Helvetica", "B", _SECTION_FONT_SIZE)
            pdf.multi_cell(0, _LINE_HEIGHT, heading, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", _SECTION_FONT_SIZE)
        pdf.multi_cell(0, _LINE_HEIGHT, body, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    pdf.ln(6)
    pdf.set_font("Helvetica", "", _SECTION_FONT_SIZE)
    pdf.multi_cell(
        0,
        _LINE_HEIGHT,
        "IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(8)
    pdf.multi_cell(0, _LINE_HEIGHT, "ACME ROBOTICS, INC.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(
        0,
        _LINE_HEIGHT,
        "By: ______________________  Title: Chief Legal Officer",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)
    pdf.multi_cell(0, _LINE_HEIGHT, "MERIDIAN LOGISTICS, INC.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(
        0,
        _LINE_HEIGHT,
        "By: ______________________  Title: General Counsel",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def write_financials_fy27(path: Path) -> None:
    """Write the deterministic FY27 projected-revenue workbook."""
    workbook = Workbook()
    workbook.properties.created = _PINNED_DATE
    workbook.properties.modified = _PINNED_DATE

    sheet = workbook.worksheets[0]
    sheet.title = "FY27 Projected Revenue"
    sheet.append(["Customer", "Segment", "Projected FY27 Revenue (USD)", "Percent of Total"])
    for entry in _CUSTOMER_REVENUES:
        share = entry.revenue / _TOTAL_REVENUE
        sheet.append([entry.customer, entry.segment, entry.revenue, share])
    sheet.append(["TOTAL", "", _TOTAL_REVENUE, 1.0])
    for row in sheet.iter_rows(min_row=2, min_col=3, max_col=3):
        for cell in row:
            cell.number_format = "#,##0"
    for row in sheet.iter_rows(min_row=2, min_col=4, max_col=4):
        for cell in row:
            cell.number_format = "0.000%"
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 20
    sheet.column_dimensions["C"].width = 30
    sheet.column_dimensions["D"].width = 16

    assumptions = workbook.create_sheet("Assumptions")
    for note in (
        "Synthetic data for the Diligence Room hackathon dataset - not real financials.",
        "FY27 projections are management estimates as of the diligence start date.",
        "Customer X is the internal alias for Meridian Logistics, Inc.",
        f"Total projected FY27 revenue is fixed at {_TOTAL_REVENUE:,} USD.",
    ):
        assumptions.append([note])
    assumptions.column_dimensions["A"].width = 100

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def write_hr_roster_draft(path: Path) -> None:
    """Write the synthetic Acme Robotics HR roster (draft; finalized D3-M7)."""
    workbook = Workbook()
    workbook.properties.created = _PINNED_DATE
    workbook.properties.modified = _PINNED_DATE

    roster = workbook.worksheets[0]
    roster.title = "Roster"
    roster.append(["Employee", "Role", "Department", "Primary Account", "Status", "Departure Date"])
    roster.append(
        [
            "Dana Whitfield",
            "VP Customer Success",
            "Customer Success",
            "Meridian Logistics, Inc.",
            "Resigning",
            datetime.combine(_WHITFIELD_DEPARTURE, datetime.min.time()),
        ]
    )
    for employee, role, department in (
        ("Priya Raman", "Director of Engineering", "Engineering"),
        ("Marcus Bell", "Finance Controller", "Finance"),
        ("Elena Kovacs", "Head of People", "Human Resources"),
        ("Tom Okafor", "Fleet Operations Lead", "Operations"),
    ):
        roster.append([employee, role, department, "", "Employed", None])
    roster.column_dimensions["A"].width = 24
    roster.column_dimensions["B"].width = 26
    roster.column_dimensions["C"].width = 20
    roster.column_dimensions["D"].width = 28
    roster.column_dimensions["E"].width = 14
    roster.column_dimensions["F"].width = 16

    notes = workbook.create_sheet("Notes (DRAFT)")
    for note in (
        "STATUS: DRAFT - authored Day 2 (D2-M6); finalized Day 3 (D3-M7).",
        f"Roster reference date: {_ROSTER_DATE.isoformat()}.",
        "Dana Whitfield owns the Meridian Logistics (Customer X) relationship; "
        "resignation effective 60 days after the roster reference date.",
        "Synthetic data - no real personnel information.",
    ):
        notes.append([note])
    notes.column_dimensions["A"].width = 100

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def write_tech_inventory_draft(path: Path) -> None:
    """Write the synthetic technology asset inventory (draft; finalized D4-M3)."""
    pdf = FPDF()
    pdf.creation_date = _PINNED_DATE_UTC
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "TECHNOLOGY ASSET INVENTORY (DRAFT)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", _SECTION_FONT_SIZE)
    pdf.multi_cell(
        0,
        _LINE_HEIGHT,
        "Acme Robotics, Inc. - prepared for Project Falcon diligence. "
        "Status: DRAFT, authored Day 2 (D2-M6); finalized Day 4 (D4-M3).",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    entries = (
        (
            "Fleet Orchestration Platform",
            "Runs on TitanBridge 4.1 (vendor end-of-life 2026-03; no support "
            "contract). Serves the Meridian Logistics, Inc. account. Migration "
            "to a supported runtime is estimated at 9-12 months.",
        ),
        (
            "Perception Stack",
            "Proprietary computer-vision pipeline; patents assigned to Acme "
            "Robotics, Inc. Open-source components under Apache-2.0.",
        ),
        (
            "Warehouse Gateway",
            "Firmware maintained in-house; hardware refresh due FY28.",
        ),
    )
    for title, body in entries:
        pdf.set_font("Helvetica", "B", _SECTION_FONT_SIZE)
        pdf.multi_cell(0, _LINE_HEIGHT, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", _SECTION_FONT_SIZE)
        pdf.multi_cell(0, _LINE_HEIGHT, body, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def main() -> None:
    contract_path = DATA_DIR / "contract_customer_x.pdf"
    financials_path = DATA_DIR / "financials_fy27.xlsx"
    roster_path = DATA_DIR / "hr_roster_acme.xlsx"
    tech_path = DATA_DIR / "tech_inventory.pdf"
    write_contract_customer_x(contract_path)
    write_financials_fy27(financials_path)
    write_hr_roster_draft(roster_path)
    write_tech_inventory_draft(tech_path)
    print(f"wrote {contract_path}")
    print(f"wrote {financials_path}")
    print(f"wrote {roster_path}")
    print(f"wrote {tech_path}")


if __name__ == "__main__":
    main()
