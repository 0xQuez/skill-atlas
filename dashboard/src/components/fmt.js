export const n = (x) => (x == null ? "–" : Number(x).toLocaleString("en-US"));
export const pct = (x, d = 1) => (x == null ? "–" : `${Number(x).toFixed(d)}%`);
export const short = (x) => (x == null ? "–" : x >= 1e6 ? `${(x / 1e6).toFixed(2)}M` : x >= 1e3 ? `${(x / 1e3).toFixed(1)}k` : `${x}`);
export const VCOLORS = {domain: ["use", "caution", "ignore"], range: ["#22a06b", "#e2a400", "#d0454c"]};
// plain-English labels for machine reason codes
export const REASON = (r) => {
  const k = r.replace(/:\d+$/, "");
  const M = {near_copy_of: "copy of another skill", slop_skill: "slop-skill", quality_low: "low quality", quality_medium: "so-so quality",
    risk_high: "high risk", risk_medium: "some risk", invalid_frontmatter: "broken header", renamed_copy: "copy under a new name",
    translated_copy_of: "translation (info only)", known_malicious_source: "from a harmful-skill collection"};
  if (M[k]) return M[k];
  if (k.startsWith("risk_flag:")) return "risky pattern: " + k.slice(10).replace(/_/g, " ");
  if (k.startsWith("junk:")) return "junk: " + k.slice(5).replace(/_/g, " ");
  return k.replace(/_/g, " ");
};
