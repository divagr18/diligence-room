"""Region verification tests (BUILD_PLAN D11-M2)."""

from __future__ import annotations

from compliance.regions import verify_regions


class TestRegionVerification:
    def test_deal_falcon_declares_us_eu(self) -> None:
        report = verify_regions("deal-falcon")
        assert report["deal_id"] == "deal-falcon"
        assert report["declared"] == ["US", "EU"]
        assert report["ok"] is True
        buckets = report["buckets"]
        assert isinstance(buckets, dict)
        assert buckets["US"] == "diligence-room-dataroom-deal-falcon-us"
        assert buckets["EU"] == "diligence-room-dataroom-deal-falcon-eu"
        regions = report["regions"]
        assert isinstance(regions, dict)
        assert regions["US"] == "us-central1"
        assert regions["EU"] == "europe-west1"

    def test_unknown_deal_is_not_ok(self) -> None:
        report = verify_regions("deal-unknown")
        assert report["ok"] is False
        error = report["error"]
        assert isinstance(error, str)
        assert "unknown" in error.lower()

    def test_cli_report_is_shape_valid(self) -> None:
        report = verify_regions("deal-falcon")
        assert set(report.keys()) == {"deal_id", "declared", "buckets", "regions", "ok", "error"}
