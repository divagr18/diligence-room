"""Shared test fixtures: local Firestore emulator lifecycle (Wave-0 infra).

The emulator is session-scoped (one process per pytest run) on a socket-probed
free port; isolation comes from a unique project id per test, so no data
cleanup is ever needed. Windows teardown kills the whole process tree
(gcloud.cmd shim -> python -> java).
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from google.cloud import firestore

from infra.bootstrap_gcp import _gcloud_executable

_EMULATOR_STARTUP_DEADLINE_S = 90.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _kill_process_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        check=False,
    )


def _await_ready(port: int, proc: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + _EMULATOR_STARTUP_DEADLINE_S
    while time.monotonic() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Firestore emulator exited with code {exit_code}:\n{tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    _kill_process_tree(proc.pid)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
    raise RuntimeError(f"Firestore emulator not ready in {_EMULATOR_STARTUP_DEADLINE_S}s:\n{tail}")


@pytest.fixture(scope="session")
def firestore_emulator() -> Iterator[str]:
    port = _free_port()
    log_path = Path(tempfile.gettempdir()) / f"firestore-emulator-{uuid.uuid4().hex[:8]}.log"
    with log_path.open("w+b") as log_file:
        proc = subprocess.Popen(  # noqa: S603 — emulator is a fixed local dev tool
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
        try:
            _await_ready(port, proc, log_path)
        except Exception:
            _kill_process_tree(proc.pid)
            raise
        previous = os.environ.get("FIRESTORE_EMULATOR_HOST")
        os.environ["FIRESTORE_EMULATOR_HOST"] = f"127.0.0.1:{port}"
        try:
            yield f"127.0.0.1:{port}"
        finally:
            if previous is None:
                os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
            else:
                os.environ["FIRESTORE_EMULATOR_HOST"] = previous
            _kill_process_tree(proc.pid)
    with contextlib.suppress(OSError):
        log_path.unlink()


@pytest.fixture()
def unique_project() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def firestore_client(firestore_emulator: str, unique_project: str) -> firestore.Client:
    return firestore.Client(project=unique_project)
