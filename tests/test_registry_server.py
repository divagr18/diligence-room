"""Unit tests for ``registry.server`` (live-Firestore module entrypoint).

The guard lives in ``_build_app`` so it can be exercised without paying the
cost of constructing a ``firestore.Client``; the module-level ``app`` is
only bound when the live-Firestore precondition holds.
"""

from __future__ import annotations

import pytest
from starlette.routing import Route

import registry.server


def test_server_refuses_emulator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_build_app`` must raise when FIRESTORE_EMULATOR_HOST is set."""
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:9222")

    with pytest.raises(RuntimeError, match="(?i)emulator"):
        registry.server._build_app()


def test_server_app_exposes_routes() -> None:
    """Module-bound ``app`` should expose the core registry routes."""
    paths = {route.path for route in registry.server.app.routes if isinstance(route, Route)}

    assert "/agents" in paths
    assert "/agents/{agent_id}/versions" in paths
    assert "/agents/{agent_id}/approval" in paths
