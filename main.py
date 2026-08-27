"""Cloud Run source-deploy entrypoint for the gateway shell (BUILD_PLAN D2-M7).

Buildpack serves ``main:app``; local ``python main.py`` honors ``$PORT``.
The policy edge (``POST /gateway/decide``) is wired only when
``DILIGENCE_GATEWAY_LIVE=1`` (set on the Cloud Run service); otherwise the
dependency-free shell serves ``/healthz`` + ``/whoami`` only, keeping tests
and local runs offline-first.
"""

from __future__ import annotations

import os

from google.cloud import firestore

from gateway.app import create_app
from memory.db import make_client


def _gateway_client() -> firestore.Client | None:
    """Live policy-engine client, only when explicitly enabled."""
    if os.environ.get("DILIGENCE_GATEWAY_LIVE") != "1":
        return None
    return make_client()


app = create_app(_gateway_client())

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
