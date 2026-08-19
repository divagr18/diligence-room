"""Chunking-with-locators tests (BUILD_PLAN D4-M2, vision §7.3, scenario S1)."""

from __future__ import annotations

import re
from pathlib import Path

from ingestion.chunking import chunk
from ingestion.parsing import LocalParser

_DATA = Path(__file__).resolve().parent.parent / "data" / "vantage_robotics"

_CLAUSE_11_3 = (
    "11.3 Termination Right. Either Party may terminate this Agreement by written "
    "notice delivered within ninety (90) days following a Change of Control of the "
    "other Party, effective on the date specified in such notice."
)


class TestChunking:
    def test_contract_clause_chunks_split_on_numbered_boundaries(self) -> None:
        doc = LocalParser().parse(
            (_DATA / "contract_meridian_logistics.pdf").read_bytes(),
            "contract_meridian_logistics.pdf",
            "deal-falcon",
        )
        chunks = chunk(doc)
        locators = [c.locator for c in chunks]
        assert "clause:11.3" in locators
        assert "clause:11.1" in locators
        assert all(c.kind == "clause" for c in chunks)

    def test_locator_resolves_verbatim_coc_span(self) -> None:
        doc = LocalParser().parse(
            (_DATA / "contract_meridian_logistics.pdf").read_bytes(),
            "contract_meridian_logistics.pdf",
            "deal-falcon",
        )
        assert doc.text is not None
        chunks = chunk(doc)
        target = next(c for c in chunks if c.locator == "clause:11.3")
        assert target.text in doc.text  # byte-identical substring of parsed text
        normalized_chunk = re.sub(r"\s+", " ", target.text).strip()
        normalized_source = re.sub(r"\s+", " ", _CLAUSE_11_3).strip()
        assert normalized_chunk.startswith(normalized_source[:80])

    def test_paragraph_fallback_without_clause_markers(self) -> None:
        from ingestion.models import FormatInfo, FormatKind, ParsedDoc

        text = "First prose paragraph.\nSecond prose paragraph."
        doc = ParsedDoc(
            document_id="memo.eml",
            deal_id="deal-falcon",
            format=FormatInfo(FormatKind.EML, "message/rfc822", 0.8, False, "test"),
            text=text,
            tables=(),
            chunks=(),
            metadata={},
        )
        chunks = chunk(doc)
        assert [c.locator for c in chunks] == ["para:0", "para:1"]
        assert all(c.text in text for c in chunks)
        assert chunks[0].text == "First prose paragraph."
        assert chunks[0].kind == "paragraph"

    def test_xlsx_sheet_row_group_chunks(self) -> None:
        doc = LocalParser().parse(
            (_DATA / "financials_fy27.xlsx").read_bytes(), "financials_fy27.xlsx", "deal-falcon"
        )
        assert doc.text is not None
        chunks = chunk(doc)
        assert chunks, "xlsx must chunk"
        assert all(c.locator.startswith("sheet:") for c in chunks)
        assert all(c.kind == "row_group" for c in chunks)
        assert all(c.text in doc.text for c in chunks)
        assert any("Meridian" in c.text for c in chunks)

    def test_scanned_doc_yields_no_chunks(self) -> None:
        from ingestion.models import FormatInfo, FormatKind, ParsedDoc

        doc = ParsedDoc(
            document_id="scan.pdf",
            deal_id="deal-falcon",
            format=FormatInfo(FormatKind.SCANNED_PDF, "application/pdf", 0.95, True, "test"),
            text=None,
            tables=(),
            chunks=(),
            metadata={},
        )
        assert chunk(doc) == ()
