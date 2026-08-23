"""Shape tests for the Day-13 timing sheet (BUILD_PLAN D13-M4, vision §17).

The rehearsal artifact is content, not code, so its "test" is a checklist
assertion (plan §1): ``docs/timing_sheet.md`` exists in the committed docs
tree, locks exactly the seven vision §17 beats in order, sums to at most the
240 s (4:00) hard constraint, records three timed dress rehearsals
(``runtime/replay.py`` wall-clock + manual narration timing), and carries no
placeholder text. CP2 freeze: the sheet is the final rehearsal artifact for
the 4-minute video.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_ROOT: Final = Path(__file__).resolve().parent.parent
SHEET_PATH: Final = _ROOT / "docs" / "timing_sheet.md"
MAX_TOTAL_SECONDS: Final = 240
EXPECTED_BEAT_COUNT: Final = 7
PLACEHOLDER_TOKENS: Final = ("todo", "lorem", "tbd", "fixme", "xxx", "placeholder")
# Locked-table row: | <beat number> | <title> | <whole seconds> |
BEAT_ROW: Final = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*$", re.MULTILINE)
# Rehearsal-log rows start with a run marker like "| R1 |" and carry numeric timings.
REHEARSAL_ROW: Final = re.compile(r"^\|\s*R(\d+)\s*\|.*\d", re.MULTILINE)


def _sheet_text() -> str:
    assert SHEET_PATH.is_file(), "docs/timing_sheet.md must exist (D13-M4 rehearsal artifact)"
    return SHEET_PATH.read_text(encoding="utf-8")


def _beat_rows(text: str) -> list[tuple[int, str, int]]:
    return [
        (int(number), title.strip(), int(seconds))
        for number, title, seconds in BEAT_ROW.findall(text)
    ]


def test_sheet_lives_in_the_committed_docs_tree() -> None:
    # The sheet is a rehearsal artifact, not a temp scratch file: it must sit in docs/.
    assert SHEET_PATH.is_file()
    assert SHEET_PATH.parent.name == "docs"
    assert SHEET_PATH.stat().st_size > 0


def test_locks_exactly_seven_beats_in_order() -> None:
    beats = _beat_rows(_sheet_text())
    assert len(beats) == EXPECTED_BEAT_COUNT, f"expected 7 locked beats, found {len(beats)}"
    assert [number for number, _, _ in beats] == list(range(1, EXPECTED_BEAT_COUNT + 1))


def test_beat_seconds_sum_within_the_four_minute_budget() -> None:
    beats = _beat_rows(_sheet_text())
    total = sum(seconds for _, _, seconds in beats)
    assert total <= MAX_TOTAL_SECONDS, (
        f"locked beats sum to {total}s; the vision §17 budget is {MAX_TOTAL_SECONDS}s"
    )


def test_every_beat_has_a_real_title_and_positive_time() -> None:
    for number, title, seconds in _beat_rows(_sheet_text()):
        assert title, f"beat {number} has an empty title"
        assert seconds > 0, f"beat {number} must carry a positive second count"
        assert title.lower() not in PLACEHOLDER_TOKENS, f"beat {number} title is a placeholder"


def test_no_placeholder_text_anywhere_in_the_sheet() -> None:
    lower = _sheet_text().lower()
    for token in PLACEHOLDER_TOKENS:
        assert token not in lower, f"timing sheet contains placeholder text {token!r}"


def test_three_rehearsals_recorded_and_sheet_locked() -> None:
    text = _sheet_text()
    runs = {int(run) for run in REHEARSAL_ROW.findall(text)}
    assert len(runs) >= 3, f"three dress rehearsals must be recorded, found runs {sorted(runs)}"
    # The plan accepts "3 rehearsals recorded" or "sheet is locked"; this sheet keeps both.
    assert "locked" in text.lower(), "the sheet must carry its lock status"
