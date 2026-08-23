"""Shape tests for the Day-13 submission stub + blog draft (BUILD_PLAN D13-M3).

The blog is content, not code, so its "test" is a checklist assertion (plan
§1): ``docs/submission.md`` exists with a ``blog_url`` field pointing at an
https host on a public platform (dev.to or medium.com), the stub is marked
public (never unlisted), and hackathon-purpose language is present
case-insensitive (required for the +0.2 bonus, vision Appendix B.3). The
companion draft ``docs/blog/draft.md`` must cover the required sections:
architecture (4-layer evidence gate + coordination keystone + human
approval), the twist, what broke (loop guard, evidence gate, crash-resume),
hackathon purpose, and a demo link. No network calls: publishing is manual
and happens outside the offline loop, so this offline shape check is what the
Day-13 gate falls back on (plan §10).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

import yaml

_ROOT: Final = Path(__file__).resolve().parent.parent
SUBMISSION_PATH: Final = _ROOT / "docs" / "submission.md"
DRAFT_PATH: Final = _ROOT / "docs" / "blog" / "draft.md"
PUBLIC_HOSTS: Final = frozenset({"dev.to", "medium.com"})
REQUIRED_DRAFT_MARKERS: Final = (
    "project falcon",
    "tl;dr",
    "architecture",
    "four layers",
    "the twist",
    "what broke",
    "loop guard",
    "evidence gate",
    "crash-resume",
    "human approval",
    "allthingsagentic",
    "hackathon",
    "demo",
)


def _squash(text: str) -> str:
    """Collapse every whitespace run to one space so hard-wrapped lines match."""
    return re.sub(r"\s+", " ", text)


def _submission_text() -> str:
    assert SUBMISSION_PATH.is_file(), "docs/submission.md must exist"
    return SUBMISSION_PATH.read_text(encoding="utf-8")


def _draft_text() -> str:
    assert DRAFT_PATH.is_file(), "docs/blog/draft.md must exist"
    return DRAFT_PATH.read_text(encoding="utf-8")


def _frontmatter() -> dict[str, Any]:
    text = _submission_text()
    assert text.startswith("---\n"), "submission.md must open with YAML frontmatter"
    end = text.find("\n---\n", 4)
    assert end > 4, "submission.md frontmatter must be closed by a --- fence"
    loaded = yaml.safe_load(text[4:end])
    assert isinstance(loaded, dict)
    return loaded


def _frontmatter_str(key: str) -> str:
    value = _frontmatter()[key]
    assert isinstance(value, str) and value.strip()
    return value


def test_submission_stub_exists_with_frontmatter() -> None:
    meta = _frontmatter()
    assert meta["submission_id"] == "diligence-room-project-falcon"
    assert meta["project"] == "Project Falcon"
    assert meta["blog_draft"] == "docs/blog/draft.md"


def test_blog_url_is_https_on_a_public_platform() -> None:
    blog_url = _frontmatter_str("blog_url")
    parsed = urlparse(blog_url)
    assert parsed.scheme == "https", f"blog_url must be https, got {blog_url!r}"
    host = parsed.netloc.lower().removeprefix("www.")
    assert host in PUBLIC_HOSTS, f"blog_url host must be one of {sorted(PUBLIC_HOSTS)}"
    assert parsed.path.strip("/"), "blog_url needs a real post path, not a bare host"


def test_submission_is_public_not_unlisted() -> None:
    assert _frontmatter_str("visibility").lower() == "public"
    combined = _squash(f"{_submission_text()}\n{_draft_text()}").lower()
    assert "unlisted" not in combined, "submission must never be marked unlisted"


def test_hackathon_language_present_case_insensitive() -> None:
    combined = _squash(f"{_submission_text()}\n{_draft_text()}").lower()
    assert "allthingsagentic" in combined
    assert "hackathon" in combined
    assert "fortified enterprise fleet" in combined


def test_created_for_this_hackathon_language() -> None:
    combined = _squash(f"{_submission_text()}\n{_draft_text()}").lower()
    assert "created for" in combined and "allthingsagentic hackathon" in combined


def test_project_summary_present() -> None:
    body = _squash(_submission_text()).lower()
    assert "project falcon" in body
    assert "vantage robotics" in body
    assert "zero-trust" in body
    assert "agent gateway" in body


def test_draft_exists_with_required_sections() -> None:
    lower = _squash(_draft_text()).lower()
    for marker in REQUIRED_DRAFT_MARKERS:
        assert marker in lower, f"draft.md missing required section marker: {marker!r}"


def test_draft_has_demo_placeholder_and_repo_link() -> None:
    text = _draft_text()
    assert "VIDEO LINK" in text, "demo video placeholder must stay visible until publish"
    assert "github.com/divagr18/diligence-room" in text


def test_no_lorem() -> None:
    combined = _squash(f"{_submission_text()}\n{_draft_text()}").lower()
    assert "lorem" not in combined
