# DESIGN.md — Diligence Room Executive Deal Room

> Binding design contract for `dashboard/web/`. Every color, font size, spacing
> value, and component in the UI **must** trace to a token in this file. No raw
> hex, no magic px, no ad-hoc component patterns. If a token doesn't exist, add
> it here first, then use it.

## 0. Research Log

| Lane | Deliverable |
|---|---|
| Embedded-reference shortlist | Considered `linear.app`, `vercel`, `raycast`, `posthog`. **Pick: `linear.app.md`** — the strongest real-world model for a beautiful, cliche-free operational console; read in full. |
| Layout doctrine | App-shell (`layout-skill`): fixed sidebar + independently scrolling body; `min-block-size:0` scroll shells. |
| Real-product screens (lazyweb) | Skipped — the picked Layer B reference is itself a shipped real-product system; no additional network harvest needed. |
| Imagen concept drafts | Skipped — operational app-shell; reference is a real product system, not a generated concept. |

## 1. Direction (locked)

**"The Deal Room Ledger."** A hushed, near-black control plane that reads like an
audited instrument, not a startup landing page.

- **Atmosphere:** a boardroom after hours — dark, calm, precise; information as
  ledger rows and instrument readings. No hype, no decoration.
- **Signature material:** hairline semi-transparent rules + **tabular monospace**
  for every ID, timestamp, percentage, and count. Elevation via luminance
  stepping (surface gets slightly lighter as it rises) — **never** shadows,
  **never** gradients.
- **Color story:** the UI chrome is achromatic (a warm-neutral grayscale ramp).
  **Only risk carries hue.** Severity, security status, and gateway verdicts are
  the sole sources of color, so a red mark genuinely means something.
- **One moment to remember:** the Overview deal-health strip — a sea of calm
  graphite KPI tiles punctuated by a few sharp severity ticks and mono
  percentages.

**Hard anti-cliche rules (from the brief):**
- No gradients anywhere (backgrounds, text, borders, buttons).
- No glassmorphism, no glow, no aurora, no emoji-as-icon.
- No fake/lorem labels — every string is real domain language (finding,
  workstream, quarantine, severity, gateway decision) or a real value from the
  API. No "Dashboard1"-style placeholders.
- No large rounded corners (max 8px on cards; controls 4–6px). No 3-up feature
  card grids, no purple-blue hero.

## 2. Color tokens

Structure is a warm-neutral grayscale ramp (NOT cool blue-black — deliberately
distinct from the reference). Severity is the only hue source.

### Surfaces (luminance ramp)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0a0b` | App canvas |
| `--panel` | `#101011` | Sidebar, header |
| `--surface` | `#161718` | Cards, tables, inputs |
| `--surface-2` | `#1e1f21` | Hover, selected row, raised |
| `--overlay` | `rgba(0,0,0,0.8)` | Dialog backdrop |

### Texture (borders)
| Token | Value | Use |
|---|---|---|
| `--border-subtle` | `rgba(255,255,255,0.06)` | default hairline |
| `--border` | `rgba(255,255,255,0.10)` | inputs, emphasis |
| `--border-strong` | `rgba(255,255,255,0.16)` | active/focus edges |

### Text
| Token | Value | Use |
|---|---|---|
| `--text-1` | `#f4f4f2` | headings, primary |
| `--text-2` | `#c8c8c4` | body, descriptions |
| `--text-3` | `#95948e` | metadata, secondary |
| `--text-4` | `#6d6c66` | timestamps, disabled, overlines |

### Severity — the only chromatic ramp
| Token | Value | Level |
|---|---|---|
| `--sev-critical` | `#f2605a` | critical |
| `--sev-high` | `#ef9d4f` | high |
| `--sev-medium` | `#d9b95c` | medium |
| `--sev-low` | `#6fa8dc` | low |
| `--sev-info` | `#9aa0a6` | informational |

### Status & interaction
| Token | Value | Use |
|---|---|---|
| `--ok` | `#4caf7d` | gateway ALLOW, blocked-threat-contained, resolved |
| `--deny` | `#f2605a` | gateway DENY, breach attempt, authz denied |
| `--accent` | `#8ab0e8` | links, focus ring, active nav only — used sparingly |

Severity/status colors are used for **dots, small text, and thin rules** — never
as large fills. A severity badge is a dot + text label (color is never the only
signal — accessibility).

## 3. Typography tokens

Fonts (loaded in `index.html`, never fall back to system defaults):
- **UI/`--font-sans`:** `Inter` (variable), with `font-feature-settings: "cv01","ss03"` on all Inter text.
- **Data/`--font-mono`:** `IBM Plex Mono` — IDs, timestamps, percentages, counts,
  checksums, versions. Tabular alignment for every numeric column.

| Token | Size / Weight / LS | Use |
|---|---|---|
| `--text-display` | 28px / 510 / -0.5px | View title (e.g. "Project Falcon") |
| `--text-h2` | 20px / 510 / -0.3px | Section headers |
| `--text-h3` | 15px / 590 / -0.1px | Card titles, panel titles |
| `--text-body` | 14px / 400 / 0 | Reading text, summaries |
| `--text-medium` | 13px / 510 / 0 | Labels, nav, table cells |
| `--text-caption` | 12px / 400 / 0 | Metadata, helper text |
| `--text-micro` | 11px / 510 / +0.4px | Overlines (uppercase) |
| `--text-mono` | 13px / 400 / 0 | IDs, numbers, timestamps, % |
| `--text-mono-lg` | 22px / 510 / -0.3px | Stat tile values |

Weight ladder: 400 read · 510 emphasize/UI · 590 announce. Never 700.
Numbers in data columns use `font-variant-numeric: tabular-nums`.

## 4. Spacing, radius, elevation

- **Spacing scale (8px grid):** 2 · 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48. Page
  padding 24px desktop / 16px mobile. Card inner padding 16px. Stack gaps 8–16px.
- **Radius:** 2 (inline badge) · 4 (badge, small) · 6 (button, input, tag) ·
  8 (card, panel). Nothing larger.
- **Elevation:** background luminance step + 1px border. No `box-shadow` depth
  stacks, no gradients. Focus ring is the only allowed shadow (see a11y).

## 5. Primitives (name = contract)

| Primitive | Anatomy & states |
|---|---|
| `AppShell` | Fixed 232px sidebar + scroll body (`min-block-size:0`); mobile: sidebar collapses to top bar |
| `SideNav` | Brand mark + project label; NavItems |
| `NavItem` | icon + label (13/510); idle `text-3`, hover bg `surface-2`+`text-2`, active bg `surface-2`+`text-1`+2px accent left rule |
| `StatTile` | label (11 uppercase `text-4`) + mono value (`--text-mono-lg`) + optional tone dot |
| `SeverityBadge` | severity dot (6px, `--sev-*`) + text label (13/510, `--sev-*` text) |
| `StatusPill` | bordered pill (1px border, radius 6) for status: open/validated/resolved/ALLOW/DENY |
| `Card` / `Panel` | bg `surface`, 1px `border-subtle`, radius 8, pad 16 |
| `SectionHeader` | h2 title + optional right-side meta/action |
| `DataTable` | header row (11 uppercase `text-4`), rows (13/510), hairline row dividers, hover `surface-2`; numeric/ID columns mono + right-aligned where sensible |
| `RowLink` | clickable table row → navigate; focus-visible ring |
| `ProgressBar` | 4px track `surface-2`, fill `text-3`→`--accent` only for the active/special case; % in mono |
| `KeyValueRow` | label (`text-3`) : value (mono or `text-2`) |
| `EvidenceBlock` | quoted span (border-left 2px `border-strong`, italic `text-2`) + doc id + locator |
| `TimelineItem` | dot + connector line + title + meta — for finding history / trace |
| `ScorecardRow` | class label + `n/m blocked` (mono) + pass/fail tick |
| `Button` | primary: bg `surface-2`, border `border`, radius 6, text `text-1`; ghost: transparent; focus ring |
| `EmptyState` | centered `text-3` caption, no illustration |

**Icons:** `lucide-react` only (SVG). No emoji anywhere.

## 6. Views (content = real API data)

1. **Overview `/`** — project header (`PROJECT FALCON`, deal meta); KPI strip
   (Deal Health, Critical, High, Open Questions, Docs Reviewed, Agents Active,
   Security Blocked); workstream progress list (8 workstreams, %, bar).
2. **Findings `/findings`** — severity/status filter + table (severity, title,
   workstream, owner, confidence%, status, updated). **`/findings/:id`** detail:
   summary, severity, evidence (quoted spans), affected workstreams, contributing
   agents, confidence, related findings, trace timeline.
3. **Security `/security`** — tabs/sections: Quarantined documents, Blocked
   injections / authz denials, Gateway decisions, Red-Team scorecard.
4. **Registry `/registry`** — agent table: name, workstream, version, approval,
   deployment status, rollback target.

## 7. Motion (meanings only)

- Hover/active: `background-color`/`border-color` 150ms ease.
- Panel/route enter: `opacity` fade 150ms (no translate bounce).
- Progress bars: `width` 300ms ease-out on mount.
- No decorative micro-animation, no hover that changes nothing, no parallax.
  GPU-composited properties only.

## 8. Accessibility

- All interactive elements: `:focus-visible` ring `0 0 0 2px var(--accent)` +
  offset. Never remove focus styles.
- Severity/status conveyed by **dot + text label**, never color alone.
- Mono numerals use `tabular-nums`. Contrast ≥ AA on text.
- Nav + rows keyboard-operable (Enter/Space). `aria-current` on active nav.

## 9. Accepted debt (intentional, named)

- Auth is a stub (Day 8 D8-M2 human-authz is not built yet) — role filter is
  wired but unenforced.
- Dark theme only (no light toggle).
- Data source: Firestore emulator when reachable, else bundled demo dataset
  (clearly a dev/demo path; production deploy talks to live Firestore).
- No i18n; English only. Trace view is a simplified timeline (full OTel drill
  down is Day 10).
