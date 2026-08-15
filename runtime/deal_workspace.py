"""Project Falcon deal-workspace provisioning (BUILD_PLAN D2-M6).

Writes the deal document per docs/firestore_layout.md. The live wiring
(bucket -> ingestion -> agents) arrives on later days; this module owns the
Firestore workspace record and its idempotency guard.
"""

from __future__ import annotations

from datetime import datetime

from google.cloud import firestore

from runtime.deal import Deal

FALCON_DEAL_ID = "deal-falcon"


class DealAlreadyProvisionedError(RuntimeError):
    """Raised when a deal workspace document already exists."""


def build_falcon_deal(now: datetime) -> Deal:
    return Deal(
        deal_id=FALCON_DEAL_ID,
        name="Project Falcon",
        target="Acme Robotics",
        deal_type="Acquisition",
        regions=("US", "EU"),
        expected_window_days=90,
        policy_profile_id="falcon-standard-v1",
        created_at=now,
    )


def provision_deal(client: firestore.Client, deal: Deal) -> None:
    ref = client.collection("deals").document(deal.deal_id)
    if ref.get().exists:
        raise DealAlreadyProvisionedError(f"deal {deal.deal_id!r} already provisioned")
    ref.set(
        {
            "deal_id": deal.deal_id,
            "name": deal.name,
            "target": deal.target,
            "deal_type": deal.deal_type,
            "regions": list(deal.regions),
            "expected_window_days": deal.expected_window_days,
            "policy_profile_id": deal.policy_profile_id,
            "status": deal.status.value,
            "created_at": deal.created_at,
        }
    )
