# Verified Model IDs (D1-M6)

Recorded 2026-08-15 per BUILD_PLAN module D1-M6 ("verify exact model ID — record it").

| Purpose | Model ID | Status | Source |
|---|---|---|---|
| All workstream agents + hello agent | `gemini-3.5-flash` | GA on Vertex AI / Gemini Enterprise Agent Platform since 2026-05-19; retirement ≥ 2027-05-19 | Gemini Enterprise Agent Platform model docs (retrieved 2026-08-15) |

## Usage in code

- ADK agent definition: `model="gemini-3.5-flash"` (short name).
- Vertex-backed resolution requires environment:
  - `GOOGLE_GENAI_USE_VERTEXAI=TRUE`
  - `GOOGLE_CLOUD_PROJECT=diligence-room`
  - `GOOGLE_CLOUD_LOCATION=us-central1`
- Related Flash-tier models on Vertex at time of writing: `gemini-3.5-flash-lite`
  (GA 2026-07-21, cost fallback candidate if budget pressure appears).

## Submission text

Per vision Rev. 2 header: all submission text uses the model name as stated in
the hackathon requirements — "Gemini 3.5 Flash".

## Runtime verification

Local/remote invocation against Vertex is the final verification step
(`scripts/smoke_local_agent.py`, then `infra/deploy/agent_engine.py invoke`).
Status: **pending — requires Application Default Credentials**
(`gcloud auth application-default login`).
