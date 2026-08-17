"""Model Armor client (BUILD_PLAN D7-M1, vision §7.6).

Screening layer between classification and agent context. Two implementations
of the same protocol:

- ``FakeModelArmor``: deterministic offline stand-in running the project rules
  layer (``armor.rules``) — clearly NOT the managed API;
- ``LiveModelArmor``: flag-gated managed Model Armor client (sanitize user
  prompt against a template with prompt-injection + malicious-URI detectors),
  with latency/cost accounting. Security posture is fail-closed: an API error
  or unparseable verdict blocks the document instead of routing it.

``run_armor`` is the pipeline wrapper: project rules always run; the managed
verdict layers on top when supplied.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Final, Protocol

from armor.rules import RuleHit, screen_project_rules

_ARMOR_FLAG: Final[str] = "DILIGENCE_MODEL_ARMOR_ENABLED"
_TEMPLATE_ID_ENV: Final[str] = "MODEL_ARMOR_TEMPLATE_ID"
_LOCATION_ENV: Final[str] = "MODEL_ARMOR_LOCATION"
_PROJECT_ENV: Final[str] = "GOOGLE_CLOUD_PROJECT"

_LAYER_PROJECT_RULES: Final[str] = "project_rules"
_LAYER_MANAGED: Final[str] = "model_armor_managed"
_LAYER_COMBINED: Final[str] = "combined"


@dataclass(frozen=True, slots=True)
class ArmorTemplateConfig:
    """Template filter surface: prompt-injection + malicious-URI detectors."""

    pi_and_jailbreak_enabled: bool = True
    pi_and_jailbreak_confidence: str = "MEDIUM_AND_ABOVE"
    malicious_uri_enabled: bool = True
    project_rules_enabled: bool = True

    def to_doc(self) -> dict[str, object]:
        return {
            "pi_and_jailbreak_enabled": self.pi_and_jailbreak_enabled,
            "pi_and_jailbreak_confidence": self.pi_and_jailbreak_confidence,
            "malicious_uri_enabled": self.malicious_uri_enabled,
            "project_rules_enabled": self.project_rules_enabled,
        }


@dataclass(frozen=True, slots=True)
class ArmorVerdict:
    """Outcome of one armor screening pass."""

    blocked: bool
    reason_codes: tuple[str, ...]
    rule_ids: tuple[str, ...]
    layer: str
    latency_ms: float


@dataclass(slots=True)
class ArmorMetrics:
    """Latency/cost accounting for managed sanitizations."""

    sanitize_calls: int = 0
    blocked_calls: int = 0
    total_latency_ms: float = 0.0
    estimated_input_tokens: int = 0


class ModelArmorModel(Protocol):
    def sanitize(self, text: str) -> ArmorVerdict: ...


def _verdict_from_hits(hits: tuple[RuleHit, ...], latency_ms: float) -> ArmorVerdict:
    return ArmorVerdict(
        blocked=bool(hits),
        reason_codes=tuple(hit.reason_code for hit in hits),
        rule_ids=tuple(hit.rule_id for hit in hits),
        layer=_LAYER_PROJECT_RULES,
        latency_ms=latency_ms,
    )


class FakeModelArmor:
    """Offline stand-in: project rules only; not the managed Model Armor API."""

    def sanitize(self, text: str) -> ArmorVerdict:
        start = time.perf_counter()
        verdict = _verdict_from_hits(screen_project_rules(text), 0.0)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return ArmorVerdict(
            blocked=verdict.blocked,
            reason_codes=verdict.reason_codes,
            rule_ids=verdict.rule_ids,
            layer=_LAYER_PROJECT_RULES,
            latency_ms=latency_ms,
        )


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"LiveModelArmor missing env: {name}")
    return value


class LiveModelArmor:
    """Managed Model Armor client; constructed only when enabled + configured."""

    def __init__(
        self,
        client: Any = None,
        template_id: str = "",
        location: str = "",
        project: str = "",
    ) -> None:
        if os.environ.get(_ARMOR_FLAG) != "1":
            raise RuntimeError(f"LiveModelArmor disabled: set {_ARMOR_FLAG}=1")
        self._template_id = template_id or _require_env(_TEMPLATE_ID_ENV)
        self._location = location or _require_env(_LOCATION_ENV)
        self._project = project or _require_env(_PROJECT_ENV)
        self._client: Any = client
        self.metrics: ArmorMetrics = ArmorMetrics()

    @property
    def template_name(self) -> str:
        return f"projects/{self._project}/locations/{self._location}/templates/{self._template_id}"

    def _get_client(self) -> Any:
        if self._client is None:
            from google.api_core.client_options import ClientOptions
            from google.cloud import modelarmor_v1

            self._client = modelarmor_v1.ModelArmorClient(
                transport="rest",
                client_options=ClientOptions(
                    api_endpoint=f"modelarmor.{self._location}.rep.googleapis.com"
                ),
            )
        return self._client

    def _sanitize_request(self, text: str) -> Any:
        from google.cloud import modelarmor_v1

        return modelarmor_v1.SanitizeUserPromptRequest(
            name=self.template_name,
            user_prompt_data=modelarmor_v1.DataItem(text=text),
        )

    @staticmethod
    def _match_state_name(holder: Any) -> str:
        state = getattr(holder, "match_state", None)
        if state is None:
            return ""
        # Proto enums stringify to their int value; .name carries the symbolic
        # form (e.g. MATCH_FOUND). Plain objects fall back to str().
        name = getattr(state, "name", None)
        candidate = name.upper() if isinstance(name, str) else str(state).upper()
        return candidate if "MATCH_FOUND" in candidate else ""

    @staticmethod
    def _filter_match_state(filter_result: Any) -> str:
        # FilterResult wraps the per-filter outcome in a oneof branch; walk the
        # proto-plus field map to reach the nested message carrying match_state.
        # Plain (non-proto) objects expose match_state directly.
        meta = getattr(type(filter_result), "meta", None)
        fields = getattr(meta, "fields", None) if meta is not None else None
        if fields:
            for field_name in fields:
                state = LiveModelArmor._match_state_name(getattr(filter_result, field_name, None))
                if state:
                    return state
            return ""
        return LiveModelArmor._match_state_name(filter_result)

    @staticmethod
    def _map_response(response: Any) -> tuple[bool, tuple[str, ...]]:
        result = getattr(response, "sanitization_result", None)
        if result is None:
            # Fail closed: an unparseable verdict cannot clear the document.
            return (True, ("armor_unparseable",))
        matched: list[str] = []
        clean_signal = False
        filter_results = getattr(result, "filter_results", None) or {}
        for key, filter_result in filter_results.items():
            state = LiveModelArmor._filter_match_state(filter_result)
            if state.endswith("NO_MATCH_FOUND"):
                clean_signal = True
            elif state.endswith("MATCH_FOUND"):
                matched.append(str(key).lower())
        if matched:
            return (True, tuple(f"armor:{name}" for name in matched))
        top_state = str(getattr(result, "filter_match_state", "")).upper()
        if top_state.endswith("MATCH_FOUND") and not top_state.endswith("NO_MATCH_FOUND"):
            return (True, ("armor:match_found",))
        if top_state.endswith("NO_MATCH_FOUND") or clean_signal:
            return (False, ())
        # Fail closed: no recognizable verdict signal.
        return (True, ("armor_unparseable",))

    def _record(self, text: str, blocked: bool, latency_ms: float) -> None:
        self.metrics.sanitize_calls += 1
        self.metrics.blocked_calls += 1 if blocked else 0
        self.metrics.total_latency_ms += latency_ms
        self.metrics.estimated_input_tokens += max(1, len(text) // 4)

    def sanitize(self, text: str) -> ArmorVerdict:
        start = time.perf_counter()
        try:
            response = self._get_client().sanitize_user_prompt(request=self._sanitize_request(text))
            blocked, codes = self._map_response(response)
        except Exception:  # noqa: BLE001 — armor is fail-closed: block on any API failure
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._record(text, True, latency_ms)
            return ArmorVerdict(True, ("armor_unavailable",), (), _LAYER_MANAGED, latency_ms)
        latency_ms = (time.perf_counter() - start) * 1000.0
        self._record(text, blocked, latency_ms)
        return ArmorVerdict(blocked, codes, (), _LAYER_MANAGED, latency_ms)

    @staticmethod
    def _build_template(modelarmor_v1: Any, config: ArmorTemplateConfig) -> Any:
        pi_settings = None
        if config.pi_and_jailbreak_enabled:
            pi_settings = modelarmor_v1.PiAndJailbreakFilterSettings(
                filter_enforcement=(
                    modelarmor_v1.PiAndJailbreakFilterSettings.PiAndJailbreakFilterEnforcement.ENABLED
                ),
                confidence_level=modelarmor_v1.DetectionConfidenceLevel[
                    config.pi_and_jailbreak_confidence
                ],
            )
        uri_settings = None
        if config.malicious_uri_enabled:
            uri_settings = modelarmor_v1.MaliciousUriFilterSettings(
                filter_enforcement=(
                    modelarmor_v1.MaliciousUriFilterSettings.MaliciousUriFilterEnforcement.ENABLED
                ),
            )
        return modelarmor_v1.Template(
            filter_config=modelarmor_v1.FilterConfig(
                pi_and_jailbreak_filter_settings=pi_settings,
                malicious_uri_filter_settings=uri_settings,
            )
        )

    def ensure_template(self, config: ArmorTemplateConfig | None = None) -> str:
        """Create the template when missing; return its managed resource name."""
        from google.api_core import exceptions as core_exceptions
        from google.cloud import modelarmor_v1

        client = self._get_client()
        try:
            client.get_template(request=modelarmor_v1.GetTemplateRequest(name=self.template_name))
            return self.template_name
        except core_exceptions.NotFound:
            pass
        client.create_template(
            request=modelarmor_v1.CreateTemplateRequest(
                parent=f"projects/{self._project}/locations/{self._location}",
                template_id=self._template_id,
                template=self._build_template(modelarmor_v1, config or ArmorTemplateConfig()),
            )
        )
        return self.template_name


def run_armor(text: str, managed: ModelArmorModel | None = None) -> ArmorVerdict:
    """Pipeline wrapper: project rules always; managed verdict layers on top."""
    start = time.perf_counter()
    hits = screen_project_rules(text)
    reason_codes = [hit.reason_code for hit in hits]
    rule_ids = [hit.rule_id for hit in hits]
    managed_verdict = managed.sanitize(text) if managed is not None else None
    if managed_verdict is not None and managed_verdict.blocked:
        reason_codes.extend(managed_verdict.reason_codes)
        rule_ids.extend(managed_verdict.rule_ids)
    blocked = bool(hits) or (managed_verdict is not None and managed_verdict.blocked)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return ArmorVerdict(blocked, tuple(reason_codes), tuple(rule_ids), _LAYER_COMBINED, latency_ms)
