import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  Check,
  ExternalLink,
  FileText,
  Flag,
  Inbox,
  Network,
  PenLine,
  Send,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  api,
  fmtPct,
  fmtTime,
  NEGOTIATION_KIND_LABEL,
  useAsync,
  WORKSTREAM_LABEL,
  type EvidenceItem,
  type NegotiationDraft,
  type NegotiationKind,
  type TraceNodeKind,
} from "../api";
import DocumentViewer from "../components/DocumentViewer";
import {
  Card,
  ErrorState,
  LoadingState,
  SectionHeader,
  SeverityBadge,
  StatusPill,
  Tag,
} from "../components/ui";

const GRAPH_ICONS: Record<TraceNodeKind, LucideIcon> = {
  document: FileText,
  agent: Bot,
  gateway: Network,
  finding: Flag,
  escalation: Inbox,
};

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[12px] font-medium text-ink3">{label}</div>
      <div className="mt-1.5 text-[13px] text-ink2">{children}</div>
    </div>
  );
}

const NEGOTIATION_KINDS: readonly NegotiationKind[] = [
  "clause_redline",
  "seller_request",
  "clarification_question",
];

const PRIMARY_BUTTON =
  "inline-flex items-center gap-1.5 rounded-md border border-line2 bg-card2 px-3 py-1.5 " +
  "text-[13px] font-medium text-ink1 transition-colors duration-150 hover:border-line3 " +
  "disabled:pointer-events-none disabled:opacity-50";

const GHOST_BUTTON =
  "inline-flex items-center gap-1.5 rounded-md border border-line bg-transparent px-3 py-1.5 " +
  "text-[13px] font-medium text-ink2 transition-colors duration-150 hover:bg-card2 hover:text-ink1 " +
  "disabled:pointer-events-none disabled:opacity-50";

function DraftCard({
  draft,
  busy,
  onApprove,
  onSend,
}: {
  draft: NegotiationDraft;
  busy: boolean;
  onApprove: (draft: NegotiationDraft) => void;
  onSend: (draft: NegotiationDraft) => void;
}) {
  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="text-[13px] font-medium text-ink1">
          {NEGOTIATION_KIND_LABEL[draft.kind]}
        </span>
        <StatusPill status={draft.state.replace("_", " ")} />
        <span className="font-mono text-[11px] text-ink4 tabular">
          {draft.draft_id} · updated {fmtTime(draft.updated_at)}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {draft.state === "pending_approval" && (
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={busy}
              onClick={() => onApprove(draft)}
            >
              <Check className="size-3.5" strokeWidth={2} aria-hidden />
              Approve
            </button>
          )}
          {draft.state === "approved" && (
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={busy}
              onClick={() => onSend(draft)}
            >
              <Send className="size-3.5" strokeWidth={2} aria-hidden />
              Record send
            </button>
          )}
        </span>
      </div>
      {draft.approved_by && (
        <p className="mt-2 font-mono text-[12px] text-ink3">approved by {draft.approved_by}</p>
      )}
      {draft.state === "send_logged" && (
        <p className="mt-2 flex items-center gap-1.5 font-mono text-[12px] text-ok">
          <span className="size-1.5 rounded-full bg-ok" aria-hidden />
          send logged — external channel recorded in the event log
        </p>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-ink3 transition-colors duration-150 hover:text-ink1">
          draft body
        </summary>
        <pre className="mt-2 overflow-x-auto border-t border-line pt-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-ink2">
          {draft.body}
        </pre>
      </details>
    </Card>
  );
}

function NegotiationPanel({ findingId }: { findingId: string }) {
  const [drafts, setDrafts] = useState<NegotiationDraft[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .negotiationsFor(findingId)
      .then((rows) => alive && setDrafts(rows))
      .catch(() => alive && setDrafts(null));
    return () => {
      alive = false;
    };
  }, [findingId]);

  if (drafts === null) return null;

  const run = async (action: () => Promise<NegotiationDraft>) => {
    setBusy(true);
    setNotice(null);
    try {
      await action();
      setDrafts(await api.negotiationsFor(findingId));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const draftKindsPresent = new Set(drafts.map((draft) => draft.kind));

  return (
    <section className="space-y-4">
      <SectionHeader title="Negotiation" meta="draft → human approval → logged send" />
      {notice && (
        <p className="flex items-center gap-1.5 font-mono text-[12px] text-deny">
          <span className="size-1.5 shrink-0 rounded-full bg-deny" aria-hidden />
          {notice}
        </p>
      )}
      {drafts.length === 0 && (
        <Card className="px-5 py-4">
          <p className="text-[13px] text-ink3">
            No negotiation artifacts drafted for this finding yet. Generation is
            confidence-gated and every draft waits on human approval before a send is logged.
          </p>
        </Card>
      )}
      {drafts.map((draft) => (
        <DraftCard
          key={draft.draft_id}
          draft={draft}
          busy={busy}
          onApprove={(d) =>
            void run(() => api.approveNegotiationDraft(d.draft_id, `deal-lead@${d.deal_id}`))
          }
          onSend={(d) => void run(() => api.sendNegotiationDraft(d.draft_id))}
        />
      ))}
      <div className="flex flex-wrap gap-2">
        {NEGOTIATION_KINDS.filter((kind) => !draftKindsPresent.has(kind)).map((kind) => (
          <button
            key={kind}
            type="button"
            className={GHOST_BUTTON}
            disabled={busy}
            onClick={() => void run(() => api.createNegotiationDraft(findingId, kind))}
          >
            <PenLine className="size-3.5" strokeWidth={1.75} aria-hidden />
            Draft {NEGOTIATION_KIND_LABEL[kind].toLowerCase()}
          </button>
        ))}
      </div>
    </section>
  );
}

export default function FindingDetail() {
  const { findingId = "" } = useParams();
  const { data, error, loading } = useAsync(() => api.finding(findingId), [findingId]);
  const [openEvidence, setOpenEvidence] = useState<EvidenceItem | null>(null);

  if (loading) return <LoadingState label={`finding ${findingId}`} />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  return (
    <div className="space-y-8">
      <div>
        <Link
          to="/findings"
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink3 transition-colors duration-150 hover:text-ink1"
        >
          <ArrowLeft className="size-3.5" strokeWidth={2} aria-hidden />
          Findings
        </Link>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <SeverityBadge severity={data.severity} />
          <StatusPill status={data.status} />
          <span className="font-mono text-[12px] text-ink4">{data.finding_id}</span>
        </div>
        <h1 className="mt-3 max-w-3xl text-[24px] font-medium leading-tight tracking-[-0.015em] text-ink1">
          {data.title}
        </h1>
        <p className="mt-1.5 font-mono text-[12px] text-ink4">
          {WORKSTREAM_LABEL[data.workstream] ?? data.workstream} · {data.owner} · created{" "}
          {fmtTime(data.created_at)} · updated {fmtTime(data.updated_at)}
        </p>
      </div>

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-line bg-card px-4 py-3">
          <div className="tabular font-mono text-[22px] font-medium text-ink1">
            {fmtPct(data.confidence)}
          </div>
          <div className="mt-2 text-[12px] font-medium text-ink3">Confidence</div>
        </div>
        <div className="rounded-lg border border-line bg-card px-4 py-3">
          <div className="tabular font-mono text-[22px] font-medium text-ink1">
            {data.source_documents.length}
          </div>
          <div className="mt-2 text-[12px] font-medium text-ink3">Source documents</div>
        </div>
        <div className="rounded-lg border border-line bg-card px-4 py-3">
          <div className="tabular font-mono text-[22px] font-medium text-ink1">
            {data.contributing_agents.length}
          </div>
          <div className="mt-2 text-[12px] font-medium text-ink3">Contributing agents</div>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader title="Summary" />
        <Card className="px-5 py-4">
          <p className="text-[14px] leading-relaxed text-ink2">{data.summary}</p>
        </Card>
      </section>

      <section className="space-y-4">
        <SectionHeader title="Evidence" meta="verbatim spans verified at write time" />
        {data.evidence.length === 0 ? (
          <p className="text-[13px] text-ink3">No evidence recorded.</p>
        ) : (
          <div className="space-y-3">
            {data.evidence.map((ev, i) => (
              <Card key={i} className="px-5 py-4">
                <blockquote className="border-l-2 border-line3 pl-4 text-[14px] italic leading-relaxed text-ink2">
                  “{ev.verbatim_span}”
                </blockquote>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOpenEvidence(ev)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-1.5 py-px font-mono text-[12px] text-ink2 transition-colors duration-150 hover:bg-card2 hover:text-ink1"
                  >
                    <FileText className="size-3" strokeWidth={1.75} aria-hidden />
                    {ev.document_id}
                  </button>
                  {ev.chunk_ref ? <Tag>{ev.chunk_ref}</Tag> : null}
                  <span className="font-mono text-[11px] text-ink4">
                    span verified against parsed source
                  </span>
                  <button
                    type="button"
                    onClick={() => setOpenEvidence(ev)}
                    className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-2.5 py-1 text-[12px] font-medium text-ink2 transition-colors duration-150 hover:bg-card2 hover:text-ink1"
                  >
                    <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden />
                    Open source
                  </button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <SectionHeader title="Scope" />
          <Card className="space-y-4 px-5 py-4">
            <MetaItem label="Affected entities">
              {data.affected_entities.length === 0 ? (
                <span className="text-ink4">None recorded</span>
              ) : (
                <span className="flex flex-wrap gap-1.5">
                  {data.affected_entities.map((e) => (
                    <Tag key={e}>{e}</Tag>
                  ))}
                </span>
              )}
            </MetaItem>
            <MetaItem label="Contributing agents">
              <span className="flex flex-col gap-1 font-mono text-[12px]">
                {data.contributing_agents.map((a) => (
                  <span key={a}>{a}</span>
                ))}
              </span>
            </MetaItem>
            <MetaItem label="Related findings">
              {data.related_findings.length === 0 ? (
                <span className="text-ink4">None</span>
              ) : (
                <span className="flex flex-wrap gap-1.5">
                  {data.related_findings.map((r) => (
                    <Link key={r} to={`/findings/${r}`} className="transition-colors duration-150 hover:text-accent">
                      <Tag>{r}</Tag>
                    </Link>
                  ))}
                </span>
              )}
            </MetaItem>
          </Card>
        </div>

        <div className="space-y-4">
          <SectionHeader title="Open questions" />
          <Card className="px-5 py-4">
            {data.questions.length === 0 ? (
              <p className="text-[13px] text-ink3">No open questions.</p>
            ) : (
              <ul className="space-y-2.5">
                {data.questions.map((q, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-ink2">
                    <span className="mt-[7px] size-1 shrink-0 rounded-full bg-ink4" aria-hidden />
                    {q}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </section>

      <NegotiationPanel findingId={data.finding_id} />

      {data.graph && (
        <section className="space-y-4">
          <SectionHeader title="Finding graph" meta="source docs → agents → gateway → finding" />
          <Card className="px-5 py-5">
            <ol className="relative space-y-4 border-l border-line pl-5">
              {data.graph.nodes.map((node) => {
                const Icon = GRAPH_ICONS[node.kind];
                return (
                  <li key={node.node_id} className="relative">
                    <span
                      className="absolute top-1 -left-[26.5px] size-2 rounded-full border border-line3 bg-card2"
                      aria-hidden
                    />
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Icon className="size-3.5 shrink-0 text-ink3" strokeWidth={1.7} aria-hidden />
                      <span className="font-mono text-[12px] font-medium text-ink1">{node.label}</span>
                      <Tag>{node.kind}</Tag>
                    </div>
                    <p className="mt-0.5 text-[13px] text-ink2">{node.detail}</p>
                  </li>
                );
              })}
            </ol>
            <div className="mt-4 space-y-1 border-t border-line pt-3">
              {data.graph.edges.map((edge, i) => (
                <div key={i} className="font-mono text-[11px] text-ink4">
                  {edge.from_id} <span className="text-ink3">→</span> {edge.to_id}
                  <span className="text-ink3"> · {edge.label}</span>
                </div>
              ))}
            </div>
          </Card>
        </section>
      )}

      <section className="space-y-4">
        <SectionHeader title="Trace" meta="audit trail: document → agents → gateway → finding" />
        <Card className="px-5 py-5">
          {data.trace.length === 0 ? (
            <p className="text-[13px] text-ink3">No trace steps recorded.</p>
          ) : (
            <ol className="relative space-y-5 border-l border-line pl-5">
              {data.trace.map((step, i) => (
                <li key={i} className="relative">
                  <span
                    className="absolute top-1.5 -left-[26.5px] size-2 rounded-full border border-line3 bg-card2"
                    aria-hidden
                  />
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                    <span className="font-mono text-[11px] text-ink4 tabular">{fmtTime(step.ts)}</span>
                    <span className="font-mono text-[12px] text-accent">{step.stage}</span>
                    <span className="font-mono text-[11px] text-ink4">{step.actor}</span>
                  </div>
                  <p className="mt-0.5 text-[13px] text-ink2">{step.detail}</p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </section>

      {openEvidence && (
        <DocumentViewer evidence={openEvidence} onClose={() => setOpenEvidence(null)} />
      )}
    </div>
  );
}
