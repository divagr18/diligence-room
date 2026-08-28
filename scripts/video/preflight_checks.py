"""Preflight assertion battery for the demo recording (blocks takes on RED).

Blocking checks prove the recording machinery and the pipeline beats that get
captured. Deployed-service checks are WARN-only: Cloud Run routing degrades
on its own schedule and the beats are recorded against the local dev shell.

Usage:
    uv run python scripts/video/preflight_checks.py [--with-shell] [--slow]
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

Results = list[tuple[str, str, str]]  # (status, name, detail)


def _ok(results: Results, name: str, detail: str) -> None:
    results.append(("PASS", name, detail))


def _fail(results: Results, name: str, detail: str) -> None:
    results.append(("FAIL", name, detail))


def _warn(results: Results, name: str, detail: str) -> None:
    results.append(("WARN", name, detail))


def _run(
    cmd: list[str], env: dict[str, str] | None = None, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=_ROOT)


def check_machine(results: Results) -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            _fail(results, f"machine:{tool}", "not on PATH")
            return
    font = Path("C:/Windows/Fonts/segoeui.ttf")
    if not font.exists():
        _fail(results, "machine:font", "segoeui.ttf missing")
        return
    grab = Path(tempfile.gettempdir()) / "preflight-grab.mp4"
    proc = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "gdigrab",
            "-framerate",
            "5",
            "-i",
            "desktop",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(grab),
        ],
        timeout=60,
    )
    if proc.returncode != 0 or not grab.exists():
        _fail(results, "machine:gdigrab", proc.stderr[-200:])
        return
    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(grab),
        ],
        timeout=30,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if streams and streams[0].get("width") == 1920 and streams[0].get("height") == 1080:
        _ok(results, "machine", "ffmpeg/ffprobe/gdigrab ok; desktop 1920x1080; segoeui present")
    else:
        _fail(results, "machine:resolution", f"desktop capture not 1920x1080: {streams}")


def check_replay_invariants(results: Results) -> None:
    from runtime.replay import DEFAULT_SCENARIO_PATH, derive_run_id

    if derive_run_id(42) != "replay-bdd640fb0667":
        _fail(results, "replay:run_id", f"got {derive_run_id(42)}")
        return
    envelope = json.loads(DEFAULT_SCENARIO_PATH.read_text(encoding="utf-8"))
    stamps = [datetime.fromisoformat(e["ts"].replace("Z", "+00:00")) for e in envelope["events"]]
    span = (max(stamps) - min(stamps)).total_seconds()
    if len(envelope["events"]) != 49 or not (1_100_000 <= span <= 1_200_000):
        _fail(results, "replay:scenario", f"events={len(envelope['events'])} span={span}")
        return
    _ok(results, "replay:invariants", f"run_id pinned; 49 events; span {span:.0f}s")


def _boot_emulator() -> tuple[subprocess.Popen[bytes], int, Path]:
    from infra.bootstrap_gcp import _gcloud_executable

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    log_path = Path(tempfile.gettempdir()) / f"preflight-emulator-{int(time.time())}.log"
    log_file = log_path.open("w+b")
    proc = subprocess.Popen(
        [
            _gcloud_executable(),
            "beta",
            "emulators",
            "firestore",
            "start",
            f"--host-port=127.0.0.1:{port}",
            "--quiet",
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"emulator exited {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return proc, port, log_path
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("emulator not ready in 90s")


def _kill(proc: subprocess.Popen[bytes]) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False
    )


def check_replay_full(results: Results) -> None:
    proc, port, _log = _boot_emulator()
    try:
        env = dict(__import__("os").environ)
        env["FIRESTORE_EMULATOR_HOST"] = f"127.0.0.1:{port}"
        env["GOOGLE_CLOUD_PROJECT"] = "preflight-replay"
        run = _run(
            [
                sys.executable,
                "scripts/video/replay_cli.py",
                "--speed",
                "1000000",
                "--seed",
                "42",
                "--deal-id",
                "preflight",
            ],
            env=env,
            timeout=300,
        )
        out = run.stdout
        needed = (
            "run_id=replay-bdd640fb0667",
            "events_injected=49",
            "findings_created=5",
            "deterministic=True",
        )
        if run.returncode == 0 and all(n in out for n in needed):
            _ok(
                results,
                "replay:full-run",
                "49 events / 5 findings / deterministic on disposable emulator",
            )
        else:
            _fail(results, "replay:full-run", out[-400:] or run.stderr[-400:])
    finally:
        _kill(proc)


def check_redteam_offline(results: Results) -> None:
    proc, port, _log = _boot_emulator()
    try:
        env = dict(__import__("os").environ)
        env["FIRESTORE_EMULATOR_HOST"] = f"127.0.0.1:{port}"
        env["GOOGLE_CLOUD_PROJECT"] = "preflight-redteam"
        run = _run(
            [sys.executable, "redteam/runner.py", "--deal-id", "preflight-rt"], env=env, timeout=300
        )
        if run.returncode == 0 and "TOTAL" in run.stdout and "20/20" in run.stdout:
            _ok(results, "redteam:offline", "20/20 blocked on disposable emulator")
        else:
            _fail(results, "redteam:offline", run.stdout[-400:] or run.stderr[-400:])
    finally:
        _kill(proc)


def check_cameo_test(results: Results) -> None:
    run = _run([sys.executable, "-m", "pytest", "tests/test_crash_resume.py", "-q"], timeout=600)
    if run.returncode == 0:
        _ok(
            results,
            "cameo:crash-resume",
            "tests/test_crash_resume.py green (self-contained emulator)",
        )
    else:
        _fail(results, "cameo:crash-resume", run.stdout[-300:] + run.stderr[-300:])


def check_d12_rollback(results: Results) -> None:
    run = _run([sys.executable, "scripts/run_d12_rollback_evidence.py"], timeout=900)
    if run.returncode == 0 and "EVIDENCE OK" in run.stdout:
        _ok(results, "beat6:rollback", "run_d12_rollback_evidence.py EVIDENCE OK")
    else:
        _fail(results, "beat6:rollback", run.stdout[-400:] or run.stderr[-400:])


def check_cards(results: Results) -> None:
    cards = _ROOT / "docs" / "video" / "cards"
    missing = [
        n for n in ("title.mp4", *(f"b{i}.png" for i in range(1, 8))) if not (cards / n).exists()
    ]
    if missing:
        _fail(results, "cards", f"missing: {missing} (run scripts/video/cards.ps1 -All)")
        return
    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(cards / "b1.png"),
        ],
        timeout=30,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if streams and streams[0].get("width") == 1920 and streams[0].get("height") == 1080:
        _ok(results, "cards", "title + 7 lower thirds rendered at 1920x1080")
    else:
        _fail(results, "cards", f"unexpected dimensions: {streams}")


def check_dev_shell(results: Results) -> None:
    for url, name in (
        ("http://127.0.0.1:8040/api/health", "shell:8040"),
        ("http://127.0.0.1:5173/api/health", "shell:5173-proxy"),
    ):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode()
            if '"status":"ok"' in body:
                _ok(results, name, body.strip())
            else:
                _fail(results, name, body[:120])
        except (urllib.error.URLError, OSError) as exc:
            _fail(results, name, str(exc))


def check_live_services(results: Results) -> None:
    dash = "https://diligence-room-dashboard-910285417505.europe-west1.run.app"
    gw = "https://gateway-910285417505.europe-west1.run.app"
    try:
        with urllib.request.urlopen(f"{dash}/api/health", timeout=8) as resp:
            _warn(results, "live:dashboard", resp.read().decode()[:120])
    except (urllib.error.URLError, OSError) as exc:
        _warn(results, "live:dashboard", f"unreachable ({exc}) - beats use local dev shell")
    try:
        req = urllib.request.Request(
            f"{gw}/gateway/decide",
            method="POST",
            data=json.dumps(
                {
                    "sender_identity": "legal-agent@deal-falcon",
                    "target_workstream": "finance",
                    "deal_id": "deal-falcon",
                    "question": "Q",
                    "purpose": "revenue_concentration",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            _warn(results, "live:gateway", resp.read().decode()[:120])
    except (urllib.error.URLError, OSError) as exc:
        _warn(results, "live:gateway", f"unreachable ({exc}) - beat 4 uses local shell + console")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-shell", action="store_true", help="also assert the local dev shell is up"
    )
    parser.add_argument(
        "--slow", action="store_true", help="include the d12 rollback evidence run (~60-90s)"
    )
    args = parser.parse_args()

    results: Results = []
    checks: list[tuple[str, Callable[[Results], None]]] = [
        ("machine", check_machine),
        ("replay invariants", check_replay_invariants),
        ("cards", check_cards),
        ("replay full run", check_replay_full),
        ("red-team offline", check_redteam_offline),
        ("cameo crash-resume", check_cameo_test),
    ]
    if args.slow:
        checks.append(("d12 rollback", check_d12_rollback))
    for label, fn in checks:
        print(f"[preflight] {label} ...", flush=True)
        try:
            fn(results)
        except Exception as exc:  # noqa: BLE001 — report, keep going
            _fail(results, label, f"{type(exc).__name__}: {exc}")
    if args.with_shell:
        check_dev_shell(results)
    check_live_services(results)

    print()
    failed = 0
    for status, name, detail in results:
        print(f"[preflight] {status:4} {name}: {detail}")
        if status == "FAIL":
            failed += 1
    print()
    if failed:
        print(f"[preflight] RED: {failed} blocking check(s) failed - recording blocked")
        return 1
    print("[preflight] GREEN: all blocking checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
