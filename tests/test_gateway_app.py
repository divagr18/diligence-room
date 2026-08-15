"""Tests for the Agent Gateway service shell (BUILD_PLAN D2-M7).

Offline tests only: fastapi.testclient.TestClient, no network.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}


def test_whoami_with_caller_identity_header(client: TestClient) -> None:
    response = client.get("/whoami", headers={"X-Caller-Identity": "legal-agent@deal-falcon"})
    assert response.status_code == 200
    assert response.json() == {"caller": "legal-agent@deal-falcon"}


def test_whoami_without_header_returns_anonymous(client: TestClient) -> None:
    response = client.get("/whoami")
    assert response.status_code == 200
    assert response.json() == {"caller": "anonymous"}


def test_request_log_captures_structured_record(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="gateway.app")
    response = client.get("/whoami", headers={"X-Caller-Identity": "legal-agent@deal-falcon"})
    assert response.status_code == 200
    records = [r for r in caplog.records if r.name == "gateway.app"]
    assert len(records) >= 1
    record = records[0]
    message = record.getMessage()
    assert "legal-agent@deal-falcon" in message
    assert "GET" in message
    assert "/whoami" in message
    assert "200" in message
