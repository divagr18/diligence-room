"""Browser-driven recording: Playwright performs the demo, ffmpeg films the screen.

The earlier takes pointed a screen recorder at a static page and hoped. This
drives the real SPA — scrolling, clicking, opening panels — and owns the capture
in the same process, so the moment an action happens is a known number rather
than a guess, and captions can be timed against it.

Chrome is launched through Playwright's ``channel="chrome"`` so it is the same
browser a judge would use, and gdigrab films the desktop rather than Playwright's
own video, which keeps the run.app URL in the address bar on screen.

Run with:
    uv run --with playwright python scripts/video/drive_<segment>.py
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parent.parent.parent
TAKES: Final = ROOT / "docs/video/takes"
BASE: Final = "https://diligence-room-dashboard-378831539922.asia-south1.run.app"

# Chrome window args are in device-independent pixels. This display runs at 125%,
# so a 1920x1080 screen is 1536x864 to the browser.
WIN_W: Final = 1536
WIN_H: Final = 864

_FFMPEG: Final = r"C:\ffmpeg\bin\ffmpeg.exe"


def _ffmpeg_args(out: Path, seconds: int) -> list[str]:
    return [
        _FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        "30",
        "-draw_mouse",
        "1",
        "-i",
        "desktop",
        "-t",
        str(seconds),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]


@dataclass
class Marks:
    """When each beat actually happened, so captions can be timed to reality."""

    started: float = field(default_factory=time.monotonic)
    entries: list[tuple[float, str]] = field(default_factory=list)

    def mark(self, label: str) -> None:
        at = time.monotonic() - self.started
        self.entries.append((at, label))
        print(f"  [{at:6.1f}s] {label}", flush=True)

    def report(self) -> None:
        print("\n=== action timeline (use these to set caption cues) ===")
        for at, label in self.entries:
            print(f"  {at:6.1f}s  {label}")


class Driver:
    """Thin wrapper over a Playwright page with motion that reads on camera."""

    def __init__(self, page: Any, marks: Marks) -> None:
        self.page = page
        self.marks = marks

    def goto(self, route: str, label: str = "") -> None:
        self.page.goto(f"{BASE}{route}", wait_until="networkidle")
        self.page.wait_for_timeout(600)
        self.marks.mark(label or f"goto {route}")

    def settle(self, ms: int = 900) -> None:
        self.page.wait_for_timeout(ms)

    def smooth_scroll_to(self, y: int, duration_ms: int = 1600) -> None:
        """Ease the page to *y*.

        Playwright's default scrolling jumps, which on camera looks like a cut
        rather than a movement. This animates it in the page itself.
        """
        self.page.evaluate(
            """([targetY, dur]) => new Promise(resolve => {
                const startY = window.scrollY;
                const delta = targetY - startY;
                const t0 = performance.now();
                const ease = t => t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t + 2, 2) / 2;
                function step(now) {
                    const t = Math.min(1, (now - t0) / dur);
                    window.scrollTo(0, startY + delta * ease(t));
                    if (t < 1) requestAnimationFrame(step); else resolve();
                }
                requestAnimationFrame(step);
            })""",
            [y, duration_ms],
        )

    def scroll_to_bottom(self, duration_ms: int = 2200, label: str = "scroll to bottom") -> None:
        height = self.page.evaluate("document.body.scrollHeight - window.innerHeight")
        if height <= 0:
            self.marks.mark(f"{label} (page already fits)")
            return
        self.smooth_scroll_to(int(height), duration_ms)
        self.marks.mark(label)

    def scroll_to_top(self, duration_ms: int = 1200) -> None:
        self.smooth_scroll_to(0, duration_ms)

    def click_text(self, text: str, label: str = "", exact: bool = False) -> bool:
        """Click the first element matching *text*; report whether it was there."""
        loc = self.page.get_by_text(text, exact=exact).first
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
            self.page.wait_for_timeout(400)
            loc.click(timeout=3000)
            self.page.wait_for_timeout(800)
            self.marks.mark(label or f"click {text!r}")
            return True
        except Exception as exc:  # noqa: BLE001 - a missing control must not kill a take
            print(f"  !! could not click {text!r}: {type(exc).__name__}", flush=True)
            return False

    def hover_text(self, text: str, label: str = "") -> None:
        try:
            self.page.get_by_text(text).first.hover(timeout=3000)
            self.page.wait_for_timeout(600)
            self.marks.mark(label or f"hover {text!r}")
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def recording(name: str, seconds: int, *, film: bool = True) -> Iterator[tuple[Driver, Marks]]:
    """Launch Chrome, roll ffmpeg, yield a driver, then wait out the capture."""
    from playwright.sync_api import sync_playwright

    TAKES.mkdir(parents=True, exist_ok=True)
    out = TAKES / f"{name}.mkv"
    marks = Marks()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--window-position=0,0",
                f"--window-size={WIN_W},{WIN_H}",
                "--disable-notifications",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
        )
        context = browser.new_context(viewport=None)
        page = context.new_page()
        driver = Driver(page, marks)

        proc: subprocess.Popen[bytes] | None = None
        if film:
            page.goto(f"{BASE}/findings", wait_until="networkidle")
            page.wait_for_timeout(1500)
            proc = subprocess.Popen(_ffmpeg_args(out, seconds))
            time.sleep(1.5)
            marks.started = time.monotonic()

        try:
            yield driver, marks
        finally:
            if proc is not None:
                proc.wait()
                print(f"\n[drive] wrote {out}")
            marks.report()
            browser.close()
