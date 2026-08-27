"""Cloud Run source-deploy entrypoint for the executive dashboard (D11-M1).

Buildpack serves ``dashboard.main:app`` (``GOOGLE_ENTRYPOINT``). Serves the
dashboard API (``/api/*``) backed by live Firestore when
``DILIGENCE_DASHBOARD_LIVE=1`` (set on the Cloud Run service), and the built
web shell (``dashboard/web/dist``) for every other path with an SPA fallback
so the client-side routes (``/findings``, ``/security``, ``/registry``)
resolve on refresh and deep links.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from google.cloud import firestore

from dashboard.api.app import create_app
from memory.db import make_client

_DIST = Path(__file__).resolve().parent / "web" / "dist"


def _dashboard_client() -> firestore.Client | None:
    """Live Firestore client (negotiation + security tallies), only when enabled."""
    if os.environ.get("DILIGENCE_DASHBOARD_LIVE") != "1":
        return None
    return make_client()


def _spa_fallback(path: str) -> FileResponse:
    """Serve a real dist file when present, else the SPA index."""
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    candidate = (_DIST / path).resolve()
    if _DIST.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(_DIST / "index.html")


app = create_app(client=_dashboard_client())

if _DIST.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str = "") -> FileResponse:
        return _spa_fallback(path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dashboard.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
