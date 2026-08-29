# Segment 4 terminal pane: the two Gemini Enterprise Agent Platform components
# the Fortified Enterprise Fleet track names by hand — Agent Registry and
# Memory Bank — shown running against the live project.
#
# Paired with the deployed dashboard's Registry view in the right pane, which
# carries the versions, approval state and eval scores our own store adds on top.

$ErrorActionPreference = "Continue"
$P = "diligence-room-live"
$LOCATION = "us-central1"

Clear-Host
Write-Host "Gemini Enterprise Agent Platform - the fleet, catalogued" -ForegroundColor Green

Write-Host ""
Write-Host "> gcloud agent-registry agents list --location $LOCATION" -ForegroundColor Cyan
# Filter out "Workspace Agent", a platform default that is not ours.
gcloud agent-registry agents list --location $LOCATION --project $P `
    --filter="displayName!='Workspace Agent'" --format="table(displayName)"

Start-Sleep 1

Write-Host ""
Write-Host "> memory bank: what do we already know about this buyer?" -ForegroundColor Cyan
# -W ignore: the ADK prints a deprecation FutureWarning that would otherwise
# land on screen in the middle of the take.
uv run python -W ignore scripts/video/recall_demo.py
