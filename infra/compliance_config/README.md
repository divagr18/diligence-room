# Compliance Config — CMEK / VPC-SC / DLP (BUILD_PLAN D11)

Guarded config-as-code for compliance controls. Offline tests assert YAML shape;
live application is `gcloud` guarded behind `--confirm-live` (refuses under
`FIRESTORE_EMULATOR_HOST` and without explicit flag). No live call is made
in CI.

## CMEK (D11-M3) — KMS keyrings per region

Applies Customer-Managed Encryption Keys to Firestore + Storage.

```bash
# US keyring
gcloud kms keyrings create diligence-room-us --location us-central1 --project diligence-room
gcloud kms keys create deal-falcon-primary --keyring diligence-room-us --location us-central1 --purpose encryption --rotation-period 90d

# EU keyring
gcloud kms keyrings create diligence-room-eu --location europe-west1 --project diligence-room
gcloud kms keys create deal-falcon-primary --keyring diligence-room-eu --location europe-west1 --purpose encryption --rotation-period 90d

# Firestore CMEK (per-database)
gcloud firestore databases update --project diligence-room --kms-key-name projects/diligence-room/locations/us-central1/keyRings/diligence-room-us/cryptoKeys/deal-falcon-primary

# Storage CMEK (per-bucket)
gsutil kms encryption -k projects/diligence-room/locations/us-central1/keyRings/diligence-room-us/cryptoKeys/deal-falcon-primary gs://diligence-room-dataroom-deal-falcon-us
gsutil kms encryption -k projects/diligence-room/locations/europe-west1/keyRings/diligence-room-eu/cryptoKeys/deal-falcon-primary gs://diligence-room-dataroom-deal-falcon-eu
```

Verification reads Cloud Audit Logs for `CreateCryptoKey` / `UpdateDatabase` entries
(`compliance.cmek.verify_audit_log`).

## VPC-SC (D11-M8) — Service perimeter

Perimeter `diligence-room-perimeter` around Storage, Firestore, Vertex AI / Agent Engine.

```bash
gcloud access-context-manager perimeters create diligence-room-perimeter \
  --title "Diligence Room perimeter" \
  --resources projects/diligence-room \
  --restricted-services storage.googleapis.com,firestore.googleapis.com,aiplatform.googleapis.com \
  --egress-policies egress-rules.yaml
# egress-rules.yaml allows Cloud Trace export (cloudtrace.googleapis.com)
```

Violation test: a `storage.objects.get` from outside the perimeter is denied
(`PERMISSION_DENIED` code 7) and `compliance.vpcsc.check_violation` detects it.

## DLP (D11-M9) — HR-path inspection template

Template `deal-falcon-hr-inspect` for EMAIL/PHONE/SSN.

```bash
gcloud dlp inspect-templates create --project diligence-room \
  --display-name "Deal Falcon HR PII inspection" \
  --inspect-config-file infra/compliance_config/dlp_inspect_template.yaml
# Trigger: heavy_pii (3+ PII spans) OR hr_roster doc_type
# Action: redact/tokenize before agent context ([EMAIL]/[SSN]/[PHONE])
```

All `gcloud` paths refuse without `--confirm-live` and under `FIRESTORE_EMULATOR_HOST`.
