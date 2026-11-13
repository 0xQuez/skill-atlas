"""Risk v2: secret-access + exfiltration signals. Adds to the v1 risk score in scores.parquet.
Usage: python risk_v2.py run  (scans text parts, 3 procs)  |  python risk_v2.py merge"""
import re, sys, glob, os, ipaddress, json
import pyarrow.parquet as pq, pyarrow as pa
from multiprocessing import Pool
OUT = 'out/full/risk2'
SECRET = re.compile(r"""\.aws/credentials|\.ssh/id_|\bid_rsa\b|\bid_ed25519\b|\bid_ecdsa\b|security\s+find-(?:generic|internet)-password|login\.keychain|\bKeychain\.dump|(?:Login\sData|Cookies)['"/\\]|cookies\.sqlite|\bLocal\sState['"]|\.netrc\b|\.git-credentials|\.docker/config\.json|\.kube/config|/etc/shadow|wallet\.dat|\.solana/id\.json|\.config/gcloud/|\bprintenv\b(?!\s+\w)|\benv\s*\|\s*(?:curl|nc|base64|xxd)|os\.environ\.copy\(\)|dict\(\s*os\.environ\s*\)|json\.dumps\(\s*(?:dict\()?\s*os\.environ|JSON\.stringify\(\s*process\.env\s*\)|in\s+os\.environ\.items\(\)|Object\.(?:entries|keys)\(\s*process\.env\s*\)|\bcat\s+[^\n|]{0,40}\.env\b""", re.I)
IPURL = re.compile(r"(?:https?|wss?|tcp)://(\d{1,3}(?:\.\d{1,3}){3})|/dev/tcp/(\d{1,3}(?:\.\d{1,3}){3})|connect\(\(\s*['\"](\d{1,3}(?:\.\d{1,3}){3})['\"]")
HOOK = re.compile(r"discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services|webhook\.site|requestbin|pipedream\.net|\bngrok(?:-free)?\.(?:io|app|dev)|pastebin\.com|transfer\.sh|\binteract\.sh|\boast\.(?:fun|me|pro|live|site|online)|burpcollaborator|\.trycloudflare\.com|api\.telegram\.org/bot|hookbin|beeceptor\.com", re.I)
POST = re.compile(r"""(?:requests\.post|httpx\.post|aiohttp[^\n]{0,30}\.post|urllib\.request\.urlopen|method\s*[:=]\s*['"]POST['"]|curl\b[^\n]{0,120}?(?:\s-d\s|--data|\s-F\s|-X\s*POST))[^\n]{0,200}?https?://([A-Za-z0-9.-]+)""", re.I)
ALLOW = re.compile(r"(?:^|\.)(?:github\.com|githubusercontent\.com|gitlab\.com|openai\.com|anthropic\.com|googleapis\.com|google\.com|microsoft\.com|azure\.com|amazonaws\.com|slack\.com|notion\.com|notion\.so|stripe\.com|atlassian\.net|atlassian\.com|linear\.app|vercel\.com|supabase\.co|cloudflare\.com|huggingface\.co|example\.com|example\.org|localhost|x\.com|twitter\.com|telegram\.org|discord\.com|openrouter\.ai|figma\.com|airtable\.com|hubspot\.com|sentry\.io|pagerduty\.com|twilio\.com|sendgrid\.com|mailgun\.net|feishu\.cn|larksuite\.com|dingtalk\.com|qq\.com|weixin\.qq\.com|baidu\.com|aliyuncs\.com|volces\.com|deepseek\.com|moonshot\.cn|bigmodel\.cn|your[-\w]*\.\w+)$", re.I)
def public_ip(s):
    try:
        ip = ipaddress.ip_address(s)
        return not (ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_reserved or ip.is_multicast or s.startswith('0.') or str(ip) in ('1.1.1.1','8.8.8.8','8.8.4.4','9.9.9.9','1.0.0.1'))
    except ValueError:
        return False
def scan(t):
    sec = SECRET.search(t)
    ips = [g for m in IPURL.finditer(t) for g in m.groups() if g]
    pip = next((i for i in ips if public_ip(i)), None)
    hook = HOOK.search(t)
    post = next((m.group(1) for m in POST.finditer(t) if not ALLOW.search(m.group(1).lower()) and not re.match(r'\d', m.group(1))), None)
    return (sec.group(0)[:60] if sec else None, pip, hook.group(0)[:60] if hook else None, post)
def work(path):
    out = f"{OUT}/{os.path.basename(path)}"
    if os.path.exists(out): return out
    rows = {k: [] for k in ('sid','sec','pip','hook','post')}
    for b in pq.ParquetFile(path).iter_batches(batch_size=4000, columns=['sid','content']):
        for sid, t in zip(b.column(0).to_pylist(), b.column(1).to_pylist()):
            if not t: continue
            r = scan(t)
            if any(r):
                rows['sid'].append(sid)
                for k, v in zip(('sec','pip','hook','post'), r): rows[k].append(v)
    pq.write_table(pa.table(rows), out + '.tmp', compression='zstd'); os.rename(out + '.tmp', out)
    return out
if __name__ == '__main__':
    if sys.argv[1] == 'run':
        parts = sorted(glob.glob('out/full/text/part-*.parquet'))
        with Pool(int(os.environ.get('PROCS', 3)), maxtasksperchild=2) as p:
            for o in p.imap_unordered(work, parts): print('done', o, flush=True)

def merge():
    """scores.parquet (v1, backed up as scores_v1.parquet) + risk2 flags -> scores.parquet with risk v2.
    risk_v2 = risk_v1 - 10*[v1 raw_ip_url, which also counted private IPs] + 20*[public_raw_ip]
              (exfil_endpoint / secret_access alone are flags only: in the 30-skill review they were mostly docs and pentest notes)
              and, when a secret is read in code AND a code statement sends data to a public IP / exfil endpoint / unknown host
              (secret_exfil_combo): at least 45 (high). Capped at 100."""
    import duckdb, shutil
    if not os.path.exists('out/full/scores_v1.parquet'): shutil.copy('out/full/scores.parquet', 'out/full/scores_v1.parquet')
    c = duckdb.connect(); c.execute("SET memory_limit='1GB'; SET threads=2")
    # pass a (risk2/: public raw IPs, exfil endpoints anywhere) + pass c (risk_v2c.py: secret READ in code, and a code statement
    # that SENDS data to a public IP / exfil endpoint / unknown host). Pass b only selects pass-c candidates.
    c.execute("""CREATE TABLE r AS SELECT sid, cc.secret_read sec, cc.code_public_ip pip, a.hook, cc.exfil_send post
      FROM 'out/full/risk2/part-*.parquet' a FULL OUTER JOIN 'out/full/risk2c.parquet' cc USING(sid)""")
    c.execute("""COPY (SELECT s.sid, s.quality,
        least(100, CASE WHEN r.sec IS NOT NULL AND r.post IS NOT NULL THEN greatest(45, base) ELSE base END)::DOUBLE AS risk,
        s.n_domains,
        nullif(array_to_string(list_filter(list_concat(list_filter(string_split(coalesce(s.risk_flags,''),','), lambda f: f<>'' AND f<>'raw_ip_url'),
          [CASE WHEN r.pip IS NOT NULL THEN 'public_raw_ip' END, CASE WHEN r.hook IS NOT NULL THEN 'exfil_endpoint' END,
           CASE WHEN r.post IS NOT NULL THEN 'post_unknown_host' END, CASE WHEN r.sec IS NOT NULL THEN 'secret_access' END,
           CASE WHEN r.sec IS NOT NULL AND r.post IS NOT NULL THEN 'secret_exfil_combo' END]), lambda f: f IS NOT NULL), ','), '') AS risk_flags,
        s.risk AS risk_v1, r.sec ev_secret, r.pip ev_ip, r.hook ev_hook, r.post ev_post_host
      FROM (SELECT *, s0.risk - 10*(coalesce(s0.risk_flags,'') LIKE '%raw_ip_url%')::INT
              + 20*(r0.pip IS NOT NULL)::INT AS base
            FROM 'out/full/scores_v1.parquet' s0 LEFT JOIN r r0 USING(sid)) s LEFT JOIN r USING(sid)) TO 'out/full/scores.parquet' (FORMAT parquet)""")
    print(c.execute("""SELECT count(*) FILTER (risk_v1<40 AND risk>=40) newly_high, count(*) FILTER (risk_v1>=40 AND risk<40) no_longer_high,
       count(*) FILTER (risk_flags LIKE '%secret_exfil_combo%') combo, count(*) FILTER (risk_flags LIKE '%public_raw_ip%') pub_ip,
       count(*) FILTER (risk_flags LIKE '%exfil_endpoint%') hook, count(*) FILTER (risk_flags LIKE '%secret_access%') sec
       FROM 'out/full/scores.parquet'""").fetchall())
    st = c.execute("""SELECT count(*) FILTER (risk_v1<40 AND risk>=40), count(*) FILTER (risk_v1>=40 AND risk<40), count(*) FILTER (risk_flags LIKE '%secret_exfil_combo%'),
       count(*) FILTER (risk_flags LIKE '%public_raw_ip%'), count(*) FILTER (risk_flags LIKE '%exfil_endpoint%'), count(*) FILTER (risk_flags LIKE '%secret_access%'),
       count(*) FILTER (risk>=40), count(*) FILTER (risk_v1>=40) FROM 'out/full/scores.parquet'""").fetchone()
    json.dump(dict(zip(['newly_high', 'no_longer_high', 'secret_exfil_combo', 'public_raw_ip', 'exfil_endpoint', 'secret_access', 'high_v2', 'high_v1'], st)), open('out/full/risk_v2_stats.json', 'w'), indent=1)

if __name__ == '__main__' and sys.argv[1] == 'merge': merge()
