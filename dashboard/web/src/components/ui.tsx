/* UI primitives — DESIGN.md §5. Every component consumes tokens only. */

import type { ReactNode } from "react";

export const SEV_DOT: Record<string, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  informational: "bg-sev-info",
};

export const SEV_TEXT: Record<string, string> = {
  critical: "text-sev-critical",
  high: "text-sev-high",
  medium: "text-sev-medium",
  low: "text-sev-low",
  informational: "text-sev-info",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium whitespace-nowrap">
      <span className={`size-1.5 rounded-full ${SEV_DOT[severity] ?? "bg-ink4"}`} aria-hidden />
      <span className={`${SEV_TEXT[severity] ?? "text-ink3"} capitalize`}>{severity}</span>
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-line bg-card px-1.5 py-px text-[12px] text-ink2 capitalize whitespace-nowrap">
      {status}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-line bg-card px-1.5 py-px font-mono text-[12px] text-ink3">
      {children}
    </span>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`rounded-lg border border-line bg-card ${className}`}>{children}</section>;
}

export function SectionHeader({
  title,
  meta,
}: {
  title: string;
  meta?: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <h2 className="text-[20px] font-medium tracking-[-0.01em] text-ink1">{title}</h2>
      {meta ? <div className="text-[12px] text-ink4">{meta}</div> : null}
    </div>
  );
}

export function StatTile({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-card px-4 py-3">
      <div className="tabular font-mono text-[22px] font-medium leading-none tracking-tight text-ink1">
        {value}
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        {tone ? <span className={`size-1.5 rounded-full ${SEV_DOT[tone] ?? "bg-ink4"}`} aria-hidden /> : null}
        <span className="text-[12px] font-medium text-ink3">{label}</span>
      </div>
      {hint ? <div className="mt-1 text-[12px] text-ink4">{hint}</div> : null}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-card2" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <div
        className="h-full rounded-full bg-ink3 transition-[width] duration-300 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function LayerPill({ layer }: { layer: string }) {
  const model = layer === "model_armor";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-1.5 py-px font-mono text-[11px] whitespace-nowrap ${
        model ? "border-line2 bg-card2 text-ink2" : "border-line bg-card text-ink3"
      }`}
    >
      <span className={`size-1.5 rounded-full ${model ? "bg-accent" : "bg-ink4"}`} aria-hidden />
      {layer === "model_armor" ? "Model Armor" : "Sentinel"}
    </span>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const blocked = outcome === "blocked" || outcome === "deny";
  const allow = outcome === "allow";
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.04em] uppercase ${
        allow ? "text-ok" : blocked ? "text-deny" : "text-ink3"
      }`}
    >
      {outcome}
    </span>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <span className="font-mono text-[13px] text-ink4">loading {label}…</span>
    </div>
  );
}

export function ErrorState({ error }: { error: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center px-6">
      <div className="max-w-md text-center">
        <p className="text-[13px] text-ink2">The dashboard cannot reach the Deal Room API.</p>
        <p className="mt-2 font-mono text-[12px] text-ink4">{error}</p>
        <p className="mt-3 text-[12px] text-ink4">
          Start it with: uv run uvicorn dashboard.api.app:app --port 8040
        </p>
      </div>
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return <div className="px-4 py-8 text-center text-[13px] text-ink3">{label}</div>;
}
