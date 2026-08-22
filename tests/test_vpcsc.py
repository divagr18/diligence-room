"""VPC-SC config tests (BUILD_PLAN D11-M8)."""

from __future__ import annotations

from pathlib import Path

import yaml

from compliance.vpcsc import check_violation, perimeter_from_yaml

_CONFIG = Path(__file__).resolve().parent.parent / "infra" / "compliance_config" / "vpc_sc.yaml"


class TestVpcScConfig:
    def test_yaml_shape(self) -> None:
        data = perimeter_from_yaml(_CONFIG)
        assert data["perimeter"] == "diligence-room-perimeter"
        assert "projects/diligence-room" in data["resources"]  # type: ignore[operator]

    def test_required_services_present(self) -> None:
        data = perimeter_from_yaml(_CONFIG)
        services = data["restricted_services"]
        assert isinstance(services, list)
        assert "storage.googleapis.com" in services
        assert "firestore.googleapis.com" in services
        assert "aiplatform.googleapis.com" in services

    def test_egress_rule_present(self) -> None:
        data = perimeter_from_yaml(_CONFIG)
        egress = data["egress_rules"]
        assert isinstance(egress, list)
        assert len(egress) >= 1

    def test_yaml_parses(self) -> None:
        raw = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert {"perimeter", "resources", "restricted_services", "egress_rules"} <= set(raw.keys())


class TestViolationCheck:
    def test_detects_denied_storage_get(self) -> None:
        entry: dict[str, object] = {
            "methodName": "google.storage.objects.get",
            "status": {"code": 7, "message": "PERMISSION_DENIED: VPC Service Controls"},
            "resourceName": (
                "projects/diligence-room/buckets/diligence-room-dataroom-deal-falcon-us"
            ),
        }
        assert check_violation(entry) is True

    def test_ignores_non_violation(self) -> None:
        assert (
            check_violation({"methodName": "google.firestore.v1.Firestore.ListDocuments"}) is False
        )
        assert (
            check_violation({"methodName": "google.storage.objects.get", "status": {"code": 0}})
            is False
        )
