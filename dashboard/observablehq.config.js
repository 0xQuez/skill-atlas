export default {
  title: "Skill Atlas",
  root: "src",
  output: process.env.OBS_OUT || "dist",
  theme: ["air", "near-midnight", "wide"],
  pages: [
    {name: "Overview", path: "/"},
    {name: "Search", path: "/search"},
    {name: "Copies", path: "/families"},
    {name: "Slop-skills", path: "/slop"},
    {name: "Security tools", path: "/security"},
    {name: "Eval", path: "/eval"},
    {name: "For agents", path: "/agents"},
    {name: "About & method", path: "/about"}
  ],
  head: '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%97%BA%EF%B8%8F%3C/text%3E%3C/svg%3E">',
  header: `<div class="sa-header"><span class="sa-logo">◆</span> <b>Skill Atlas</b> <span class="sa-muted">which agent skills are worth using</span><span class="sa-pill">${process.env.ATLAS_PILL || "local preview"}</span></div>`,
  footer: 'Data: <a href="https://huggingface.co/datasets/mvaccargiu/gitskills">GitSkills</a> (Destefanis et al., arXiv 2608.10906), CC BY 4.0. Verdicts come from simple rules and can be wrong.',
  toc: true,
  search: false,
  linkify: true,
  style: "style.css"
};
