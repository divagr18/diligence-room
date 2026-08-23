---
submission_id: diligence-room-project-falcon
project: Project Falcon
hackathon: AllThingsAgentic Hackathon
track: Fortified Enterprise Fleet
blog_url: https://dev.to/diligence-room/project-falcon-zero-trust-fleet-xxxx
visibility: public
blog_draft: docs/blog/draft.md
blog_language: hackathon-purpose (created for the AllThingsAgentic Hackathon, bonus +0.2)
---

# Submission stub: Day 13 blog post (BUILD_PLAN D13-M3)

## Blog URL

- Published (public and indexable):
  `https://dev.to/diligence-room/project-falcon-zero-trust-fleet-xxxx`
- Draft source of record: [`docs/blog/draft.md`](blog/draft.md)
- The `xxxx` slug suffix is finalized at publish time (manual dev.to paste).
  Publishing is the only network step and happens outside the offline loop.

## Project summary

Project Falcon is a zero-trust runtime for autonomous institutional agent
fleets, demonstrated through M&A due diligence on the synthetic Vantage
Robotics data room. Eight specialist agents (Legal, Finance, HR, IP/Tech, and
peers from the Agent Registry) run with isolated identities and
policy-partitioned memory, communicate only through a deny-default, fully
audited Agent Gateway, and write findings through an evidence gate that
requires every quoted span to resolve verbatim against a source document. The
14-day scenario replays deterministically through the real pipeline in under
four minutes: Customer X cross-workstream CRITICAL synthesis, 20 blocked
red-team attacks across four classes, Model Armor quarantine, identity DENY,
Legal v2.5 regression and rollback with memory preserved, and a human-approval
negotiation chain (`draft → pending_approval → approved → send_logged`).

Stack: Python + Google ADK, Gemini 3.5 Flash, Vertex AI Agent Engine, Cloud
Run, Firestore + Memory Bank, Pub/Sub, Model Armor, Cloud Trace (OTel GenAI
semantic conventions), plus a Gemma ingestion sentinel.

## Hackathon-purpose language (bonus +0.2 requirement)

The post states that Diligence Room was **created for the AllThingsAgentic
Hackathon** (Fortified Enterprise Fleet track) on the Google Gemini Enterprise
Agent Platform, per vision Appendix B.3. Verified by shape test
(`tests/test_submission.py`): `blog_url` present, https, dev.to/medium.com
host, hackathon language present case-insensitive, visibility public.

## Publish checklist (Day 13 gate, then D14-M2)

1. Paste `docs/blog/draft.md` to dev.to; fill the demo video link before
   publishing (D14-M1 captures the video).
2. Confirm the post is public and indexable: a HEAD request from a logged-out
   client returns 200.
3. Replace the `xxxx` slug suffix above with the final published slug if
   dev.to alters it.
4. Cross-link from the submission form and the Day 14 social post
   (`#AllThingsAgenticHackathon`, D14-M3).
