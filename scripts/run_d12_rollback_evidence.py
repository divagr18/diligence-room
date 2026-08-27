"""Offline evidence receipt: Legal v2.5 upgrade + rollback preserving memory (D12-M4).

Starts a local Firestore emulator, seeds the eight-agent registry, publishes
Legal v2.5 (the deliberate CoC-prompt regression), records the shadow harness
going RED on the missing CoC pin, rolls back through
``AgentRegistryStore.rollback``, and records the restored fleet going GREEN
with the ``deals/{id}/findings/{fid}`` partition untouched. The beat runs
twice on isolated projects to prove the rollback demo is repeatable (plan §9).
Fully offline and deterministic: no network, no live LLM call.

Usage: ``uv run python scripts/run_d12_rollback_evidence.py``
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import firestore

from agents.fleet import DEEP_WORKSTREAM_DOCUMENTS
from evals.harness import run_harness
from evals.legal_v25 import extractor_from_registry, publish_legal_v25
from infra.bootstrap_gcp import _gcloud_executable
from memory.db import make_client
from memory.findings import FindingsStore
from registry.seed import seed_registry
from registry.store import AgentRegistryStore

SEED_NOW = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
PUBLISH_NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)
KNOWN_GOOD_VERSION = "2.4.0"
EMULATOR_STARTUP_DEADLINE_S = 90.0


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


@contextmanager
def _emulator() -> Iterator[str]:
    port = _free_port()
    log_path = Path(tempfile.gettempdir()) / f"firestore-evidence-{uuid.uuid4().hex[:8]}.log"
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
        deadline = time.monotonic() + EMULATOR_STARTUP_DEADLINE_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Firestore emulator exited with code {proc.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            _kill_process_tree(proc.pid)
            raise RuntimeError(f"Firestore emulator not ready in {EMULATOR_STARTUP_DEADLINE_S}s")
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


def _finding_counts(client: firestore.Client, deal_id: str) -> dict[str, int]:
    store = FindingsStore(client)
    return {
        workstream.value: len(store.list_for_workstream(deal_id, workstream))
        for workstream in DEEP_WORKSTREAM_DOCUMENTS
    }


def _run_beat(round_id: int) -> None:
    project = f"d12-m4-evidence-{round_id}"
    print(f"--- round {round_id} (project {project}) ---")
    client = make_client(project)
    registry = AgentRegistryStore(client)
    seeded = seed_registry(registry, now=SEED_NOW)
    print(
        f"[seed]     {seeded} manifests created; legal at {registry.get_manifest('legal').version}"
    )

    published = publish_legal_v25(registry, now=PUBLISH_NOW)
    print(
        f"[publish]  legal {published.version} approved={published.approved} "
        f"rollback_target={published.rollback_target}"
    )

    red = run_harness(client, f"deal-d12-red-{round_id}", extractor_from_registry(registry))
    print(f"[RED]      harness passed={red.passed} missing={[doc.doc_id for doc in red.missing]}")
    if red.passed:
        raise SystemExit("expected the Legal v2.5 candidate to fail the shadow harness")
    counts_before = _finding_counts(client, f"deal-d12-red-{round_id}")
    print(f"[memory]   findings before rollback: {counts_before}")

    rolled_back = registry.rollback("legal", KNOWN_GOOD_VERSION)
    print(
        f"[rollback] legal {rolled_back.version} approved={rolled_back.approved} "
        f"rollback_target={rolled_back.rollback_target}"
    )

    counts_after = _finding_counts(client, f"deal-d12-red-{round_id}")
    print(
        f"[memory]   findings after rollback:  {counts_after} "
        f"identical={counts_after == counts_before}"
    )
    if counts_after != counts_before:
        raise SystemExit("rollback must not touch the findings partition")

    green = run_harness(client, f"deal-d12-green-{round_id}", extractor_from_registry(registry))
    print(
        f"[GREEN]    harness passed={green.passed} missing={list(green.missing)} "
        f"downgraded={len(green.downgraded)}"
    )
    if not green.passed:
        raise SystemExit("expected the restored fleet to pass the shadow harness")


def main() -> int:
    print("D12-M4 evidence — Legal v2.5 regression + rollback preserving memory")
    print("offline emulator run; no network, no live LLM call")
    with _emulator() as host:
        print(f"emulator ready at {host}")
        _run_beat(1)
        _run_beat(2)
    print("EVIDENCE OK: RED -> rollback -> GREEN twice; findings counts identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
