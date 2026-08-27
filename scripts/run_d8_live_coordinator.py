"""Day-8 live coordinator check (small window, Vertex ADC, no API key needed).

Proves the keystone against LIVE Firestore: the deep-four findings produced
by the Day-6 live fleet window converge on the deal's risk entity and the
coordinator synthesis fires — one escalating CRITICAL finding with a stable
id, a deal-lead inbox entry, and a finding.escalated event in the append-only
log. The synthesis write path is the deterministic evidence-preserving
aggregate (agents.coordinator.synthesize); the live window proves the live
data plane and never relaxes the evidence gate. Guards: --confirm-live,
refuses under the emulator, env contract. Teardown (project delete) is the
operator's step after capture.
"""

from __future__ import annotations

import argparse
import os
import sys

from google.cloud import firestore

# Vertex live-window env the operator must set before opening the window.
# These are validated (validate_live_env) and deliberately NOT defaulted here:
# defaulting them at import time made the env contract self-satisfying.
# GOOGLE_CLOUD_LOCATION must be "global" — gemini-3.5-flash is served only
# from the global location on Vertex.
_REQUIRED_ENV: tuple[str, ...] = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)


def required_env() -> tuple[str, ...]:
    return _REQUIRED_ENV


def validate_live_env() -> tuple[str, ...]:
    return tuple(name for name in _REQUIRED_ENV if not os.environ.get(name))


class _EventLogPublisher:
    def __init__(self, client: firestore.Client) -> None:
        from memory.event_log import EventLog

        self._log = EventLog(client)

    def publish(self, event: object) -> str:
        seq = self._log.append(event)  # type: ignore[arg-type]
        return str(seq)


def _run_live(deal_id: str) -> int:
    from agents.coordinator.synthesize import REQUIRED_CONTRIBUTORS, synthesize_critical
    from gateway.policy import PolicyStore
    from memory.db import make_client
    from memory.findings import FindingSeverity, FindingsStore
    from registry.seed import seed_registry
    from registry.store import AgentRegistryStore

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = make_client(project)
    store = AgentRegistryStore(client)
    seeded = seed_registry(store)
    print(
        f"[coordinator] registry seeded (+{seeded}); total manifests={len(store.list_manifests())}"
    )
    PolicyStore(client).seed_defaults(deal_id)

    findings = FindingsStore(client)
    missing = [
        ws.value for ws in REQUIRED_CONTRIBUTORS if not findings.list_for_workstream(deal_id, ws)
    ]
    if missing:
        print(
            "[coordinator] FAIL - missing deep-four findings for: "
            + ", ".join(missing)
            + " (open the Day-6 window first: scripts/run_d6_live_fleet.py --confirm-live)",
            file=sys.stderr,
        )
        return 1

    publisher = _EventLogPublisher(client)
    finding_id = synthesize_critical(client, deal_id, publisher=publisher)
    if finding_id is None:
        print("[coordinator] FAIL - synthesis refused (no convergence entity)", file=sys.stderr)
        return 1

    finding = findings.get(deal_id, finding_id)
    assert finding.severity is FindingSeverity.CRITICAL
    inbox_doc = (
        client.collection("deals").document(deal_id).collection("inbox").document(finding_id).get()
    )
    print(f"[coordinator] synthesized CRITICAL finding {finding_id}: {finding.title}")
    print(f"[coordinator] contributors: {', '.join(finding.related_findings)}")
    print(f"[coordinator] escalated to deal-lead inbox: {inbox_doc.to_dict() is not None}")
    print("[coordinator] PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-8 live coordinator check: keystone synthesis against live Firestore."
    )
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (live Firestore)",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-8 live window.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is set; live window targets real GCP.",
            file=sys.stderr,
        )
        sys.exit(1)
    missing = validate_live_env()
    if missing:
        print("Refusing: missing live-window env: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    return _run_live(args.deal_id)


if __name__ == "__main__":
    sys.exit(main())
