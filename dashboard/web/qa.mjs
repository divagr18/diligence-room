import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";

const BASE = "http://127.0.0.1:5173";
const OUT = "C:\\Users\\Keshav\\AppData\\Local\\Temp\\opencode\\d7-qa";
fs.mkdirSync(OUT, { recursive: true });

const ROUTES = [
  ["overview", "/"],
  ["findings", "/findings"],
  ["finding-detail", "/findings/SYN-001"],
  ["security", "/security"],
  ["registry", "/registry"],
];
const VIEWPORTS = [
  ["1280", 1280, 800],
  ["768", 768, 1024],
  ["375", 375, 667],
];

const browser = await chromium.launch();
const issues = [];
for (const [vname, w, h] of VIEWPORTS) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: h },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") issues.push(`[${vname}] console: ${m.text()}`);
  });
  page.on("requestfailed", (req) => {
    if (!req.url().includes("favicon"))
      issues.push(`[${vname}] reqfail: ${req.url()} ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    if (res.status() >= 400 && !res.url().includes("favicon"))
      issues.push(`[${vname}] http ${res.status()}: ${res.url()}`);
  });
  for (const [name, route] of ROUTES) {
    await page.goto(BASE + route, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    const fontsOk = await page.evaluate(
      () =>
        document.fonts.check("500 14px Inter") &&
        document.fonts.check("400 13px 'IBM Plex Mono'"),
    );
    await page.screenshot({ path: path.join(OUT, `${name}-${vname}.png`), fullPage: true });
    console.log(`shot ${name}-${vname} inter+plex-loaded=${fontsOk}`);
  }
  await ctx.close();
}
await browser.close();
if (issues.length) {
  console.log("ISSUES:");
  for (const i of issues) console.log(i);
} else {
  console.log("no console/network issues");
}
