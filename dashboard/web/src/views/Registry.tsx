import { api, useAsync, WORKSTREAM_LABEL } from "../api";
import { ErrorState, LoadingState, SectionHeader, StatusPill, Tag } from "../components/ui";

export default function Registry() {
  const { data, error, loading } = useAsync(api.registry, []);

  if (loading) return <LoadingState label="agent registry" />;
  if (error || !data) return <ErrorState error={error ?? "no data"} />;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Agent registry"
        meta={`${data.filter((a) => a.approved).length} of ${data.length} agents approved`}
      />

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="overline px-4 py-2.5 font-medium">Agent</th>
              <th scope="col" className="overline hidden px-4 py-2.5 font-medium md:table-cell">
                Workstream
              </th>
              <th scope="col" className="overline px-4 py-2.5 font-medium">Version</th>
              <th scope="col" className="overline hidden px-4 py-2.5 font-medium lg:table-cell">
                Model
              </th>
              <th scope="col" className="overline px-4 py-2.5 font-medium">Approval</th>
              <th scope="col" className="overline hidden px-4 py-2.5 text-right font-medium sm:table-cell">
                Eval
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((agent) => (
              <tr key={agent.agent_id} className="border-b border-line align-top last:border-b-0 hover:bg-card2">
                <td className="px-4 py-3">
                  <div className="text-[13px] font-medium text-ink1">{agent.name}</div>
                  <div className="mt-0.5 font-mono text-[11px] text-ink4">{agent.agent_id}</div>
                  <div className="mt-1.5 hidden max-w-[300px] md:block">
                    <span className="flex flex-wrap gap-1">
                      {agent.capabilities.slice(0, 3).map((c) => (
                        <Tag key={c}>{c}</Tag>
                      ))}
                    </span>
                  </div>
                </td>
                <td className="hidden px-4 py-3 text-[13px] text-ink2 md:table-cell">
                  {WORKSTREAM_LABEL[agent.workstream] ?? agent.workstream}
                </td>
                <td className="px-4 py-3">
                  <div className="font-mono text-[13px] text-ink2 tabular">v{agent.version}</div>
                  <div className="mt-0.5">
                    <StatusPill status={agent.deployment_status} />
                  </div>
                  {agent.rollback_target ? (
                    <div className="mt-1 font-mono text-[11px] text-ink4">
                      rollback → v{agent.rollback_target}
                    </div>
                  ) : null}
                </td>
                <td className="hidden px-4 py-3 font-mono text-[12px] text-ink3 lg:table-cell">
                  {agent.model_id}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.04em] uppercase ${
                      agent.approved ? "text-ok" : "text-sev-high"
                    }`}
                  >
                    <span
                      className={`size-1.5 rounded-full ${agent.approved ? "bg-ok" : "bg-sev-high"}`}
                      aria-hidden
                    />
                    {agent.approved ? "approved" : "pending"}
                  </span>
                </td>
                <td className="hidden px-4 py-3 text-right font-mono text-[13px] text-ink2 tabular sm:table-cell">
                  {agent.eval_score === null ? "—" : agent.eval_score.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[12px] text-ink4">
        External communication is prohibited for all agents by registry policy. Version changes
        require approval and shadow evaluation before deployment.
      </p>
    </div>
  );
}
