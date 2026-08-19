"""Structural format detection tests (BUILD_PLAN D4-M1, scenarios S1/S2)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from PIL import Image

from ingestion.formats import detect_format
from ingestion.models import FormatKind

_DATA = Path(__file__).resolve().parent.parent / "data" / "vantage_robotics"
_PINNED = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)


def _image_only_pdf_bytes() -> bytes:
    """Deterministic scanned-style PDF: one embedded image, no text layer."""
    img = Image.new("RGB", (420, 240), "white")
    png = BytesIO()
    img.save(png, format="PNG")
    png.seek(0)
    pdf = FPDF()
    pdf.creation_date = _PINNED
    pdf.add_page()
    pdf.image(png)
    return bytes(pdf.output())


class TestSniff:
    def test_native_pdf_detected(self) -> None:
        blob = (_DATA / "contract_meridian_logistics.pdf").read_bytes()
        info = detect_format(blob, "contract_meridian_logistics.pdf")
        assert info.kind is FormatKind.NATIVE_PDF
        assert info.needs_ocr is False
        assert info.mime == "application/pdf"
        assert info.confidence > 0.9

    def test_scanned_pdf_detected_needs_ocr(self) -> None:
        info = detect_format(_image_only_pdf_bytes(), "scanned_invoice.pdf")
        assert info.kind is FormatKind.SCANNED_PDF
        assert info.needs_ocr is True
        assert info.confidence > 0.8

    def test_xlsx_detected(self) -> None:
        blob = (_DATA / "financials_fy27.xlsx").read_bytes()
        info = detect_format(blob, "financials_fy27.xlsx")
        assert info.kind is FormatKind.XLSX
        assert info.mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_docx_detected(self) -> None:
        from docx import Document

        doc = Document()
        doc.add_paragraph("Fleet operations memo body.")
        buf = BytesIO()
        doc.save(buf)
        info = detect_format(buf.getvalue(), "memo.docx")
        assert info.kind is FormatKind.DOCX

    def test_eml_detected(self) -> None:
        eml = (
            b"From: dana.whitfield@example.com\r\n"
            b"To: deal-team@example.com\r\n"
            b"Subject: Project Falcon - fleet operations memo\r\n"
            b"Date: Wed, 01 Jul 2026 09:00:00 +0000\r\n"
            b"Message-ID: <memo-1@example.com>\r\n"
            b"\r\n"
            b"Fleet maintenance window moved to next quarter.\r\n"
        )
        info = detect_format(eml, "memo.eml")
        assert info.kind is FormatKind.EML
        assert info.mime == "message/rfc822"

    def test_image_detected(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (16, 16), "black").save(buf, format="PNG")
        info = detect_format(buf.getvalue(), "scan.png")
        assert info.kind is FormatKind.IMAGE
        assert info.needs_ocr is True

    def test_unknown_bytes_rejected_cleanly(self) -> None:
        info = detect_format(b"\x00\x01\x02\x03garbage", "mystery.bin")
        assert info.kind is FormatKind.UNKNOWN
        assert info.confidence == 0.0

    def test_extension_lies_pdf_bytes_named_txt(self) -> None:
        blob = (_DATA / "contract_meridian_logistics.pdf").read_bytes()
        info = detect_format(blob, "actually_a_contract.txt")
        assert info.kind is FormatKind.NATIVE_PDF

    def test_zip_that_is_neither_docx_nor_xlsx(self) -> None:
        import zipfile

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.md", "not an office doc")
        info = detect_format(buf.getvalue(), "bundle.zip")
        assert info.kind is FormatKind.UNKNOWN
        assert "zip" in info.reason.lower()
