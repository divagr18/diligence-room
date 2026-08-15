# Acme Robotics — Synthetic Dataset Plan (BUILD_PLAN D2-M4, vision §26)

Target under diligence: **Acme Robotics, Inc.** Deal: **Project Falcon** (`deal-falcon`).
All data is synthetic; no real company, person, or figure is represented.

## Entity aliases (single source of truth for consistency)

| Alias | Synthetic identity |
|---|---|
| Customer X | Meridian Logistics, Inc. (Enterprise logistics customer) |
| Key person | Dana Whitfield, VP Customer Success — owns the Meridian relationship |
| Unsupported component | "TitanBridge 4.1" fleet-orchestration runtime (vendor EOL) |
| Deal team lead | (human) deal lead, Project Falcon |

**Hard consistency rules** (enforced by evals and the Day-8 keystone):

1. Customer X = **18.3% of projected FY27 revenue** — identical figure in
   `financials_fy27.xlsx`, every Finance finding, and every gateway response.
2. The change-of-control termination right lives ONLY in
   `contract_customer_x.pdf` §11.3; no other doc may grant or waive it.
3. Dana Whitfield's departure timeline (60 days from roster date) appears only
   in the HR roster; HR doc and contract must not cross-reference.
4. TitanBridge 4.1 dependency appears in `tech_inventory.pdf` and
   `vendor_agreement_2027.pdf`; the 2030 amendment modifies ONLY the
   exclusivity term, nothing else.

## Seed table

| # | File | Format | Workstream | Planted fact | Day | Consumed by |
|---|---|---|---|---|---|---|
| 1 | `contract_customer_x.pdf` | native PDF | Legal | Meridian CoC termination right (§11.3); 3-year master services term | 2 | D3 finding smoke, Day-5 governed query, Day-8 keystone |
| 2 | `financials_fy27.xlsx` | XLSX | Finance | Meridian = $8,893,800 of $48,600,000 projected FY27 revenue = 18.3% | 2 | Day-5 gateway aggregate, Day-8 keystone |
| 3 | `hr_roster_acme.xlsx` | XLSX | HR | Dana Whitfield (VP Customer Success, Meridian account owner) resignation effective in 60 days | **DRAFT authored D2 (D2-M6)**; finalized 3 (D3-M7) | Day-8 keystone |
| 4 | `tech_inventory.pdf` | native PDF | IP/Tech | Meridian-serving fleet-orchestration subsystem runs on TitanBridge 4.1 (vendor EOL, no support contract) | **DRAFT authored D2 (D2-M6)**; finalized 4 (D4-M3) | Day-8 keystone |
| 5 | `vendor_agreement_2027.pdf` | native PDF | Legal/IP | TitanBridge license: exclusivity ends 2027-06-30 | 4 (D4-M3) | Day-5 amendment lineage |
| 6 | `amendment_2030.pdf` | native PDF | Legal | Extends TitanBridge exclusivity to 2030-06-30; lineage-linked to #5; tests update-not-duplicate (vision §16 Day 7) | 5 (D5-M5) | D10 memory test, Day-7 scenario beat |
| 7 | malicious batch #1 (×5) | mixed | Armor/Red-team | injection ×2, exfiltration ×2, obfuscated injection ×1 | 6 (D6-M6) | D7 quarantine beat |
| 8 | attacks wave 2 (×4) + noise (×3) | mixed | Armor + ingestion realism | +2 injection, +1 exfil, +1 priv-esc; email export / scan / junk spreadsheet | 10 (D10-M5) | scorecard realism |
| 9 | attack wave 3 (×6) | mixed | Armor | completes the 20-attack ledger (8/5/4/3) | 12 (D12-M3) | final scorecard |

## Document authoring rules

- Authored programmatically via `scripts/author_dataset.py` so every artifact is
  reproducible; committed PDFs/XLSX are the generated output of that script.
- Contracts use clause numbering (§11.3 etc.) so evidence spans can quote a
  locator; verbatim span in findings must match the PDF text byte-for-byte.
- No PII beyond synthetic names/roles in HR docs (DLP path still exercised Day 11).
- Amounts are exact: FY27 total $48,600,000; Meridian $8,893,800 (= 18.300%).
