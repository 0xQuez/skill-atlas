// Headless check: load every view, collect console errors / failed requests, save full-page screenshots.
import {chromium} from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8770";
const pages = [["overview", "/"], ["search", "/search"], ["families", "/families"], ["slop", "/slop"], ["security", "/security"], ["eval", "/eval"], ["agents", "/agents"], ["about", "/about"]];
const scheme = process.env.SCHEME || "light";
const browser = await chromium.launch({executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"]});
let bad = 0;
for (const [name, path] of pages) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}, colorScheme: scheme, deviceScaleFactor: 1});
  const page = await ctx.newPage(); const errs = []; let bytes = 0;
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errs.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => errs.push("requestfailed: " + r.url() + " " + r.failure()?.errorText));
  page.on("response", async (r) => { const l = +(r.headers()["content-length"] || 0); bytes += l; });
  const t0 = Date.now();
  await page.goto(BASE + path, {waitUntil: "networkidle", timeout: 120000});
  if (name === "search") await page.waitForSelector(".result", {timeout: 120000});
  await page.waitForTimeout(1500);
  const errorCells = await page.$$eval(".observablehq--error", (els) => els.map((e) => e.textContent.slice(0, 300)));
  const file = `screenshots/${name}${scheme === "dark" ? "-dark" : ""}.png`;
  await page.screenshot({path: file, fullPage: true});
  console.log(`${name}: ${((Date.now() - t0) / 1000).toFixed(1)}s, ~${(bytes / 1e6).toFixed(1)} MB transferred, console=${errs.length}, cellErrors=${errorCells.length} -> ${file}`);
  for (const e of [...errs, ...errorCells]) console.log("   ", e.slice(0, 300));
  bad += errs.filter((e) => !e.startsWith("warning")).length + errorCells.length;
  await ctx.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
