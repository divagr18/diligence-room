import { api, fmtTime, quarantinedDocumentUrl, useAsync } from "../api";
import {
  ErrorState,
  LayerPill,
  LoadingState,
  OutcomeBadge,
  SectionHeader,
  Tag,
} from "../components/ui";

export default function Security() {
  const { data, error, loading } = useAsync(api.security, []);

  if (loading) return <LoadingState label="security events" />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  return (
    <div className="space-y-8">
      <SectionHeader
        title="Security"
        meta={`${data.total_blocked} hostile documents blocked before agent context`}
      />

      <section aria-label="Red-team scorecard" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {data.scorecard.map((g) => {
          const complete = g.blocked === g.total;
          return (
            <div key={g.group} className="rounded-lg border border-line bg-card px-4 py-3">
              <div className="flex items-baseline gap-2">
                <span
                  className={`tabular font-mono text-[22px] font-medium leading-none ${
                    complete ? "text-ok" : "text-sev-high"
                  }`}
                >
                  {g.blocked}/{g.total}
                </span>
                <span className="text-[12px] text-ink4">blocked</span>
              </div>
              <div className="mt-2 text-[12px] font-medium text-ink3">{g.group}</div>
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-card2">
                <div
                  className={`h-full rounded-full transition-[width] duration-300 ease-out ${
                    complete ? "bg-ok" : "bg-sev-high"
                  }`}
                  style={{ width: `${g.total === 0 ? 0 : (g.blocked / g.total) * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </section>

      <section className="space-y-4">
        <SectionHeader title="Quarantined documents" meta="never routed, never read by agents" />
        <div className="overflow-x-auto rounded-lg border border-line bg-card">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Document</th>
                <th scope="col" className="px-4 py-2.5 text-[12px] font-medium text-ink3">Blocking layer</th>
                <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 md:table-cell">
                  Reason codes
                </th>
                <th scope="col" className="hidden px-4 py-2.5 text-[12px] font-medium text-ink3 sm:table-cell">
                  Class
                </th>
                <th scope="col" className="hidden px-4 py-2.5 text-right text-[12px] font-medium text-ink3 lg:table-cell">
                  Time
                </th>
              </tr>
            </thead>
            <tbody>
              {data.quarantined.map((q) => (
                <tr key={q.document_id + q.ts} className="border-b border-line last:border-b-0 hover:bg-card2">
                  <td className="px-4 py-3">
                    {/* The blocked payload is openable: a reviewer should be
                        able to read the attack rather than trust the verdict. */}
                    <a
                      href={quarantinedDocumentUrl(q.document_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-[12px] text-ink1 underline decoration-line3 underline-offset-2 hover:decoration-ink3"
                    >
                      {q.document_id}
                    </a>
                  </td>
                  <td className="px-4 py-3">
                    <LayerPill layer={q.layer} />
                  </td>
                  <td className="hidden px-4 py-3 md:table-cell">
                    <span className="flex flex-wrap gap-1.5">
                      {q.reason_codes.map((r) => (
                        <Tag key={r}>{r}</Tag>
                      ))}
                    </span>
                  </td>
                  <td className="hidden px-4 py-3 text-[12px] text-ink2 capitalize sm:table-cell">
                    {q.attack_class.replace("_", " ")}
                  </td>
                  <td className="hidden px-4 py-3 text-right font-mono text-[11px] text-ink4 lg:table-cell">
                    {fmtTime(q.ts)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader title="Security feed" meta="quarantines, gateway decisions, authz denials" />
        <div className="overflow-hidden rounded-lg border border-line bg-card">
          <ul>
            {data.feed.map((item, i) => (
              <li
                key={i}
                className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-b border-line px-4 py-3 last:border-b-0 sm:grid-cols-[150px_auto_1fr]"
              >
                <span className="font-mono text-[11px] text-ink4 tabular sm:pt-0.5">
                  {fmtTime(item.ts)}
                </span>
                <span className="flex items-center gap-2 sm:pt-0.5">
                  <Tag>{item.kind}</Tag>
                  <OutcomeBadge outcome={item.outcome} />
                </span>
                <span className="col-span-2 min-w-0 text-[13px] text-ink2 sm:col-span-1">
                  <span className="font-mono text-[12px] text-ink3">{item.subject}</span>
                  <span className="mx-1.5 text-ink4">—</span>
                  {item.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
