/* API client — typed to the FastAPI contract in dashboard/api/models.py. */

import { useEffect, useState } from "react";

export interface DealSummary {
  deal_id: string;
  name: string;
  target: string;
  deal_type: string;
  health: string;
  health_tone: string;
  critical_findings: number;
  high_findings: number;
  open_questions: number;
  documents_reviewed: number;
  agents_active: number;
  security_blocked: number;
  updated_at: string;
}

export interface WorkstreamProgress {
  workstream: string;
  label: string;
  documents: number;
  findings: number;
  progress: number;
}

export interface InboxEntry {
  finding_id: string;
  title: string;
  severity: string;
  workstream: string;
  owner: string;
  message: string;
  status: string;
  created_at: string;
}

export interface DealBundle {
  summary: DealSummary;
  workstreams: WorkstreamProgress[];
  inbox: InboxEntry[];
}

export interface FindingListItem {
  finding_id: string;
  title: string;
  severity: string;
  workstream: string;
  owner: string;
  confidence: number;
  status: string;
  documents: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceItem {
  verbatim_span: string;
  document_id: string;
  chunk_ref: string | null;
}

export interface TraceStep {
  ts: string;
  stage: string;
  actor: string;
  detail: string;
}

export type TraceNodeKind = "document" | "agent" | "gateway" | "finding" | "escalation";

export interface TraceNode {
  kind: TraceNodeKind;
  node_id: string;
  label: string;
  detail: string;
}

export interface TraceEdge {
  from_id: string;
  to_id: string;
  label: string;
}

export interface FindingGraph {
  finding_id: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
}

export interface FindingDetail extends FindingListItem {
  summary: string;
  evidence: EvidenceItem[];
  source_documents: string[];
  affected_entities: string[];
  contributing_agents: string[];
  related_findings: string[];
  questions: string[];
  trace: TraceStep[];
  graph: FindingGraph | null;
}

export interface QuarantineItem {
  document_id: string;
  layer: string;
  reason_codes: string[];
  rule_ids: string[];
  attack_class: string;
  ts: string;
}

export interface SecurityFeedItem {
  ts: string;
  kind: string;
  outcome: string;
  subject: string;
  detail: string;
}

export interface ScorecardGroup {
  group: string;
  blocked: number;
  total: number;
}

export interface SecurityBundle {
  quarantined: QuarantineItem[];
  feed: SecurityFeedItem[];
  scorecard: ScorecardGroup[];
  total_blocked: number;
}

export interface AgentOut {
  agent_id: string;
  name: string;
  workstream: string;
  version: string;
  model_id: string;
  approved: boolean;
  deployment_status: string;
  rollback_target: string | null;
  eval_score: number | null;
  capabilities: string[];
}

/* Document locators — GET /api/documents/{id}/locate. The backend reuses the
   ingestion parser's extraction, so a span already verified against the parsed
   text is guaranteed to resolve to a page (PDF) or sheet+row (XLSX). */
export interface PdfLocator {
  kind: "pdf";
  page: number | null;
  page_count: number;
}

export interface XlsxLocator {
  kind: "xlsx";
  sheet: string | null;
  row_index: number | null;
  headers: string[];
  rows: string[][];
}

export interface OtherLocator {
  kind: string;
  page: null;
  page_count: null;
}

export type DocumentLocator = PdfLocator | XlsxLocator | OtherLocator;

export type NegotiationKind = "clause_redline" | "seller_request" | "clarification_question";

export type NegotiationDraftState = "draft" | "pending_approval" | "approved" | "send_logged";

export interface NegotiationDraft {
  draft_id: string;
  deal_id: string;
  finding_id: string;
  kind: NegotiationKind;
  state: NegotiationDraftState;
  body: string;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
}

export const NEGOTIATION_KIND_LABEL: Record<NegotiationKind, string> = {
  clause_redline: "Clause redline",
  seller_request: "Seller request",
  clarification_question: "Clarification questions",
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText} for ${path}`;
    try {
      const err = (await res.json()) as { detail?: unknown };
      if (typeof err.detail === "string") detail = err.detail;
    } catch {
      /* non-JSON error body: keep the status-line detail */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  deal: () => fetchJson<DealBundle>("/api/deal"),
  findings: () => fetchJson<FindingListItem[]>("/api/findings"),
  finding: (id: string) => fetchJson<FindingDetail>(`/api/findings/${encodeURIComponent(id)}`),
  security: () => fetchJson<SecurityBundle>("/api/security"),
  registry: () => fetchJson<AgentOut[]>("/api/registry"),
  locate: (documentId: string, span: string) =>
    fetchJson<DocumentLocator>(
      `/api/documents/${encodeURIComponent(documentId)}/locate?span=${encodeURIComponent(span)}`,
    ),
  negotiationsFor: (findingId: string) =>
    fetchJson<NegotiationDraft[]>(
      `/api/negotiation?finding_id=${encodeURIComponent(findingId)}`,
    ),
  createNegotiationDraft: (findingId: string, kind: NegotiationKind) =>
    postJson<NegotiationDraft>("/api/negotiation/drafts", { finding_id: findingId, kind }),
  approveNegotiationDraft: (draftId: string, approver: string) =>
    postJson<NegotiationDraft>(`/api/negotiation/${encodeURIComponent(draftId)}/approve`, {
      approver,
    }),
  sendNegotiationDraft: (draftId: string) =>
    postJson<NegotiationDraft>(`/api/negotiation/${encodeURIComponent(draftId)}/send`),
};

/* Served-file URL for the document viewer (GET /api/documents/{id}). */
export function documentUrl(documentId: string): string {
  return `/api/documents/${encodeURIComponent(documentId)}`;
}

export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[] = [], pollIntervalMs = 0) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({
    loading: true,
  });
  useEffect(() => {
    let alive = true;
    const run = () => {
      fn()
        .then((data) => alive && setState({ data, loading: false }))
        .catch((err: unknown) =>
          alive && setState({ error: err instanceof Error ? err.message : String(err), loading: false }),
        );
    };
    setState({ loading: true });
    run();
    let timer: number | undefined;
    if (pollIntervalMs > 0) {
      timer = window.setInterval(run, pollIntervalMs);
    }
    return () => {
      alive = false;
      if (timer !== undefined) window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

export const WORKSTREAM_LABEL: Record<string, string> = {
  legal: "Legal",
  finance: "Finance",
  hr: "HR",
  ip_tech: "IP & Tech",
  tax: "Tax",
  regulatory: "Regulatory",
  esg: "ESG",
  real_estate: "Real Estate",
};

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ") + "Z";
}

export function fmtPct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}
