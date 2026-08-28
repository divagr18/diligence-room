import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtTime, fmtPct, SEVERITY_RANK, useAsync, WORKSTREAM_LABEL } from "../api";
import { EmptyState, ErrorState, LoadingState, SectionHeader, SeverityBadge, StatusPill } from "../components/ui";

const SEVERITY_FILTERS = ["all", "critical", "high", "medium", "low", "informational"] as const;
const STATUS_FILTERS = ["all", "open", "validated", "resolved"] as const;

export default function Findings() {
  const navigate = useNavigate();
  const { data, error, loading } = useAsync(api.findings, [], 2000);
  const [severity, setSeverity] = useState<(typeof SEVERITY_FILTERS)[number]>("all");
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const rows = useMemo(() => {
    if (!data) return [];
    return [...data]
      .filter((f) => severity === "all" || f.severity === severity)
      .filter((f) => status === "all" || f.status === status)
      .sort(
        (a, b) =>
          (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9) ||
          b.updated_at.localeCompare(a.updated_at),
      );
  }, [data, severity, status]);

  if (loading) return <LoadingState label="findings" />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  return (
    <div className="space-y-5">
      <SectionHeader title="Findings" meta={`${data.length} findings across 8 workstreams`} />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by severity">
          {SEVERITY_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSeverity(s)}
              aria-pressed={severity === s}
              className={`rounded-md border px-2.5 py-1 font-mono text-[12px] capitalize transition-colors duration-150 ${
                severity === s
                  ? "border-line3 bg-card2 text-ink1"
                  : "border-line bg-card text-ink3 hover:border-line2 hover:text-ink2"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              aria-pressed={status === s}
              className={`rounded-md border px-2.5 py-1 font-mono text-[12px] capitalize transition-colors duration-150 ${
                status === s
                  ? "border-line3 bg-card2 text-ink1"
                  : "border-line bg-card text-ink3 hover:border-line2 hover:text-ink2"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Severity</th>
              <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Finding</th>
              <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 lg:table-cell">Workstream</th>
              <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 sm:table-cell">
                Confidence
              </th>
              <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 md:table-cell">Status</th>
              <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 xl:table-cell">
                Updated
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <EmptyState label="No findings match the current filters." />
                </td>
              </tr>
            ) : (
              rows.map((f) => (
                <tr
                  key={f.finding_id}
                  tabIndex={0}
                  role="link"
                  aria-label={`Open finding ${f.finding_id}`}
                  onClick={() => navigate(`/findings/${f.finding_id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      navigate(`/findings/${f.finding_id}`);
                    }
                  }}
                  className="cursor-pointer border-b border-line transition-colors duration-150 last:border-b-0 hover:bg-card2"
                >
                  <td className="px-4 py-3 align-top">
                    <SeverityBadge severity={f.severity} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="max-w-[480px] text-[13px] font-medium text-ink1">{f.title}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-ink4">
                      {f.finding_id} · {f.documents} doc{f.documents === 1 ? "" : "s"}
                    </div>
                  </td>
                  <td className="hidden px-4 py-3 align-top text-[13px] text-ink2 lg:table-cell">
                    {WORKSTREAM_LABEL[f.workstream] ?? f.workstream}
                    <div className="mt-0.5 font-mono text-[11px] text-ink4">{f.owner}</div>
                  </td>
                  <td className="hidden px-4 py-3 text-right align-top font-mono text-[13px] text-ink2 tabular sm:table-cell">
                    {fmtPct(f.confidence)}
                  </td>
                  <td className="hidden px-4 py-3 align-top md:table-cell">
                    <StatusPill status={f.status} />
                  </td>
                  <td className="hidden px-4 py-3 text-right align-top font-mono text-[11px] text-ink4 xl:table-cell">
                    {fmtTime(f.updated_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
