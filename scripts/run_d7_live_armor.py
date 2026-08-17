"""Day-7 live Model Armor window (BUILD_PLAN D7-M1 live beat, vision §7.6).

Small live window against real GCP: creates (or reuses) a managed Model Armor
template (prompt-injection/jailbreak + malicious-URI detectors), sanitizes one
poisoned red-team fixture through the managed ``sanitize_user_prompt`` API,
layers the project rules on top, and — when the document is blocked — writes
the quarantine record plus security event to live Firestore. Guards:
--confirm-live, refuses under the emulator, env contract (no import-time
defaults). Teardown (project delete) is the operator's step after capture; the
template goes with the project.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from google.cloud import firestore

# Vertex live-window env the operator must set before opening the window.
# These are validated (validate_live_env) and deliberately NOT defaulted here:
# defaulting them at import time made the env contract self-satisfying.
_REQUIRED_ENV: tuple[str, ...] = (
    "DILIGENCE_MODEL_ARMOR_ENABLED",
    "GOOGLE_CLOUD_PROJECT",
    "MODEL_ARMOR_LOCATION",
    "MODEL_ARMOR_TEMPLATE_ID",
)

_FIXTURE_PATH = Path("redteam/attacks/injection/direct_a.pdf")
_DEAL_ID_DEFAULT = "deal-redteam-live"


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
    from armor.model_armor import LiveModelArmor, run_armor
    from armor.quarantine import QuarantineStore
    from armor.rules import screen_project_rules
    from ingestion.lineage import checksum
    from ingestion.parsing import LocalParser

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ["MODEL_ARMOR_LOCATION"]
    template_id = os.environ["MODEL_ARMOR_TEMPLATE_ID"]

    armor = LiveModelArmor(template_id=template_id, location=location, project=project)
    template_name = armor.ensure_template()
    print(f"[armor] template ready: {template_name}")

    repo_root = Path(__file__).resolve().parent.parent
    blob = (repo_root / _FIXTURE_PATH).read_bytes()
    parsed = LocalParser().parse(blob, _FIXTURE_PATH.name, deal_id)
    assert parsed.text is not None
    text = parsed.text
    digest = checksum(blob)
    print(
        f"[armor] fixture: {_FIXTURE_PATH.as_posix()} ({len(text)} chars, sha256 {digest[:12]}...)"
    )

    managed_verdict = armor.sanitize(text)
    print(
        f"[armor] managed verdict: blocked={managed_verdict.blocked} "
        f"reasons={list(managed_verdict.reason_codes)} "
        f"latency_ms={managed_verdict.latency_ms:.1f}"
    )

    rules_only = [hit.rule_id for hit in screen_project_rules(text)]
    print(f"[armor] project-rules layer: {rules_only}")

    combined = run_armor(text, managed=armor)
    print(
        f"[armor] combined verdict: blocked={combined.blocked} "
        f"reasons={list(combined.reason_codes)} rules={list(combined.rule_ids)}"
    )
    metrics = armor.metrics
    print(
        f"[armor] metrics: sanitize_calls={metrics.sanitize_calls} "
        f"blocked_calls={metrics.blocked_calls} "
        f"total_latency_ms={metrics.total_latency_ms:.1f} "
        f"estimated_input_tokens={metrics.estimated_input_tokens}"
    )

    if not combined.blocked:
        print("[armor] RED: fixture was NOT blocked - window captured as a red result")
        return 1

    client = firestore.Client(project=project)
    store = QuarantineStore(client)
    publisher = _EventLogPublisher(client)
    record = store.quarantine(
        deal_id,
        _FIXTURE_PATH.name,
        checksum=digest,
        version=1,
        layer="model_armor",
        reason_codes=tuple(dict.fromkeys(combined.reason_codes + managed_verdict.reason_codes)),
        rule_ids=combined.rule_ids,
        publisher=publisher,
        emit_event=True,
    )
    print(f"[armor] quarantine record written: deals/{deal_id}/quarantined/{record.document_id}")
    print(f"[armor] security event appended to deals/{deal_id}/events (armor_quarantine)")
    print("[armor] PASS: poisoned fixture blocked by managed Model Armor + project rules")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-7 live window: managed Model Armor sanitize on a poisoned fixture."
    )
    parser.add_argument("--deal-id", default=_DEAL_ID_DEFAULT)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (Model Armor API + live Firestore)",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-7 live window.", file=sys.stderr)
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
