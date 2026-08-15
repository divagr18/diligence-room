"""Planted-fact tests for the committed synthetic dataset artifacts (D2-M4/S5).

The contract PDF and FY27 financials carry the keystone demo facts; these
tests pin them byte-exactly so later gates (evidence gate, golden set) can
quote them verbatim.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from scripts.author_dataset import write_contract_customer_x, write_financials_fy27

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "acme_robotics"
CONTRACT_PDF = DATA_DIR / "contract_customer_x.pdf"
FINANCIALS_XLSX = DATA_DIR / "financials_fy27.xlsx"

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
