"""Agent Gateway — service shell (BUILD_PLAN D2-M7) + policy HTTP edge (D5-M3).

Day-1 scope: ``create_app()`` factory with caller-identity middleware
and two trivial routes (``/healthz``, ``/whoami``).  Every request is
logged *after* the response with method, path, caller, and status code.

Day-5 scope: when constructed with a Firestore client, the factory registers
``POST /gateway/decide`` over the policy engine (gateway.decide). The route is
absent (404) when no client is wired, keeping the shell dependency-free.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import fastapi
import pydantic
from google.cloud import firestore
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from gateway.decide import GatewayRequest, decide
from identity.principals import parse_identity
from registry.agent_card import build_agent_card
from registry.models import Workstream
from registry.store import AgentRegistryStore

logger = logging.getLogger(__name__)

_CALLER_HEADER = "X-Caller-Identity"
_ANONYMOUS: str = "anonymous"


class DecideBody(pydantic.BaseModel):
    """HTTP-edge schema for POST /gateway/decide."""

    deal_id: str
    sender_identity: str
    target_workstream: str
    question: str
    purpose: str


class DecideResponseModel(pydantic.BaseModel):
    """HTTP-edge schema for the decision verdict."""

    request_id: str
    decision: str
    reason: str
    rule_id: str | None


class _CallerIdentityMiddleware(BaseHTTPMiddleware):
    """Capture ``X-Caller-Identity`` into ``request.state``, then log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        caller: str = request.headers.get(_CALLER_HEADER) or _ANONYMOUS
        request.state.caller_identity = caller
        response = await call_next(request)
        logger.info(
            "request method=%s path=%s caller=%s status_code=%d",
            request.method,
            request.url.path,
            caller,
            response.status_code,
        )
        return response


def _healthz() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


def _index() -> dict[str, object]:
    """Name the service and its routes at the root.

    The gateway URL is published in the README and on the submission form, so
    the root cannot be a bare 404: someone following the link should learn what
    the service is and where to look next.
    """
    return {
        "service": "Diligence Room - Agent Gateway",
        "description": (
            "Deny-by-default policy edge for cross-workstream agent reads. Every "
            "request is evaluated against a Firestore policy store; absent an "
            "allow rule the answer is deny, and the decision is logged."
        ),
        "endpoints": {
            "POST /gateway/decide": "evaluate one cross-workstream access request",
            "GET /agents/{agent_id}": "A2A agent card for a published agent",
            "GET /whoami": "echo the caller identity header the edge saw",
            "GET /health": "liveness",
            "GET /docs": "OpenAPI browser",
        },
        "dashboard": ("https://diligence-room-dashboard-378831539922.asia-south1.run.app"),
        "repository": "https://github.com/divagr18/diligence-room",
    }


def _whoami(request: Request) -> dict[str, str]:
    caller: str = getattr(request.state, "caller_identity", _ANONYMOUS)
    return {"caller": caller}


def _make_agent_card_route(
    gateway_client: firestore.Client,
) -> Callable[[str], dict[str, object]]:
    """Serve each agent's A2A card at its own path.

    The Agent Registry entry for every agent publishes this URL, and the
    registry requires a distinct interface URL per service. Serving the card
    here means the address in the catalogue actually resolves, and gives the
    fleet a real discovery endpoint rather than an advertised 404.
    """

    def _agent_card(agent_id: str) -> dict[str, object]:
        store = AgentRegistryStore(gateway_client)
        try:
            manifest = store.get_manifest(agent_id)
        except KeyError as exc:
            raise fastapi.HTTPException(status_code=404, detail=f"no agent {agent_id!r}") from exc
        return build_agent_card(manifest)

    return _agent_card


def _make_decide_route(
    gateway_client: firestore.Client,
) -> Callable[[DecideBody], Awaitable[DecideResponseModel]]:
    async def _decide(body: DecideBody) -> DecideResponseModel:
        try:
            sender = parse_identity(body.sender_identity)
            target = Workstream(body.target_workstream)
        except ValueError as exc:
            raise fastapi.HTTPException(status_code=422, detail=str(exc)) from None
        request = GatewayRequest(
            request_id=uuid.uuid4().hex,
            deal_id=body.deal_id,
            sender=sender,
            target_workstream=target,
            question=body.question,
            purpose=body.purpose,
            ts=datetime.now(UTC),
        )
        decision = decide(gateway_client, request)
        return DecideResponseModel(
            request_id=decision.request_id,
            decision=decision.verdict.value,
            reason=decision.reason.value,
            rule_id=decision.rule_id,
        )

    return _decide


def create_app(
    gateway_client: firestore.Client | None = None,
) -> fastapi.FastAPI:
    """Build the gateway FastAPI app; policy route only when a client is wired."""
    app = fastapi.FastAPI(title="Diligence Room - Agent Gateway")
    app.add_middleware(_CallerIdentityMiddleware)
    app.add_api_route("/", _index, methods=["GET"])
    app.add_api_route("/healthz", _healthz, methods=["GET"])
    # /health alias: Google Frontend answers /healthz itself on Cloud Run
    # (returns an edge 404 before the container sees it), so the
    # deployed liveness probe uses /health.
    app.add_api_route("/health", _healthz, methods=["GET"])
    app.add_api_route("/whoami", _whoami, methods=["GET"])
    if gateway_client is not None:
        app.add_api_route("/gateway/decide", _make_decide_route(gateway_client), methods=["POST"])
        app.add_api_route(
            "/agents/{agent_id}", _make_agent_card_route(gateway_client), methods=["GET"]
        )
    return app
