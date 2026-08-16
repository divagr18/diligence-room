"""Shared ingestion data models (BUILD_PLAN Day 4, Step-0 scaffolding).

Pure data containers consumed by the Day-4 ingestion modules
(``ingestion.formats`` / ``parsing`` / ``chunking`` / ``lineage`` /
``sentinel`` / ``classifier`` / ``pipeline``). Deliberately logic-free:
behaviour lives in the modules that produce and consume these shapes, so
each module owns its own tests.

Vision §8 metadata contract per processed document: document_id, deal_id,
document_type, workstream, classification, security_status,
ingestion_timestamp, source, version, checksum.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FormatKind(StrEnum):
    """Structurally detected document class (D4-M1)."""

    NATIVE_PDF = "native_pdf"
    SCANNED_PDF = "scanned_pdf"
    XLSX = "xlsx"
    DOCX = "docx"
    IMAGE = "image"
    EML = "eml"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FormatInfo:
    """Outcome of structural format detection."""

    kind: FormatKind
    mime: str
    confidence: float
    needs_ocr: bool
    reason: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """A chunked slice of a parsed document with a resolving locator.

    ``locator`` is a stable, human-readable pointer into the source
    document — e.g. ``clause:11.3``, ``sheet:FY27 Projected Revenue!rows:2-6``,
    ``para:7`` — so findings can later quote evidence spans byte-verbatim
    (vision §7.3 chunking; memory/findings.py evidence gate).
    """

    locator: str
    text: str
    kind: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class TableData:
    """An extracted table: header row plus body rows as strings."""

    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ParsedDoc:
    """Parser output contract shared by LocalParser and DocumentAIParser.

    ``text`` is ``None`` (never fabricated) when the document needs OCR and
    no OCR backend is enabled — the honest offline behaviour for scans.
    """

    document_id: str
    deal_id: str
    format: FormatInfo
    text: str | None
    tables: tuple[TableData, ...]
    chunks: tuple[Chunk, ...]
    metadata: Mapping[str, object]


class SentinelDecision(StrEnum):
    """Sentinel outcome for a document (D4-M4)."""

    CLEAR = "clear"
    TRIPWIRE = "tripwire"


@dataclass(frozen=True, slots=True)
class PiiSpan:
    """A character span flagged as likely PII (half-open)."""

    start: int
    end: int
    category: str


@dataclass(frozen=True, slots=True)
class TripwireVerdict:
    """Injection-tripwire outcome."""

    tripped: bool
    reason: str
    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassHint:
    """Cheap pre-classification hint feeding the Flash classifier."""

    label: str
    confidence: float
    rationale: str


@dataclass(frozen=True, slots=True)
class SentinelReport:
    """Aggregated sentinel pass: verdict + hints + trace surface."""

    decision: SentinelDecision
    class_hint: ClassHint
    pii_spans: tuple[PiiSpan, ...]
    tripwire: TripwireVerdict
    span_attributes: Mapping[str, object]


class LineageStatus(StrEnum):
    """Registration verdict from the lineage store (D4-M6)."""

    NEW = "new"
    SUPPRESSED = "suppressed"
    NEW_VERSION = "new_version"


@dataclass(frozen=True, slots=True)
class LineageRecord:
    """Checksum + version-chain record for one document version."""

    document_id: str
    deal_id: str
    logical_key: str
    checksum: str
    version: int
    supersedes: str | None
    ingested_at: datetime
    status: LineageStatus


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Classifier routing outcome (D4-M5).

    ``workstream`` is ``None`` for junk/unclassifiable content that must not
    enter any workstream runtime.
    """

    document_id: str
    doc_type: str
    workstream: str | None
    confidence: float
    reasons: tuple[str, ...]
