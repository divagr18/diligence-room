# Beat 7 terminal pane: the human-approval gate, then Google Cloud deployment
# proof. Runs beside the Cloud Console in the left pane.
#
# Uses Invoke-RestMethod rather than curl.exe: passing a JSON body through
# curl.exe under PowerShell strips the quotes and the API rejects it.

$ErrorActionPreference = "Continue"
$D = "https://diligence-room-dashboard-378831539922.asia-south1.run.app"
$F = "f4c993d48cda"
$P = "diligence-room-live"

Clear-Host
Write-Host "Human approval gate + Google Cloud deployment proof" -ForegroundColor Green

Write-Host ""
Write-Host "> negotiation agent drafts the seller request" -ForegroundColor Cyan
$draft = Invoke-RestMethod -Method Post -Uri "$D/api/negotiation/drafts" `
    -ContentType "application/json" `
    -Body (@{ finding_id = $F; kind = "seller_request" } | ConvertTo-Json)
Write-Host ("  draft_id : {0}" -f $draft.draft_id)
Write-Host ("  state    : {0}" -f $draft.state)
Write-Host ("  approved : {0}" -f $(if ($draft.approved_by) { $draft.approved_by } else { "nobody yet" }))
Write-Host "  -> it will NOT send. A human has to approve." -ForegroundColor Yellow
Start-Sleep 4

Write-Host ""
Write-Host "> deal lead approves" -ForegroundColor Cyan
$ok = Invoke-RestMethod -Method Post -Uri "$D/api/negotiation/$($draft.draft_id)/approve" `
    -ContentType "application/json" `
    -Body (@{ approver = "divyansh@deal-falcon" } | ConvertTo-Json)
Write-Host ("  state    : {0}" -f $ok.state)
Write-Host ("  approved : {0}" -f $ok.approved_by)
Start-Sleep 4

Write-Host ""
Write-Host "> gcloud run services list --project $P" -ForegroundColor Cyan
gcloud run services list --project $P --format="table(metadata.name,region,status.url)"
Start-Sleep 2

Write-Host ""
Write-Host "Vertex AI Agent Engine:" -ForegroundColor Green
Write-Host "  projects/378831539922/locations/us-central1/reasoningEngines/7141202128323739648"
