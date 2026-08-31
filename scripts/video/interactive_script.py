"""The interactive cut's narration, and the .srt it exports.

Supersedes the caption block in ``build_final.py``, which encodes the earlier
eight-beat plan including the 14-day seeding and rollback segments. Here every
caption sits under an action the recorder actually performs, so the timing is
set by the choreography in ``record_interactive.py`` rather than by narration
alone.

The order is deliberate. The Devpost session asked to "show your project
working in the first 10 to 15 seconds, skip long intros and title screens", so
the cut opens on the findings table already full and the fleet's single critical
result, not on a name and a track. Identity lands at ~0:40, over live motion,
once the viewer has a reason to care who made it. Nothing is narrated that isn't
on screen while it is said.

Cue times are laid out inside each segment's window, split in proportion to word
count so a long line gets more screen time than a short one, with a small gap
between cues. Nothing crosses a segment boundary.

Run:
    uv run python scripts/video/interactive_script.py
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent.parent
SRT_OUT: Final = ROOT / "docs/video/demo_script.srt"
MD_OUT: Final = ROOT / "docs/video/demo_script.md"

GAP: Final = 0.35  # seconds of blank between cues, so lines don't smear together
WRAP: Final = 48  # characters per caption line
LEAD: Final = 0.5  # a beat of clean footage before the first cue of a segment


@dataclass(frozen=True)
class Segment:
    number: int
    title: str
    action: str
    start: float
    end: float
    lines: tuple[str, ...]


SEGMENTS: Final[tuple[Segment, ...]] = (
    Segment(
        1,
        "The find",
        "findings table, scrolls the list, filters critical -> high -> all, opens the critical",
        0.0,
        26.0,
        (
            "Eight AI agents just finished reading this company's entire data room.",
            "Five findings. Filtering to the one that matters: a single critical.",
            "Two high as well. Every row is a finding an agent wrote, with its evidence attached.",
            "This critical one is the one that changes the price. Opening it.",
        ),
    ),
    Segment(
        2,
        "Evidence",
        'scrolls summary -> evidence spans, clicks "Open source", the viewer opens',
        26.0,
        58.0,
        (
            "The target's largest customer can walk the moment the deal closes, "
            "taking eighteen percent of next year's revenue.",
            "Ninety percent confidence, four source documents, four contributing "
            "agents. No single agent could call this alone.",
            "I'm Divyansh Agrawal, and this is Diligence Room, my entry for the "
            "Fortified Enterprise Fleet track.",
            "Every finding quotes the clause it came from, and I can open the "
            "source document right here, at that line.",
        ),
    ),
    Segment(
        3,
        "Trace",
        "scrolls scope -> open questions -> finding graph -> audit trace",
        58.0,
        88.0,
        (
            "Scope shows which agents contributed, and what each one filed on its own.",
            "The finding graph traces it back: which documents, which agents, "
            "which gateway decision.",
            "And the audit trail. Document parsed, finding created, gateway decision, escalation.",
            "Any claim the fleet makes can be walked back to the source text.",
        ),
    ),
    Segment(
        4,
        "The room",
        "deal room scrolled to the escalation inbox, then the Documents tab",
        88.0,
        116.0,
        (
            "That was one finding. Here is the whole deal room: coverage per "
            "workstream, documents ingested, threats blocked.",
            "And the escalation inbox, which is what the fleet decided a human needs to see.",
            "Every document the agents read is listed, with the workstream it "
            "was routed to and the confidence behind that call.",
        ),
    ),
    Segment(
        5,
        "Security",
        "scrolls the full quarantine table",
        116.0,
        146.0,
        (
            "Analysts are not the only thing reading these files. I hit this "
            "fleet with twenty red-team attacks.",
            "Prompt injection, encoded payloads, data theft, cross-agent writes. "
            "All twenty blocked, zero false positives.",
            "Gemma 4 screens every file, then Model Armor. Nothing here ever "
            "reached an agent runtime.",
        ),
    ),
    Segment(
        6,
        "Platform",
        "Agent Registry listing + Memory Bank recall",
        146.0,
        172.0,
        (
            "The whole fleet is published into the Agent Registry on Gemini "
            "Enterprise Agent Platform, discoverable company-wide.",
            "All eight, with versions, approval state and eval scores.",
            "Memory Bank holds what we know about this buyer across sessions, "
            "retrieved here in a fresh process.",
        ),
    ),
    Segment(
        7,
        "Human-in-the-loop",
        "clicks Draft -> expands the draft body -> Approve -> Record send",
        172.0,
        210.0,
        (
            "Now the part that decides whether you can run this on a real deal. "
            "The negotiation agent can draft, but it cannot send.",
            "I click draft. It writes the redline, quoting the evidence it just showed me.",
            "It stops at pending approval. Nothing leaves the building until a human says so.",
            "I approve it. Now, and only now, can the send be recorded.",
        ),
    ),
    Segment(
        8,
        "Google Cloud proof",
        "Cloud Logging + Cloud Trace",
        210.0,
        238.0,
        (
            "That approval lands in Cloud Logging as a request against Cloud Run.",
            "Agent Runtime, Cloud Run in two regions, Firestore and Pub/Sub, all "
            "live on Google Cloud.",
            "And the same call in Cloud Trace, span by span, so an auditor can "
            "follow any claim back to the source.",
        ),
    ),
)


def _stamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def cues() -> list[tuple[float, float, str]]:
    """Lay every line out on the timeline, weighted by length."""
    out: list[tuple[float, float, str]] = []
    for seg in SEGMENTS:
        budget = (seg.end - seg.start) - LEAD - GAP * len(seg.lines)
        weights = [len(line.split()) for line in seg.lines]
        total = sum(weights)
        at = seg.start + LEAD
        for line, weight in zip(seg.lines, weights, strict=True):
            span = budget * weight / total
            out.append((at, at + span, line))
            at += span + GAP
    return out


def to_srt() -> str:
    blocks = []
    for index, (start, end, line) in enumerate(cues(), start=1):
        body = "\n".join(textwrap.wrap(line, WRAP))
        blocks.append(f"{index}\n{_stamp(start)} --> {_stamp(end)}\n{body}\n")
    return "\n".join(blocks)


def to_markdown() -> str:
    parts = [
        "# Demo narration - the interactive cut",
        "",
        "Generated by `scripts/video/interactive_script.py`. Timed captions live",
        "in `demo_script.srt`; this file is the read-aloud version.",
        "",
        "Every caption has an action under it. Segment windows are fixed; cue",
        "times inside a window are split by word count.",
        "",
    ]
    timeline = cues()
    cursor = 0
    for seg in SEGMENTS:
        span = f"{int(seg.start // 60)}:{int(seg.start % 60):02d}"
        stop = f"{int(seg.end // 60)}:{int(seg.end % 60):02d}"
        parts += [f"## {seg.number}. {seg.title} ({span}-{stop})", "", f"*{seg.action}*", ""]
        for _ in seg.lines:
            start, _end, line = timeline[cursor]
            cursor += 1
            parts.append(f"- **{start:6.1f}s** {line}")
        parts.append("")
    return "\n".join(parts)


def main() -> int:
    SRT_OUT.write_text(to_srt(), encoding="utf-8")
    MD_OUT.write_text(to_markdown(), encoding="utf-8")
    timeline = cues()
    words = sum(len(line.split()) for _s, _e, line in timeline)
    speaking = sum(end - start for start, end, _l in timeline)
    print(f"{len(timeline)} cues, ends at {timeline[-1][1]:.1f}s")
    print(f"{words} words over {speaking:.0f}s of cue time = {words / speaking:.2f} words/sec")
    for seg in SEGMENTS:
        seg_words = sum(len(line.split()) for line in seg.lines)
        seg_speak = (seg.end - seg.start) - LEAD - GAP * len(seg.lines)
        print(f"  {seg.number}. {seg.title:20s} {seg_words / seg_speak:.2f} w/s")
    print(f"-> {SRT_OUT}")
    print(f"-> {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
