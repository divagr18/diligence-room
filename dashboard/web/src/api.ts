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

export interface FindingDetail extends FindingListItem {
  summary: string;
  evidence: EvidenceItem[];
  source_documents: string[];
  affected_entities: string[];
  contributing_agents: string[];
  related_findings: string[];
  questions: string[];
  trace: TraceStep[];
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

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return (await res.json()) as T;
}

export const api = {
  deal: () => fetchJson<DealBundle>("/api/deal"),
  findings: () => fetchJson<FindingListItem[]>("/api/findings"),
  finding: (id: string) => fetchJson<FindingDetail>(`/api/findings/${encodeURIComponent(id)}`),
  security: () => fetchJson<SecurityBundle>("/api/security"),
  registry: () => fetchJson<AgentOut[]>("/api/registry"),
};

export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[] = []) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({
    loading: true,
  });
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    fn()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((err: unknown) =>
        alive && setState({ error: err instanceof Error ? err.message : String(err), loading: false }),
      );
    return () => {
      alive = false;
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
