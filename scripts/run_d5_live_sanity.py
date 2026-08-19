"""Day-5 live sanity check (small window, no API key needed).

Real gemini-3.5-flash ADK Finance agent answers the CoC revenue-concentration
question through the governed gateway chain:

    PolicyStore.seed_defaults -> decide() ALLOW (audited in live Firestore)
    -> ADK finance agent with the governed aggregate tool -> "18.3%"

Flash runs on Vertex via ADC (location=global), so no Gemini Developer API key
is required. Guards: --confirm-live, refuses under the emulator, env contract.
Teardown (project delete) is the operator's step after capture.
"""

from __future__ import annotations

import argparse
import os
import sys

# Vertex live-window env the operator must set before opening the window.
# These are validated (validate_live_env) and deliberately NOT defaulted here:
# defaulting them at import time made the env contract self-satisfying.
# GOOGLE_CLOUD_LOCATION must be "global" — gemini-3.5-flash is served only
# from the global location on Vertex.
_REQUIRED_ENV: tuple[str, ...] = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)

_QUESTION = "What percentage of projected FY27 revenue comes from Meridian Logistics?"
_MARKER = "18.3"


def required_env() -> tuple[str, ...]:
    return _REQUIRED_ENV


def validate_live_env() -> tuple[str, ...]:
    return tuple(name for name in _REQUIRED_ENV if not os.environ.get(name))


async def _run_live(deal_id: str) -> int:
    import uuid
    from datetime import UTC, datetime

    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.cloud import firestore
    from google.genai import types

    from agents.finance.prompts import SYSTEM_PROMPT as FINANCE_PROMPT
    from agents.tools.gateway_query import OfflineFinanceResponder
    from gateway.aggregate import render_aggregate
    from gateway.decide import GatewayRequest, Verdict, decide
    from gateway.policy import PolicyStore
    from identity.principals import principal_for
    from registry.models import Workstream

    responder = OfflineFinanceResponder()

    def finance_aggregate(question: str) -> dict[str, str]:
        """Return the governed scalar financial aggregate for a revenue question.

        Args:
            question: The revenue-concentration question being asked.

        Returns:
            Dict with "value" (scalar aggregate) and "source" (workbook name).
        """
        del question
        aggregate = responder.compute_share()
        return {"value": render_aggregate(aggregate), "source": aggregate.source_document}

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = firestore.Client(project=project)
    PolicyStore(client).seed_defaults(deal_id)

    legal = principal_for(Workstream.LEGAL, deal_id)
    request = GatewayRequest(
        request_id=uuid.uuid4().hex,
        deal_id=deal_id,
        sender=legal,
        target_workstream=Workstream.FINANCE,
        question=_QUESTION,
        purpose="change_of_control_exposure",
        ts=datetime.now(UTC),
    )
    decision = decide(client, request)
    print(
        f"gateway: verdict={decision.verdict.value} reason={decision.reason.value} "
        f"rule={decision.rule_id} request_id={decision.request_id}"
    )
    if decision.verdict is not Verdict.ALLOW:
        print("[sanity] FAIL: expected ALLOW for the governed corridor")
        return 1

    agent = Agent(
        name="diligence_room_finance_live",
        model="gemini-3.5-flash",
        description="Day-5 live sanity finance agent (governed aggregate only).",
        instruction=(
            FINANCE_PROMPT + "\nWhen the gateway has ALLOWed a question, call finance_aggregate "
            "exactly once, then answer with ONLY the scalar value and the source "
            "document. No tables, no model details.\n"
        ),
        tools=[finance_aggregate],
    )
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    session = await runner.session_service.create_session(
        app_name=agent.name, user_id="day5-sanity"
    )
    message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text=(
                    "Gateway decision: ALLOW (purpose=change_of_control_exposure). "
                    f"Question: {_QUESTION}"
                )
            )
        ],
    )
    tool_called = False
    final_text = ""
    async for event in runner.run_async(
        user_id="day5-sanity", session_id=session.id, new_message=message
    ):
        content = event.content
        if content is None or content.parts is None:
            continue
        for part in content.parts:
            if part.function_call is not None and part.function_call.name == "finance_aggregate":
                tool_called = True
                print(f"[sanity] finance_aggregate called: args={part.function_call.args}")
            if part.text:
                final_text = part.text
                print(f"[sanity] agent text: {part.text!r}")

    if tool_called and _MARKER in final_text:
        print("[sanity] PASS")
        return 0
    print(f"[sanity] FAIL (tool_called={tool_called}, marker_seen={_MARKER in final_text})")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Day-5 live sanity: real Flash agent through the governed gateway."
    )
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required: run against real GCP (Vertex Flash + live Firestore)",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("Refusing: pass --confirm-live to open the Day-5 live window.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print(
            "Refusing: FIRESTORE_EMULATOR_HOST is set; live window targets real GCP.",
            file=sys.stderr,
        )
        sys.exit(1)
    missing = validate_live_env()
    if missing:
        print("Refusing: missing live-window env: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    import asyncio

    return asyncio.run(_run_live(args.deal_id))


if __name__ == "__main__":
    sys.exit(main())
