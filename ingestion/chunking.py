"""Chunk extraction with resolvable locators (BUILD_PLAN D4-M2, vision §7.3).

Chunking strategies per document class: clause-level splitting for contracts
(numbered-clause headings, paragraph fallback when no markers exist),
sheet/row-group chunks for spreadsheets, paragraph chunks for correspondence.
Every chunk's ``text`` is a byte-identical substring of ``doc.text`` so
downstream evidence gates can quote spans verbatim.
"""

from __future__ import annotations

import re

from ingestion.models import Chunk, FormatKind, ParsedDoc

_CLAUSE_HEADING = re.compile(r"(?m)^(\d+(?:\.\d+)*)\.?[ \t]+\S")
_ROW_GROUP_SIZE = 20


def _clause_chunks(text: str, headings: list[re.Match[str]]) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for index, match in enumerate(headings):
        start = match.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        chunks.append(
            Chunk(
                locator=f"clause:{match.group(1)}",
                text=text[start:end],
                kind="clause",
            )
        )
    return tuple(chunks)


def _paragraph_chunks(text: str) -> tuple[Chunk, ...]:
    chunks = [
        Chunk(locator=f"para:{index}", text=line, kind="paragraph")
        for index, line in enumerate(line for line in text.split("\n") if line.strip())
    ]
    return tuple(chunks)


def _row_group_chunks(doc: ParsedDoc) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for table in doc.tables:
        lines = ["\t".join(table.headers), *("\t".join(row) for row in table.rows)]
        lines = [line for line in lines if line.strip()]
        for start in range(0, len(lines), _ROW_GROUP_SIZE):
            group = lines[start : start + _ROW_GROUP_SIZE]
            chunks.append(
                Chunk(
                    locator=f"sheet:{table.name}!rows:{start + 1}-{start + len(group)}",
                    text="\n".join(group),
                    kind="row_group",
                )
            )
    return tuple(chunks)


def chunk(doc: ParsedDoc) -> tuple[Chunk, ...]:
    """Split *doc* into located chunks; returns () when there is no text."""
    text = doc.text
    if text is None:
        return ()
    if doc.format.kind is FormatKind.XLSX:
        return _row_group_chunks(doc)
    headings = list(_CLAUSE_HEADING.finditer(text))
    if len(headings) >= 2:
        return _clause_chunks(text, headings)
    return _paragraph_chunks(text)
