"""Tests for the Agent Gateway service shell (BUILD_PLAN D2-M7 + D5-M3 HTTP).

Offline tests only: fastapi.testclient.TestClient, no network.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from gateway.app import create_app
from gateway.policy import PolicyStore
from main import app as main_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}


def test_health_alias_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}


def test_healthz_and_health_share_one_contract(client: TestClient) -> None:
    assert client.get("/healthz").json() == client.get("/health").json()


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


def test_root_main_app_serves_healthz() -> None:
    """The root ``main:app`` wired for Cloud Run buildpack must serve /healthz."""
    response = TestClient(main_app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway"}


class TestDecideEndpoint:
    """POST /gateway/decide (Day 5): policy verdicts over HTTP."""

    @pytest.fixture()
    def wired_client(self, firestore_client: firestore.Client) -> TestClient:
        PolicyStore(firestore_client).seed_defaults("deal-falcon")
        return TestClient(create_app(gateway_client=firestore_client))

    def test_allow_decision(self, wired_client: TestClient) -> None:
        response = wired_client.post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "legal-agent@deal-falcon",
                "target_workstream": "finance",
                "question": "What share of projected revenue comes from Meridian Logistics?",
                "purpose": "revenue_concentration",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "allow"
        assert body["reason"] == "aggregate_permitted"
        assert body["rule_id"] == "legal->finance"
        assert body["request_id"]

    def test_deny_decision_with_machine_reason(self, wired_client: TestClient) -> None:
        response = wired_client.post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "legal-agent@deal-falcon",
                "target_workstream": "hr",
                "question": "q",
                "purpose": "roster_review",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "deny"
        assert body["reason"] == "no_policy"

    def test_malformed_identity_returns_422(self, wired_client: TestClient) -> None:
        response = wired_client.post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "not-an-identity",
                "target_workstream": "finance",
                "question": "q",
                "purpose": "revenue_concentration",
            },
        )
        assert response.status_code == 422

    def test_malformed_workstream_returns_422(self, wired_client: TestClient) -> None:
        response = wired_client.post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "legal-agent@deal-falcon",
                "target_workstream": "astrology",
                "question": "q",
                "purpose": "revenue_concentration",
            },
        )
        assert response.status_code == 422

    def test_missing_field_returns_422(self, wired_client: TestClient) -> None:
        response = wired_client.post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "legal-agent@deal-falcon",
                "target_workstream": "finance",
                "question": "q",
            },
        )
        assert response.status_code == 422

    def test_route_absent_without_gateway_client(self) -> None:
        response = TestClient(create_app()).post(
            "/gateway/decide",
            json={
                "deal_id": "deal-falcon",
                "sender_identity": "legal-agent@deal-falcon",
                "target_workstream": "finance",
                "question": "q",
                "purpose": "revenue_concentration",
            },
        )
        assert response.status_code == 404


class TestIndex:
    """The gateway URL is published, so its root must not 404."""

    def test_root_names_the_service_and_its_routes(self) -> None:
        from fastapi.testclient import TestClient

        from gateway.app import create_app

        body = TestClient(create_app()).get("/").json()
        assert "Agent Gateway" in body["service"]
        assert "POST /gateway/decide" in body["endpoints"]
        assert body["repository"].startswith("https://github.com/")
