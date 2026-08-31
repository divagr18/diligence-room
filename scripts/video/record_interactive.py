"""Browser-driven demo capture: Playwright works the app, ffmpeg films the screen.

The first cut pointed a screen recorder at static pages. This drives the real
SPA — scrolling, filtering, opening source documents, expanding the trace panel,
and running a human approval end to end — so things actually happen on camera.

Chrome comes from Playwright's ``channel="chrome"``, i.e. the same browser a
judge would use, and gdigrab films the desktop rather than Playwright's built-in
video, which keeps the run.app URL in the address bar on screen.

Every action is timestamped and printed at the end, so caption cues are set
against what really happened rather than guessed.

Prepare (HITL needs an unapproved draft):
    uv run python scripts/video/reset_deal.py --deal-id deal-falcon \\
        --drafts-only --confirm

Run:
    uv run --with playwright python scripts/video/record_interactive.py
    uv run --with playwright python scripts/video/record_interactive.py --only hitl
"""

from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parent.parent.parent
TAKES: Final = ROOT / "docs/video/takes"
BASE: Final = "https://diligence-room-dashboard-378831539922.asia-south1.run.app"
CRITICAL: Final = "f4c993d48cda"

# The panel is 1920x1080 and gdigrab films all of it. Windows sits at 125% and
# this Chrome profile carries a 120% page zoom, which together render content at
# 1.5x and leave a 1280x720 CSS viewport. --force-device-scale-factor=1 plus a
# reset zoom maps CSS pixels 1:1 onto the panel, so the capture is a true
# 1920x1080 of the app rather than a magnified crop of it.
SCREEN_W: Final = 1920
SCREEN_H: Final = 1080
FFMPEG: Final = r"C:\ffmpeg\bin\ffmpeg.exe"


class Driver:
    """A Playwright page plus motion that reads as movement on camera."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self._t0 = time.monotonic()
        self.timeline: list[tuple[float, str]] = []

    def mark(self, label: str) -> None:
        at = time.monotonic() - self._t0
        self.timeline.append((at, label))
        print(f"    [{at:5.1f}s] {label}", flush=True)

    def reset_clock(self) -> None:
        self._t0 = time.monotonic()
        self.timeline.clear()

    def goto(self, route: str) -> None:
        self.page.goto(f"{BASE}{route}", wait_until="networkidle")
        self.page.wait_for_timeout(700)

    def settle(self, ms: int = 900) -> None:
        self.page.wait_for_timeout(ms)

    def glide_to(self, y: int, ms: int = 800) -> None:
        """Ease the scroll position to *y*.

        Playwright's own scrolling jumps, which on camera looks like a cut. This
        animates inside the page so the movement is visible.
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
            [y, ms],
        )

    def glide_bottom(self, ms: int = 1100, label: str = "scroll to bottom") -> None:
        limit = self.page.evaluate("document.body.scrollHeight - window.innerHeight")
        if limit <= 0:
            self.mark(f"{label} (page already fits)")
            return
        self.glide_to(int(limit), ms)
        self.mark(label)

    def glide_frac(self, frac: float, ms: int = 800, label: str = "") -> None:
        """Scroll to *frac* of the way down the page.

        Long tables get taller as data lands, so a fraction survives a reseed
        where a pixel offset does not.
        """
        limit = self.page.evaluate("document.body.scrollHeight - window.innerHeight")
        if limit <= 0:
            self.mark(f"{label or 'scroll'} (page already fits)")
            return
        self.glide_to(int(limit * frac), ms)
        self.mark(label or f"scroll to {frac:.0%}")

    def glide_to_text(self, text: str, ms: int = 800, label: str = "") -> None:
        """Scroll a heading into view without the instant jump."""
        y = self.page.evaluate(
            """(needle) => {
                const el = [...document.querySelectorAll('h1,h2,h3,h4')]
                    .find(e => e.textContent.trim().toLowerCase().includes(needle.toLowerCase()));
                return el ? window.scrollY + el.getBoundingClientRect().top - 90 : null;
            }""",
            text,
        )
        if y is None:
            self.mark(f"!! heading {text!r} not found")
            return
        self.glide_to(int(y), ms)
        self.mark(label or f"scroll to {text!r}")

    def click_chip(self, group: str, name: str, label: str = "") -> bool:
        """Click a filter chip inside its own group.

        Both the severity and status groups contain a button reading "all", so an
        unscoped query is a strict-mode violation. Chip text is lowercase in the
        DOM; the uppercase look is CSS only.
        """
        try:
            self.page.get_by_role("group", name=group).get_by_role(
                "button", name=name, exact=True
            ).click(timeout=4000)
            self.page.wait_for_timeout(1000)
            self.mark(label or f"filter {name!r}")
            return True
        except Exception as exc:  # noqa: BLE001
            self.mark(f"!! chip {name!r} in {group!r} ({type(exc).__name__})")
            return False

    def press_escape(self, label: str = "close the viewer") -> None:
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(900)
        self.mark(label)

    def click_text(self, text: str, label: str = "", settle: int = 1100) -> bool:
        loc = self.page.get_by_text(text).first
        try:
            loc.scroll_into_view_if_needed(timeout=4000)
            self.page.wait_for_timeout(500)
            loc.click(timeout=4000)
            self.page.wait_for_timeout(settle)
            self.mark(label or f"click {text!r}")
            return True
        except Exception as exc:  # noqa: BLE001 - a missing control must not kill a take
            self.mark(f"!! could not click {text!r} ({type(exc).__name__})")
            return False


def _powershell(body: str) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{ROOT.as_posix()}/scripts/video/lib/windows.ps1'; {body}",
        ],
        capture_output=True,
    )


def stage_desktop() -> None:
    """Hide the taskbar and always-on-top system chrome.

    Chrome maximises into the *work area*, so the taskbar has to go first or the
    window stops short of the bottom of the screen.
    """
    _powershell(
        "Move-Taskbar -Action park | Out-Null; "
        "Hide-ImeIndicators | Out-Null; Hide-SystemFlyouts | Out-Null"
    )


def unstage_desktop() -> None:
    _powershell("Move-Taskbar -Action restore | Out-Null")


@contextmanager
def capture(name: str, seconds: int) -> Iterator[None]:
    TAKES.mkdir(parents=True, exist_ok=True)
    out = TAKES / f"{name}.mkv"
    proc = subprocess.Popen(
        [
            FFMPEG,
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
    )
    time.sleep(1.2)
    try:
        yield
    finally:
        proc.wait()
        print(f"    -> {out.name}", flush=True)


# --------------------------------------------------------------------------
# Choreography. One function per segment; each assumes it owns the screen.
# --------------------------------------------------------------------------


def seg_room(d: Driver) -> None:
    """The deal room down to the escalation inbox, then every document read.

    The nav click is deliberate rather than a ``goto``: the sidebar moving is
    what tells the viewer these are tabs of one app, not four screenshots.
    """
    d.settle(1100)
    d.mark("deal room: Project Falcon, workstream progress")
    d.glide_to_text("Workstreams", 700, "scroll to workstreams")
    d.settle(1400)
    d.glide_bottom(900, "escalation inbox")
    d.settle(2200)
    d.click_text("Documents", "open the Documents tab")
    d.settle(1800)
    d.mark("documents: every file the fleet read, routed and scored")
    d.glide_bottom(1400, "down the document list")
    d.settle(1800)


def seg_findings(d: Driver) -> None:
    """The cold open: the findings table, filtered down to the one that matters."""
    d.settle(900)
    d.mark("findings: five across eight workstreams")
    d.glide_bottom(900, "down the findings list")
    d.settle(1200)
    d.glide_to(0, 700)
    d.settle(700)
    d.click_chip("Filter by severity", "critical", "filter to critical only")
    d.settle(1600)
    d.click_chip("Filter by severity", "high", "filter to high")
    d.settle(1400)
    d.click_chip("Filter by severity", "all", "back to all findings")
    d.settle(1200)
    d.click_text("Compound customer-exit exposure", "open the critical finding")
    d.settle(1600)


def seg_evidence(d: Driver) -> None:
    """Evidence spans, and the source document behind one of them."""
    d.settle(1100)
    d.mark("critical finding: 90% confidence, 4 documents, 4 agents")
    d.glide_to_text("Summary", 600, "summary")
    d.settle(1400)
    d.glide_to_text("Evidence", 700, "evidence spans")
    d.settle(1800)
    d.click_text("Open source", "open the source document")
    d.settle(3000)
    d.press_escape()
    d.settle(1000)


def seg_trace(d: Driver) -> None:
    """Scope, open questions, the negotiation panel and the audit trace."""
    d.goto(f"/findings/{CRITICAL}")
    d.settle(900)
    d.glide_to_text("Scope", 650, "scope")
    d.settle(1300)
    d.glide_to_text("Open questions", 650, "open questions")
    d.settle(1400)
    d.glide_to_text("Finding graph", 700, "finding graph: documents to agents to finding")
    d.settle(1800)
    d.glide_to_text("Trace", 700, "audit trace panel")
    d.settle(2000)
    d.glide_bottom(700, "end of the trace")
    d.settle(1200)


def seg_security(d: Driver) -> None:
    """The whole quarantine table, top to bottom.

    Scroll targets are fractions of the page rather than pixel offsets: forcing a
    1:1 pixel mapping made the viewport taller, and the old absolute offsets
    would run past the end of the table.
    """
    d.settle(1500)
    d.mark("security: 20/20 blocked, four attack classes")
    d.glide_frac(0.30, 900)
    d.settle(1000)
    d.glide_frac(0.60, 900)
    d.settle(1000)
    d.glide_bottom(1000, "bottom of the quarantine log")
    d.settle(1400)


def seg_hitl(d: Driver) -> None:
    """The human gate, performed: draft, then approve, then send."""
    d.settle(900)
    d.glide_to_text("Negotiation", 700, "negotiation panel")
    d.settle(1200)
    d.click_text("Draft clause redline", "agent drafts the redline", settle=3800)
    d.settle(1600)
    d.click_text("draft body", "expand the drafted letter", settle=1800)
    d.settle(2100)
    d.click_text("Approve", "I approve it - the human gate", settle=3200)
    d.settle(1700)
    d.click_text("Record send", "send is recorded", settle=2600)
    d.settle(1600)


# Keyed in cut order, and each length is its window in interactive_script.py
# plus a couple of seconds of handle to trim against.
SEGMENTS: Final[dict[str, tuple[str, int, Callable[[Driver], None]]]] = {
    "findings": ("/findings", 28, seg_findings),
    "evidence": (f"/findings/{CRITICAL}", 34, seg_evidence),
    "trace": (f"/findings/{CRITICAL}", 32, seg_trace),
    "room": ("/", 30, seg_room),
    "security": ("/security", 32, seg_security),
    "hitl": (f"/findings/{CRITICAL}", 40, seg_hitl),
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the interactive demo segments.")
    parser.add_argument("--only", default="", help="record just this segment")
    parser.add_argument("--prefix", default="ui_", help="take filename prefix")
    args = parser.parse_args(argv)

    wanted = [args.only] if args.only else list(SEGMENTS)
    unknown = [name for name in wanted if name not in SEGMENTS]
    if unknown:
        raise SystemExit(f"unknown segment(s): {unknown}; have {list(SEGMENTS)}")

    from playwright.sync_api import sync_playwright

    stage_desktop()
    time.sleep(1.0)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--start-maximized",
                "--force-device-scale-factor=1",
                "--window-position=0,0",
                "--disable-notifications",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
        )
        page = browser.new_context(viewport=None).new_page()
        page.goto(f"{BASE}/findings", wait_until="networkidle")
        size = page.evaluate(
            "({w: window.innerWidth, h: window.innerHeight,"
            " ow: window.outerWidth, oh: window.outerHeight,"
            " sw: screen.width, sh: screen.height, dpr: window.devicePixelRatio})"
        )
        print(
            f"window: inner {size['w']}x{size['h']}  outer {size['ow']}x{size['oh']}"
            f"  screen {size['sw']}x{size['sh']}  dpr {size['dpr']}",
            flush=True,
        )
        # gdigrab films SCREEN_W x SCREEN_H of physical panel; anything narrower
        # here means the capture is a magnified crop rather than the whole app.
        if size["sw"] * size["dpr"] < SCREEN_W - 4:
            print(
                f"  !! CSS viewport maps to {size['sw'] * size['dpr']:.0f}px, "
                f"not {SCREEN_W}: content will be magnified",
                flush=True,
            )
        d = Driver(page)

        for name in wanted:
            route, seconds, choreograph = SEGMENTS[name]
            print(f"\n=== {name} ({seconds}s) ===", flush=True)
            d.goto(route)
            d.settle(744)
            d.reset_clock()
            with capture(f"{args.prefix}{name}", seconds):
                choreograph(d)

            print(f"  --- {name} timeline ---")
            for at, label in d.timeline:
                print(f"    {at:5.1f}s  {label}")

        browser.close()
    unstage_desktop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
