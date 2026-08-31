/**
 * Render docs/diagram/Architecture.tsx to docs/diagram/architecture.png.
 *
 * esbuild compiles the component to a browser bundle, Playwright rasterises it
 * at 2x for a crisp PNG. Run from dashboard/web:
 *   node render-diagram.mjs
 */
import { build } from "esbuild";
import { chromium } from "playwright";
import { writeFileSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Lives in dashboard/web because that is where esbuild, React and Playwright
// are installed; Node resolves bare imports from the script's directory.
const HERE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "diagram");
const OUT_PNG = join(HERE, "architecture.png");

// The entry has to live inside dashboard/web: esbuild resolves react and
// react-dom relative to the importing file, not the working directory.
const entry = join(dirname(fileURLToPath(import.meta.url)), ".arch-entry.tsx");
writeFileSync(
  entry,
  `import { createRoot } from "react-dom/client";
   import Architecture from ${JSON.stringify(join(HERE, "Architecture.tsx"))};
   createRoot(document.getElementById("root")).render(<Architecture />);`,
);

const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "iife",
  jsx: "automatic",
  loader: { ".tsx": "tsx" },
  absWorkingDir: process.cwd(),
  // Architecture.tsx lives in docs/, so its react/jsx-runtime import cannot
  // resolve from its own directory; point esbuild at this package's modules.
  nodePaths: [join(dirname(fileURLToPath(import.meta.url)), "node_modules")],
});
const js = bundled.outputFiles[0].text;

const html = `<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;background:#fff}#root{display:inline-block}</style>
<div id="root"></div><script>${js}</script>`;

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: "networkidle" });
await page.waitForSelector("svg");
const svg = await page.$("svg");
await svg.screenshot({ path: OUT_PNG });
rmSync(entry, { force: true });
console.log("wrote", OUT_PNG);
await browser.close();
