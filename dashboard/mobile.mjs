import {chromium} from "playwright";
const b = await chromium.launch({executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"]});
const ctx = await b.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 2, isMobile: true, hasTouch: true});
const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(e.message));
for (const [n, path] of [["overview", "/"], ["search", "/search"]]) {
  await p.goto("http://127.0.0.1:8770" + path, {waitUntil: "networkidle"}); if (n === "search") await p.waitForSelector(".result");
  await p.waitForTimeout(1000); await p.screenshot({path: `screenshots/${n}-mobile.png`});
}
console.log("mobile errors:", errs.length); await b.close();
