"""Red-team runner tests (BUILD_PLAN D7-M4, scenario S9).

The runner feeds every committed attack fixture through the full pipeline and
scores the outcome against ``redteam/expected.yaml``: one row per fixture plus
the vision §13 scorecard grouped by attack class. Offline against the emulator
all 20 fixtures must be blocked at their declared layer with their declared
reason.
"""

from __future__ import annotations

import pytest
from google.cloud import firestore

from redteam.runner import (
    RedteamReport,
    RedteamRow,
    attack_class_of,
    main,
    render_report,
    run_redteam,
)


class TestRunnerRows:
    def test_one_row_per_ledger_fixture(self, firestore_client: firestore.Client) -> None:
        report = run_redteam(firestore_client)
        assert report.total == 20
        assert [row.path for row in report.rows][:3] == [
            "injection/direct_a.pdf",
            "injection/direct_b.pdf",
            "injection/obfuscated/a.pdf",
        ]

    def test_all_twenty_fixtures_pass_offline(self, firestore_client: firestore.Client) -> None:
        report = run_redteam(firestore_client)
        assert report.total == 20
        assert report.blocked == 20
        assert report.all_passed is True
        for row in report.rows:
            assert row.blocked is True, row.path
            assert row.passed is True, row.path
            assert row.actual_layer == row.expected_layer, row.path
            assert row.expected_reason in row.reasons_seen, (row.path, row.reasons_seen)

    def test_rows_record_status_per_layer(self, firestore_client: firestore.Client) -> None:
        report = run_redteam(firestore_client)
        sentinel_rows = [row for row in report.rows if row.expected_layer == "sentinel_tripwire"]
        armor_rows = [row for row in report.rows if row.expected_layer == "model_armor"]
        assert len(sentinel_rows) == 9
        assert len(armor_rows) == 11
        assert all(row.actual_status == "tripwired" for row in sentinel_rows)
        assert all(row.actual_status == "quarantined" for row in armor_rows)

    def test_fresh_deal_per_run_avoids_suppression(
        self, firestore_client: firestore.Client
    ) -> None:
        first = run_redteam(firestore_client)
        second = run_redteam(firestore_client, deal_id=first.deal_id)
        suppressed = [row for row in second.rows if row.actual_status == "suppressed"]
        assert suppressed == [], "same deal rerun must not suppress the fixtures"


class TestScorecard:
    def test_scorecard_groups_by_class(self, firestore_client: firestore.Client) -> None:
        report = run_redteam(firestore_client)
        assert report.scorecard == {
            "injection": (8, 8),
            "exfiltration": (5, 5),
            "cross_ws": (4, 4),
            "poisoning_cross_deal": (3, 3),
        }

    def test_render_report_shows_the_board(self, firestore_client: firestore.Client) -> None:
        rendered = render_report(run_redteam(firestore_client))
        assert "Prompt Injection            8/8 blocked" in rendered
        assert "Exfiltration                5/5 blocked" in rendered
        assert "Cross-Workstream Leak       4/4 blocked" in rendered
        assert "Tool Poisoning / Cross-Deal 3/3 blocked" in rendered
        assert "TOTAL                       20/20 blocked" in rendered

    def test_render_report_marks_a_failed_row(self) -> None:
        row = RedteamRow(
            path="injection/rogue.pdf",
            attack_class="injection",
            expected_layer="model_armor",
            expected_reason="authority_forgery",
            actual_status="routed",
            actual_layer=None,
            reasons_seen=(),
            blocked=False,
            passed=False,
        )
        rendered = render_report(RedteamReport(rows=(row,), deal_id="deal-x"))
        assert "Prompt Injection            0/1 blocked" in rendered
        assert "TOTAL                       0/1 blocked" in rendered
        assert "FAIL" in rendered


class TestRunnerCli:
    def test_refuses_without_emulator_or_confirm_live(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        with pytest.raises(SystemExit):
            main([])
        captured = capsys.readouterr()
        assert "emulator" in (captured.err + captured.out).lower()


class TestAttackClassOf:
    def test_recovers_every_ledger_class_from_run_document_ids(self) -> None:
        cases = {
            "rt-abc12345__injection_direct_a.pdf": "injection",
            "rt-abc12345__injection_obfuscated_a.pdf": "injection",
            "rt-abc12345__exfiltration_a.pdf": "exfiltration",
            "rt-abc12345__cross_ws_state_mutation_a.pdf": "cross_ws",
            "rt-abc12345__cross_deal_cross_deal_probe_a.pdf": "cross_deal",
            "rt-abc12345__poisoning_tool_poisoning_a.pdf": "poisoning",
        }
        for document_id, expected in cases.items():
            assert attack_class_of(document_id) == expected, document_id

    def test_non_ledger_documents_yield_none(self) -> None:
        assert attack_class_of("contract_meridian_logistics.pdf") is None
        assert attack_class_of("rt-abc12345__memo_fleet_operations.docx") is None
        assert attack_class_of("") is None
