# Demo video shot list — the recorded cut

The video that ships: `docs/video/final/diligence-room-demo.mp4`, 239.5s
(3:59.5), 1920x1080, captions burned in. Rebuild it with
`uv run python scripts/video/build_final.py`; `--captions-only` regenerates the
caption and voiceover files without touching footage.

Supersedes the seven-beat plan in `docs/timing_sheet.md`. The structure changed
after the Devpost "How to Win" session, which asked for two things the old cut
did not do: *"wowing them in the first like maybe 30 seconds"* and, from the
official checklist, *"show your project working in the first 10 to 15 seconds,
skip long intros and title screens."*

## What changed and why

**No title card.** The old cut opened on three seconds of title, then thirty
seconds of narration over a *static* findings table. Nothing moved until 1:15.

**The replay is the spine.** Segments 1 and 2 are one continuous take —
`beat23_take1` from 6s to 22s, then 22s to 80s — so the pipeline runs unbroken
across the first 74 seconds with no cut and no repeat. Identity, friction and
value proposition land as captions *over live motion* instead of over a still
page. The separate intro beat is gone.

## Segments

| # | From | Dur | Content | Take | @ |
|---|---|---|---|---|---|
| 1 | 0:00 | 16.0 | Pipeline running, dashboard empty | `beat23_take1` | 6 |
| 2 | 0:16 | 58.0 | Same take: friction, value, findings land, report | `beat23_take1` | 22 |
| 3 | 1:14 | 31.0 | Findings list, CRITICAL at top | `beat0_take3` | 0 |
| 4 | 1:45 | 26.0 | Agent Registry + Memory Bank | `platform_take3` | 4 |
| 5 | 2:11 | 36.0 | Gateway delegation, the 18.3% aggregate | `beat4_take3` | 0 |
| 6 | 2:47 | 24.0 | Twenty red-team attacks blocked | `beat5_take2` | 0 |
| 7 | 3:11 | 24.0 | Publish v2.5, eval fails it, roll back | `beat6_take6` | 5 |
| 8 | 3:35 | 24.5 | Cloud Logging + Cloud Trace | `beat7_take3` | 0 |

Caption text lives in `SEGMENTS` in `scripts/video/build_final.py` and is
exported to `docs/video/vo_script.md` (readable) and `.srt` (timed).

## Rules compliance

- **≤ 4 minutes**: 239.5s, half a second inside the cap.
- **English subtitles**: burned in; the file ships silent for a voiceover pass.
- **Backend on Google Cloud**: the `run.app` URL is in the address bar through
  every dashboard segment, and segment 8 is Logs Explorer beside Cloud Trace.
- **Unedited live execution**: segments 1-2 are one continuous take in which the
  dashboard goes from 0 findings to 5.

## Recording notes

Each recorder stages its own windows and captures with ffmpeg gdigrab:

- `record_beat3.ps1` — split screen, terminal left, dashboard right (segments 1-2)
- `record_view.ps1` — single full-screen route (segments 3, 5, 6)
- `record_beat6.ps1` — split screen with Registry refreshes (segment 7)
- `record_platform.ps1` — split screen, platform components (segment 4)
- `record_beat7.ps1` — two Cloud Console panes (segment 8)
- `record_all.sh` — runs a full set with per-step logs in `docs/video/logs/`

Things that cost a take when they were not known:

- Chrome runs in an **isolated profile** and windowed, not app mode: app mode
  hides the address bar, and the rules ask for the `run.app` URL.
- `Resolve-Ffmpeg` resolves an absolute path, because `Start-Process` searches
  the Windows PATH rather than the calling shell's.
- Window rects are in the process's DPI space (1536x864 here, not 1920x1080),
  and panes overlap slightly or the desktop shows through the seam.
- `reset_deal.py` clears the deal, the global registry, or just the negotiation
  drafts, so takes are repeatable. Draft creation is idempotent per finding, so
  without the drafts reset a second take dies approving an approved draft.
- Segment 4 warms the Vertex client during staging: the first Memory Bank call
  pays a cold start that otherwise runs past the end of the segment.
