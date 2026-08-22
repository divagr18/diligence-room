"""DLP HR-path tests (BUILD_PLAN D11-M9)."""

from __future__ import annotations

from pathlib import Path

import yaml

from compliance.dlpcfg import load_template, redact, trigger_on

_CONFIG = (
    Path(__file__).resolve().parent.parent
    / "infra"
    / "compliance_config"
    / "dlp_inspect_template.yaml"
)


class TestTemplate:
    def test_yaml_shape(self) -> None:
        tpl = load_template(_CONFIG)
        assert tpl.template_id == "deal-falcon-hr-inspect"
        assert "EMAIL_ADDRESS" in tpl.info_types
        assert "PHONE_NUMBER" in tpl.info_types
        assert "US_SOCIAL_SECURITY_NUMBER" in tpl.info_types
        assert tpl.min_likelihood == "POSSIBLE"

    def test_yaml_parses(self) -> None:
        raw = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert {"template_id", "info_types", "min_likelihood"} <= set(raw.keys())


class TestTriggerAndRedact:
    def test_heavy_pii_triggers(self) -> None:
        synthetic = (
            "Contact: jane.doe@example.com, ssn 123-45-6789, phone (415) 555-1234. "
            "Additional: bob@example.com, 987-65-4321, 415-555-9876 signals."
        )
        assert trigger_on(synthetic) is True
        assert trigger_on(synthetic, doc_type="hr_roster") is True

    def test_clean_hr_text_does_not_trigger(self) -> None:
        clean = "Dana Whitfield, VP Customer Success, resigns effective 60 days out."
        assert trigger_on(clean) is False
        assert redact(clean) == clean

    def test_redact_tokenizes_pii(self) -> None:
        text = "Reach jane.doe@example.com or 123-45-6789 or (415) 555-1234."
        out = redact(text)
        assert "[EMAIL]" in out
        assert "[SSN]" in out
        assert "[PHONE]" in out
        assert "jane.doe@example.com" not in out
        assert "123-45-6789" not in out
