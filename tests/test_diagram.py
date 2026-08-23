"""Shape tests for the Day-13 architecture diagram (BUILD_PLAN D13-M5, vision §22).

The diagram is content, not code, so its "test" is a checklist assertion (plan
§7): ``docs/diagram/architecture.mmd`` exists in the committed docs tree, is
genuine Mermaid (a ``flowchart``/``graph`` declaration with real edges) instead
of the ASCII art the vision §22 draft carried, parses structurally (balanced
``subgraph``/``end`` blocks, every edge endpoint resolves to a declared node or
subgraph), covers the full §22 component set, ships rendered SVG/PNG exports,
and is referenced by the README hero.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_ROOT: Final = Path(__file__).resolve().parent.parent
DIAGRAM_DIR: Final = _ROOT / "docs" / "diagram"
DIAGRAM_PATH: Final = DIAGRAM_DIR / "architecture.mmd"
SVG_PATH: Final = DIAGRAM_DIR / "architecture.svg"
PNG_PATH: Final = DIAGRAM_DIR / "architecture.png"
README_PATH: Final = _ROOT / "README.md"

PLACEHOLDER_TOKENS: Final = ("lorem", "tbd", "fixme", "placeholder", "todo")
# Box-drawing / ASCII-art fragments that would mean someone pasted the §22 draft.
ASCII_ART_TOKENS: Final = ("+--", "|--", "┌", "┐", "└", "┘", "│", "─", "▼", "▲")
GRAPH_DECL: Final = re.compile(r"^\s*(flowchart|graph)\s+(TD|TB|LR|RL|BT)\s*$", re.MULTILINE)
NODE_DEF: Final = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\[", re.MULTILINE)
SUBGRAPH_DEF: Final = re.compile(r"^\s*subgraph\s+([A-Za-z_][A-Za-z0-9_]*)\[", re.MULTILINE)
ARROW: Final = re.compile(r"-->|-\.->|==>")
EDGE_LABEL: Final = re.compile(r"^\|[^|]*\|")
ENDPOINT: Final = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")

# vision §22 component set, lower-cased substrings the diagram must carry.
REQUIRED_COMPONENTS: Final = (
    "agent registry",
    "data room",
    "region-pinned",
    "format detection",
    "document ai",
    "gemma sentinel",
    "model armor",
    "cloud dlp",
    "agent gateway",
    "deny-default",
    "legal",
    "finance",
    "hr",
    "ip/tech",
    "tax",
    "regulatory",
    "esg",
    "real estate",
    "coordinator",
    "negotiation",
    "red-flag",
    "dashboard",
    "portfolio",
    "org / deal / workstream",
    "loop guard",
    "evidence gate",
    "crash-resume",
    "opentelemetry",
    "cloud trace",
    "cmek",
    "vpc-sc",
    "region pinning",
    "retention",
)


def _diagram_text() -> str:
    assert DIAGRAM_PATH.is_file(), "docs/diagram/architecture.mmd must exist (D13-M5)"
    return DIAGRAM_PATH.read_text(encoding="utf-8")


def _edge_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if line.startswith(("classDef ", "class ", "subgraph ", "direction ")):
            continue
        if ARROW.search(line):
            lines.append(line.replace("<-->", "-->").replace("<-.->", "-.->"))
    return lines


def _declared_ids(text: str) -> set[str]:
    ids = set(NODE_DEF.findall(text))
    ids |= set(SUBGRAPH_DEF.findall(text))
    return ids


def _endpoints(line: str) -> list[str]:
    endpoints = []
    for part in ARROW.split(line):
        token = EDGE_LABEL.sub("", part.strip()).strip()
        match = ENDPOINT.match(token)
        if match:
            endpoints.append(match.group(1))
    return endpoints


def test_diagram_lives_in_the_committed_docs_tree() -> None:
    assert DIAGRAM_PATH.is_file()
    assert DIAGRAM_PATH.parent.name == "diagram"
    assert DIAGRAM_PATH.stat().st_size > 0


def test_diagram_is_mermaid_not_ascii_art() -> None:
    text = _diagram_text()
    assert GRAPH_DECL.search(text), "diagram must open with a flowchart/graph declaration"
    assert ARROW.search(text), "diagram must carry real Mermaid data-flow edges"
    for token in ASCII_ART_TOKENS:
        assert token not in text, f"diagram contains ASCII-art fragment {token!r}"
    lower = text.lower()
    for token in PLACEHOLDER_TOKENS:
        assert token not in lower, f"diagram contains placeholder text {token!r}"


def test_mermaid_structure_parses() -> None:
    text = _diagram_text()
    opens = len(SUBGRAPH_DEF.findall(text))
    closes = len(re.findall(r"^\s*end\s*$", text, re.MULTILINE))
    assert opens == closes, f"{opens} subgraph blocks but {closes} end lines"
    declared = _declared_ids(text)
    edges = _edge_lines(text)
    assert edges, "diagram must carry data-flow arrows"
    for line in edges:
        for endpoint in _endpoints(line):
            assert endpoint in declared, f"edge endpoint {endpoint!r} is never declared"


def test_covers_the_vision_22_component_set() -> None:
    lower = _diagram_text().lower()
    missing = [component for component in REQUIRED_COMPONENTS if component not in lower]
    assert not missing, f"vision §22 components missing from the diagram: {missing}"


def test_rendered_exports_ship_alongside_the_source() -> None:
    assert SVG_PATH.is_file() and SVG_PATH.stat().st_size > 0, "SVG export missing"
    assert PNG_PATH.is_file() and PNG_PATH.stat().st_size > 0, "PNG export missing"
    head = SVG_PATH.read_text(encoding="utf-8", errors="replace")[:200]
    assert "<svg" in head or "<?xml" in head, "architecture.svg is not an SVG document"


def test_readme_links_the_diagram() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert re.search(r"docs/diagram/architecture\.svg", readme), "README hero image missing"
    assert re.search(r"docs/diagram/architecture\.mmd", readme), "README must link the source"
