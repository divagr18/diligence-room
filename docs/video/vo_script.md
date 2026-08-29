# Voiceover script

Timed to `docs/video/final/diligence-room-demo.mp4` (3:59.5).
These lines are burned into the picture, so you can read straight off it.
`docs/video/vo_script.srt` is the subtitle file if you want to re-time.

- **00:00:03** — Hi, I'm Divyansh Agrawal. This is Diligence Room, my entry for the Fortified Enterprise Fleet track.
- **00:00:10** — M&A due diligence is too complex for a single AI model.
- **00:00:17** — It needs a network of institutional agents that hook directly into enterprise infrastructure.
- **00:00:24** — Human teams take weeks to check thousands of deal files. I built a fleet of eight specialists that runs it end to end, workstream by workstream.
- **00:00:33** — Operational Utility is forty percent of the score, and it asks for real delegation, not a chat bot.
- **00:00:40** — This is the central Agent Registry, where a manager can discover, audit and manage eight cataloged specialists.
- **00:00:48** — Each owns one domain, with no shared raw access. Every agent is versioned and scored, so a bad build rolls back.
- **00:00:57** — Visible proof of live execution. Left is my terminal running the pipeline, right is the app on Cloud Run.
- **00:01:04** — Deals run for weeks, so the Agent Runtime handles long-running async execution.
- **00:01:09** — I'm replaying fourteen days of deal events into Firestore, the Memory Bank that holds context across sessions.
- **00:01:15** — Architectural Discipline, thirty percent, shows up at the boundary.
- **00:01:22** — Before any agent sees a file, Gemma 4 parses the text and Model Armor runs inline checks for prompt injection, tool poisoning and PII leaks.
- **00:01:32** — Google ADK orchestrates the agents, Gemini 3.5 Flash routes the work.
- **00:01:41** — To stop hallucinations, an agent cannot post a finding unless it quotes the exact source text.
- **00:01:51** — Pub/Sub carries the messages, Cloud Trace logs every step.
- **00:02:00** — Look at the dashboard. Forty-nine events processed, five findings flagged.
- **00:02:09** — The Legal agent spots a change-of-control clause in a vendor contract.
- **00:02:16** — To size the risk it needs revenue data, but under Agent Identity's zero-trust model it has no read access to the finance ledgers.
- **00:02:25** — So it sends a request to the Agent Gateway, which enforces policy and returns one safe aggregate.
- **00:02:34** — Eighteen point three percent of next year's revenue sits in this single contract.
- **00:02:41** — When four sub-agents flag the same vendor, the coordinator escalates to critical.
- **00:02:47** — A fortified fleet has to prove its security posture. Twenty red-team attacks: prompt injection, encoded payloads, data theft, illegal cross-agent writes.
- **00:02:56** — All twenty blocked, with zero false positives.
- **00:03:03** — Here an attacker fakes a deal approval, and Model Armor quarantined it before it reached an agent runtime.
- **00:03:11** — What happens when an agent fails? Legal runs 2.4. I publish 2.5.
- **00:03:19** — The shadow harness replays a golden set against it, and it fails: 2.5 missed the contract clause.
- **00:03:26** — I roll back to 2.4. The version reverts, but the Memory Bank partition stays intact.
- **00:03:35** — Finally, governance. The negotiation agent drafts the letter, but only I can send it, and that approval lands in Cloud Logging as a request against Cloud Run.
- **00:03:43** — Cloud Run in two regions, Firestore, Pub/Sub and Vertex AI Agent Engine, all live on Google Cloud.
- **00:03:51** — And the same call in Cloud Trace, span by span, so an auditor can follow any claim back to its source.
