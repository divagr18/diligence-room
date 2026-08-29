"""Assemble the 4:00 demo cut from the per-beat takes, with burned-in captions.

The captions are the presenter's own words, timed where they belong, so they
double as the voiceover script. Styling follows the YouTube caption convention:
small white text in a translucent black box at the bottom of frame.

Usage: uv run python scripts/video/build_final.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TAKES = ROOT / "docs/video/takes"
FINAL = ROOT / "docs/video/final"
WORK = FINAL / "work"
CARDS = ROOT / "docs/video/cards"

TITLE_DUR = 3.0


@dataclass
class Beat:
    number: int
    take: str
    dur: float
    start_in: float = 0.0
    lines: list[tuple[float, float, str]] = field(default_factory=list)


# Beat order, durations (sum 237s; +3s title = 240s), and caption cues, each
# (start, end) in seconds RELATIVE to its own beat.
BEATS: list[Beat] = [
    Beat(
        0,
        "beat0_take3.mkv",
        30.0,
        0.0,
        [
            (
                0.5,
                7.0,
                "Hi, I'm Divyansh Agrawal. This is Diligence Room,\n"
                "my entry for the Fortified Enterprise Fleet track.",
            ),
            (7.5, 14.0, "M&A due diligence is too complex for a single AI model."),
            (
                14.5,
                21.0,
                "It needs a network of institutional agents that hook\n"
                "directly into enterprise infrastructure.",
            ),
            (
                21.5,
                29.5,
                "Human teams take weeks to check thousands of deal files.\n"
                "I built a fleet of eight specialists that runs it\n"
                "end to end, workstream by workstream.",
            ),
        ],
    ),
    Beat(
        1,
        "beat1_take2.mkv",
        24.0,
        0.0,
        [
            (
                0.5,
                6.5,
                "Operational Utility is forty percent of the score,\n"
                "and it asks for real delegation, not a chat bot.",
            ),
            (
                7.0,
                15.0,
                "This is the central Agent Registry, where a manager can\n"
                "discover, audit and manage eight cataloged specialists.",
            ),
            (
                15.5,
                23.5,
                "Each owns one domain, with no shared raw access. Every\n"
                "agent is versioned and scored, so a bad build rolls back.",
            ),
        ],
    ),
    # Beats 2 and 3 are one continuous split-screen take, cut only for captions.
    Beat(
        2,
        "beat23_take1.mkv",
        18.0,
        6.0,
        [
            (
                0.5,
                6.5,
                "Visible proof of live execution. Left is my terminal\n"
                "running the pipeline, right is the app on Cloud Run.",
            ),
            (
                7.0,
                12.0,
                "Deals run for weeks, so the Agent Runtime handles\nlong-running async execution.",
            ),
            (
                12.5,
                17.5,
                "I'm replaying fourteen days of deal events into Firestore,\n"
                "the Memory Bank that holds context across sessions.",
            ),
        ],
    ),
    Beat(
        3,
        "beat23_take1.mkv",
        54.0,
        24.0,
        [
            (0.5, 7.0, "Architectural Discipline, thirty percent, shows up\nat the boundary."),
            (
                7.5,
                17.0,
                "Before any agent sees a file, Gemma 4 parses the text and\n"
                "Model Armor runs inline checks for prompt injection,\n"
                "tool poisoning and PII leaks.",
            ),
            (17.5, 26.0, "Google ADK orchestrates the agents, Gemini 3.5 Flash\nroutes the work."),
            (
                26.5,
                36.0,
                "To stop hallucinations, an agent cannot post a finding\n"
                "unless it quotes the exact source text.",
            ),
            (36.5, 45.0, "Pub/Sub carries the messages, Cloud Trace logs every step."),
            (
                45.5,
                53.0,
                "Look at the dashboard. Forty-nine events processed,\nfive findings flagged.",
            ),
        ],
    ),
    Beat(
        4,
        "beat4_take3.mkv",
        38.0,
        0.0,
        [
            (0.5, 7.0, "The Legal agent spots a change-of-control clause\nin a vendor contract."),
            (
                7.5,
                16.0,
                "To size the risk it needs revenue data, but under Agent\n"
                "Identity's zero-trust model it has no read access\n"
                "to the finance ledgers.",
            ),
            (
                16.5,
                25.0,
                "So it sends a request to the Agent Gateway, which enforces\n"
                "policy and returns one safe aggregate.",
            ),
            (
                25.5,
                32.0,
                "Eighteen point three percent of next year's revenue\n"
                "sits in this single contract.",
            ),
            (
                32.5,
                37.5,
                "When four sub-agents flag the same vendor,\n"
                "the coordinator escalates to critical.",
            ),
        ],
    ),
    Beat(
        5,
        "beat5_take2.mkv",
        24.0,
        0.0,
        [
            (
                0.5,
                9.0,
                "A fortified fleet has to prove its security posture.\n"
                "Twenty red-team attacks: prompt injection, encoded\n"
                "payloads, data theft, illegal cross-agent writes.",
            ),
            (9.5, 16.0, "All twenty blocked, with zero false positives."),
            (
                16.5,
                23.5,
                "Here an attacker fakes a deal approval, and Model Armor\n"
                "quarantined it before it reached an agent runtime.",
            ),
        ],
    ),
    # Timed against the take: uv startup ends ~5s, the publish lands ~11s, the
    # eval verdict ~16s, the rollback ~20s. start_in trims the dead head so each
    # caption sits on the step it actually describes.
    Beat(
        6,
        "beat6_take6.mkv",
        24.0,
        5.0,
        [
            (0.5, 8.0, "What happens when an agent fails? Legal runs 2.4.\nI publish 2.5."),
            (
                8.5,
                14.5,
                "The shadow harness replays a golden set against it,\n"
                "and it fails: 2.5 missed the contract clause.",
            ),
            (
                15.0,
                23.5,
                "I roll back to 2.4. The version reverts, but the Memory\n"
                "Bank partition stays intact.",
            ),
        ],
    ),
    # Both panes are the Google Cloud Console: Logs Explorer and Cloud Trace.
    # The captions describe what is on screen, so no local terminal is claimed.
    Beat(
        7,
        "beat7_take3.mkv",
        24.5,
        0.0,
        [
            (
                0.5,
                8.0,
                "Finally, governance. The negotiation agent drafts the\n"
                "letter, but only I can send it, and that approval lands\n"
                "in Cloud Logging as a request against Cloud Run.",
            ),
            (
                8.5,
                16.0,
                "Cloud Run in two regions, Firestore, Pub/Sub and\n"
                "Vertex AI Agent Engine, all live on Google Cloud.",
            ),
            (
                16.5,
                24.0,
                "And the same call in Cloud Trace, span by span, so an\n"
                "auditor can follow any claim back to its source.",
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
    offset = TITLE_DUR
    for beat in BEATS:
        for start, end, text in beat.lines:
            out.append((offset + start, offset + min(end, beat.dur), text))
        offset += beat.dur
    return out


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


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(args)}\n{proc.stderr[-2000:]}")


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    srt = WORK / "captions.srt"
    ass = WORK / "captions.ass"
    write_srt(srt)
    write_ass(ass)
    total = TITLE_DUR + sum(b.dur for b in BEATS)
    print(f"[build] {len(cues())} cues; total {total:.1f}s")

    missing = [b.take for b in BEATS if not (TAKES / b.take).exists()]
    if missing:
        sys.exit("missing takes: " + ", ".join(sorted(set(missing))))

    segments: list[Path] = []
    title = CARDS / "title.mp4"
    if title.exists():
        seg0 = WORK / "seg_title.mp4"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(title),
                "-vf",
                "scale=1920:1080,fps=30,format=yuv420p",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-r",
                "30",
                str(seg0),
            ]
        )
        segments.append(seg0)

    for beat in BEATS:
        src = TAKES / beat.take
        seg = WORK / f"seg{beat.number}.mp4"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(beat.start_in),
                "-t",
                str(beat.dur),
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
        segments.append(seg)
        print(f"[build] beat {beat.number} <- {beat.take} @{beat.start_in} ({beat.dur}s)")

    concat_list = WORK / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in segments), encoding="ascii")
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
