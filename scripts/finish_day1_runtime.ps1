# Finishes Day-1 runtime verification once Application Default Credentials
# exist. Run AFTER: gcloud auth application-default login
#
# What it does:
#   1. local smoke test (scenario S4) — hello agent + echo tool via Vertex
#   2. deploys the agent to Vertex AI Agent Engine (~5-10 min)
#   3. async session invoke against the deployed agent (scenario S5)
#   4. captures CLI evidence under docs/evidence/
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==> 1/4 Local smoke test (S4)"
uv run python scripts/smoke_local_agent.py
if ($LASTEXITCODE -ne 0) { throw "local smoke failed" }

Write-Host "==> 2/4 Deploy to Agent Engine (5-10 minutes)"
uv run python infra/deploy/agent_engine.py deploy
if ($LASTEXITCODE -ne 0) { throw "deploy failed" }

Write-Host "==> 3/4 Async invoke (S5)"
uv run python infra/deploy/agent_engine.py invoke
if ($LASTEXITCODE -ne 0) { throw "async invoke failed" }

Write-Host "==> 4/4 Evidence"
& {
    "# Day 1 Agent Engine Evidence - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    ""
    "== Deployed agents =="
    (uv run python infra/deploy/agent_engine.py list 2>&1)
    ""
    "== Local state =="
    (Get-Content infra/deploy/agent_engine_state.json -Raw)
} | Out-File -FilePath "docs/evidence/d1-agent-engine.txt" -Encoding utf8

Write-Host "Day-1 runtime verification complete."
