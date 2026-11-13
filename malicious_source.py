"""Flag skills whose content comes from self-described malicious / poisoned skill collections.
direct  : exact content held by a deny-listed repo (or a deny-listed fixture path inside a scanner repo),
          unless a trusted ordinary repo also holds the same exact content (benign control copied into the benchmark).
derived : a near-copy (pair edge) of a direct skill that carries the direct skill's "payload lines"
          (lines absent from the most-starred ordinary neighbour = the likely original).
Writes out/full/malicious_source.parquet (sid, source_kind, evidence)."""
import duckdb, re, json, hashlib, numpy as np, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc, glob
# Reviewed and NOT listed: AeonDave/malskill (README: "Full-spectrum security skill collection" - offensive-security tooling,
# not deliberately poisoned skills), dazeb/ai-supply-chain-lab, LazyOwn, Find-Evil hackathon repos, malware-analysis packs,
# ry0y4n/evil-sample-skill ("harmless demo"), name false positives (evildarkarchon, poisontr33s, hellopoisonx, ...).
WHOLE = ['trailofbits/overtly-malicious-skills',
 'snyk-labs/toxicskills-goof','Security-Phoenix-demo/ai-goat-ai-vulnerability-exploits-collection','jiaxiaojunQAQ/SkillJect',
 'RUC-NLPIR/ClawTrojan','hushuguo/malicious-mathHelper','Fldicoahkiin/malicious-skill-sample','oussamaelfig/GhostClaw_PoC',
 'hugobatista/unicode-skill-injection-poc','danielmeppiel/poisoned-reviewer-demo','aisa-group/skill-inject',
 'knownasnaffy/prompthound','JSGforever/skillguard']
WHOLE_NAMES = ['overtly-malicious-skills','toxicskills-goof','SkillJect','ClawTrojan','skill-inject']
# keyed by repo NAME so forks / re-uploads are caught; MalSkillBench benign/ controls and PoisonedSkills *_clean sets are not flagged
PATH_RULES = {'SkillAttack': r'^data/skillinject/', 'MalSkillBench': r'^Dataset/Skills/malware/', 'PoisonedSkills': r'.'}
SCANNERS = ['Teycir/SkillsGuard','LichAmnesia/skill-lint','north-echo/waingro','nivishay/SkillGuard','NVIDIA/SkillSpector',
 'agentverus/agentverus-scanner','ondrej-merkun/skill-audit','thedevappsecguy/skill-scanner','jbovet/oxidized-agentic-audit',
 'xcode4tux/skill-specter','pezhik/skilltotal','felixondesk/guardskills','gsknnft/skill-safe-core','hashgraph-online/hol-guard',
 'leizhao7/livepi','MohibShaikh/clawvet','MSal2020/skillguard','YAMRAJ13y/skillsentry','Starry-49/Skill-Auditor','thefernandopaes/skillscan']
FIXTURE = r'(^|/)(tests?|test_fixtures|testskills|fixtures|evals?/corpus|eval_corpus|examples/suite|benchmarks)/'
BENIGN = r'benign|good|clean|safe|legit'
c = duckdb.connect(); c.execute("SET memory_limit='1GB'; SET threads=2")
lst = lambda xs: "(" + ",".join("'" + x + "'" for x in xs) + ")"
pr = ' OR '.join(f"(split_part(a.repo_full_name,'/',2)='{k}' AND regexp_matches(a.path,'{v}') AND NOT regexp_matches(lower(a.path),'_clean/|/benign/'))" for k, v in PATH_RULES.items())
c.execute(f"""CREATE TABLE h AS SELECT a.file_sha, a.repo_full_name repo, a.path, coalesce(r.stars,0) stars,
  CASE WHEN a.repo_full_name IN {lst(WHOLE)} OR split_part(a.repo_full_name,'/',2) IN {lst(WHOLE_NAMES)} THEN 'deny_repo'
       WHEN {pr} THEN 'deny_path'
       WHEN a.repo_full_name IN {lst(SCANNERS)} AND regexp_matches(a.path,'{FIXTURE}') AND NOT regexp_matches(lower(a.path),'{BENIGN}') THEN 'scanner_fixture'
       ELSE NULL END kind
  FROM (SELECT file_sha, repo_full_name, path FROM 'hf/data/artifacts/*.parquet') a LEFT JOIN 'hf/data/repos/*.parquet' r ON r.full_name=a.repo_full_name""")
print('deny holders by repo', c.execute("SELECT repo, kind, count(*) FROM h WHERE kind IS NOT NULL GROUP BY 1,2 ORDER BY 3 DESC").fetchall(), flush=True)
c.execute("""CREATE TABLE fs AS SELECT file_sha, max(stars) FILTER (kind IS NOT NULL) deny_stars,
   max(stars) FILTER (kind IS NULL) ok_stars, arg_max(repo, stars) FILTER (kind IS NULL) ok_repo,
   arg_max(repo||'/'||path, stars) FILTER (kind IS NOT NULL) deny_where, arg_max(kind, stars) FILTER (kind IS NOT NULL) kind
   FROM h GROUP BY 1 HAVING count(*) FILTER (kind IS NOT NULL) > 0""")
c.execute("CREATE TABLE d2 AS SELECT s.sid, s.cluster_id, fs.*, coalesce(ok_stars,-1) >= greatest(5, deny_stars) AS exempt FROM fs JOIN 'out/full/skills.parquet' s USING(file_sha)")
c.execute("COPY (SELECT sid, ok_repo, ok_stars, deny_where, deny_stars FROM d2 WHERE exempt) TO 'out/full/malicious_source_exempt.csv'")
stats = dict(c.execute("SELECT 'held_by_deny', count(*) FROM d2 UNION ALL SELECT 'exempt_trusted_copy', count(*) FROM d2 WHERE exempt UNION ALL SELECT 'direct', count(*) FROM d2 WHERE NOT exempt").fetchall())
print(stats, c.execute("SELECT kind, count(*) FROM d2 WHERE NOT exempt GROUP BY 1").fetchall(), flush=True)
direct = c.execute("SELECT sid, kind, deny_where FROM d2 WHERE NOT exempt").fetchall()
D = {s for s, _, _ in direct}
c.execute("CREATE TABLE ds AS SELECT sid FROM d2 WHERE NOT exempt")
c.execute("""CREATE TABLE e AS SELECT sid_a x, sid_b y FROM 'out/full/pairs.parquet' WHERE kind<>'embedding_rejected' AND sid_a IN (SELECT sid FROM ds)
             UNION ALL SELECT sid_b, sid_a FROM 'out/full/pairs.parquet' WHERE kind<>'embedding_rejected' AND sid_b IN (SELECT sid FROM ds)""")
c.execute("CREATE TABLE e2 AS SELECT DISTINCT e.x, e.y, s.max_stars ys FROM e JOIN 'out/full/skills.parquet' s ON s.sid=e.y WHERE e.y NOT IN (SELECT sid FROM ds)")
print('edges to ordinary skills', c.execute("SELECT count(*), count(DISTINCT y) FROM e2").fetchone(), flush=True)
need = D | {y for (y,) in c.execute("SELECT DISTINCT y FROM e2").fetchall()}
SUS = re.compile(r"glot\.io|pastebin\.com|rentry\.co|paste\.ee|hastebin|webhook\.site|discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services|ngrok|requestbin|pipedream\.net|transfer\.sh|interact\.sh|burpcollaborator|base64\s+(?:-d|--decode|-D)[^\n]{0,40}\|\s*(?:ba|z)?sh\b|L2Jpbi9iYXNo|L2Jpbi9zaC|echo\s+['\"][A-Za-z0-9+/=]{40,}|do not (?:tell|inform|mention|reveal|alert|notify) the user|without (?:telling|asking|notifying|informing) the user|(?:silently|covertly|secretly) (?:send|upload|post|copy|exfil|forward|collect|read|run|execute)|\.aws/credentials|\.ssh/id_|authorized_keys|/dev/tcp/|\bnc\s+-e\b|login\.keychain|find-generic-password|(?:https?|tcp)://(?!(?:10|127|0)\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}(?:\.\d{1,3}){3}|password[\s:=]+\w+[^\n]{0,40}(?:zip|archive|extract)", re.I)
SUSH = {}
def lines(t, keep_sus=False):
    out = set()
    for l in (t or '').splitlines():
        l = re.sub(r'\s+', ' ', l.strip().lower())
        if len(l) >= 15 and not l.startswith(('name:', 'description:', '---')):
            h = int.from_bytes(hashlib.blake2b(l.encode(), digest_size=8).digest(), 'little'); out.add(h)
            if keep_sus and SUS.search(l): SUSH.setdefault(keep_sus, set()).add(h)
    return np.array(sorted(out), dtype=np.uint64)
LH = {}; needarr = pa.array(sorted(need), pa.int64())
for p in sorted(glob.glob('out/full/text/part-*.parquet')):
    for b in pq.ParquetFile(p).iter_batches(batch_size=8000, columns=['sid', 'content']):
        m = pc.is_in(b.column(0), value_set=needarr)
        if not pc.any(m).as_py(): continue
        f = b.filter(m)
        for s, t in zip(f.column(0).to_pylist(), f.column(1).to_pylist()): LH[s] = lines(t, s if s in D else False)
print('loaded line sets', len(LH), flush=True)
E = np.array([], np.uint64); nb = {}
# offensive-security skills legitimately quote attack commands; they are judged by the risk score, not by propagation
OFFSEC = {s for (s,) in c.execute("""SELECT s.sid FROM 'out/full/skills.parquet' s WHERE s.sid IN (SELECT y FROM e2)
  AND regexp_matches(lower(coalesce(s.name,'')||' '||coalesce(s.description,'')), 'pentest|penetration|privilege.?escalation|exploit|red.?team|ctf|offensive|attack|forensic|malware|security|vulnerab|hacking')""").fetchall()}
for x, y, ys in c.execute("SELECT x, y, ys FROM e2").fetchall(): nb.setdefault(x, []).append((ys or 0, y))
derived = {}
for x, ys in nb.items():
    ref = max(ys)[1]
    pay = np.setdiff1d(LH.get(x, E), LH.get(ref, E))
    sus = SUSH.get(x, set())
    pay = np.array([h for h in pay if int(h) in sus], np.uint64)   # only lines with a strong malicious signal that the original lacks count
    if len(pay) < 1: continue
    for _, y in ys:
        if y == ref or y in derived or y in OFFSEC: continue
        hit = np.isin(pay, LH.get(y, E)).mean()
        if hit >= 0.6: derived[y] = (x, round(float(hit), 2), int(len(pay)))
rows = [(s, 'direct_' + k, w) for s, k, w in direct] + [(y, 'derived_copy', json.dumps({'of': x, 'payload_lines': n, 'share_carried': h})) for y, (x, h, n) in derived.items()]
pq.write_table(pa.table({'sid': [r[0] for r in rows], 'source_kind': [r[1] for r in rows], 'evidence': [r[2] for r in rows]}), 'out/full/malicious_source.parquet')
stats.update(derived=len(derived), total=len(rows), with_ordinary_neighbours=len(nb))
json.dump(stats, open('out/full/malicious_source_stats.json', 'w'), indent=1); print(stats)
