/**
 * Diligence Room architecture.
 *
 * Layered bands, not a flow chart: each band is a tier of the system and names
 * every component that actually ships in it, with the cross-cutting planes
 * (platform, observability, compliance) on a rail down the right. Positions are
 * explicit rather than solved by a layout engine, so the render is stable.
 *
 * Rendered to docs/diagram/architecture.png by dashboard/web/render-diagram.mjs.
 */

import type { ReactNode } from "react";

const INK = "#000000";
const BODY = "#1f1f1f";
const MUTED = "#454545";
const LINE = "#7d7d7d";
const RULE = "#a8a8a8";
const FILL = "#ffffff";
const PANEL = "#f5f5f5";
const CHIP = "#ffffff";
const ACCENT = "#b3301f";
const ACCENT_BG = "#fdf1ef";

const LEFT = 30;
const MAIN_W = 1150;
const RAIL_X = LEFT + MAIN_W + 24;
const RAIL_W = 424;
const W = RAIL_X + RAIL_W + LEFT;

type Chip = { label: string; note?: string; accent?: boolean };
type Band = { title: string; tech: string; chips: Chip[] };

const BANDS: Band[] = [
  {
    title: "Executive dashboard",
    tech: "React 19 · Vite · TypeScript · Tailwind — static bundle served from Cloud Run",
    chips: [
      { label: "Overview", note: "workstreams, inbox" },
      { label: "Findings + detail", note: "evidence, graph, trace" },
      { label: "Documents", note: "data room, routing" },
      { label: "Security", note: "scorecard, quarantine" },
      { label: "Registry", note: "versions, evals" },
    ],
  },
  {
    title: "API and policy edge",
    tech: "FastAPI on Cloud Run — asia-south1 and us-central1",
    chips: [
      { label: "/api/deal" },
      { label: "/api/findings" },
      { label: "/api/documents" },
      { label: "/api/security" },
      { label: "/api/registry" },
      { label: "/api/negotiation", note: "draft · approve · send" },
      { label: "Agent Gateway", note: "/gateway/decide — deny by default", accent: true },
      { label: "Agent Identity", note: "per-workstream principals" },
    ],
  },
  {
    title: "Agent fleet",
    tech: "Google ADK 2.7 on Agent Runtime / Vertex AI Agent Engine · Gemini 3.5 Flash",
    chips: [
      { label: "Legal" },
      { label: "Finance" },
      { label: "HR" },
      { label: "IP / Tech" },
      { label: "Tax" },
      { label: "Regulatory" },
      { label: "ESG" },
      { label: "Real Estate" },
      { label: "Coordinator", note: "red-flag scoring, escalation" },
      { label: "Negotiation", note: "drafts, human approval gate" },
      { label: "Evidence gate", note: "verbatim span required" },
      { label: "Loop guard", note: "crash resume" },
    ],
  },
  {
    title: "Ingestion and screening",
    tech: "every upload is hostile input until it clears both layers",
    chips: [
      { label: "Format detection", note: "magic bytes, not filenames" },
      { label: "Document AI", note: "OCR and parsing" },
      { label: "Chunking + lineage", note: "checksum, versions" },
      { label: "Gemma sentinel", note: "gemma-4-26b-a4b-it", accent: true },
      { label: "Model Armor", note: "injection, jailbreak", accent: true },
      { label: "Flash classifier", note: "workstream routing" },
      { label: "Quarantine store", note: "never routed" },
    ],
  },
  {
    title: "State and messaging",
    tech: "partitioned by policy, not convenience",
    chips: [
      { label: "Firestore", note: "findings · events · drafts" },
      { label: "Firestore", note: "lineage · quarantine · policy" },
      { label: "Memory Bank", note: "entity memory across sessions" },
      { label: "Cloud Storage", note: "region-pinned data room" },
      { label: "Pub/Sub", note: "object-finalize → pipeline" },
      { label: "Event log", note: "append-only audit" },
    ],
  },
];

type Rail = { title: string; tech: string; items: string[] };

const RAILS: Rail[] = [
  {
    title: "Platform services",
    tech: "Gemini Enterprise Agent Platform",
    items: [
      "Agent Registry — 8 agents published as A2A cards",
      "Versions, approval state, eval scores, rollback",
      "Agent Runtime — deployed ADK reasoning engine",
      "Memory Bank — durable entity memory per deal",
    ],
  },
  {
    title: "Observability",
    tech: "OpenTelemetry GenAI semantic conventions",
    items: [
      "Spans from every agent and gateway decision",
      "Cloud Trace — finding audit_trace_id resolves",
      "Cloud Logging — Cloud Run request log",
      "Shadow eval harness · 20-attack red-team ledger",
    ],
  },
  {
    title: "Compliance plane",
    tech: "enforced in code, not asserted in prose",
    items: [
      "Cloud KMS — CMEK on the Firestore database",
      "Cloud DLP — inspect templates on ingest",
      "VPC Service Controls — perimeter configuration",
      "Region pinning · retention · audit log",
    ],
  },
];

/* Rough advance width for the label face; good enough to pack chips. */
const chipWidth = (c: Chip) =>
  Math.max(c.label.length * 9.4 + 30, c.note ? c.note.length * 7.2 + 30 : 0);

const BAND_PAD = 15;
const chipHeight = (c: Chip) => (c.note ? 52 : 34);
const CHIP_GAP = 9;
const HEAD_H = 48;

function layout(chips: Chip[], maxW: number) {
  const rows: Array<{ chips: Array<Chip & { w: number }>; h: number }> = [];
  let row: Array<Chip & { w: number }> = [];
  let used = 0;
  for (const c of chips) {
    const w = chipWidth(c);
    if (used + w > maxW && row.length) {
      rows.push({ chips: row, h: Math.max(...row.map(chipHeight)) });
      row = [];
      used = 0;
    }
    row.push({ ...c, w });
    used += w + CHIP_GAP;
  }
  if (row.length) rows.push({ chips: row, h: Math.max(...row.map(chipHeight)) });
  return rows;
}

const BAND_LAYOUTS = BANDS.map((b) => layout(b.chips, MAIN_W - BAND_PAD * 2));
const BAND_H = BAND_LAYOUTS.map(
  (rows) => HEAD_H + rows.reduce((s, r) => s + r.h + CHIP_GAP, 0) + BAND_PAD - CHIP_GAP,
);

const TOP = 98;
const BAND_GAP = 24;
const BAND_Y: number[] = [];
BAND_H.reduce((y, h, i) => {
  BAND_Y[i] = y;
  return y + h + BAND_GAP;
}, TOP);

const H = BAND_Y[BAND_Y.length - 1] + BAND_H[BAND_H.length - 1] + 34;

function ChipBox({ c, x, y, h }: { c: Chip & { w: number }; x: number; y: number; h: number }) {
  return (
    <g>
      <rect x={x} y={y} width={c.w} height={h} rx={6} fill={c.accent ? ACCENT_BG : CHIP}
        stroke={c.accent ? ACCENT : LINE} strokeWidth={c.accent ? 2.4 : 1.8} />
      <text x={x + c.w / 2} y={y + (c.note ? 22 : h / 2 + 6)} textAnchor="middle"
        fontSize={15.5} fontWeight={700} fill={c.accent ? ACCENT : INK}>
        {c.label}
      </text>
      {c.note && (
        <text x={x + c.w / 2} y={y + 41} textAnchor="middle" fontSize={13} fill={MUTED}>
          {c.note}
        </text>
      )}
    </g>
  );
}

export default function Architecture() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`}
      fontFamily="Inter, 'Segoe UI', system-ui, sans-serif">
      <defs>
        <marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6"
          orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={LINE} />
        </marker>
      </defs>
      <rect width={W} height={H} fill={FILL} />

      <text x={LEFT} y={42} fontSize={27} fontWeight={800} fill={INK}>
        Diligence Room — system architecture
      </text>
      <text x={LEFT} y={70} fontSize={15} fill={BODY}>
        Zero-trust runtime for an autonomous agent fleet. Documents are adversaries, agents are principals, memory is partitioned by policy.
      </text>

      {BANDS.map((band, bi) => {
        const y = BAND_Y[bi];
        let cy = y + HEAD_H;
        const rowNodes: ReactNode[] = [];
        BAND_LAYOUTS[bi].forEach((row, ri) => {
          let x = LEFT + BAND_PAD;
          const boxes = row.chips.map((c) => {
            const node = <ChipBox key={c.label + (c.note ?? "")} c={c} x={x} y={cy} h={row.h} />;
            x += c.w + CHIP_GAP;
            return node;
          });
          rowNodes.push(<g key={ri}>{boxes}</g>);
          cy += row.h + CHIP_GAP;
        });
        return (
          <g key={band.title}>
            <rect x={LEFT} y={y} width={MAIN_W} height={BAND_H[bi]} rx={9} fill={PANEL}
              stroke={RULE} strokeWidth={1.9} />
            <text x={LEFT + BAND_PAD} y={y + 25} fontSize={18} fontWeight={800} fill={INK}>
              {band.title}
            </text>
            <text x={LEFT + BAND_PAD} y={y + 43} fontSize={13.5} fill={MUTED}>{band.tech}</text>
            {rowNodes}
            {bi < BANDS.length - 1 && (
              <line x1={LEFT + MAIN_W / 2} y1={y + BAND_H[bi]} x2={LEFT + MAIN_W / 2}
                y2={y + BAND_H[bi] + BAND_GAP - 5} stroke={LINE} strokeWidth={2.4}
                markerEnd="url(#tip)" />
            )}
          </g>
        );
      })}

      {RAILS.map((rail, ri) => {
        const h = 60 + rail.items.length * 25;
        const y = TOP + ri * (h + BAND_GAP);
        return (
          <g key={rail.title}>
            <rect x={RAIL_X} y={y} width={RAIL_W} height={h} rx={9} fill={PANEL} stroke={RULE}
              strokeWidth={1.9} />
            <text x={RAIL_X + BAND_PAD} y={y + 25} fontSize={18} fontWeight={800} fill={INK}>
              {rail.title}
            </text>
            <text x={RAIL_X + BAND_PAD} y={y + 43} fontSize={13.5} fill={MUTED}>{rail.tech}</text>
            {rail.items.map((it, i) => (
              <text key={it} x={RAIL_X + BAND_PAD} y={y + 67 + i * 25} fontSize={14} fill={BODY}>
                <tspan fill={LINE} fontWeight={700}>▪ </tspan>
                {it}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}
