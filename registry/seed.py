"""Registry seed data and idempotent seeding (BUILD_PLAN D2-M5).

Eight workstream agents per vision §4.2 with the locked version set.
The live seeder (``main``) is a runbook step; tests call ``seed_registry``
against an emulator-backed store.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from registry.models import AgentManifest, AgentVersion
from registry.store import AgentRegistryStore

_MODEL_ID = "gemini-3.5-flash"
_POLICY_PROFILE = "falcon-standard-v1"
_ALLOWED_TOOLS: tuple[str, ...] = ("data-room-read", "finding-create", "gateway-query")


def _prompt_ref(agent_id: str) -> str:
    return f"agents.{agent_id}.prompts:SYSTEM_PROMPT"


def _build_seeds(created_at: datetime) -> tuple[AgentManifest, ...]:
    specs: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
        (
            "legal",
            "Legal Agent",
            "2.4.0",
            ("contract analysis", "change-of-control detection", "litigation extraction"),
            ("contract", "litigation"),
        ),
        (
            "finance",
            "Finance Agent",
            "3.1.0",
            ("revenue quality analysis", "concentration measurement", "model maintenance"),
            ("financial-statement", "projection"),
        ),
        (
            "hr",
            "HR Agent",
            "1.8.0",
            ("retention risk detection", "key-person dependency"),
            ("roster", "compensation"),
        ),
        (
            "ip_tech",
            "IP & Technology Agent",
            "2.2.0",
            ("dependency risk", "license exposure", "infrastructure risk"),
            ("patent", "license", "tech-inventory"),
        ),
        (
            "tax",
            "Tax Agent",
            "1.5.0",
            ("tax exposure", "carryforward analysis"),
            ("tax-filing",),
        ),
        (
            "regulatory",
            "Regulatory Agent",
            "2.0.0",
            ("market concentration", "permit review"),
            ("regulatory-correspondence",),
        ),
        (
            "esg",
            "ESG Agent",
            "1.3.0",
            ("environmental liability", "disclosure review"),
            ("esg-report",),
        ),
        (
            "real_estate",
            "Real Estate Agent",
            "1.1.0",
            ("lease review", "renewal windows", "CoC provisions in property agreements"),
            ("lease",),
        ),
    )
    manifests: list[AgentManifest] = []
    for agent_id, name, version, capabilities, document_types in specs:
        manifests.append(
            AgentManifest(
                agent_id=agent_id,
                name=name,
                version=version,
                capabilities=capabilities,
                owner="team-b",
                required_identity=f"{agent_id}-agent@deal",
                allowed_tools=_ALLOWED_TOOLS,
                supported_document_types=document_types,
                policy_profile=_POLICY_PROFILE,
                created_at=created_at,
                approved=True,
            )
        )
    return tuple(manifests)


SEED_MANIFESTS: tuple[AgentManifest, ...] = _build_seeds(datetime(2026, 8, 14, tzinfo=UTC))


def seed_registry(store: AgentRegistryStore, now: datetime | None = None) -> int:
    """Seed manifests + current versions; skip anything already present.

    Returns the number of manifests newly created.
    """
    created_at = now if now is not None else datetime.now(UTC)
    created = 0
    for manifest in _build_seeds(created_at):
        try:
            store.get_manifest(manifest.agent_id)
            continue
        except KeyError:
            pass
        store.create_manifest(manifest)
        store.add_version(
            manifest.agent_id,
            AgentVersion(
                version=manifest.version,
                model_id=_MODEL_ID,
                prompt_ref=_prompt_ref(manifest.agent_id),
                created_at=created_at,
                approved=True,
            ),
        )
        created += 1
    return created


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the agent registry.")
    parser.add_argument("--project", default="diligence-room")
    args = parser.parse_args(argv)

    from google.cloud import firestore

    client = firestore.Client(project=args.project)
    store = AgentRegistryStore(client)
    created = seed_registry(store)
    total = len(store.list_manifests())
    print(f"Seeded {created} new manifest(s); registry now holds {total} agent(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
