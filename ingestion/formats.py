"""Structural document format detection (BUILD_PLAN D4-M1).

Detection is structural — magic bytes and internal container layout, never
the file extension (extensions lie in adversarial bundles). Scanned PDFs are
recognized as pages with no extractable text so the pipeline can mark them
``needs_ocr`` instead of fabricating text.
"""

from __future__ import annotations

import zipfile
from email.parser import BytesParser
from email.policy import default as email_policy
from io import BytesIO

from ingestion.models import FormatInfo, FormatKind

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

_MIME_PDF = "application/pdf"
_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_EML = "message/rfc822"
_MIME_OCTET = "application/octet-stream"

_SCANNED_SAMPLE_PAGES = 5
_SCANNED_CHAR_THRESHOLD = 50
_EML_REQUIRED_HEADERS = ("from", "to", "subject")


def _sniff_pdf(blob: bytes) -> FormatInfo:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(blob))
        pages = reader.pages[:_SCANNED_SAMPLE_PAGES]
        if not pages:
            return FormatInfo(FormatKind.UNKNOWN, _MIME_OCTET, 0.0, False, "pdf without pages")
        total_chars = sum(len((page.extract_text() or "").strip()) for page in pages)
    except Exception:  # noqa: BLE001 — unparseable bytes fall to UNKNOWN
        return FormatInfo(
            FormatKind.UNKNOWN, _MIME_OCTET, 0.0, False, "pdf header present but unparseable"
        )
    if total_chars < _SCANNED_CHAR_THRESHOLD:
        return FormatInfo(
            FormatKind.SCANNED_PDF,
            _MIME_PDF,
            0.95,
            True,
            f"{total_chars} extractable chars over {len(pages)} sampled pages",
        )
    return FormatInfo(
        FormatKind.NATIVE_PDF, _MIME_PDF, 1.0, False, "pdf with extractable text layer"
    )


def _sniff_zip(blob: bytes) -> FormatInfo:
    try:
        with zipfile.ZipFile(BytesIO(blob)) as archive:
            names = set(archive.namelist())
    except Exception:  # noqa: BLE001 — corrupt zip is unknown
        return FormatInfo(FormatKind.UNKNOWN, _MIME_OCTET, 0.0, False, "corrupt zip container")
    if "xl/workbook.xml" in names:
        return FormatInfo(FormatKind.XLSX, _MIME_XLSX, 1.0, False, "zip with xl/workbook.xml")
    if "word/document.xml" in names:
        return FormatInfo(FormatKind.DOCX, _MIME_DOCX, 1.0, False, "zip with word/document.xml")
    return FormatInfo(
        FormatKind.UNKNOWN, _MIME_OCTET, 0.0, False, "zip container, unrecognized layout"
    )


def _sniff_eml(blob: bytes) -> FormatInfo | None:
    try:
        message = BytesParser(policy=email_policy).parse(BytesIO(blob))
    except Exception:  # noqa: BLE001
        return None
    present = [name for name in _EML_REQUIRED_HEADERS if message.get(name)]
    if len(present) >= 2 and not message.defects:
        return FormatInfo(
            FormatKind.EML,
            _MIME_EML,
            0.8,
            False,
            f"rfc822 headers present: {', '.join(present)}",
        )
    return None


def detect_format(blob: bytes, name: str) -> FormatInfo:
    """Structurally classify *blob*; *name* is recorded only, never trusted."""
    if blob.startswith(_PDF_MAGIC):
        return _sniff_pdf(blob)
    if blob.startswith(_ZIP_MAGIC):
        return _sniff_zip(blob)
    if blob.startswith(_PNG_MAGIC):
        return FormatInfo(FormatKind.IMAGE, "image/png", 1.0, True, "png magic bytes")
    if blob.startswith(_JPEG_MAGIC):
        return FormatInfo(FormatKind.IMAGE, "image/jpeg", 1.0, True, "jpeg magic bytes")
    eml = _sniff_eml(blob)
    if eml is not None:
        return eml
    return FormatInfo(
        FormatKind.UNKNOWN,
        _MIME_OCTET,
        0.0,
        False,
        f"no structural signature matched for {name!r}",
    )
