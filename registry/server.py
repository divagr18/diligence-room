"""Registry API server entrypoint for the live-Firestore demo runbook.

Run ONLY with Application Default Credentials and FIRESTORE_EMULATOR_HOST
unset: ``uv run uvicorn registry.server:app --host 127.0.0.1 --port 8451``.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from memory.db import make_client
from registry.api import create_app
from registry.store import AgentRegistryStore

_PROJECT_ID = "diligence-room"


def _build_app() -> FastAPI:
    """Construct the registry FastAPI application bound to live Firestore.

    Raises:
        RuntimeError: if ``FIRESTORE_EMULATOR_HOST`` is set — this module is
            reserved for the live demo path; the emulator belongs to the
            offline runbook and the test suite.
    """
    if "FIRESTORE_EMULATOR_HOST" in os.environ:
        raise RuntimeError(
            "FIRESTORE_EMULATOR_HOST is set; registry.server runs against "
            "live Firestore only. Unset the variable (or use the offline "
            "runbook) before starting the live demo."
        )
    client = make_client(_PROJECT_ID)
    store = AgentRegistryStore(client)
    return create_app(store)


app: FastAPI = _build_app()
