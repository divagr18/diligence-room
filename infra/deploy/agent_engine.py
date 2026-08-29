"""Deploy and invoke the Diligence Room ADK agent on Vertex AI Agent Engine.

BUILD_PLAN module D1-M7. Subcommands:

    deploy   - deploy agents.base_agent.root_agent (ADK BaseAgent) directly;
               the reasoningEngines resource name is stored in
               infra/deploy/agent_engine_state.json
    invoke   - async session invoke against the deployed agent; asserts the
               echo marker round-trips (scenario S5)
    list     - list deployed agent engines
    delete   - delete the deployed agent engine

Requires Application Default Credentials (gcloud auth application-default login).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.get(
    "DILIGENCE_PROJECT_ID", os.environ.get("GOOGLE_CLOUD_PROJECT", "diligence-room")
)
# Agent Engine resources live in us-central1 (canonical supported region);
# the gemini-3.5-flash model itself is only served from the global location,
# so the remote ADK runtime gets GOOGLE_CLOUD_LOCATION=global via env_vars.
# DILIGENCE_AGENT_ENGINE_LOCATION overrides the region (post-undelete the
# us-central1 control plane can lag; europe-west1 serves as fallback).
LOCATION = os.environ.get("DILIGENCE_AGENT_ENGINE_LOCATION", "us-central1")
MODEL_LOCATION = "global"
STAGING_BUCKET = f"gs://{PROJECT_ID}-staging"
DISPLAY_NAME = "diligence-room-hello"
STATE_PATH = Path(__file__).parent / "agent_engine_state.json"
MARKER = "diligence-room-day1-smoke"
REMOTE_REQUIREMENTS: list[str] = [
    "google-cloud-aiplatform[adk,agent_engines]>=1.100.0",
    "google-adk>=1.5.0,<3.0.0",
    "google-genai>=1.5.0",
    # base_agent and its tool closure import these at module level; the
    # Agent Engine container fails to start without them.
    "google-cloud-firestore>=2.16",
    "opentelemetry-api>=1.25",
    "opentelemetry-sdk>=1.25",
    "openpyxl>=3.1",
    "pypdf>=4.0",
    "python-docx>=1.1",
]


def init_vertex() -> None:
    import vertexai

    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)


def load_resource_name(explicit: str | None) -> str:
    if explicit:
        return explicit
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        name = state.get("resource_name")
        if isinstance(name, str) and name:
            return name
    raise SystemExit("no deployed agent known: pass --resource-name or run `deploy` first")


def cmd_deploy(args: argparse.Namespace) -> int:
    init_vertex()
    from vertexai import agent_engines

    from agents.base_agent import root_agent

    print(f"Deploying {DISPLAY_NAME} (this takes 5-10 minutes)...", flush=True)
    remote_app: Any = agent_engines.create(
        root_agent,
        display_name=args.display_name or DISPLAY_NAME,
        requirements=REMOTE_REQUIREMENTS,
        # Full first-party import closure of agents.base_agent.root_agent:
        # cloudpickle re-imports these modules on the remote container.
        extra_packages=[
            "./agents",
            "./identity",
            "./registry",
            "./memory",
            "./observability",
            "./gateway",
            "./runtime",
            "./ingestion",
            "./armor",
            "./coordination",
        ],
        env_vars={
            "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
            "GOOGLE_CLOUD_LOCATION": MODEL_LOCATION,
        },
    )
    resource_name: str = remote_app.resource_name
    STATE_PATH.write_text(
        json.dumps(
            {
                "resource_name": resource_name,
                "display_name": args.display_name or DISPLAY_NAME,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Deployed: {resource_name}")
    print(f"State written to {STATE_PATH}")
    return 0


def _extract_text(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    content = event.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    texts = [str(part.get("text")) for part in parts if isinstance(part, dict) and part.get("text")]
    return "".join(texts)


async def invoke_text(resource_name: str, message: str) -> str:
    """Send one message to the deployed agent and return the response text.

    Creates an async session, prefers ``async_query`` and falls back to
    draining ``async_stream_query``; text parts from all events are joined
    with newlines. Reused by the Day-2 live consumer (runtime.consumer).
    """
    init_vertex()
    from vertexai import agent_engines

    remote_app: Any = agent_engines.get(resource_name)
    user_id = "day1-smoke"
    session: Any = await remote_app.async_create_session(user_id=user_id)
    session_id = session["id"] if isinstance(session, dict) else session.id
    print(f"Session: {session_id}")

    collected: list[str] = []
    query = getattr(remote_app, "async_query", None)
    if query is not None:
        events = await query(user_id=user_id, session_id=session_id, message=message)
        for event in events if isinstance(events, list) else [events]:
            collected.append(_extract_text(event))
    else:
        stream = remote_app.async_stream_query(
            user_id=user_id, session_id=session_id, message=message
        )
        async for event in stream:
            collected.append(_extract_text(event))
    return "\n".join(text for text in collected if text)


async def run_invoke(resource_name: str) -> int:
    message = f"Please call the echo tool with exactly: {MARKER}"
    response_text = await invoke_text(resource_name, message)
    print(f"Agent response: {response_text!r}")
    if MARKER not in response_text:
        print(f"FAIL: marker {MARKER!r} not found in response")
        return 1
    print("PASS: deployed agent answered async with the echo marker")
    return 0


def cmd_invoke(args: argparse.Namespace) -> int:
    return asyncio.run(run_invoke(load_resource_name(args.resource_name)))


def cmd_list(args: argparse.Namespace) -> int:
    del args
    init_vertex()
    from vertexai import agent_engines

    engines = agent_engines.list()
    found = False
    for engine in engines:
        found = True
        name = getattr(engine, "resource_name", None) or getattr(engine, "name", engine)
        print(name)
    if not found:
        print("(no agent engines deployed)")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    init_vertex()
    from vertexai import agent_engines

    resource_name = load_resource_name(args.resource_name)
    # force=True removes the sessions created by invoke; without it the delete
    # fails with FailedPrecondition (child resources).
    agent_engines.delete(resource_name=resource_name, force=True)
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    print(f"Deleted: {resource_name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_deploy = sub.add_parser("deploy", help="deploy the hello agent")
    p_deploy.add_argument("--display-name", default=None)
    p_deploy.set_defaults(func=cmd_deploy)

    p_invoke = sub.add_parser("invoke", help="async invoke the deployed agent")
    p_invoke.add_argument("--resource-name", default=None)
    p_invoke.set_defaults(func=cmd_invoke)

    p_list = sub.add_parser("list", help="list deployed agent engines")
    p_list.set_defaults(func=cmd_list)

    p_delete = sub.add_parser("delete", help="delete the deployed agent engine")
    p_delete.add_argument("--resource-name", default=None)
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
