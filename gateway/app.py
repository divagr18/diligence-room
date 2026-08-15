"""Agent Gateway — service shell (BUILD_PLAN D2-M7).

Day-1 scope: ``create_app()`` factory with caller-identity middleware
and two trivial routes (``/healthz``, ``/whoami``).  Every request is
logged *after* the response with method, path, caller, and status code.
"""

from __future__ import annotations

import logging

import fastapi
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_CALLER_HEADER = "X-Caller-Identity"
_ANONYMOUS: str = "anonymous"


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


def _whoami(request: Request) -> dict[str, str]:
    caller: str = getattr(request.state, "caller_identity", _ANONYMOUS)
    return {"caller": caller}


def create_app() -> fastapi.FastAPI:
    """Build the gateway FastAPI application (no globals, no lifespan)."""
    app = fastapi.FastAPI(title="Diligence Room - Agent Gateway")
    app.add_middleware(_CallerIdentityMiddleware)
    app.add_api_route("/healthz", _healthz, methods=["GET"])
    app.add_api_route("/whoami", _whoami, methods=["GET"])
    return app
