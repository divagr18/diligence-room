"""Cloud Run source-deploy entrypoint for the gateway shell (BUILD_PLAN D2-M7).

Buildpack serves ``main:app``; local ``python main.py`` honors ``$PORT``.
"""

from __future__ import annotations

from gateway.app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
