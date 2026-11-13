import {chromium} from "playwright";
const b = await chromium.launch({executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"]});
const p = await (await b.newContext({viewport: {width: 1280, height: 900}})).newPage(); const errs = [];
p.on("pageerror", (e) => errs.push(e.message)); p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
await p.goto((process.env.BASE || "http://127.0.0.1:8770") + "/search", {waitUntil: "networkidle"}); await p.waitForSelector("#status");
for (const [q, slop, verdict, wh = "include"] of [["active directory", "include", "any", "only"], ["active directory", "include", "any", "leave out"], ["owner:neuralblitz", "only", "any"], ["code review", "leave out", "use"], ["terraform module", "include", "any"], ["react native testing", "include", "any"], ["id:590504", "include", "any"], ["zzzqqqxyz", "include", "any"]]) {
  const radio = (group, v) => p.locator("form", {hasText: group}).getByLabel(v, {exact: true}).check();
  await radio("Slop-skills", slop); await radio("Verdict", verdict); await radio("Security tools", wh);
  await p.fill('input[type=text]', q); { const b = p.locator("button:has-text('Search')"); if (await b.isEnabled()) await b.click(); }
  await p.waitForSelector(`#status[data-q="${q}|${verdict}|${slop}"][data-wh="${wh}"]`, {timeout: 180000});
  const status = await p.textContent("#status");
  const first = await p.$$eval(".result h3", (e) => e.slice(0, 3).map((x) => x.textContent.replace(/\s+/g, " ").trim()));
  const nwh = await p.$$eval(".result .badge.whitehat", (e) => e.length);
  console.log(`${q} [verdict=${verdict}, slop=${slop}, security=${wh}] => ${status}, white-hat badges ${nwh}`, first);
}
console.log("errors", errs); await b.close();
