"""Agent Platform Memory Bank — durable cross-session memory about entities.

Deliberately *not* a second findings store. Firestore keeps the append-only
event log and the evidence-gated findings; Memory Bank holds what the fleet has
learned about a counterparty, so a session opened weeks later starts knowing
that Meridian Logistics carries a change-of-control right, without replaying the
deal. That is the "persistent, secure cross-session context over extended
timelines" the Fortified Enterprise Fleet track asks for.

Design notes worth keeping:

* ``VertexAiMemoryBankService.add_memory`` and ``search_memory`` are **async**,
  and everything around them here is synchronous. This module is the seam: it
  exposes a sync facade and owns the event-loop handling, rather than turning the
  coordinator async for one call.
* Live use is gated on ``DILIGENCE_MEMORY_BANK_ENABLED=1``, mirroring
  ``ingestion.sentinel.GemmaSentinel``, so the offline battery never reaches the
  network and ``memory_bank_from_env`` returns ``None`` by default.
* Scope is ``(app_name="diligence-room", user_id=deal_id)``: one deal is one
  long-running subject, which is the isolation boundary the track describes.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol

APP_NAME: Final[str] = "diligence-room"
_ENABLED_FLAG: Final[str] = "DILIGENCE_MEMORY_BANK_ENABLED"
_PROJECT_ENV: Final[str] = "GOOGLE_CLOUD_PROJECT"
_LOCATION_ENV: Final[str] = "DILIGENCE_MEMORY_BANK_LOCATION"
_ENGINE_ENV: Final[str] = "DILIGENCE_AGENT_ENGINE_ID"

DEFAULT_LOCATION: Final[str] = "us-central1"
# The deployed Agent Runtime; Memory Bank attaches to a runtime instance.
DEFAULT_AGENT_ENGINE_ID: Final[str] = "7141202128323739648"


@dataclass(frozen=True, slots=True)
class EntityMemory:
    """One durable fact about a counterparty, scoped to a deal."""

    deal_id: str
    entity: str
    summary: str
    finding_id: str

    def as_text(self) -> str:
        """The stored form: entity first, so a similarity search on a name hits."""
        return f"{self.entity}: {self.summary} (finding {self.finding_id})"


class MemoryBank(Protocol):
    def remember_entity(self, memory: EntityMemory) -> None: ...

    def recall(self, deal_id: str, query: str) -> tuple[str, ...]: ...


@dataclass
class FakeMemoryBank:
    """In-process stand-in used by tests and any offline run.

    Matches the live scoping so a test can assert on isolation between deals.
    """

    written: list[EntityMemory] = field(default_factory=list)

    def remember_entity(self, memory: EntityMemory) -> None:
        self.written.append(memory)

    def recall(self, deal_id: str, query: str) -> tuple[str, ...]:
        needle = query.casefold()
        return tuple(
            m.as_text()
            for m in self.written
            if m.deal_id == deal_id and needle in m.as_text().casefold()
        )


def _run_sync(coro: Any) -> Any:
    """Run *coro* to completion from synchronous code.

    ``asyncio.run`` raises if a loop is already running (for example when called
    from inside an async web handler), so in that case the coroutine is driven on
    its own loop in a worker thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class LiveMemoryBank:
    """Memory Bank client on the deployed Agent Runtime instance.

    Constructed only when ``DILIGENCE_MEMORY_BANK_ENABLED=1``; the underlying
    service is built lazily so importing this module stays cheap and offline.
    """

    def __init__(
        self,
        project: str = "",
        location: str = "",
        agent_engine_id: str = "",
    ) -> None:
        if os.environ.get(_ENABLED_FLAG) != "1":
            raise RuntimeError(f"LiveMemoryBank disabled: set {_ENABLED_FLAG}=1")
        resolved_project = project or os.environ.get(_PROJECT_ENV, "")
        if not resolved_project:
            raise RuntimeError(f"LiveMemoryBank needs a project: set {_PROJECT_ENV}")
        self._project = resolved_project
        self._location = location or os.environ.get(_LOCATION_ENV, DEFAULT_LOCATION)
        self._agent_engine_id = agent_engine_id or os.environ.get(
            _ENGINE_ENV, DEFAULT_AGENT_ENGINE_ID
        )
        self._service: Any | None = None

    def _get_service(self) -> Any:
        if self._service is None:
            from google.adk.memory import VertexAiMemoryBankService

            self._service = VertexAiMemoryBankService(
                project=self._project,
                location=self._location,
                agent_engine_id=self._agent_engine_id,
            )
        return self._service

    def remember_entity(self, memory: EntityMemory) -> None:
        from google.adk.memory.memory_entry import MemoryEntry
        from google.genai import types

        entry = MemoryEntry(
            content=types.Content(role="user", parts=[types.Part(text=memory.as_text())]),
            author="coordinator",
            timestamp=datetime.now(UTC).isoformat(),
        )
        _run_sync(
            self._get_service().add_memory(
                app_name=APP_NAME,
                user_id=memory.deal_id,
                memories=[entry],
            )
        )

    def recall(self, deal_id: str, query: str) -> tuple[str, ...]:
        response = _run_sync(
            self._get_service().search_memory(
                app_name=APP_NAME,
                user_id=deal_id,
                query=query,
            )
        )
        out: list[str] = []
        for memory in getattr(response, "memories", []) or []:
            content = getattr(memory, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", "")
                if text:
                    out.append(str(text))
        return tuple(out)


def memory_bank_from_env() -> MemoryBank | None:
    """Return a live Memory Bank when enabled, else ``None``.

    ``None`` is the normal offline answer, and every caller treats it as "skip",
    so the flag being unset can never fail a run.
    """
    if os.environ.get(_ENABLED_FLAG) != "1":
        return None
    try:
        return LiveMemoryBank()
    except RuntimeError:
        return None
