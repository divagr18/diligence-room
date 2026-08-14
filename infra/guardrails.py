"""Diligence Room - org-safety guardrails (BUILD_PLAN module D1-M2).

Applies project-level Cloud Audit Logs configuration (ADMIN_READ, DATA_READ,
DATA_WRITE for Firestore and Cloud Storage) and documents org-scope controls
that cannot be applied without a Cloud Organization node.

SAFETY: the IAM policy merge never drops ``bindings``/``etag`` — see
tests/test_guardrails_policy.py for the pinned invariants.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from infra.bootstrap_gcp import run_gcloud

DESIRED_LOG_TYPES: tuple[str, ...] = ("ADMIN_READ", "DATA_READ", "DATA_WRITE")
# Firestore audit logging is configured via the datastore service name.
AUDIT_SERVICES: tuple[str, ...] = (
    "datastore.googleapis.com",
    "storage.googleapis.com",
)


def merge_audit_configs(
    policy: dict[str, object], target_services: Sequence[str]
) -> dict[str, object]:
    """Merge desired audit configs into an IAM policy without touching bindings.

    Existing configs for non-target services are preserved; target services get
    the full DESIRED_LOG_TYPES set, replacing any partial prior configuration.
    """
    if not target_services:
        raise ValueError("at least one target service is required")
    result = copy.deepcopy(policy)
    existing = result.get("auditConfigs")
    configs: list[dict[str, object]] = []
    if isinstance(existing, list):
        configs = [
            config
            for config in existing
            if isinstance(config, dict) and config.get("service") not in target_services
        ]
    for service in target_services:
        configs.append(
            {
                "service": service,
                "auditLogConfigs": [{"logType": log_type} for log_type in DESIRED_LOG_TYPES],
            }
        )
    result["auditConfigs"] = configs
    return result


def current_policy(project_id: str) -> dict[str, object]:
    result = run_gcloud(["projects", "get-iam-policy", project_id, "--format=json"])
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


def audit_configs_equal(a: object, b: object) -> bool:
    def normalize(value: object) -> list[tuple[str, tuple[str, ...]]]:
        if not isinstance(value, list):
            return []
        out = []
        for config in value:
            if not isinstance(config, dict):
                continue
            entries = config.get("auditLogConfigs")
            log_types = tuple(
                entry.get("logType", "")
                for entry in (entries if isinstance(entries, list) else [])
                if isinstance(entry, dict)
            )
            service = str(config.get("service", ""))
            out.append((service, tuple(sorted(log_types))))
        return sorted(out)

    return normalize(a) == normalize(b)


def apply_audit_configs(project_id: str) -> None:
    print(f"==> Audit configs: {', '.join(AUDIT_SERVICES)} x {DESIRED_LOG_TYPES}")
    policy = current_policy(project_id)
    merged = merge_audit_configs(policy, list(AUDIT_SERVICES))
    if audit_configs_equal(policy.get("auditConfigs"), merged.get("auditConfigs")):
        print("    already applied - ok")
        return
    with tempfile.TemporaryDirectory() as tmp_dir:
        policy_path = Path(tmp_dir) / "policy.json"
        policy_path.write_text(json.dumps(merged), encoding="utf-8")
        result = run_gcloud(
            ["projects", "set-iam-policy", project_id, str(policy_path)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"set-iam-policy failed: {result.stderr}")
    print("    applied")


def organization_exists() -> bool:
    result = run_gcloud(["organizations", "list", "--format=value(name)"], check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def service_account_key_count(project_id: str) -> int:
    result = run_gcloud(
        [
            "iam",
            "service-accounts",
            "list",
            f"--project={project_id}",
            "--format=value(email)",
        ],
        check=False,
    )
    count = 0
    for email in result.stdout.splitlines():
        email = email.strip()
        if not email:
            continue
        keys = run_gcloud(
            [
                "iam",
                "service-accounts",
                "keys",
                "list",
                f"--iam-account={email}",
                "--format=value(name)",
                "--managed-by=user",
            ],
            check=False,
        )
        count += sum(1 for line in keys.stdout.splitlines() if line.strip())
    return count


def verify(project_id: str) -> None:
    print("==> Verification")
    policy = current_policy(project_id)
    configs = policy.get("auditConfigs")
    verified: set[str] = set()
    if isinstance(configs, list):
        for config in configs:
            if not isinstance(config, dict):
                continue
            service = config.get("service")
            if service not in AUDIT_SERVICES:
                continue
            entries = config.get("auditLogConfigs")
            log_types = {
                entry.get("logType")
                for entry in (entries if isinstance(entries, list) else [])
                if isinstance(entry, dict)
            }
            if set(DESIRED_LOG_TYPES) <= log_types:
                verified.add(str(service))
    missing = set(AUDIT_SERVICES) - verified
    if missing:
        raise RuntimeError(f"audit configs missing for: {sorted(missing)}")
    print(f"    audit configs verified for: {sorted(verified)}")
    keys = service_account_key_count(project_id)
    if keys:
        raise RuntimeError(
            f"{keys} user-managed service account key(s) exist - project policy is zero SA keys"
        )
    print("    service account keys: none - ok")
    if organization_exists():
        print("    organization node present - org policies could be added")
    else:
        print(
            "    no organization node - org-scope constraints unavailable "
            "(documented deviation, see README)"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply Diligence Room guardrails")
    parser.add_argument("--project", default="diligence-room")
    args = parser.parse_args(argv)
    apply_audit_configs(args.project)
    verify(args.project)
    print("\nGuardrails applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
