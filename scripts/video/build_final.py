"""Assemble the 4:00 demo cut from the per-segment takes, with burned-in captions.

The captions are the presenter's own words, timed where they belong, so they
double as the voiceover script. Styling follows the YouTube caption convention:
small white text in a translucent black box at the bottom of frame.

There is deliberately no title card. The hackathon checklist asks to "show your
project working in the first 10 to 15 seconds, skip long intros and title
screens", so the cut opens on the pipeline already running.

Segments 1 and 2 are the same continuous take, split only for captioning: the
replay plays once, unbroken, across the first 74 seconds.

Usage:
    uv run python scripts/video/build_final.py
    uv run python scripts/video/build_final.py --captions-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TAKES = ROOT / "docs/video/takes"
FINAL = ROOT / "docs/video/final"
WORK = FINAL / "work"


@dataclass
class Segment:
    number: int
    take: str
    dur: float
    start_in: float = 0.0
    lines: list[tuple[float, float, str]] = field(default_factory=list)


# Segment order, durations (sum 239.5s, inside the 4:00 cap), and caption cues,
# each (start, end) in seconds RELATIVE to its own segment.
SEGMENTS: list[Segment] = [
    Segment(
        1,
        "beat23_take1.mkv",
        16.0,
        6.0,
        [
            (
                0.5,
                6.5,
                "This is Diligence Room, running right now. Eight agents\n"
                "doing end-to-end due diligence on an M&A deal.",
            ),
            (
                7.0,
                12.5,
                "On the left, you see the live pipeline. On the right,\n"
                "my app deployed on Cloud Run.",
            ),
            (13.0, 15.5, "It starts clean. Watch it fill up."),
        ],
    ),
    # Same take as segment 1, continuing unbroken. Findings land ~12s in.
    Segment(
        2,
        "beat23_take1.mkv",
        58.0,
        22.0,
        [
            (
                0.5,
                7.0,
                "I'm Divyansh Agrawal, and this is my entry for the\n"
                "Fortified Enterprise Fleet track.",
            ),
            (7.5, 11.5, "I am replaying fourteen days of a real deal at high speed."),
            (
                12.0,
                19.0,
                "And look at that, there they are. Findings landing live\n"
                "as agents write them into Firestore.",
            ),
            (
                19.5,
                27.0,
                "When one company buys another, human analysts must read\n"
                "every paper the seller hands over.",
            ),
            (
                27.5,
                36.0,
                "Thousands of files, weeks of tedious work. Things slip\n"
                "through simply because nobody has time to cross-reference\n"
                "all of it.",
            ),
            (
                36.5,
                44.0,
                "Here, Gemma 4 screens every file first, and Model Armor\n"
                "checks it for prompt injection.",
            ),
            (
                44.5,
                51.0,
                "An agent cannot post a finding unless it quotes the exact\nclause it came from.",
            ),
            (
                51.5,
                57.5,
                "Forty-nine events processed, five findings flagged, and it\n"
                "reproduces the exact same way every time.",
            ),
        ],
    ),
    Segment(
        3,
        "beat0_take3.mkv",
        31.0,
        0.0,
        [
            (
                0.5,
                7.0,
                "Here is what the fleet uncovered: one critical, two high,\ntwo medium.",
            ),
            (
                7.5,
                17.0,
                "That critical alert did not come from a single agent.\n"
                "Legal, Finance, HR and IP each caught one piece\n"
                "of the puzzle.",
            ),
            (
                17.5,
                26.5,
                "The target's largest customer can walk away the moment\n"
                "the deal closes, taking eighteen percent of next year's\n"
                "revenue with them.",
            ),
            (27.0, 30.5, "No single specialist had the authority to call that alone."),
        ],
    ),
    # Filmed after phases 2 and 3 land: nothing here is narrated before it exists.
    Segment(
        4,
        "platform_take3.mkv",
        26.0,
        # Timed against the take: the registry listing lands ~t=10 and the
        # recalled memories ~t=21, so each caption sits on its own content.
        4.0,
        [
            (
                0.5,
                9.0,
                "I published this entire fleet into the Agent Registry on\n"
                "Gemini Enterprise Agent Platform, discoverable across\n"
                "the whole company.",
            ),
            (
                9.5,
                16.5,
                "All eight specialists sit here with their versions,\n"
                "approval states and eval scores.",
            ),
            (
                17.0,
                25.5,
                "And Memory Bank holds everything we know about this buyer\n"
                "across long-running sessions, retrieved right here\n"
                "in a fresh process.",
            ),
        ],
    ),
    Segment(
        5,
        "beat4_take3.mkv",
        36.0,
        0.0,
        [
            (
                0.5,
                7.5,
                "Let's look at how they work together. Legal finds a\n"
                "change-of-control clause in the contract.",
            ),
            (
                8.0,
                16.0,
                "To size the financial risk it needs revenue data. But under\n"
                "Agent Identity, Legal cannot read financial ledgers.",
            ),
            (
                16.5,
                24.0,
                "So it asks through the Agent Gateway. The gateway denies\n"
                "access by default unless a policy allows it.",
            ),
            (
                24.5,
                30.5,
                "Finance returns one safe aggregate, eighteen percent,\n"
                "without exposing the underlying data to the model.",
            ),
            (
                31.0,
                35.5,
                "Four workstreams pointing at the same vendor is what lets\n"
                "the coordinator escalate this to critical.",
            ),
        ],
    ),
    Segment(
        6,
        "beat5_take2.mkv",
        24.0,
        0.0,
        [
            (
                0.5,
                8.5,
                "I hit this fleet with twenty direct red-team attacks:\n"
                "prompt injections, encoded payloads, data theft,\n"
                "and cross-team writes.",
            ),
            (9.0, 14.0, "The system blocked all twenty with zero false positives."),
            (
                14.5,
                23.5,
                "An attacker tried telling Finance the deal was already\n"
                "approved. Model Armor quarantined the payload before any\n"
                "agent runtime ever saw it.",
            ),
        ],
    ),
    Segment(
        7,
        "beat6_take6.mkv",
        24.0,
        5.0,
        [
            (
                0.5,
                8.0,
                "What happens when an agent fails in production?\n"
                "Legal runs on version 2.4. I publish version 2.5.",
            ),
            (
                8.5,
                15.0,
                "Our shadow harness replays a golden test set against it\n"
                "and fails it: 2.5 missed that ownership clause.",
            ),
            (
                15.5,
                23.5,
                "I roll back to 2.4 instantly. The version reverts, but the\n"
                "memory partition stays untouched. Logic and memory\n"
                "stay separate.",
            ),
        ],
    ),
    Segment(
        8,
        "beat7_take3.mkv",
        24.5,
        0.0,
        [
            (
                0.5,
                8.0,
                "Finally, human-in-the-loop control. The negotiation agent\n"
                "drafts the request to the seller, but it cannot send it\n"
                "until I approve it.",
            ),
            (8.5, 12.5, "That sign-off records as a POST in Cloud Logging."),
            (
                13.0,
                19.0,
                "The fleet runs live on Agent Runtime and Cloud Run across\n"
                "two regions, backed by Firestore and Pub/Sub.",
            ),
            (
                19.5,
                24.0,
                "And here is that same call in Cloud Trace, span by span,\n"
                "so an auditor can follow any claim back to the source.",
            ),
        ],
    ),
]


def ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def cues() -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    offset = 0.0
    for segment in SEGMENTS:
        for start, end, text in segment.lines:
            out.append((offset + start, offset + min(end, segment.dur), text))
        offset += segment.dur
    return out


def total_duration() -> float:
    return sum(segment.dur for segment in SEGMENTS)


def write_srt(path: Path) -> None:
    blocks = [
        f"{i}\n{ts_srt(a)} --> {ts_srt(b)}\n{text}\n"
        for i, (a, b, text) in enumerate(cues(), start=1)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_ass(path: Path) -> None:
    """Write captions as ASS so the font size is in real 1080p pixels.

    Converting SRT inside ffmpeg leaves libass on its default 384x288 canvas,
    which scales a nominally small font up to something enormous at 1080p.
    Declaring PlayResX/Y here is what keeps the text the size it claims to be.
    """
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # BorderStyle 3 = opaque box; Outline doubles as the box padding.
        # BackColour &H80000000 is black at ~50% alpha, the YouTube look.
        "Style: Cap,Segoe UI,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,3,7,0,2,80,80,96,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    # Python 3.11 forbids a backslash inside an f-string expression, so the
    # newline -> \N conversion happens before the format string.
    lines = []
    for a, b, text in cues():
        body = text.replace("\n", r"\N")
        lines.append(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Cap,,0,0,0,,{body}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def write_vo_script(path: Path) -> None:
    """Render the cue list as a readable voiceover script."""
    out = [
        "# Voiceover script",
        "",
        f"Timed to `docs/video/final/diligence-room-demo.mp4` ({total_duration():.1f}s).",
        "These lines are burned into the picture, so you can read straight off it.",
        "`docs/video/vo_script.srt` is the subtitle file if you want to re-time.",
        "",
    ]
    offset = 0.0
    for segment in SEGMENTS:
        mins, secs = divmod(int(offset), 60)
        out.append(f"## Segment {segment.number} - from {mins}:{secs:02d}")
        out.append("")
        for start, _end, text in segment.lines:
            at = offset + start
            m, s = divmod(int(at), 60)
            spoken = text.replace("\n", " ")
            out.append(f"- **{m}:{s:02d}** - {spoken}")
        out.append("")
        offset += segment.dur
    path.write_text("\n".join(out), encoding="utf-8")


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(args)}\n{proc.stderr[-2000:]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the demo cut.")
    parser.add_argument(
        "--captions-only",
        action="store_true",
        help="Write the caption and voiceover files without touching video.",
    )
    args = parser.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    srt = WORK / "captions.srt"
    ass = WORK / "captions.ass"
    write_srt(srt)
    write_ass(ass)
    write_srt(ROOT / "docs/video/vo_script.srt")
    write_vo_script(ROOT / "docs/video/vo_script.md")
    print(f"[build] {len(cues())} cues; total {total_duration():.1f}s")

    if args.captions_only:
        print("[build] captions only; no video written")
        return 0

    missing = [s.take for s in SEGMENTS if not (TAKES / s.take).exists()]
    if missing:
        sys.exit("missing takes: " + ", ".join(sorted(set(missing))))

    parts: list[Path] = []
    for segment in SEGMENTS:
        src = TAKES / segment.take
        seg = WORK / f"seg{segment.number}.mp4"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(segment.start_in),
                "-t",
                str(segment.dur),
                "-i",
                str(src),
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-r",
                "30",
                str(seg),
            ]
        )
        parts.append(seg)
        print(
            f"[build] segment {segment.number} <- {segment.take} "
            f"@{segment.start_in} ({segment.dur}s)"
        )

    concat_list = WORK / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="ascii")
    joined = WORK / "joined.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(joined),
        ]
    )

    sub_arg = ass.as_posix().replace(":", "\\:")
    FINAL.mkdir(parents=True, exist_ok=True)
    out = FINAL / "diligence-room-demo.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(joined),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf",
            f"subtitles='{sub_arg}'",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(out),
        ]
    )
    print(f"[build] FINAL -> {out}")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-of",
            "default=nw=1",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    print(probe.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
