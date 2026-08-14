"""Tests for infra.guardrails.merge_audit_configs — the IAM policy merge.

DANGER CONTEXT: `gcloud projects set-iam-policy` computes its updateMask from
the policy file's top-level keys, and `bindings` is ALWAYS in the mask. A merge
helper that drops or mutates `bindings` would wipe all project access. These
tests pin the safety properties of the merge before the script ever touches a
live policy.
"""

from __future__ import annotations

import copy

import pytest

from infra.guardrails import DESIRED_LOG_TYPES, merge_audit_configs

BASE_POLICY: dict[str, object] = {
    "bindings": [
        {
            "role": "roles/owner",
            "members": ["user:keshav.agr2007@gmail.com"],
        },
        {
            "role": "roles/editor",
            "members": ["serviceAccount:123@cloudbuild.gserviceaccount.com"],
        },
    ],
    "etag": "BwXqwxkr40M=",
    "version": 1,
}


class TestMergeAuditConfigs:
    def test_bindings_untouched(self) -> None:
        result = merge_audit_configs(copy.deepcopy(BASE_POLICY), ["storage.googleapis.com"])
        assert result["bindings"] == BASE_POLICY["bindings"]

    def test_etag_and_version_untouched(self) -> None:
        result = merge_audit_configs(copy.deepcopy(BASE_POLICY), ["storage.googleapis.com"])
        assert result["etag"] == "BwXqwxkr40M="
        assert result["version"] == 1

    def test_adds_desired_log_types_for_target_service(self) -> None:
        result = merge_audit_configs(copy.deepcopy(BASE_POLICY), ["storage.googleapis.com"])
        configs = result["auditConfigs"]
        assert isinstance(configs, list)
        storage = next(c for c in configs if c["service"] == "storage.googleapis.com")
        log_types = {entry["logType"] for entry in storage["auditLogConfigs"]}
        assert log_types == set(DESIRED_LOG_TYPES)

    def test_preserves_audit_configs_of_other_services(self) -> None:
        policy = copy.deepcopy(BASE_POLICY)
        policy["auditConfigs"] = [
            {
                "service": "bigquery.googleapis.com",
                "auditLogConfigs": [{"logType": "DATA_READ"}],
            }
        ]
        result = merge_audit_configs(policy, ["storage.googleapis.com"])
        configs = result["auditConfigs"]
        assert isinstance(configs, list)
        services = {c["service"] for c in configs if isinstance(c, dict)}
        assert services == {"bigquery.googleapis.com", "storage.googleapis.com"}

    def test_idempotent(self) -> None:
        targets = ["datastore.googleapis.com", "storage.googleapis.com"]
        once = merge_audit_configs(copy.deepcopy(BASE_POLICY), targets)
        twice = merge_audit_configs(copy.deepcopy(once), targets)
        assert once == twice

    def test_replaces_partial_existing_config_for_target(self) -> None:
        policy = copy.deepcopy(BASE_POLICY)
        policy["auditConfigs"] = [
            {
                "service": "storage.googleapis.com",
                "auditLogConfigs": [{"logType": "DATA_READ"}],
            }
        ]
        result = merge_audit_configs(policy, ["storage.googleapis.com"])
        configs = result["auditConfigs"]
        assert isinstance(configs, list)
        storage = next(
            c for c in configs if isinstance(c, dict) and c["service"] == "storage.googleapis.com"
        )
        entries = storage["auditLogConfigs"]
        assert isinstance(entries, list)
        log_types = {e["logType"] for e in entries if isinstance(e, dict)}
        assert log_types == set(DESIRED_LOG_TYPES)

    def test_rejects_empty_targets(self) -> None:
        with pytest.raises(ValueError, match="target"):
            merge_audit_configs(copy.deepcopy(BASE_POLICY), [])
