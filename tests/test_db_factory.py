"""Tests for the Firestore client factory (named-database switch).

The live ``(default)`` database was destroyed by the project delete/undelete
cycle; ``memory.db.make_client`` routes live traffic onto a named database
selected by ``DILIGENCE_FIRESTORE_DATABASE`` while keeping the default
database (and every test/emulator path) unchanged.
"""

from __future__ import annotations

import pytest

from memory import db


def test_default_database_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(db.LIVE_DATABASE_ENV, raising=False)
    assert db.database_id() == db.DEFAULT_DATABASE


def test_env_selects_named_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(db.LIVE_DATABASE_ENV, "diligence")
    assert db.database_id() == "diligence"


def test_make_client_binds_project_and_named_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(db.LIVE_DATABASE_ENV, "diligence")
    client = db.make_client("diligence-room")
    assert client.project == "diligence-room"
    assert db.client_database(client) == "diligence"


def test_make_client_defaults_to_default_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(db.LIVE_DATABASE_ENV, raising=False)
    client = db.make_client("diligence-room")
    assert db.client_database(client) == db.DEFAULT_DATABASE


def test_make_client_without_project_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(db.LIVE_DATABASE_ENV, "diligence")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "diligence-room")
    client = db.make_client()
    assert db.client_database(client) == "diligence"
