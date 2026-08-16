# Decision: Gemma Sentinel Serving (Day 4, D4-M4)

Date: 2026-08-16 · Status: ACCEPTED · Supersedes: BUILD_PLAN D4-M4 default ("Vertex endpoint or containerized on Cloud Run")

## Context

BUILD_PLAN D4-M4 and vision §7.6.1 require a Gemma ingestion sentinel — a
genuine two-model pipeline (cheap Gemma first pass; Gemini 3.5 Flash only for
cleared documents). The plan's primary serving path was a Vertex Model Garden
endpoint (GPU-backed); its documented red path: "Gemma serving friction →
hosted Gemma API call instead of endpoint; bonus still earned, decision
documented."

## Decision

Serve the sentinel via the **hosted Gemini Developer API (AI Studio path)**
using the `google-genai` SDK, model **`gemma-4-26b-a4b-it`** (fallback
`gemma-4-31b-it`), selected explicitly in code:

```python
from google import genai

client = genai.Client(vertexai=False, api_key=...)  # non-Vertex path
```

Guarded by `DILIGENCE_GEMMA_ENABLED=1` + `GOOGLE_API_KEY`; offline tests use
`FakeSentinel` behind the `SentinelModel` protocol.

## Rationale

1. **Minimal cost (user constraint).** Model Garden endpoint ≈ $0.7–1/h GPU
   for a multi-hour window; hosted API ≈ $0 for this volume.
2. **Same bonus semantics.** Vision §7.6.1's claim is a genuine two-model
   pipeline visible in traces/cost model — hosting tier does not change the
   pipeline shape, and BUILD_PLAN explicitly sanctions the hosted fallback.
3. **Lower operational risk** for a one-shot live evidence window.

## Model facts (verified 2026-08-16, sources below)

- The Gemini Developer API dropped ALL Gemma 3 ids (`gemma-3-27b-it` etc.)
  on ~2026-04-30; Gemma 3/3n are "legacy" in the Gemma docs.
- Current supported lineup (official page, updated 2026-07-02):
  `gemma-4-31b-it`, `gemma-4-26b-a4b-it` (Gemma 4, released 2026-04-02).
- Gemma 4 supports system_instruction, function calling, thinking toggle,
  image input. Structured output (`response_schema`) is NOT documented for
  Gemma → the sentinel uses strict-JSON-in-text prompting with defensive
  parsing and defined degrade behavior.
- Free-tier limits ≈ 30 RPM / 16K TPM / 1.5K RPD (AI Studio, July 2026) —
  ample for the mixed-bundle window.
- `gemma-4-26b-a4b-it` chosen as primary: mixture-of-experts with ~4B active
  parameters — cheapest + fastest of the two; 31B retained as fallback
  constant in `ingestion/sentinel.py` (single-place swap).

## Credential deviation (recorded)

Repository security posture: "No service-account keys; ADC / workload
identity only." The hosted path authenticates with an **AI Studio API key**
(`GOOGLE_API_KEY`, environment-only, never committed, gitleaks-scanned).
This is a different credential class from a service-account key; the
deviation is recorded here alongside the standalone-billing-account
deviations in README.md and revisited if the project moves under an org.

## Sources

- ai.google.dev — "Run Gemma with the Gemini API" (updated 2026-07-02):
  supported Gemma 4 ids + capabilities.
- ai.google.dev Gemini API changelog — Gemma 4 release entry (2026-04-02).
- Google AI Developers Forum — Gemma 3 discontinuation (2026-04-16), token
  limit change threads (2026-07).
- googleapis/python-genai (google-genai SDK) — client construction,
  vertexai=False path.
