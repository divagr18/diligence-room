"""Diligence Room — GCP bootstrap (BUILD_PLAN module D1-M1).

Idempotent project bootstrap:

1. project verify/create
2. billing account link
3. API enablement (Vertex AI/Agent Engine, Model Armor, Firestore, Cloud Run,
   Pub/Sub, Document AI, DLP, Cloud Trace, KMS)
4. Agent Engine staging bucket (us-central1)
5. Budget alerts at $85 / $136 / $170 (50% / 80% / 100% of the hard cap)

Everything shells out to ``gcloud`` so the script has zero third-party
dependencies and every step is verifiable with plain gcloud commands.

Usage:
    uv run python infra/bootstrap_gcp.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence

PROJECT_ID = "diligence-room"
BILLING_ACCOUNT = "012D4F-261885-E006CE"
REGION = "us-central1"
STAGING_BUCKET = f"{PROJECT_ID}-staging"
BUDGET_DISPLAY_NAME = f"{PROJECT_ID}-hard-cap"
# Hard cost cap is $170 USD (vision: $150 credits + $20). The billing account
# currency is INR, and GCP rejects budgets whose currency differs from the
# account's, so the cap is converted. The planning rate is deliberately BELOW
# the market rate (~95.5 INR/USD, 2026-08): this makes the 100% alert fire at
# or before the true USD cap is reached. Early alerts are the safe direction.
BUDGET_CAP_USD = 170
USD_TO_BILLING_CURRENCY_RATE = 94.0
BUDGET_AMOUNT_UNITS = int(BUDGET_CAP_USD * USD_TO_BILLING_CURRENCY_RATE)
BUDGET_THRESHOLDS: tuple[float, ...] = (0.5, 0.8, 1.0)

# Canonical API services required by the stack (vision §23 / BUILD_PLAN D1-M1).
# Agent Engine has no dedicated service id — it is served by aiplatform.
REQUIRED_SERVICES: tuple[str, ...] = (
    "aiplatform.googleapis.com",
    # Cloud Run --source deploys build with Cloud Build and push to Artifact
    # Registry; without both enabled the first deploy fails SERVICE_DISABLED.
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudtrace.googleapis.com",
    "dlp.googleapis.com",
    "documentai.googleapis.com",
    "firestore.googleapis.com",
    "modelarmor.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
)
# Future-proofing: enable a dedicated Agent Engine service if/when it appears;
# unknown-service errors are tolerated here.
BEST_EFFORT_SERVICES: tuple[str, ...] = ("agentengine.googleapis.com",)


def _gcloud_executable() -> str:
    """Resolve the gcloud launcher (on Windows it is a .cmd shim)."""
    exe = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if exe is None:
        raise RuntimeError("gcloud not found on PATH")
    return exe


def run_gcloud(
    args: Sequence[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a gcloud command with stdout captured as text."""
    cmd = ["gcloud", *args, "--quiet"] if "--quiet" not in args else ["gcloud", *args]
    cmd[0] = _gcloud_executable()
    return subprocess.run(  # noqa: S603 — gcloud is a fixed, trusted binary
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


# --------------------------------------------------------------------------
# Pure planning helpers (unit-tested in tests/test_bootstrap_plan.py)
# --------------------------------------------------------------------------


def plan_service_enables(enabled: set[str], target: Sequence[str]) -> list[str]:
    """Return the services from *target* that are not yet enabled, in order."""
    return [svc for svc in target if svc not in enabled]


def build_budget_args(
    billing_account: str,
    display_name: str,
    amount_units: int,
    thresholds: Sequence[float],
) -> list[str]:
    """Build the ``gcloud billing budgets create`` argument list.

    ``amount_units`` is expressed in the billing account's own currency
    (no currency suffix — GCP rejects mismatched currencies).
    Thresholds are 1.0-based fractions (0.5 == 50% of the budget amount).
    """
    if amount_units <= 0:
        raise ValueError(f"budget amount must be positive, got {amount_units}")
    for threshold in thresholds:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"each threshold must be in (0, 1.0], got {threshold!r}")
    args: list[str] = [
        "billing",
        "budgets",
        "create",
        f"--billing-account={billing_account}",
        f"--display-name={display_name}",
        f"--budget-amount={amount_units}",
    ]
    for threshold in thresholds:
        args.append(f"--threshold-rule=percent={threshold}")
    return args


# --------------------------------------------------------------------------
# Imperative steps
# --------------------------------------------------------------------------


def project_exists(project_id: str) -> bool:
    result = run_gcloud(
        ["projects", "describe", project_id],
        check=False,
    )
    return result.returncode == 0


def ensure_project(project_id: str) -> None:
    step(f"Project: {project_id}")
    if project_exists(project_id):
        print("    already exists - ok")
        return
    result = run_gcloud(
        [
            "projects",
            "create",
            project_id,
            # GCP constraint: display name <= 30 chars, no special characters.
            "--name=Diligence Room",
        ]
    )
    last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else project_id
    print(f"    created: {last_line}")


def billing_linked(project_id: str) -> bool:
    result = run_gcloud(
        [
            "billing",
            "projects",
            "describe",
            project_id,
            "--format=value(billingAccountName)",
        ],
        check=False,
    )
    return bool(result.stdout.strip())


def ensure_billing_link(project_id: str, billing_account: str) -> None:
    step(f"Billing link: {billing_account}")
    if billing_linked(project_id):
        print("    already linked - ok")
        return
    run_gcloud(
        [
            "billing",
            "projects",
            "link",
            project_id,
            f"--billing-account={billing_account}",
        ]
    )
    print("    linked")


def enabled_services(project_id: str) -> set[str]:
    result = run_gcloud(
        [
            "services",
            "list",
            "--enabled",
            f"--project={project_id}",
            "--format=value(config.name)",
        ]
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def ensure_services(project_id: str) -> None:
    step("API enablement")
    current = enabled_services(project_id)
    to_enable = plan_service_enables(current, list(REQUIRED_SERVICES))
    if to_enable:
        print(f"    enabling: {', '.join(to_enable)}")
        run_gcloud(["services", "enable", *to_enable, f"--project={project_id}"])
    else:
        print("    all required services already enabled - ok")
    for svc in BEST_EFFORT_SERVICES:
        result = run_gcloud(
            ["services", "enable", svc, f"--project={project_id}"],
            check=False,
        )
        if result.returncode == 0:
            print(f"    best-effort enabled {svc}")
        else:
            print(
                f"    note: {svc} not available (Agent Engine is served by "
                "aiplatform.googleapis.com) - skipped"
            )


def bucket_exists(bucket: str) -> bool:
    # `gcloud storage buckets describe` needs no project flag for a full gs:// URL.
    result = run_gcloud(
        ["storage", "buckets", "describe", f"gs://{bucket}"],
        check=False,
    )
    return result.returncode == 0


def ensure_staging_bucket(project_id: str, bucket: str, location: str) -> None:
    step(f"Agent Engine staging bucket: gs://{bucket} ({location})")
    if bucket_exists(bucket):
        print("    already exists - ok")
        return
    run_gcloud(
        [
            "storage",
            "buckets",
            "create",
            f"gs://{bucket}",
            f"--project={project_id}",
            f"--location={location}",
            "--uniform-bucket-level-access",
        ]
    )
    print("    created")


def project_number(project_id: str) -> str:
    result = run_gcloud(["projects", "describe", project_id, "--format=value(projectNumber)"])
    number = result.stdout.strip()
    if not number:
        raise RuntimeError(f"could not resolve project number for {project_id}")
    return number


def find_budget(billing_account: str, display_name: str, project_id: str) -> str | None:
    """Return the full resource name of a budget with the given display name."""
    result = run_gcloud(
        [
            "billing",
            "budgets",
            "list",
            f"--billing-account={billing_account}",
            f"--project={project_id}",
            "--format=value(name)",
        ]
    )
    for name in result.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        detail = run_gcloud(
            [
                "billing",
                "budgets",
                "describe",
                name,
                f"--project={project_id}",
                "--format=value(displayName)",
            ],
            check=False,
        )
        if detail.stdout.strip() == display_name:
            return name
    return None


def describe_budget(budget_name: str, project_id: str) -> dict[str, object] | None:
    result = run_gcloud(
        [
            "billing",
            "budgets",
            "describe",
            budget_name,
            f"--project={project_id}",
            "--format=json",
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


def budget_matches_desired(
    budget: dict[str, object],
    display_name: str,
    amount_units: int,
    project_number: str,
    thresholds: Sequence[float],
) -> bool:
    amount = budget.get("amount")
    specified = amount.get("specifiedAmount") if isinstance(amount, dict) else None
    units = int(specified.get("units", "0")) if isinstance(specified, dict) else 0
    if units != amount_units:
        return False
    if budget.get("displayName") != display_name:
        return False
    budget_filter = budget.get("budgetFilter")
    projects = budget_filter.get("projects", []) if isinstance(budget_filter, dict) else []
    if f"projects/{project_number}" not in projects:
        return False
    rules = budget.get("thresholdRules")
    actual = sorted(
        float(rule.get("thresholdPercent", -1))
        for rule in (rules if isinstance(rules, list) else [])
        if isinstance(rule, dict)
    )
    return actual == sorted(thresholds)


def ensure_budget(
    billing_account: str,
    project_id: str,
    display_name: str,
    amount_units: int,
    thresholds: Sequence[float],
) -> None:
    step(
        f"Budget: {display_name} @ {amount_units} (account currency), thresholds {list(thresholds)}"
    )
    number = project_number(project_id)
    existing = find_budget(billing_account, display_name, project_id)
    if existing is None:
        base = build_budget_args(billing_account, display_name, amount_units, thresholds)
        run_gcloud([*base, f"--filter-projects=projects/{number}", f"--project={project_id}"])
        print("    created")
        return

    current = describe_budget(existing, project_id)
    if current is not None and budget_matches_desired(
        current, display_name, amount_units, number, thresholds
    ):
        print(f"    already correct ({existing}) - ok")
        return

    current_rules = current.get("thresholdRules") if current else None
    thresholds_drifted = current is None or not budget_thresholds_match(current_rules, thresholds)
    if thresholds_drifted:
        # gcloud `budgets update --threshold-rules-from-file` is broken, so a
        # threshold change is applied as delete + recreate.
        print("    thresholds drifted - recreating budget")
        run_gcloud(["billing", "budgets", "delete", existing, f"--project={project_id}"])
        base = build_budget_args(billing_account, display_name, amount_units, thresholds)
        run_gcloud([*base, f"--filter-projects=projects/{number}", f"--project={project_id}"])
        print("    recreated")
        return

    update_args = [
        "billing",
        "budgets",
        "update",
        existing,
        f"--display-name={display_name}",
        f"--budget-amount={amount_units}",
        f"--filter-projects=projects/{number}",
        f"--project={project_id}",
    ]
    run_gcloud(update_args)
    print(f"    updated (existing budget {existing})")


def budget_thresholds_match(rules: object, thresholds: Sequence[float]) -> bool:
    actual = sorted(
        float(rule.get("thresholdPercent", -1))
        for rule in (rules if isinstance(rules, list) else [])
        if isinstance(rule, dict)
    )
    return actual == sorted(thresholds)


def check_adc() -> None:
    step("Application Default Credentials check")
    result = run_gcloud(
        ["auth", "application-default", "print-access-token"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        print("    ADC present - ok")
    else:
        print(
            "    ADC MISSING - run `gcloud auth application-default login` before deploying agents"
        )


def verify(project_id: str, billing_account: str, display_name: str) -> None:
    step("Verification")
    enabled = sorted(enabled_services(project_id))
    required = set(REQUIRED_SERVICES)
    missing = required - set(enabled)
    print(f"    enabled services: {len(enabled)}")
    if missing:
        raise RuntimeError(f"services still disabled: {sorted(missing)}")
    budget = find_budget(billing_account, display_name, project_id)
    if budget is None:
        raise RuntimeError(f"budget {display_name!r} not found after bootstrap")
    print(f"    budget present: {budget}")
    if billing_linked(project_id):
        print("    billing linked - ok")
    else:
        raise RuntimeError("billing not linked after bootstrap")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=PROJECT_ID)
    parser.add_argument("--billing-account", default=BILLING_ACCOUNT)
    args = parser.parse_args(argv)

    # Derive per-project names: the module constants are bound to the default
    # project id, but bucket names are globally unique and budget display names
    # are per-project, so a --project override must carry through to both or the
    # bootstrap silently adopts another project's staging bucket.
    staging_bucket = f"{args.project}-staging"
    budget_display_name = f"{args.project}-hard-cap"

    ensure_project(args.project)
    ensure_billing_link(args.project, args.billing_account)
    ensure_services(args.project)
    ensure_staging_bucket(args.project, staging_bucket, REGION)
    ensure_budget(
        args.billing_account,
        args.project,
        budget_display_name,
        BUDGET_AMOUNT_UNITS,
        BUDGET_THRESHOLDS,
    )
    check_adc()
    verify(args.project, args.billing_account, budget_display_name)

    step(f"Setting default project to {args.project}")
    run_gcloud(["config", "set", "project", args.project])

    print(f"\nBootstrap complete for project {args.project!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
