# Verified Model IDs (D1-M6)

Recorded 2026-08-15 per BUILD_PLAN module D1-M6 ("verify exact model ID — record it").

| Purpose | Model ID | Status | Source |
|---|---|---|---|
| All workstream agents + hello agent | `gemini-3.5-flash` | GA on Vertex AI / Gemini Enterprise Agent Platform since 2026-05-19; retirement ≥ 2027-05-19 | Gemini Enterprise Agent Platform model docs (retrieved 2026-08-15) |
| Ingestion sentinel (Day 4) | `gemma-4-26b-a4b-it` (fallback `gemma-4-31b-it`) | Hosted on the Gemini Developer API (AI Studio path); Gemma 4 lineup GA since 2026-04-02 — ALL Gemma 3 ids removed ~2026-04-30 | ai.google.dev "Run Gemma with the Gemini API" (updated 2026-07-02, retrieved 2026-08-16); decision in `docs/decisions/gemma-serving.md` |

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

**Verified live 2026-08-16 (project diligence-room):**

- `gemini-3.5-flash` is served ONLY from the **`global`** location. Regional
  endpoints (us-central1, us-east1, us-east5, europe-west1, us-west1) returned
  404 in a live probe; `global` returned 200. All runtimes therefore set
  `GOOGLE_CLOUD_LOCATION=global` for the model client.
- Agent Engine resources are created in `us-central1` (canonical supported
  region); the remote ADK runtime receives the model location via
  `env_vars={"GOOGLE_GENAI_USE_VERTEXAI": "TRUE", "GOOGLE_CLOUD_LOCATION": "global"}`.
  Note: `GOOGLE_CLOUD_PROJECT` is RESERVED by Agent Engine env injection and
  must not be set manually.
- Local smoke `[smoke] PASS`; deployed agent
  `projects/910285417505/locations/us-central1/reasoningEngines/5096132490892935168`
  answered the async invoke with the echo marker: PASS.
