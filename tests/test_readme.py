"""Shape tests for README v1 (BUILD_PLAN D13-M6, Day-13 plan wave 6).

The README is content, not code, so its "test" is a checklist assertion
(doctrine §1): ``README.md`` exists at the repo root and carries the v1
shape — hero image linking the ``docs/diagram`` architecture SVG (plus the
``.png`` export and ``.mmd`` source), quickstart (``uv sync``,
``infra/bootstrap_gcp.py``, ``uv run pytest``, dashboard build), credentials
(ADC via ``gcloud auth application-default login``), a stack table naming the
platform (FastAPI, ADK, Firestore, Pub/Sub, Cloud Run, Model Armor, Cloud
Trace), the Apache-2.0 license, and an evaluation section pointing at
``evals/`` (20-doc golden set + strict-exact harness + 20-attack ledger).
No lorem filler.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_ROOT: Final = Path(__file__).resolve().parent.parent
README_PATH: Final = _ROOT / "README.md"

# The four quickstart commands plan wave 6 requires (verbatim).
QUICKSTART_COMMANDS: Final = (
    "uv sync",
    "uv run python infra/bootstrap_gcp.py",
    "uv run pytest",
    "npm --prefix dashboard/web run build",
)

# Minimum platform set the stack table must name.
STACK_COMPONENTS: Final = (
    "FastAPI",
    "ADK",
    "Firestore",
    "Pub/Sub",
    "Cloud Run",
    "Model Armor",
    "Cloud Trace",
)


def _read() -> str:
    return README_PATH.read_text(encoding="utf-8")


def _section(readme: str, heading: str) -> str:
    """Return one ``## heading`` section, title line through the next ``## ``."""
    pattern = re.compile(rf"^## {re.escape(heading)}\b.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(readme)
    assert match is not None, f"README is missing the `## {heading}` section"
    return match.group(0)


def test_readme_exists() -> None:
    assert README_PATH.is_file(), "README.md missing at repository root"
    assert len(_read()) > 4000, "README.md looks like the Day-1 skeleton, not v1"


def test_hero_links_the_diagram() -> None:
    readme = _read()
    hero = re.search(r"!\[[^\]]*\]\(docs/diagram/architecture\.svg\)", readme)
    assert hero is not None, "hero image ![...](docs/diagram/architecture.svg) missing"
    assert "docs/diagram/architecture.png" in readme, "README must link the PNG export"
    assert "docs/diagram/architecture.mmd" in readme, "README must link the Mermaid source"
    first_section = readme.find("\n## ")
    assert hero.start() < first_section, "hero image must sit above the first section"


def test_overview_names_the_deal() -> None:
    overview = _section(_read(), "Overview: Project Falcon").lower()
    assert "project falcon" in overview, "overview must name Project Falcon"
    assert "vantage robotics" in overview, "overview must name the target company"
    assert "zero trust" in overview or "zero-trust" in overview


def test_quickstart_commands() -> None:
    quickstart = _section(_read(), "Quickstart")
    for command in QUICKSTART_COMMANDS:
        assert command in quickstart, f"quickstart misses `{command}`"


def test_credentials_section() -> None:
    credentials = _section(_read(), "Credentials")
    assert "Application Default Credentials" in credentials, "ADC not named"
    assert "gcloud auth application-default login" in credentials


def test_stack_table_lists_the_platform() -> None:
    stack = _section(_read(), "Stack")
    assert "|" in stack, "Stack section must be a markdown table"
    for component in STACK_COMPONENTS:
        assert component in stack, f"stack table misses {component}"


def test_evaluation_points_at_evals() -> None:
    evaluation = _section(_read(), "Evaluation")
    lowered = evaluation.lower()
    assert "evals/golden_set.py" in evaluation, "evaluation must link the golden set"
    assert "evals/harness.py" in evaluation, "evaluation must link the shadow harness"
    assert "golden set" in lowered, "evaluation must name the golden set"
    assert "20" in evaluation, "evaluation must name the 20-doc set / 20-attack ledger"
    assert "strict" in lowered and "exact" in lowered, "harness diff is strict exact match"
    assert "redteam/expected.yaml" in evaluation, "20-attack ledger lives in redteam/"


def test_license_is_apache() -> None:
    assert "Apache-2.0" in _section(_read(), "License")


def test_no_lorem_filler() -> None:
    assert "lorem" not in _read().lower(), "README contains lorem filler"
