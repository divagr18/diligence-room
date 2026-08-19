import { api, fmtTime, useAsync } from "../api";
import { ErrorState, LoadingState, ProgressBar, SectionHeader, StatTile } from "../components/ui";

export default function Overview() {
  const { data, error, loading } = useAsync(api.deal, []);

  if (loading) return <LoadingState label="deal summary" />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  const { summary, workstreams, inbox } = data;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-medium tracking-[-0.02em] text-ink1">
            {summary.name}
          </h1>
          <p className="mt-1 text-[13px] text-ink3">
            Target: <span className="text-ink2">{summary.target}</span>
            <span className="mx-2 text-ink4">·</span>
            <span className="font-mono text-[12px]">{summary.deal_id}</span>
          </p>
        </div>
        <div className="rounded-lg border border-line bg-card px-4 py-3 text-right">
          <div className="flex items-center justify-end gap-2">
            <span
              className={`size-2 rounded-full ${
                summary.health_tone === "critical" ? "bg-sev-critical" : "bg-ok"
              }`}
              aria-hidden
            />
            <span
              className={`text-[18px] font-medium tracking-tight ${
                summary.health_tone === "critical" ? "text-sev-critical" : "text-ok"
              }`}
            >
              {summary.health}
            </span>
          </div>
          <div className="mt-1 font-mono text-[11px] text-ink4">
            updated {fmtTime(summary.updated_at)}
          </div>
        </div>
      </header>

      <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatTile label="Critical" value={String(summary.critical_findings)} tone="critical" hint="escalated to deal lead" />
        <StatTile label="High" value={String(summary.high_findings)} tone="high" hint="open, owner assigned" />
        <StatTile label="Open questions" value={String(summary.open_questions)} hint="across workstreams" />
        <StatTile label="Docs reviewed" value={String(summary.documents_reviewed)} hint="ingested this deal" />
        <StatTile label="Agents active" value={String(summary.agents_active)} hint="of 8 registered" />
        <StatTile label="Blocked threats" value={String(summary.security_blocked)} hint="quarantined, never routed" />
      </section>

      <section className="space-y-4">
        <SectionHeader title="Workstreams" meta="document coverage and finding counts" />
        <div className="overflow-hidden rounded-lg border border-line bg-card">
          <div className="hidden grid-cols-[140px_1fr_120px_64px] gap-4 border-b border-line px-4 py-2.5 md:grid">
            <span className="text-[12px] font-medium text-ink3">Workstream</span>
            <span className="text-[12px] font-medium text-ink3">Progress</span>
            <span className="text-[12px] font-medium text-ink3 text-right">Docs / findings</span>
            <span className="text-[12px] font-medium text-ink3 text-right">%</span>
          </div>
          <ul>
            {workstreams.map((ws) => (
              <li
                key={ws.workstream}
                className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3 last:border-b-0 md:grid-cols-[140px_1fr_120px_64px]"
              >
                <span className="text-[13px] font-medium text-ink1">{ws.label}</span>
                <div className="col-span-2 md:col-span-1">
                  <ProgressBar value={ws.progress} />
                </div>
                <span className="hidden text-right font-mono text-[12px] text-ink3 tabular md:block">
                  {ws.documents} / {ws.findings}
                </span>
                <span className="text-right font-mono text-[13px] text-ink2 tabular">
                  {ws.progress}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader title="Escalation inbox" meta="critical findings awaiting deal-lead review" />
        <div className="overflow-hidden rounded-lg border border-line bg-card">
          {inbox.length === 0 ? (
            <p className="px-4 py-6 text-[13px] text-ink3">No open escalations.</p>
          ) : (
            <ul>
              {inbox.map((entry) => (
                <li key={entry.finding_id} className="border-b border-line px-4 py-3 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="size-1.5 rounded-full bg-sev-critical" aria-hidden />
                    <a
                      href={`/findings/${entry.finding_id}`}
                      className="text-[13px] font-medium text-ink1 transition-colors duration-150 hover:text-accent"
                    >
                      {entry.title}
                    </a>
                    <span className="font-mono text-[11px] text-ink4">{entry.finding_id}</span>
                  </div>
                  <p className="mt-1 text-[12px] text-ink3">{entry.message}</p>
                  <div className="mt-1 font-mono text-[11px] text-ink4">
                    {entry.workstream} · {entry.owner} · {fmtTime(entry.created_at)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
