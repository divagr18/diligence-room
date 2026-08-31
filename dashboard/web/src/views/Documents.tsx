import { useMemo, useState } from "react";
import { api, documentUrl, fmtPct, useAsync, WORKSTREAM_LABEL } from "../api";
import { EmptyState, ErrorState, LoadingState, SectionHeader, StatusPill, Tag } from "../components/ui";

const WORKSTREAM_FILTERS = [
  "all",
  "legal",
  "finance",
  "hr",
  "ip_tech",
  "tax",
  "regulatory",
  "esg",
  "real_estate",
  "unrouted",
] as const;

const STATUS_FILTERS = ["all", "cleared", "quarantined"] as const;

/* Bytes are the honest unit on the wire; readers want kB. */
function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* "native_pdf" reads badly in a column header-width cell. */
function fmtFormat(format: string): string {
  return format.replace(/_/g, " ");
}

export default function Documents() {
  const { data, error, loading } = useAsync(api.documents, [], 0);
  const [workstream, setWorkstream] = useState<(typeof WORKSTREAM_FILTERS)[number]>("all");
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const rows = useMemo(() => {
    if (!data) return [];
    return [...data]
      .filter((d) =>
        workstream === "all"
          ? true
          : workstream === "unrouted"
            ? d.workstream === null
            : d.workstream === workstream,
      )
      .filter((d) => status === "all" || d.security_status === status)
      .sort(
        (a, b) =>
          (a.workstream ?? "zzz").localeCompare(b.workstream ?? "zzz") ||
          a.document_id.localeCompare(b.document_id),
      );
  }, [data, workstream, status]);

  if (loading) return <LoadingState label="documents" />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  const pages = data.reduce((sum, d) => sum + (d.page_count ?? 0), 0);
  const quarantined = data.filter((d) => d.security_status === "quarantined").length;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Documents"
        meta={`${data.length} in the data room · ${pages} pages · ${quarantined} quarantined`}
      />

      <div className="flex flex-wrap items-center gap-4">
        <div role="group" aria-label="Filter by workstream" className="flex flex-wrap gap-1.5">
          {WORKSTREAM_FILTERS.map((w) => (
            <button
              key={w}
              type="button"
              aria-pressed={workstream === w}
              onClick={() => setWorkstream(w)}
              className={`rounded-md border px-2.5 py-1 font-mono text-[12px] capitalize transition-colors duration-150 ${
                workstream === w
                  ? "border-line3 bg-card2 text-ink1"
                  : "border-line bg-card text-ink3 hover:border-line2 hover:text-ink2"
              }`}
            >
              {w === "all" || w === "unrouted" ? w : (WORKSTREAM_LABEL[w] ?? w)}
            </button>
          ))}
        </div>

        <div className="hidden h-5 w-px bg-line2 sm:block" aria-hidden />

        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={status === s}
              onClick={() => setStatus(s)}
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
              <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Document</th>
              <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Workstream</th>
              <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 md:table-cell">
                Type
              </th>
              <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 lg:table-cell">
                Format
              </th>
              <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 sm:table-cell">
                Pages
              </th>
              <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 lg:table-cell">
                Size
              </th>
              <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 xl:table-cell">
                Routing
              </th>
              <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <EmptyState label="No documents match the current filters." />
                </td>
              </tr>
            )}
            {rows.map((d) => (
              <tr key={d.document_id} className="border-b border-line align-top last:border-b-0 hover:bg-card2">
                <td className="px-4 py-3">
                  <a
                    href={documentUrl(d.document_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-[12px] text-ink1 underline decoration-line3 underline-offset-2 hover:decoration-ink3"
                  >
                    {d.document_id}
                  </a>
                </td>
                <td className="px-4 py-3 text-[13px] text-ink2">
                  {d.workstream ? (WORKSTREAM_LABEL[d.workstream] ?? d.workstream) : (
                    <span className="text-ink4">unrouted</span>
                  )}
                </td>
                <td className="hidden px-4 py-3 md:table-cell">
                  <Tag>{d.doc_type}</Tag>
                </td>
                <td className="hidden px-4 py-3 text-[12px] text-ink3 lg:table-cell">
                  {fmtFormat(d.format)}
                  {d.needs_ocr && <span className="ml-1.5 text-ink4">· OCR</span>}
                </td>
                <td className="hidden px-4 py-3 text-right font-mono text-[13px] text-ink2 tabular sm:table-cell">
                  {d.page_count ?? "—"}
                </td>
                <td className="hidden px-4 py-3 text-right font-mono text-[13px] text-ink2 tabular lg:table-cell">
                  {fmtSize(d.size_bytes)}
                </td>
                <td className="hidden px-4 py-3 text-right font-mono text-[13px] text-ink2 tabular xl:table-cell">
                  {d.workstream ? fmtPct(d.confidence) : "—"}
                </td>
                <td className="px-4 py-3">
                  {d.security_status === "quarantined" ? (
                    <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-1.5 py-px text-[12px] whitespace-nowrap text-deny">
                      <span className="size-1.5 rounded-full bg-deny" aria-hidden />
                      quarantined
                    </span>
                  ) : (
                    <StatusPill status="cleared" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
