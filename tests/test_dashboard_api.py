"""Dashboard API tests (BUILD_PLAN D8-M4 data plane, pulled early for the
Day-11 web shell; vision §15 four views)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.api.data import _COC_SPAN, _FIN_CUSTOMER_ROW

_CLIENT = TestClient(create_app())

SEVERITIES = {"critical", "high", "medium", "low", "informational"}
WORKSTREAMS = {"legal", "finance", "hr", "ip_tech", "tax", "regulatory", "esg", "real_estate"}


class TestHealthAndDeal:
    def test_health_reports_deal(self) -> None:
        body = _CLIENT.get("/api/health").json()
        assert body == {"status": "ok", "deal": "deal-falcon"}

    def test_deal_bundle_shape(self) -> None:
        res = _CLIENT.get("/api/deal")
        assert res.status_code == 200
        body = res.json()
        summary = body["summary"]
        assert summary["name"] == "Project Falcon"
        assert summary["health"] == "HIGH RISK"
        assert summary["critical_findings"] >= 1
        assert len(body["workstreams"]) == 8
        assert {ws["workstream"] for ws in body["workstreams"]} == WORKSTREAMS
        assert all(0 <= ws["progress"] <= 100 for ws in body["workstreams"])
        assert body["inbox"], "critical findings must surface in the inbox"


class TestFindings:
    def test_findings_list_is_severity_consistent(self) -> None:
        res = _CLIENT.get("/api/findings")
        assert res.status_code == 200
        findings = res.json()
        assert len(findings) >= 10
        assert {f["severity"] for f in findings} <= SEVERITIES
        assert {f["workstream"] for f in findings} <= WORKSTREAMS
        assert all(0.0 <= f["confidence"] <= 1.0 for f in findings)

    def test_finding_detail_carries_evidence_and_trace(self) -> None:
        res = _CLIENT.get("/api/findings/SYN-001")
        assert res.status_code == 200
        detail = res.json()
        assert detail["severity"] == "critical"
        assert detail["evidence"], "detail must carry evidence spans"
        assert all(ev["verbatim_span"].strip() for ev in detail["evidence"])
        assert detail["trace"], "keystone finding must carry a trace"
        assert any(step["stage"] == "finding.escalated" for step in detail["trace"])

    def test_unknown_finding_returns_404(self) -> None:
        assert _CLIENT.get("/api/findings/NOPE-999").status_code == 404


class TestSecurity:
    def test_security_bundle_matches_red_team_ledger(self) -> None:
        body = _CLIENT.get("/api/security").json()
        assert body["total_blocked"] == len(body["quarantined"]) == 10
        layers = {q["layer"] for q in body["quarantined"]}
        assert layers == {"sentinel_tripwire", "model_armor"}
        assert all(q["reason_codes"] for q in body["quarantined"])
        blocked = sum(g["blocked"] for g in body["scorecard"])
        total = sum(g["total"] for g in body["scorecard"])
        assert blocked == total == 10
        assert body["feed"], "security feed must not be empty"


class TestRegistry:
    def test_registry_lists_eight_approved_agents(self) -> None:
        agents = _CLIENT.get("/api/registry").json()
        assert len(agents) == 8
        assert {a["workstream"] for a in agents} == WORKSTREAMS
        assert all(a["approved"] for a in agents)
        assert all(a["deployment_status"] == "deployed" for a in agents)
        assert all(a["model_id"] == "gemini-3.5-flash" for a in agents)


class TestDocuments:
    def test_serve_pdf_returns_pdf_media_type(self) -> None:
        res = _CLIENT.get("/api/documents/contract_meridian_logistics.pdf")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/pdf")

    def test_locate_pdf_evidence_span(self) -> None:
        res = _CLIENT.get(
            "/api/documents/contract_meridian_logistics.pdf/locate",
            params={"span": _COC_SPAN},
        )
        assert res.status_code == 200
        locator = res.json()
        assert locator["kind"] == "pdf"
        assert locator["page_count"] == 2
        assert locator["page"] is not None and 1 <= locator["page"] <= locator["page_count"]

    def test_locate_xlsx_evidence_span(self) -> None:
        res = _CLIENT.get(
            "/api/documents/financials_fy27.xlsx/locate",
            params={"span": _FIN_CUSTOMER_ROW},
        )
        assert res.status_code == 200
        locator = res.json()
        assert locator["kind"] == "xlsx"
        assert locator["sheet"] == "FY27 Projected Revenue"
        assert locator["row_index"] == 1
        assert locator["headers"]
        assert locator["rows"]
        located_row = locator["rows"][locator["row_index"]]
        assert "Meridian Logistics, Inc." in located_row
        assert "0.183" in located_row

    def test_xlsx_header_is_first_row(self) -> None:
        locator = _CLIENT.get(
            "/api/documents/financials_fy27.xlsx/locate",
            params={"span": _FIN_CUSTOMER_ROW},
        ).json()
        assert locator["rows"][0] == locator["headers"]

    def test_unknown_document_returns_404(self) -> None:
        assert _CLIENT.get("/api/documents/no_such_doc.pdf").status_code == 404
        assert (
            _CLIENT.get("/api/documents/no_such_doc.pdf/locate", params={"span": "x"}).status_code
            == 404
        )

    def test_path_traversal_is_rejected(self) -> None:
        # The resolver must never serve a file that escapes the data room.
        assert (
            _CLIENT.get(
                "/api/documents/%2e%2e%2f%2e%2e%2ftests%2ftest_dashboard_api.py"
            ).status_code
            == 404
        )

    def test_unresolvable_document_name_fails_closed(self) -> None:
        # Names the OS refuses to resolve (NUL bytes) must 404, never 500.
        assert _CLIENT.get("/api/documents/a%00b.pdf").status_code == 404
        assert (
            _CLIENT.get("/api/documents/a%00b.pdf/locate", params={"span": "x"}).status_code == 404
        )


class TestRoleFilter:
    _ALL_FINDING_IDS = {
        "SYN-001",
        "LEGAL-014",
        "FIN-007",
        "IP-009",
        "REG-005",
        "RE-004",
        "HR-003",
        "TAX-002",
        "ESG-001",
        "LEGAL-021",
        "IP-002",
    }

    def _finding_ids(self, role: str | None = None) -> set[str]:
        params = {"role": role} if role is not None else {}
        res = _CLIENT.get("/api/findings", params=params)
        assert res.status_code == 200
        return {f["finding_id"] for f in res.json()}

    def test_default_role_sees_everything(self) -> None:
        assert self._finding_ids() == self._ALL_FINDING_IDS

    def test_deal_lead_sees_everything(self) -> None:
        assert self._finding_ids("deal_lead") == self._ALL_FINDING_IDS

    def test_junior_legal_sees_only_legal_findings(self) -> None:
        assert self._finding_ids("junior_legal") == {"SYN-001", "LEGAL-014", "LEGAL-021"}

    def test_junior_legal_cannot_open_a_finance_finding(self) -> None:
        # Zero-trust: a hidden finding is indistinguishable from a missing one.
        res = _CLIENT.get("/api/findings/FIN-007", params={"role": "junior_legal"})
        assert res.status_code == 404

    def test_hr_analyst_sees_only_hr_findings(self) -> None:
        assert self._finding_ids("hr_analyst") == {"HR-003"}

    def test_outside_counsel_sees_only_approved_legal_materials(self) -> None:
        # SYN-001 is legal but still open -> not approved for external eyes.
        assert self._finding_ids("outside_counsel") == {"LEGAL-014", "LEGAL-021"}

    def test_inbox_is_role_filtered(self) -> None:
        def inbox(role: str) -> list[dict[str, object]]:
            res = _CLIENT.get("/api/deal", params={"role": role})
            assert res.status_code == 200
            body: dict[str, object] = res.json()
            entries = body["inbox"]
            assert isinstance(entries, list)
            return entries

        assert {e["finding_id"] for e in inbox("deal_lead")} == {"SYN-001", "LEGAL-014"}
        assert {e["finding_id"] for e in inbox("junior_legal")} == {"SYN-001", "LEGAL-014"}
        # Open escalations are not approved-for-external material; HR scope excludes legal.
        assert inbox("outside_counsel") == []
        assert inbox("hr_analyst") == []

    def test_unknown_role_is_rejected(self) -> None:
        assert _CLIENT.get("/api/findings", params={"role": "intern"}).status_code == 422
