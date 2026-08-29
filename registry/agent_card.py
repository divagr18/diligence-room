"""A2A Agent Cards derived from the Firestore manifests.

Lives in ``registry/`` because the manifest is the source of truth: the card is
a projection of it, never a second roster. Two consumers share this module —
``infra/agent_registry.py`` publishes cards into the Gemini Enterprise Agent
Platform Agent Registry, and the gateway serves the same card at
``GET /agents/{agent_id}`` so the URL published in the catalogue resolves.

Platform constraints encoded here, each learned from a rejection:

* ``service_id`` must match ``^[a-z][a-z0-9-]{2,61}[a-z0-9]$``. Agent ids use
  underscores (``ip_tech``) and three of them are under the four-character
  minimum (``esg``, ``hr``, ``tax``), so ids are prefixed and hyphenated.
* ``protocolVersion`` is required; the card is rejected without it.
* Each registered service needs a distinct interface URL, so the card points at
  the agent's own path on the gateway rather than the gateway root.
"""

from __future__ import annotations

from typing import Any, Final

from registry.models import AgentManifest

A2A_PROTOCOL_VERSION: Final[str] = "0.3.0"
SERVICE_ID_PREFIX: Final[str] = "diligence-"
DEFAULT_GATEWAY_URL: Final[str] = "https://gateway-378831539922.asia-south1.run.app"


def service_id(manifest: AgentManifest) -> str:
    """Registry service id for *manifest*, legal under the platform pattern."""
    return f"{SERVICE_ID_PREFIX}{manifest.agent_id.replace('_', '-')}"


def display_name(manifest: AgentManifest) -> str:
    """Display name safe to pass through the Windows gcloud shim.

    "IP & Technology Agent" would otherwise be split by cmd.exe at the
    ampersand, truncating the command.
    """
    return manifest.name.replace(" & ", " and ")


def agent_url(manifest: AgentManifest, gateway_url: str = DEFAULT_GATEWAY_URL) -> str:
    """Where this agent is reachable.

    Agents are not directly addressable: every call crosses the deny-default
    Agent Gateway, so the published address is the agent's path on the gateway,
    which serves its card.
    """
    return f"{gateway_url.rstrip('/')}/agents/{manifest.agent_id}"


def build_agent_card(
    manifest: AgentManifest, gateway_url: str = DEFAULT_GATEWAY_URL
) -> dict[str, Any]:
    """Render one manifest as an A2A Agent Card.

    Every field derives from the manifest, so a catalogue entry cannot claim a
    capability the fleet does not have.
    """
    skills: list[dict[str, Any]] = [
        {
            "id": f"{manifest.agent_id}.{capability.replace(' ', '-')}",
            "name": capability,
            "description": f"{capability} for the {manifest.workstream.value} workstream",
            "tags": [manifest.workstream.value],
        }
        for capability in manifest.capabilities
    ]
    url = agent_url(manifest, gateway_url)
    return {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": manifest.name,
        "description": (
            f"{manifest.name} for M&A due diligence. Reads only "
            f"{', '.join(manifest.supported_document_types)}. External "
            f"communication is {manifest.external_communication}; every call is "
            f"mediated by the deny-default Agent Gateway under identity "
            f"{manifest.required_identity}."
        ),
        "url": url,
        "version": manifest.version,
        "provider": {"organization": manifest.owner, "url": url},
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": skills,
    }
