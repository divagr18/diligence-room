"""Publish the fleet into the Gemini Enterprise Agent Platform Agent Registry.

The track asks for agents to be "cataloged for cross-department use", and the
platform's own Agent Registry is the sanctioned place to do that. The consumer
side (``gcloud agent-registry agents``) is read-only — describe, list, search —
so registration goes through ``services create``, which Agent Registry then
projects back as a discoverable read-only Agent.

Division of labour, deliberately not duplicated:

* **Agent Registry (this module)** is the org-wide catalogue: what agents exist,
  what they do, where to reach them.
* **``registry/`` (Firestore)** stays the lifecycle layer: versions, approval
  state, eval scores and rollback targets. The platform registry does not model
  a rollback target, and that is the thing the demo actually exercises.

Cards come from ``registry.agent_card``, which projects them from the Firestore
manifests, so the two registries cannot drift.

One Windows detail worth knowing: the card is passed as a *file path*, not
inline JSON. ``gcloud`` is a ``.CMD`` shim here, so cmd.exe re-parses the ``&``
in "M&A" and truncates the payload; flags accept a ``.json`` path instead.

Usage:
    uv run python infra/agent_registry.py --dry-run
    uv run python infra/agent_registry.py --project diligence-room-live --confirm-live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from infra.bootstrap_gcp import run_gcloud, step
from registry.agent_card import (
    DEFAULT_GATEWAY_URL,
    build_agent_card,
    display_name,
    service_id,
)
from registry.models import AgentManifest

PROJECT_ID: Final[str] = os.environ.get("DILIGENCE_PROJECT_ID", "diligence-room")
LOCATION: Final[str] = "us-central1"
GATEWAY_URL: Final[str] = os.environ.get("DILIGENCE_GATEWAY_URL", DEFAULT_GATEWAY_URL)

_SPEC_TYPE: Final[str] = "a2a-agent-card"


def write_cards(
    manifests: Sequence[AgentManifest],
    card_dir: Path,
    gateway_url: str = GATEWAY_URL,
) -> dict[str, Path]:
    """Write one agent card per manifest; return agent_id -> path."""
    card_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for manifest in manifests:
        path = card_dir / f"{service_id(manifest)}.json"
        path.write_text(
            json.dumps(build_agent_card(manifest, gateway_url), indent=2), encoding="utf-8"
        )
        paths[manifest.agent_id] = path
    return paths


def plan_registration(
    manifests: Sequence[AgentManifest],
    card_paths: Mapping[str, Path],
    project: str = PROJECT_ID,
    location: str = LOCATION,
) -> list[list[str]]:
    """Return the ordered gcloud argv plan, one `services create` per agent.

    Pure: builds arguments and touches nothing, so the shape is unit-testable
    without gcloud, matching `infra.data_room.plan_data_room`.
    """
    steps: list[list[str]] = []
    for manifest in manifests:
        steps.append(
            [
                "agent-registry",
                "services",
                "create",
                service_id(manifest),
                f"--location={location}",
                f"--project={project}",
                f"--display-name={display_name(manifest)}",
                f"--description=Diligence Room {manifest.workstream.value} specialist",
                f"--agent-spec-type={_SPEC_TYPE}",
                f"--agent-spec-content={card_paths[manifest.agent_id]}",
            ]
        )
    return steps


def main(argv: Sequence[str] | None = None) -> int:
    """Parse argv and either print the plan or publish the fleet."""
    parser = argparse.ArgumentParser(description="Publish the fleet into Agent Registry.")
    parser.add_argument("--project", default=PROJECT_ID)
    parser.add_argument("--location", default=LOCATION)
    parser.add_argument("--gateway-url", default=GATEWAY_URL)
    parser.add_argument("--card-dir", default="")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the full gcloud command plan and exit without executing.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        default=False,
        help="Required together with the absence of --dry-run to execute live.",
    )
    args = parser.parse_args(argv)

    from memory.db import make_client
    from registry.store import AgentRegistryStore

    store = AgentRegistryStore(make_client(args.project))
    manifests = sorted(store.list_manifests(), key=lambda m: m.agent_id)
    if not manifests:
        sys.exit("Refused: the Firestore registry is empty; run registry/seed.py first.")

    card_dir = Path(args.card_dir) if args.card_dir else Path(tempfile.gettempdir()) / "dr-cards"
    card_paths = write_cards(manifests, card_dir, args.gateway_url)
    steps = plan_registration(manifests, card_paths, args.project, args.location)

    if args.dry_run:
        for step_argv in steps:
            print(" ".join(step_argv))
        return 0

    if not args.confirm_live:
        print("WRITE-ONLY: this script refuses to publish without --confirm-live.")
        sys.exit("Refused: pass --confirm-live to acknowledge a live registration.")

    step(f"Publishing {len(manifests)} agents into Agent Registry ({args.location})")
    failures = 0
    for manifest, step_argv in zip(manifests, steps, strict=True):
        result = run_gcloud(step_argv, check=False)
        stderr = (result.stderr or "").strip()
        if result.returncode == 0:
            print(f"    registered {service_id(manifest)} v{manifest.version}")
        elif "ALREADY_EXISTS" in stderr or "already exists" in stderr.lower():
            print(f"    {service_id(manifest)} already registered - ok")
        else:
            failures += 1
            print(f"    FAILED {service_id(manifest)}: {stderr[-300:]}")

    if failures:
        print(f"\n{failures} of {len(manifests)} registrations failed.")
        return 1
    print(f"\nAgent Registry holds the {len(manifests)}-agent fleet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
