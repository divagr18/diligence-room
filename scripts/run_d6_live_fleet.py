"""Day-6 live fleet check (small window, Vertex ADC, no API key needed).

Builds each deep workstream agent FROM ITS REGISTRY MANIFEST (the D6-M1
factory) and drives a real gemini-3.5-flash agent loop (Vertex ADC,
location=global) that reads its seeded document with the authz-scoped
``data_room_read`` tool and creates a finding with the evidence-gated
``finding_create`` tool. Asserts at least one gated finding per deep
workstream — the Checkpoint-1 "deep four produce independent findings" beat,
run live. Guards: --confirm-live, refuses under the emulator, env contract.
Teardown (project delete) is the operator's step after capture.
"""

from __future__ import annotations

import argparse
import os
import sys

from google.cloud import firestore

from agents.tools.data_room_read import DocSource

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

# agent_id -> (document, category) for the authz-scoped data-room read.
_DEEP_TASKS: dict[str, tuple[str, str]] = {
    "legal": ("contract_meridian_logistics.pdf", "contracts"),
    "finance": ("financials_fy27.xlsx", "financials"),
    "hr": ("hr_roster_vantage.xlsx", "rosters"),
    "ip_tech": ("tech_inventory.pdf", "tech-inventory"),
}


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


async def _run_agent(
    client: firestore.Client,
    publisher: _EventLogPublisher,
    doc_source: DocSource,
    deal_id: str,
    agent_id: str,
    document_name: str,
    category: str,
) -> int:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from agents.base_agent import build_agent_from_manifest
    from memory.findings import FindingsStore
    from registry.models import Workstream

    agent = build_agent_from_manifest(client, agent_id, deal_id, publisher, doc_source)
    store = FindingsStore(client)
    workstream = Workstream(agent_id)
    before = len(store.list_for_workstream(deal_id, workstream))

    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    session = await runner.session_service.create_session(app_name=agent.name, user_id="day6-fleet")
    task = (
        f"Document '{document_name}' (category '{category}') was just ingested "
        f"into deal {deal_id}. Call data_room_read(category='{category}', "
        f"name='{document_name}') to read it. If it contains a material finding "
        "within your workstream, create exactly ONE finding with finding_create "
        "following the finding JSON contract. COPY one exact sentence from the "
        "returned document text verbatim (character-for-character) and use it as "
        f"the evidence verbatim_span, and set each evidence entry's category to "
        f"'{category}'. If there is no finding-worthy content, reply "
        'with {"no_finding": true}.'
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=task)])
    async for event in runner.run_async(
        user_id="day6-fleet", session_id=session.id, new_message=message
    ):
        content = event.content
        if content is None or content.parts is None:
            continue
        for part in content.parts:
            if part.function_call is not None:
                print(f"[fleet:{agent_id}] tool call: {part.function_call.name}")
            if part.text:
                print(f"[fleet:{agent_id}] text: {part.text.strip()[:200]!r}")

    after = len(store.list_for_workstream(deal_id, workstream))
    created = after - before
    print(f"[fleet:{agent_id}] findings created this run: {created}")
    return created


async def _run_live(deal_id: str) -> int:
    from agents.tools.data_room_read import DatasetDocSource
    from gateway.policy import PolicyStore
    from registry.seed import seed_registry
    from registry.store import AgentRegistryStore

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = firestore.Client(project=project)
    store = AgentRegistryStore(client)
    seeded = seed_registry(store)
    print(f"[fleet] registry seeded (+{seeded}); total manifests={len(store.list_manifests())}")
    PolicyStore(client).seed_defaults(deal_id)

    publisher = _EventLogPublisher(client)
    doc_source = DatasetDocSource()
    workstreams_ok = 0
    for agent_id, (document_name, category) in _DEEP_TASKS.items():
        try:
            created = await _run_agent(
                client, publisher, doc_source, deal_id, agent_id, document_name, category
            )
        except Exception as exc:  # noqa: BLE001 — one agent failing must not abort the fleet
            print(f"[fleet:{agent_id}] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            created = 0
        if created >= 1:
            workstreams_ok += 1

    print(f"[fleet] deep workstreams with >=1 finding: {workstreams_ok}/4")
    if workstreams_ok == 4:
        print("[fleet] PASS")
        return 0
    print(f"[fleet] FAIL ({workstreams_ok}/4 workstreams produced gated findings)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-6 live fleet check: real Flash agents from manifests."
    )
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (Vertex Flash + live Firestore)",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-6 live window.", file=sys.stderr)
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

    import asyncio

    return asyncio.run(_run_live(args.deal_id))


if __name__ == "__main__":
    sys.exit(main())
