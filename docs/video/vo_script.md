# Voiceover script

Timed to `docs/video/final/diligence-room-demo.mp4` (239.5s).
These lines are burned into the picture, so you can read straight off it.
`docs/video/vo_script.srt` is the subtitle file if you want to re-time.

## Segment 1 - from 0:00

- **0:00** - This is Diligence Room, running right now. Eight agents doing end-to-end due diligence on an M&A deal.
- **0:07** - On the left, you see the live pipeline. On the right, my app deployed on Cloud Run.
- **0:13** - It starts clean. Watch it fill up.

## Segment 2 - from 0:16

- **0:16** - I'm Divyansh Agrawal, and this is my entry for the Fortified Enterprise Fleet track.
- **0:23** - I am replaying fourteen days of a real deal at high speed.
- **0:28** - And look at that, there they are. Findings landing live as agents write them into Firestore.
- **0:35** - When one company buys another, human analysts must read every paper the seller hands over.
- **0:43** - Thousands of files, weeks of tedious work. Things slip through simply because nobody has time to cross-reference all of it.
- **0:52** - Here, Gemma 4 screens every file first, and Model Armor checks it for prompt injection.
- **1:00** - An agent cannot post a finding unless it quotes the exact clause it came from.
- **1:07** - Forty-nine events processed, five findings flagged, and it reproduces the exact same way every time.

## Segment 3 - from 1:14

- **1:14** - Here is what the fleet uncovered: one critical, two high, two medium.
- **1:21** - That critical alert did not come from a single agent. Legal, Finance, HR and IP each caught one piece of the puzzle.
- **1:31** - The target's largest customer can walk away the moment the deal closes, taking eighteen percent of next year's revenue with them.
- **1:41** - No single specialist had the authority to call that alone.

## Segment 4 - from 1:45

- **1:45** - I published this entire fleet into the Agent Registry on Gemini Enterprise Agent Platform, discoverable across the whole company.
- **1:54** - All eight specialists sit here with their versions, approval states and eval scores.
- **2:02** - And Memory Bank holds everything we know about this buyer across long-running sessions, retrieved right here in a fresh process.

## Segment 5 - from 2:11

- **2:11** - Let's look at how they work together. Legal finds a change-of-control clause in the contract.
- **2:19** - To size the financial risk it needs revenue data. But under Agent Identity, Legal cannot read financial ledgers.
- **2:27** - So it asks through the Agent Gateway. The gateway denies access by default unless a policy allows it.
- **2:35** - Finance returns one safe aggregate, eighteen percent, without exposing the underlying data to the model.
- **2:42** - Four workstreams pointing at the same vendor is what lets the coordinator escalate this to critical.

## Segment 6 - from 2:47

- **2:47** - I hit this fleet with twenty direct red-team attacks: prompt injections, encoded payloads, data theft, and cross-team writes.
- **2:56** - The system blocked all twenty with zero false positives.
- **3:01** - An attacker tried telling Finance the deal was already approved. Model Armor quarantined the payload before any agent runtime ever saw it.

## Segment 7 - from 3:11

- **3:11** - What happens when an agent fails in production? Legal runs on version 2.4. I publish version 2.5.
- **3:19** - Our shadow harness replays a golden test set against it and fails it: 2.5 missed that ownership clause.
- **3:26** - I roll back to 2.4 instantly. The version reverts, but the memory partition stays untouched. Logic and memory stay separate.

## Segment 8 - from 3:35

- **3:35** - Finally, human-in-the-loop control. The negotiation agent drafts the request to the seller, but it cannot send it until I approve it.
- **3:43** - That sign-off records as a POST in Cloud Logging.
- **3:48** - The fleet runs live on Agent Runtime and Cloud Run across two regions, backed by Firestore and Pub/Sub.
- **3:54** - And here is that same call in Cloud Trace, span by span, so an auditor can follow any claim back to the source.
