"""Planted-fact tests for the committed synthetic dataset artifacts (D2-M4/S5).

The contract PDF and FY27 financials carry the keystone demo facts; these
tests pin them byte-exactly so later gates (evidence gate, golden set) can
quote them verbatim.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from scripts.author_dataset import (
    MERIDIAN_REVENUE,
    TOTAL_REVENUE,
    write_contract_customer_x,
    write_financials_fy27,
    write_hr_roster,
    write_tech_inventory_draft,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "acme_robotics"
CONTRACT_PDF = DATA_DIR / "contract_customer_x.pdf"
FINANCIALS_XLSX = DATA_DIR / "financials_fy27.xlsx"
HR_ROSTER_XLSX = DATA_DIR / "hr_roster_acme.xlsx"
TECH_INVENTORY_PDF = DATA_DIR / "tech_inventory.pdf"

ROSTER_DATE = date(2026, 8, 14)
WHITFIELD_DEPARTURE = date(2026, 10, 13)

COC_SPAN = (
    "may terminate this Agreement by written notice delivered within ninety "
    "(90) days following a Change of Control"
)

EXPECTED_REVENUES: dict[str, int] = {
    "Meridian Logistics, Inc.": 8_893_800,
    "Halbrook Manufacturing": 12_400_000,
    "Cascade Retail Group": 9_850_000,
    "Public Sector & Municipal": 8_106_200,
    "Other (43 accounts)": 9_350_000,
}
EXPECTED_TOTAL = 48_600_000


def _normalized_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return " ".join(raw.split())


class TestContractArtifact:
    def test_coc_span_extractable_byte_exact(self) -> None:
        assert COC_SPAN in _normalized_pdf_text(CONTRACT_PDF)

    def test_meridian_is_a_party(self) -> None:
        assert "Meridian Logistics" in _normalized_pdf_text(CONTRACT_PDF)

    def test_clause_locator_present(self) -> None:
        assert "11.3" in _normalized_pdf_text(CONTRACT_PDF)

    def test_regeneration_is_byte_identical(self, tmp_path: Path) -> None:
        regenerated = tmp_path / "contract_customer_x.pdf"
        write_contract_customer_x(regenerated)
        assert regenerated.read_bytes() == CONTRACT_PDF.read_bytes()


class TestFinancialsArtifact:
    def _revenue_rows(self, path: Path) -> dict[str, int]:
        workbook = load_workbook(path, data_only=True)
        sheet = workbook["FY27 Projected Revenue"]
        rows: dict[str, int] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            customer, _segment, revenue, _percent = row[0], row[1], row[2], row[3]
            if customer is None or customer == "TOTAL":
                continue
            assert isinstance(revenue, (int, float))
            rows[str(customer)] = int(revenue)
        return rows

    def _total_row(self, path: Path) -> int:
        workbook = load_workbook(path, data_only=True)
        sheet = workbook["FY27 Projected Revenue"]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row[0] == "TOTAL":
                total = row[2]
                assert isinstance(total, (int, float))
                return int(total)
        raise AssertionError("TOTAL row missing from FY27 Projected Revenue sheet")

    def test_exact_customer_revenues(self) -> None:
        assert self._revenue_rows(FINANCIALS_XLSX) == EXPECTED_REVENUES

    def test_total_and_share_of_customer_x(self) -> None:
        total = self._total_row(FINANCIALS_XLSX)
        meridian = self._revenue_rows(FINANCIALS_XLSX)["Meridian Logistics, Inc."]
        assert total == EXPECTED_TOTAL
        assert sum(EXPECTED_REVENUES.values()) == EXPECTED_TOTAL
        ratio = meridian / total
        assert ratio == 0.183
        assert f"{ratio:.3%}" == "18.300%"

    def test_regeneration_preserves_values(self, tmp_path: Path) -> None:
        regenerated = tmp_path / "financials_fy27.xlsx"
        write_financials_fy27(regenerated)
        assert self._revenue_rows(regenerated) == self._revenue_rows(FINANCIALS_XLSX)
        assert self._total_row(regenerated) == self._total_row(FINANCIALS_XLSX)


class TestHrRosterAndTechInventory:
    def _whitfield_row(self, path: Path) -> tuple[object, ...]:
        workbook = load_workbook(path)
        sheet = workbook["Roster"]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row[0] == "Dana Whitfield":
                return row
        raise AssertionError("Dana Whitfield missing from HR roster")

    def test_hr_roster_finalized_without_draft_flag(self) -> None:
        workbook = load_workbook(HR_ROSTER_XLSX)
        assert "Roster" in workbook.sheetnames
        assert not any("DRAFT" in name for name in workbook.sheetnames)

    def test_hr_roster_contains_whitfield_resignation(self) -> None:
        whitfield = self._whitfield_row(HR_ROSTER_XLSX)
        assert whitfield[1] == "VP Customer Success"
        assert whitfield[3] == "Meridian Logistics, Inc."
        assert whitfield[4] == "Resigning"
        departure = whitfield[5]
        assert isinstance(departure, datetime)
        assert departure.date() == WHITFIELD_DEPARTURE
        assert (departure.date() - ROSTER_DATE).days == 60

    def test_hr_roster_regeneration_preserves_whitfield(self, tmp_path: Path) -> None:
        regenerated = tmp_path / "hr_roster_acme.xlsx"
        write_hr_roster(regenerated)
        assert self._whitfield_row(regenerated) == self._whitfield_row(HR_ROSTER_XLSX)

    def test_tech_inventory_flagged_draft_with_titanbridge(self) -> None:
        text = _normalized_pdf_text(TECH_INVENTORY_PDF)
        assert "DRAFT" in text
        assert "TitanBridge 4.1" in text
        assert "Meridian" in text

    def test_tech_inventory_regeneration_byte_identical(self, tmp_path: Path) -> None:
        regenerated = tmp_path / "tech_inventory.pdf"
        write_tech_inventory_draft(regenerated)
        assert regenerated.read_bytes() == TECH_INVENTORY_PDF.read_bytes()


class TestDatasetConsistency:
    def test_customer_x_share_exact_in_workbook(self) -> None:
        financials = TestFinancialsArtifact()
        meridian = financials._revenue_rows(FINANCIALS_XLSX)["Meridian Logistics, Inc."]
        total = financials._total_row(FINANCIALS_XLSX)
        assert meridian == MERIDIAN_REVENUE
        assert total == TOTAL_REVENUE
        assert meridian / total == 0.183
        assert f"{meridian / total:.3%}" == "18.300%"

    def test_plan_doc_pins_the_same_figures(self) -> None:
        plan = (DATA_DIR / "DATASET_PLAN.md").read_text(encoding="utf-8")
        assert "8,893,800" in plan
        assert "48,600,000" in plan
        assert "18.300%" in plan
