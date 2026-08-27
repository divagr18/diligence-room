"""Dashboard HTTP API (BUILD_PLAN D8-M4, pulled early; vision §15).

Read-only endpoints over the demo data plane (``dashboard.api.data``) that
back the Executive Deal Room frontend:

- GET /api/health                  liveness probe
- GET /api/deal                    deal summary + workstreams + inbox
- GET /api/findings                finding list (sortable/filterable client-side)
- GET /api/findings/{finding_id}   finding detail (evidence + trace)
- GET /api/security                quarantined docs + feed + scorecard
- GET /api/registry                agent roster (manifests)
- GET /api/negotiation             drafts for a finding (?finding_id=)
- POST /api/negotiation/drafts     generate + submit a draft (kind-branched)
- POST /api/negotiation/{id}/approve   pending_approval -> approved (human)
- POST /api/negotiation/{id}/send      approved -> send_logged

The negotiation endpoints are client-backed (503 without a Firestore client)
and keep the CUTLINE-1 machine: draft -> pending_approval -> approved ->
send_logged, confidence-gated below the candidate threshold; every transition
is persisted to the deal event log (vision §11).

CORS is open for local dev (Vite at 5173); Cloud Run deploy front-door auth is
Day 11 work.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google.cloud import firestore

from agents.negotiation.drafts import (
    DraftNotFound,
    DraftRefused,
    InvalidNegotiationTransition,
    NegotiationDraft,
    NegotiationState,
    NegotiationStore,
    approve_draft,
    generate_draft,
    record_send,
    submit_for_approval,
)
from dashboard.api import data, documents
from dashboard.api.models import (
    AgentOut,
    ApproveRequest,
    DealBundle,
    FindingDetail,
    FindingListItem,
    NegotiationDraftOut,
    NegotiationDraftRequest,
    SecurityBundle,
)
from identity.human_authz import Role, can_view
from memory.db import make_client
from memory.event_log import EventLog, EventLogPublisher
from memory.findings import FindingNotFoundError, FindingStatus
from registry.models import AgentManifest, Workstream


@dataclass(frozen=True, slots=True)
class _ViewableRow:
    workstream: Workstream
    status: FindingStatus


def _visible(role: Role, workstream: str, status: str) -> bool:
    return can_view(role, _ViewableRow(Workstream(workstream), FindingStatus(status)))


def create_app(
    registry_manifests: Sequence[AgentManifest] | None = None,
    client: firestore.Client | None = None,
) -> FastAPI:
    """Build the dashboard API; ``registry_manifests`` swaps the Registry view
    onto live-store manifests (post publish/rollback) instead of the seed, and
    ``client`` swaps the Security view onto live red-team tallies and activates
    the negotiation endpoints (draft/approve/send) instead of the demo data.
    When ``FIRESTORE_EMULATOR_HOST`` is set and no client is supplied, an
    emulator client is built so the dev shell serves live numbers; without
    either, the no-client demo shell stays green and negotiation requests get
    a 503."""
    live_client = client
    if live_client is None and os.environ.get("FIRESTORE_EMULATOR_HOST"):
        live_client = make_client(os.environ.get("GOOGLE_CLOUD_PROJECT", "diligence-room"))
    publisher = EventLogPublisher(EventLog(live_client)) if live_client is not None else None
    app = FastAPI(title="Diligence Room Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def _negotiation_client() -> firestore.Client:
        if live_client is None:
            raise HTTPException(
                status_code=503,
                detail="negotiation endpoints require a Firestore-backed client",
            )
        return live_client

    def _draft_out(draft: NegotiationDraft) -> NegotiationDraftOut:
        return NegotiationDraftOut(
            draft_id=draft.draft_id,
            deal_id=draft.deal_id,
            finding_id=draft.finding_id,
            kind=draft.kind,
            state=draft.state.value,
            body=draft.body,
            approved_by=draft.approved_by,
            created_at=draft.created_at.isoformat(),
            updated_at=draft.updated_at.isoformat(),
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "deal": data.DEAL_ID}

    @app.get("/api/deal", response_model=DealBundle)
    def deal(role: Role = Role.DEAL_LEAD) -> DealBundle:
        bundle = data.build_deal_bundle()
        return DealBundle(
            summary=bundle.summary,
            workstreams=bundle.workstreams,
            inbox=[
                entry for entry in bundle.inbox if _visible(role, entry.workstream, entry.status)
            ],
        )

    @app.get("/api/findings", response_model=list[FindingListItem])
    def findings(role: Role = Role.DEAL_LEAD) -> list[FindingListItem]:
        items = data.build_findings()
        return [item for item in items if _visible(role, item.workstream, item.status)]

    @app.get("/api/findings/{finding_id}", response_model=FindingDetail)
    def finding_detail(finding_id: str, role: Role = Role.DEAL_LEAD) -> FindingDetail:
        detail = data.build_finding_detail(finding_id)
        if detail is None or not _visible(role, detail.workstream, detail.status):
            raise HTTPException(status_code=404, detail=f"finding {finding_id!r} not found")
        return detail

    @app.get("/api/security", response_model=SecurityBundle)
    def security() -> SecurityBundle:
        return data.build_security_bundle(live_client)

    @app.get("/api/registry", response_model=list[AgentOut])
    def registry() -> list[AgentOut]:
        return data.build_agents(registry_manifests)

    @app.get("/api/documents/{document_id}")
    def document_file(document_id: str) -> FileResponse:
        path = documents.resolve_document_path(document_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
        return FileResponse(path)

    @app.get("/api/documents/{document_id}/locate")
    def document_locate(document_id: str, span: str = Query(default="")) -> dict[str, object]:
        locator = documents.locate_evidence(document_id, span)
        if locator is None:
            raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
        return locator

    @app.exception_handler(DraftNotFound)
    def _draft_not_found(request: Request, exc: DraftNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"draft {exc} not found"})

    @app.exception_handler(FindingNotFoundError)
    def _finding_not_found(request: Request, exc: FindingNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"finding {exc} not found"})

    @app.exception_handler(DraftRefused)
    def _draft_refused(request: Request, exc: DraftRefused) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidNegotiationTransition)
    def _bad_transition(request: Request, exc: InvalidNegotiationTransition) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/negotiation", response_model=list[NegotiationDraftOut])
    def negotiation_drafts(finding_id: str = Query(min_length=1)) -> list[NegotiationDraftOut]:
        client = _negotiation_client()
        drafts = NegotiationStore(client).list_for_finding(data.DEAL_ID, finding_id)
        return [_draft_out(draft) for draft in sorted(drafts, key=lambda d: d.created_at)]

    @app.post("/api/negotiation/drafts", response_model=NegotiationDraftOut)
    def create_negotiation_draft(payload: NegotiationDraftRequest) -> NegotiationDraftOut:
        client = _negotiation_client()
        draft = generate_draft(
            client,
            data.DEAL_ID,
            payload.finding_id,
            payload.kind,
            publisher=publisher,
        )
        if draft.state is NegotiationState.DRAFT:
            draft = submit_for_approval(client, data.DEAL_ID, draft.draft_id, publisher=publisher)
        return _draft_out(draft)

    @app.post("/api/negotiation/{draft_id}/approve", response_model=NegotiationDraftOut)
    def approve_negotiation_draft(draft_id: str, payload: ApproveRequest) -> NegotiationDraftOut:
        client = _negotiation_client()
        draft = approve_draft(
            client,
            data.DEAL_ID,
            draft_id,
            approver=payload.approver,
            publisher=publisher,
        )
        return _draft_out(draft)

    @app.post("/api/negotiation/{draft_id}/send", response_model=NegotiationDraftOut)
    def send_negotiation_draft(draft_id: str) -> NegotiationDraftOut:
        client = _negotiation_client()
        draft = record_send(client, data.DEAL_ID, draft_id, publisher=publisher)
        return _draft_out(draft)

    return app


app: FastAPI = create_app()
