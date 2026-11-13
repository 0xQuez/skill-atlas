"""Skill Atlas service: JSON API + MCP (streamable HTTP at /mcp) over verdicts_compact.parquet.
DuckDB queries the Parquet file in place (nothing loaded into RAM up front); memory_limit keeps it small-host friendly.
Run: SKILL_ATLAS_DATA=../out/full/verdicts_compact.parquet uvicorn app:app --host 127.0.0.1 --port 8765"""
import os, re, json, threading, time
import duckdb
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
try:
    from mcp.server.mcpserver import MCPServer
    _MCP_V2 = True
except ImportError:  # Gradio Spaces ship mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
    _MCP_V2 = False
from mcp.server.transport_security import TransportSecuritySettings

DATA = os.environ.get("SKILL_ATLAS_DATA", os.path.join(os.path.dirname(__file__), "..", "out", "full", "verdicts_compact.parquet"))
STATS = os.environ.get("SKILL_ATLAS_STATS", os.path.join(os.path.dirname(DATA), "headline.json"))
_con = duckdb.connect()
_con.execute(f"SET memory_limit='{os.environ.get('DUCKDB_MEMORY','256MB')}'; SET threads={int(os.environ.get('DUCKDB_THREADS','2'))}")
_con.execute(f"CREATE VIEW skills AS SELECT * FROM read_parquet('{DATA}')")  # point lookups by skill_id
# token index built by server/build_search.py (name + owner/repo + first 200 chars of description, normalised, rank-sorted)
SEARCH = os.environ.get("SKILL_ATLAS_SEARCH", os.path.join(os.path.dirname(DATA), "search_api.parquet"))
_con.execute(f"CREATE VIEW sidx AS SELECT * FROM read_parquet('{SEARCH}')")
_lock = threading.Lock()
COLS = ("skill_id, canonical_id, name, description, top_repo, rep_repo, rep_path, github_url, license, max_stars, n_files, n_repos, "
        "cluster_id, cluster_size, name_key, family_canonical_id, canon_basis, renamed_copy, is_canonical, quality, risk, risk_flags, slop_skill, slop_reasons, verdict, reasons, white_hat, white_hat_kind, category")
VERDICTS = {"use", "caution", "ignore"}
WHITE_HAT_MODES = {"include", "exclude", "only"}
WHITE_HAT_NOTE = ("White-hat security tool: a legit offensive-security / pentest / CTF / forensics skill that does dangerous things on purpose. "
                  "Use only for authorised security work. This tag does not change the verdict or risk score.")

def _q(sql, params=()):
    cur = _con.cursor()
    rel = cur.execute(sql, list(params)); names = [d[0] for d in rel.description]
    return [dict(zip(names, r)) for r in rel.fetchall()]

def _shape(r):
    if r is None: return None
    return {"skill_id": r["skill_id"], "canonical_id": r["canonical_id"], "is_canonical": bool(r["is_canonical"]),
            "name": r["name"], "description": r["description"], "repo": r["top_repo"] or r["rep_repo"], "github_url": r["github_url"], "dataset_copy": {"repo": r["rep_repo"], "path": r["rep_path"]},
            "license": r["license"] or None, "max_stars": r["max_stars"], "copies": {"files": r["n_files"], "repos": r["n_repos"]},
            "family": {"cluster_id": r["cluster_id"] if r["cluster_id"] is not None and r["cluster_id"] >= 0 else None, "size": r["cluster_size"], "family_canonical_id": r["family_canonical_id"]},
            "name_key": r["name_key"], "canon_basis": r["canon_basis"], "renamed_copy": bool(r["renamed_copy"]),
            "verdict": r["verdict"], "reasons": json.loads(r["reasons"]) if r["reasons"] else [],
            "quality": r["quality"], "risk": r["risk"], "risk_flags": [f for f in (r["risk_flags"] or "").split(",") if f],
            "slop_skill": bool(r["slop_skill"]), "slop_evidence": [e for e in (r["slop_reasons"] or "").split(" | ") if e],
            "category": r.get("category"), "white_hat": bool(r.get("white_hat")), "white_hat_kind": r.get("white_hat_kind"),
            **({"white_hat_note": WHITE_HAT_NOTE} if r.get("white_hat") else {})}

def get_skill(skill_id: int):
    rows = _q(f"SELECT {COLS} FROM skills WHERE skill_id = ?", (int(skill_id),))
    return _shape(rows[0]) if rows else None

def tokens(q: str):
    """Same normalisation as build_search.py: lowercase, split on whitespace and - _ . / : , ; ( ) [ ] quotes."""
    return [t for t in re.split(r"[\s\-_./:,;()\[\]\"'`]+", (q or "").lower()) if t][:8]

def search(q: str = "", verdict: str | None = None, slop: bool | None = None, limit: int = 20, white_hat: str | None = "include"):
    """Every query word must appear (any order) in name, owner/repo or the first 200 chars of the description.
    Ranking: exact owner/repo first, then all words in the name, then exact name, then use > caution > ignore, canonical, stars."""
    limit = max(1, min(int(limit), 100)); where = []; params = []
    toks = tokens(q)
    for t in toks:
        where.append("contains(hay, ?)"); params.append(t)
    if verdict:
        if verdict not in VERDICTS: raise ValueError("verdict must be use, caution or ignore")
        where.append("verdict = ?"); params.append(verdict)
    if slop is not None:
        where.append("slop_skill = ?"); params.append(bool(slop))
    white_hat = (white_hat or "include").lower()
    if white_hat not in WHITE_HAT_MODES: raise ValueError("white_hat must be include, exclude or only")
    if white_hat == "exclude": where.append("NOT white_hat")
    if white_hat == "only": where.append("white_hat")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    name_all = " AND ".join(["contains(name_n, ?)"] * len(toks)) or "rk < 0"
    order = f"ORDER BY (repo_n = ?) DESC, ({name_all}) DESC, (name_n = ?) DESC, rk"
    # phase 1 scans only the small text columns; phase 2 fetches full rows by rk (file is rk-sorted, so each lookup hits one row group)
    oparams = [" ".join(toks)] + toks + [" ".join(toks)]
    if not toks: order, oparams = "ORDER BY rk", []
    rks = [r["rk"] for r in _q(f"SELECT rk FROM sidx {w} {order} LIMIT {limit}", params + oparams)]
    got = {}
    if rks:
        for r in _q(" UNION ALL ".join(f"SELECT rk, {COLS} FROM sidx WHERE rk = {int(k)}" for k in rks)): got[r["rk"]] = r
    res = [_shape(got[k]) for k in rks if k in got]
    return {"query": q, "tokens": toks, "match": "all words, any order, in name / owner-repo / description[:200]",
            "filters": {"verdict": verdict, "slop": slop, "white_hat": white_hat}, "count": len(res), "results": res}

def canonical(skill_id: int):
    s = get_skill(skill_id)
    if s is None: return None
    if s["canonical_id"] is None:   # every member of this group comes from a known-malicious source: no safe pick
        return {"skill_id": s["skill_id"], "canonical_id": None, "is_canonical": False, "family_size": s["family"]["size"],
                "canonical": None, "note": "no_safe_canonical: all members come from known malicious sources", "same_name_members_sample": [],
                "browse_family": {"cluster_id": s["family"]["cluster_id"], "size": s["family"]["size"], "family_canonical_id": s["family"]["family_canonical_id"]}}
    c = s if s["is_canonical"] else get_skill(s["canonical_id"])
    others = []
    if s["family"]["cluster_id"] is not None:
        others = [{"skill_id": r["skill_id"], "name": r["name"], "repo": r["rep_repo"], "verdict": r["verdict"], "github_url": r["github_url"]}
                  for r in _q("SELECT skill_id, name, coalesce(top_repo, rep_repo) rep_repo, verdict, github_url FROM skills WHERE cluster_id = ? AND name_key IS NOT DISTINCT FROM ? AND skill_id <> ? ORDER BY max_stars DESC NULLS LAST LIMIT 5",
                              (s["family"]["cluster_id"], c["name_key"], c["skill_id"]))]
    return {"skill_id": s["skill_id"], "canonical_id": c["skill_id"], "is_canonical": s["is_canonical"], "family_size": s["family"]["size"],
            "canonical": c, "same_name_members_sample": others,
            "browse_family": {"cluster_id": s["family"]["cluster_id"], "size": s["family"]["size"], "family_canonical_id": s["family"]["family_canonical_id"]}}

def stats():
    out = {"rows": _q("SELECT count(*) n FROM skills")[0]["n"],
           "verdicts": {r["verdict"]: r["n"] for r in _q("SELECT verdict, count(*) n FROM skills GROUP BY 1 ORDER BY 2 DESC")},
           "slop_skills": _q("SELECT count(*) n FROM skills WHERE slop_skill")[0]["n"],
           "white_hat_skills": _q("SELECT count(*) n FROM skills WHERE white_hat")[0]["n"], "white_hat_note": WHITE_HAT_NOTE}
    if os.path.exists(STATS):
        h = json.load(open(STATS))
        out["headline"] = {k: h.get(k) for k in ("artifact_rows", "distinct_contents", "exact_copy_occurrence_pct", "clusters", "near_copy_rate_distinct_pct",
                                                 "file_rows_redundant_pct_exact_or_near", "embedded")}
        out["slop_criteria"] = h.get("slop", {}).get("criteria")
    out["source"] = "GitSkills (Destefanis et al., arXiv 2608.10906), CC BY 4.0; derived verdicts by Skill Atlas"
    return out

# ---------------- MCP ----------------
def _csv_env(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]

def _bind_host():
    return os.environ.get("HOST") or os.environ.get("SPACE_HOST") or "127.0.0.1"

def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1", "[::1]")

def _production(host: str) -> bool:
    if os.environ.get("ATLAS_PRODUCTION", "").strip() in ("1", "true", "yes"):
        return True
    if os.environ.get("SPACE_HOST"):
        return True
    return not _is_loopback(host)

_host = _bind_host()
_prod = _production(_host)
_allowed_hosts = list(dict.fromkeys([_host, *_csv_env("ALLOWED_HOSTS"), *(_csv_env("SPACE_HOST") if os.environ.get("SPACE_HOST") else [])]))
_origins = _csv_env("CORS_ORIGINS", "*" if _prod else "")
_rate = int(os.environ.get("RATE_LIMIT_PER_MIN", "60" if _prod else "0") or 0)
_max_body = int(os.environ.get("MAX_REQUEST_BODY", str(1_048_576 if _prod else 4_194_304)))
if _prod:
    _ts = TransportSecuritySettings(enable_dns_rebinding_protection=False, allowed_hosts=[], allowed_origins=[])
else:
    _ts = None

_INSTRUCTIONS = ("Look up agent skills (SKILL.md files on GitHub) and whether they are worth using. "
                "verdict is use / caution / ignore with machine-readable reasons; prefer canonical_id over near-copies. "
                "category 'white_hat_security' marks legit offensive-security tools: use them only for authorised security work.")
if _MCP_V2:
    mcp = MCPServer("skill-atlas", instructions=_INSTRUCTIONS)
else:
    mcp = MCPServer("skill-atlas", instructions=_INSTRUCTIONS,
                    streamable_http_path="/mcp", json_response=True, stateless_http=True,
                    host=_host, transport_security=_ts, max_request_body_size=_max_body)

@mcp.tool()
def search_skills(query: str, verdict: str | None = None, slop: bool | None = None, limit: int = 10, white_hat: str = "include") -> dict:
    """Search skills: every word of the query must appear (any order, case-insensitive) in the name, owner/repo or description. Optional filters: verdict (use|caution|ignore), slop (true/false), white_hat (include|exclude|only; white-hat = legit offensive-security / pentest / CTF / forensics tools that do dangerous things on purpose, for authorised security work only). Max 100."""
    return search(query, verdict, slop, limit, white_hat)

@mcp.tool()
def get_skill_verdict(skill_id: int) -> dict:
    """Return the verdict (use|caution|ignore), reasons, quality/risk scores, slop flag + evidence, category (white_hat_security for legit offensive-security tools), canonical_id and GitHub link for one skill."""
    return get_skill(skill_id) or {"error": "not_found", "skill_id": skill_id}

@mcp.tool()
def find_canonical(skill_id: int) -> dict:
    """Return the canonical (best) member of this skill's near-copy family, plus a sample of other members."""
    return canonical(skill_id) or {"error": "not_found", "skill_id": skill_id}

# ---------------- JSON API (same app) ----------------
def _bool(v):
    return None if v in (None, "") else v.lower() in ("1", "true", "yes")

@mcp.custom_route("/skills/search", methods=["GET"])
async def api_search(req: Request):
    p = req.query_params
    try: return JSONResponse(search(p.get("q", ""), p.get("verdict") or None, _bool(p.get("slop")), int(p.get("limit", 20)), p.get("white_hat") or "include"))
    except ValueError as e: return JSONResponse({"error": str(e)}, status_code=400)

@mcp.custom_route("/skills/{skill_id:int}/verdict", methods=["GET"])
async def api_verdict(req: Request):
    s = get_skill(req.path_params["skill_id"]); return JSONResponse(s) if s else JSONResponse({"error": "not_found"}, status_code=404)

@mcp.custom_route("/skills/{skill_id:int}/canonical", methods=["GET"])
async def api_canonical(req: Request):
    s = canonical(req.path_params["skill_id"]); return JSONResponse(s) if s else JSONResponse({"error": "not_found"}, status_code=404)

@mcp.custom_route("/stats", methods=["GET"])
async def api_stats(req: Request):
    return JSONResponse(stats())

@mcp.custom_route("/healthz", methods=["GET"])
async def health(req: Request):
    return JSONResponse({"ok": True})

@mcp.custom_route("/", methods=["GET"])
async def api_root(req: Request):
    return JSONResponse({"service": "skill-atlas", "health": "/healthz", "mcp": "/mcp",
                         "search": "/skills/search", "stats": "/stats",
                         "source": "GitSkills (Destefanis et al., arXiv 2608.10906), CC BY 4.0; derived verdicts by Skill Atlas"})

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP sliding window. Uses X-Forwarded-For when present (Hugging Face Spaces)."""
    def __init__(self, app, per_min: int):
        super().__init__(app)
        self.per_min = per_min
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()
        self._n = 0

    def _client_ip(self, request) -> str:
        # Prefer platform-set headers. Do not trust a client-supplied first
        # X-Forwarded-For hop (it is easy to rotate and bypass the limiter).
        for name in ("cf-connecting-ip", "true-client-ip", "x-real-ip"):
            val = (request.headers.get(name) or "").strip()
            if val:
                return val.split(",")[0].strip()
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            # Hugging Face appends the connecting client; the last hop is the
            # one the platform observed, the first hops may be spoofed.
            if parts:
                return parts[-1]
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request, call_next):
        if request.url.path in ("/healthz", "/"):
            return await call_next(request)
        ip = self._client_ip(request)
        now = time.time()
        with self.lock:
            window = [t for t in self.hits.get(ip, []) if now - t < 60]
            if len(window) >= self.per_min:
                retry = max(1, int(60 - (now - window[0])))
                return JSONResponse({"error": "rate_limited", "retry_after": retry},
                                    status_code=429, headers={"Retry-After": str(retry)})
            window.append(now)
            self.hits[ip] = window
            self._n += 1
            if self._n % 500 == 0 and len(self.hits) > 1000:
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60}
        return await call_next(request)

class HostCheckMiddleware(BaseHTTPMiddleware):
    """Allow only configured Host headers (DNS-rebinding protection) when running as a public service."""
    def __init__(self, app, allowed: list[str]):
        super().__init__(app)
        self.allowed = set(allowed)

    def _ok(self, host: str | None) -> bool:
        if not host:
            return False
        # Gradio (and other local health checks) probe http://localhost:PORT; always allow loopback.
        base = host.rsplit(":", 1)[0] if ":" in host and not host.startswith("[") else host
        if base in ("127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"):
            return True
        if host in self.allowed:
            return True
        # allow "name:port" when "name:*" is in the list
        if ":" in host:
            if f"{base}:*" in self.allowed or base in self.allowed:
                return True
        return False

    async def dispatch(self, request, call_next):
        if not self._ok(request.headers.get("host")):
            return JSONResponse({"error": "invalid_host"}, status_code=421)
        return await call_next(request)

if _MCP_V2:
    app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                  host=_host, transport_security=_ts, max_request_body_size=_max_body)
else:
    app = mcp.streamable_http_app()
if _prod and _origins:
    app.add_middleware(CORSMiddleware,
                       allow_origins=["*"] if _origins == ["*"] else _origins,
                       allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["*"],
                       max_age=3600)
if _prod:
    host_list = []
    for h in _allowed_hosts:
        host_list += [h, f"{h}:*"] if not h.endswith(":*") else [h]
    app.add_middleware(HostCheckMiddleware, allowed=host_list)
if _rate > 0:
    app.add_middleware(RateLimitMiddleware, per_min=_rate)
