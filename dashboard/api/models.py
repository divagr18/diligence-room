"""Dashboard API response models (BUILD_PLAN D8-M4, pulled early for the
Executive Deal Room frontend, vision §15).

Read-only DTOs returned by ``dashboard.api.app``. Field names mirror the
storage models (``memory.findings``, registry manifests, event log) so the
frontend contract stays honest to the data layer.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agents.negotiation.drafts import NegotiationArtifactKind


class TraceNodeKind(StrEnum):
    DOCUMENT = "document"
    AGENT = "agent"
    GATEWAY = "gateway"
    FINDING = "finding"
    ESCALATION = "escalation"


class DealSummary(BaseModel):
    deal_id: str
    name: str
    target: str
    deal_type: str
    health: str
    health_tone: str
    critical_findings: int
    high_findings: int
    open_questions: int
    documents_reviewed: int
    agents_active: int
    security_blocked: int
    updated_at: str


class WorkstreamProgress(BaseModel):
    workstream: str
    label: str
    documents: int
    findings: int
    progress: int


class EvidenceItem(BaseModel):
    verbatim_span: str
    document_id: str
    chunk_ref: str | None = None


class TraceStep(BaseModel):
    ts: str
    stage: str
    actor: str
    detail: str


class TraceNode(BaseModel):
    kind: TraceNodeKind
    node_id: str
    label: str
    detail: str


class TraceEdge(BaseModel):
    from_id: str
    to_id: str
    label: str


class FindingGraph(BaseModel):
    finding_id: str
    nodes: list[TraceNode]
    edges: list[TraceEdge]


class FindingListItem(BaseModel):
    finding_id: str
    title: str
    severity: str
    workstream: str
    owner: str
    confidence: float
    status: str
    documents: int
    created_at: str
    updated_at: str


class FindingDetail(FindingListItem):
    summary: str
    evidence: list[EvidenceItem]
    source_documents: list[str]
    affected_entities: list[str]
    contributing_agents: list[str]
    related_findings: list[str]
    questions: list[str]
    trace: list[TraceStep]
    graph: FindingGraph | None = None


class QuarantineItem(BaseModel):
    document_id: str
    layer: str
    reason_codes: list[str]
    rule_ids: list[str]
    attack_class: str
    ts: str


class SecurityFeedItem(BaseModel):
    ts: str
    kind: str
    outcome: str
    subject: str
    detail: str


class ScorecardGroup(BaseModel):
    group: str
    blocked: int
    total: int


class SecurityBundle(BaseModel):
    quarantined: list[QuarantineItem]
    feed: list[SecurityFeedItem]
    scorecard: list[ScorecardGroup]
    total_blocked: int


class InboxEntry(BaseModel):
    finding_id: str
    title: str
    severity: str
    workstream: str
    owner: str
    message: str
    status: str
    created_at: str


class AgentOut(BaseModel):
    agent_id: str
    name: str
    workstream: str
    version: str
    model_id: str
    approved: bool
    deployment_status: str
    rollback_target: str | None
    eval_score: float | None
    capabilities: list[str]


class DocumentOut(BaseModel):
    document_id: str
    format: str
    mime: str
    needs_ocr: bool
    size_bytes: int
    page_count: int | None
    checksum: str
    doc_type: str
    workstream: str | None
    confidence: float
    security_status: str


class DealBundle(BaseModel):
    summary: DealSummary
    workstreams: list[WorkstreamProgress]
    inbox: list[InboxEntry]


class NegotiationDraftOut(BaseModel):
    draft_id: str
    deal_id: str
    finding_id: str
    kind: NegotiationArtifactKind
    state: str
    body: str
    approved_by: str | None
    created_at: str
    updated_at: str


class NegotiationDraftRequest(BaseModel):
    finding_id: str = Field(min_length=1)
    kind: NegotiationArtifactKind


class ApproveRequest(BaseModel):
    approver: str = Field(min_length=1)
