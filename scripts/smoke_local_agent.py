"""Local smoke test for the hello agent via ADK InMemoryRunner (scenario S4).

Requires Application Default Credentials with access to project diligence-room
(gcloud auth application-default login). Exits non-zero unless the echo tool is
called and its marker returns in an agent response.
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "diligence-room")
# gemini-3.5-flash is served from the global location on Vertex (verified by
# regional probe; regional endpoints return 404 for this model).
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from agents.base_agent import root_agent  # noqa: E402

MARKER = "diligence-room-day1-smoke"


async def run() -> int:
    runner = InMemoryRunner(agent=root_agent, app_name=root_agent.name)
    session = await runner.session_service.create_session(
        app_name=root_agent.name, user_id="day1-smoke"
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Please call the echo tool with exactly: {MARKER}")],
    )
    saw_echo_call = False
    saw_marker = False
    async for event in runner.run_async(
        user_id="day1-smoke",
        session_id=session.id,
        new_message=message,
    ):
        content = event.content
        if content is None or content.parts is None:
            continue
        for part in content.parts:
            if part.function_call is not None and part.function_call.name == "echo":
                saw_echo_call = True
                print(f"[smoke] echo tool called: args={part.function_call.args}")
            if part.text and MARKER in part.text:
                saw_marker = True
                print(f"[smoke] agent response contains marker: {part.text!r}")
    if saw_echo_call and saw_marker:
        print("[smoke] PASS")
        return 0
    print(f"[smoke] FAIL (echo_called={saw_echo_call}, marker_seen={saw_marker})")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
