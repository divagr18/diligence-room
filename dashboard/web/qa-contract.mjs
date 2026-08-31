/* Programmatic design-contract QA — verifies DESIGN.md rules without pixels.
 * False-positive-safe: ignores html-root dev artifact color, allows rounded-full
 * pills/dots/progressbars (compute to ~9999px+), matches content
 * case-insensitively (labels are uppercased via .overline).
 */
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:5173";
const ROUTES = ["/", "/findings", "/findings/SYN-001", "/documents", "/security", "/registry"];
const VIEWPORTS = [
  ["1280", 1280, 800],
  ["768", 768, 1024],
  ["375", 375, 667],
];

const APPROVED = [
  "rgb(10, 10, 11)", "rgb(16, 16, 17)", "rgb(22, 23, 24)", "rgb(30, 31, 33)",
  "rgba(255, 255, 255, 0.06)", "rgba(255, 255, 255, 0.1)", "rgba(255, 255, 255, 0.16)",
  "rgb(244, 244, 242)", "rgb(200, 200, 196)", "rgb(149, 148, 142)", "rgb(109, 108, 102)",
  "rgb(242, 96, 90)", "rgb(239, 157, 79)", "rgb(217, 185, 92)", "rgb(111, 168, 220)",
  "rgb(154, 160, 166)", "rgb(76, 175, 125)", "rgb(138, 176, 232)", "rgba(138, 176, 232, 0.25)",
];

const issues = [];
const browser = await chromium.launch();

for (const [vname, w, h] of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();

  for (const route of ROUTES) {
    await page.goto(BASE + route, { waitUntil: "networkidle" });
    await page.waitForTimeout(400);
    const label = `${route}@${vname}`;

    const gradientEls = await page.evaluate(() => {
      const bad = [];
      for (const el of document.body.querySelectorAll("*")) {
        const v = getComputedStyle(el).getPropertyValue("background-image");
        if (v && /gradient/i.test(v) && v !== "none") {
          bad.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 50)} bg-image=${v.slice(0, 80)}`);
        }
      }
      return bad;
    });
    if (gradientEls.length) issues.push(`[${label}] GRADIENTS: ${gradientEls.slice(0, 3).join(" | ")}`);

    const colorViolations = await page.evaluate((approved) => {
      const clean = (v) => v.replace(/\s+/g, " ").trim();
      const badColors = new Set();
      const badRadius = new Set();
      for (const el of document.body.querySelectorAll("*")) {
        const cs = getComputedStyle(el);
        for (const prop of ["color", "backgroundColor", "borderTopColor"]) {
          const v = clean(cs.getPropertyValue(prop));
          if (v && v !== "rgba(0, 0, 0, 0)" && v !== "transparent" && !approved.includes(v)) {
            badColors.add(`${prop}:${v}`);
          }
        }
        const br = cs.borderRadius;
        if (br && br !== "0px") {
          const maxPx = Math.max(...br.split(" ").map((s) => parseFloat(s) || 0));
          if (maxPx > 8.5 && maxPx < 9999) {
            badRadius.add(`${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 40)} radius=${br}`);
          }
        }
      }
      return { colors: [...badColors].slice(0, 8), radii: [...badRadius].slice(0, 5) };
    }, APPROVED);
    for (const c of colorViolations.colors) issues.push(`[${label}] OFF-PALETTE ${c}`);
    for (const r of colorViolations.radii) issues.push(`[${label}] CARD-RADIUS>8px ${r}`);

    const pageOverflow = await page.evaluate((vw) => {
      const docW = document.documentElement.scrollWidth;
      return docW > vw + 1 ? `document scrollWidth=${docW} > viewport=${vw}` : null;
    }, w);
    if (pageOverflow) issues.push(`[${label}] PAGE-OVERFLOW ${pageOverflow}`);

    const bodyText = await page.evaluate(() => document.body.innerText.toLowerCase());
    for (const banned of ["lorem", "todo", "placeholder", "dashboard1", "sample text"]) {
      if (bodyText.includes(banned)) issues.push(`[${label}] PLACEHOLDER-TEXT contains "${banned}"`);
    }

    const fontsOk = await page.evaluate(
      () => document.fonts.check("500 14px Inter") && document.fonts.check("400 13px 'IBM Plex Mono'"),
    );
    if (!fontsOk) issues.push(`[${label}] FONTS not loaded`);

    const txt = (await page.evaluate(() => document.body.innerText)).toLowerCase();
    const requireStrings = (arr) => {
      for (const must of arr) {
        if (!txt.includes(must.toLowerCase())) issues.push(`[${label}] MISSING-CONTENT "${must}"`);
      }
    };
    if (route === "/") {
      requireStrings(["Project Falcon", "HIGH RISK", "Critical", "Workstreams", "Legal", "Real Estate", "Escalation inbox"]);
    }
    if (route === "/findings") {
      const rows = await page.locator('tbody tr[role="link"]').count();
      if (rows < 10) issues.push(`[${label}] FINDINGS-ROWS only ${rows}`);
      requireStrings(["SYN-001", "change-of-control"]);
    }
    if (route === "/findings/SYN-001") {
      requireStrings(["Summary", "Evidence", "Trace", "Contributing agents", "clause:11.3", "finding.escalated"]);
    }
    if (route === "/security") {
      requireStrings(["Prompt Injection", "Quarantined documents", "Security feed", "Model Armor", "Sentinel"]);
    }
    if (route === "/registry") {
      const rows = await page.locator("tbody tr").count();
      if (rows !== 8) issues.push(`[${label}] REGISTRY-AGENTS ${rows} != 8`);
      requireStrings(["Legal Agent", "Real Estate Agent", "Agent registry"]);
    }
  }
  await ctx.close();
}

await browser.close();
if (issues.length) {
  console.log(`CONTRACT VIOLATIONS (${issues.length}):`);
  for (const i of issues) console.log(" -", i);
  process.exit(1);
} else {
  console.log("ALL DESIGN-CONTRACT CHECKS PASS (gradients, palette, card-radius, page-overflow, placeholder, fonts, content)");
}
