"""CMEK config tests (BUILD_PLAN D11-M3)."""

from __future__ import annotations

from pathlib import Path

import yaml

from compliance.cmek import load_keyring, verify_audit_log

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "infra" / "compliance_config"


class TestKmsConfig:
    def test_kms_us_yaml_shape(self) -> None:
        data = load_keyring(_CONFIG_DIR / "kms_us.yaml")
        assert data["keyring"] == "diligence-room-us"
        assert data["location"] == "us-central1"
        assert data["key"] == "deal-falcon-primary"
        assert data["rotation_days"] == 90

    def test_kms_eu_yaml_shape(self) -> None:
        data = load_keyring(_CONFIG_DIR / "kms_eu.yaml")
        assert data["keyring"] == "diligence-room-eu"
        assert data["location"] == "europe-west1"
        assert data["key"] == "deal-falcon-primary"
        assert data["rotation_days"] == 90

    def test_yaml_files_exist_and_parse(self) -> None:
        for name in ("kms_us.yaml", "kms_eu.yaml"):
            path = _CONFIG_DIR / name
            assert path.is_file()
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert isinstance(raw, dict)
            assert {"keyring", "location", "key", "rotation_days"} <= set(raw.keys())


class TestCmekVerifier:
    def test_accepts_canned_audit_entry(self) -> None:
        entries = [
            {"methodName": "google.cloud.kms.v1.KeyManagementService.CreateCryptoKey"},
            {"methodName": "google.firestore.v1.Firestore.UpdateDatabase"},
        ]
        assert verify_audit_log(entries) is True

    def test_rejects_missing_entries(self) -> None:
        assert verify_audit_log([]) is False
        assert verify_audit_log([{"methodName": "storage.objects.get"}]) is False
