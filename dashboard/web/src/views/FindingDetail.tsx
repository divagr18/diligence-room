import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api, fmtPct, fmtTime, useAsync, WORKSTREAM_LABEL } from "../api";
import {
  Card,
  ErrorState,
  LoadingState,
  SectionHeader,
  SeverityBadge,
  StatusPill,
  Tag,
} from "../components/ui";

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="overline">{label}</div>
      <div className="mt-1.5 text-[13px] text-ink2">{children}</div>
    </div>
  );
}

export default function FindingDetail() {
  const { findingId = "" } = useParams();
  const { data, error, loading } = useAsync(() => api.finding(findingId), [findingId]);

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
          <div className="overline">Confidence</div>
          <div className="tabular mt-1.5 font-mono text-[22px] font-medium text-ink1">
            {fmtPct(data.confidence)}
          </div>
        </div>
        <div className="rounded-lg border border-line bg-card px-4 py-3">
          <div className="overline">Source documents</div>
          <div className="tabular mt-1.5 font-mono text-[22px] font-medium text-ink1">
            {data.source_documents.length}
          </div>
        </div>
        <div className="rounded-lg border border-line bg-card px-4 py-3">
          <div className="overline">Contributing agents</div>
          <div className="tabular mt-1.5 font-mono text-[22px] font-medium text-ink1">
            {data.contributing_agents.length}
          </div>
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
                  <Tag>{ev.document_id}</Tag>
                  {ev.chunk_ref ? <Tag>{ev.chunk_ref}</Tag> : null}
                  <span className="font-mono text-[11px] text-ink4">
                    span verified against parsed source
                  </span>
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
    </div>
  );
}
