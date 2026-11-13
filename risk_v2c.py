"""Risk v2, pass c: strict secret-read + exfiltration detection on the ~15k skills that mention secrets (passes a/b).
secret_read : a strong secret source is READ in code (code fence / indented / inline-code line, not a negated prose line):
              ~/.aws/credentials, ssh private keys (cat/open/read/copy, not `ssh -i`), keychain dumps (not a targeted `find-generic-password -s <service>` lookup), browser cookie / login stores,
              /etc/shadow, .netrc, .git-credentials, docker/kube config, cloud-metadata credential endpoints when requested directly (not quoted as an SSRF/XXE payload), whole-environment dumps.
exfil_send  : a code statement that sends data (POST/PUT, data=, curl -d/-F/-T, nc, /dev/tcp, sendBeacon ...) to a hard-coded
              public raw IP, a webhook/paste/tunnel endpoint, or a non-allowlisted, non-placeholder host (directly or via a URL constant).
code_public_ip: a URL to a public raw IP on a code line (prose / CTF write-up mentions don't count).
Output out/full/risk2c.parquet (sid, secret_read, exfil_send, code_public_ip)."""
import duckdb, re, ipaddress, pyarrow as pa, pyarrow.parquet as pq, glob
from risk_v2 import ALLOW, HOOK
c = duckdb.connect(); c.execute("SET memory_limit='1GB'; SET threads=2; SET preserve_insertion_order=false")
c.execute("""CREATE TABLE cand AS SELECT sid FROM 'out/full/risk2/part-*.parquet' WHERE sec IS NOT NULL
             UNION SELECT sid FROM 'out/full/risk2b.parquet' UNION SELECT sid FROM 'out/full/risk2/part-*.parquet' WHERE pip IS NOT NULL""")
print('candidates', c.execute("select count(*) from cand").fetchone()[0], flush=True)
SECRET = re.compile(r"""(?:cat|less|head|tail|open\(|read_text|readFileSync|readFile|Path\(|base64|cp|scp|tar|zip|glob|get-content|type|strings|sqlite3|shutil\.copy|curl[^\n]*-F)[^\n]{0,80}(?:\.aws/credentials|\.ssh/id_|\bid_rsa\b|\bid_ed25519\b|\.netrc|\.git-credentials|\.docker/config\.json|\.kube/config|/etc/shadow|wallet\.dat|\.solana/id\.json|\.config/gcloud/)
 |["'](?:~|/|\$HOME|%USERPROFILE%)[^"'\n]*(?:\.aws/credentials|\.ssh/id_[a-z0-9]+|/etc/shadow|\.git-credentials|wallet\.dat)["']
 |(?:Chrome|Chromium|Firefox|Brave|Edge|Opera|Safari)[^\n]{0,80}(?:Cookies|Login\sData|cookies\.sqlite|logins\.json|key4\.db)
 |security\s+dump-keychain|find-generic-password\s+-ga\b|login\.keychain(?:-db)?['"\s]
 |(?:urlopen|requests\.get|httpx\.get|Request|fetch|curl(?:\s+-\w+)*)\s*\(?\s*f?['"]?http://(?:169\.254\.169\.254/[^\s'"]*security-credentials|169\.254\.170\.2)
 |\bprintenv\s*(?:\|(?!\s*(?:grep|head|less|wc|cut))|>|\))|\benv\s*\|\s*(?:curl|nc|base64|xxd|gzip)|json\.dumps\(\s*(?:dict\()?\s*os\.environ|in\s+os\.environ\.items\(\)|JSON\.stringify\(\s*process\.env\s*\)|Object\.(?:entries|keys)\(\s*process\.env\s*\)""", re.I | re.X)
SEND = re.compile(r"""requests\.(?:post|put)|httpx\.(?:post|put)|session\.(?:post|put)|\.post\(|urllib\.request\.Request\(|urlopen\(|data\s*=\s*(?:json\.dumps|payload|body|urllib)|method\s*[:=]\s*['"]?(?:POST|PUT)|curl\b[^\n]*(?:\s-d\s|\s-d['"@]|--data|\s-F\s|-X\s*(?:POST|PUT)|\s-T\s|--upload-file)|fetch\(|axios\.(?:post|put)|sendBeacon|XMLHttpRequest|\bnc\s+(?:-\w+\s+)*[\w.]+\s+\d+|/dev/tcp/|wget\s[^\n]*--post-(?:data|file)|Invoke-(?:WebRequest|RestMethod)[^\n]*-Method\s+(?:Post|Put)|socket\.(?:connect|create_connection)|smtplib|send_message""", re.I)
URL = re.compile(r"""(?:https?|wss?|tcp|ftp)://([A-Za-z0-9][A-Za-z0-9.-]*)|connect\(\(\s*['"]([\w.-]+)['"]|/dev/tcp/([\w.-]+)""")
CONST = re.compile(r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*[fr]?['"](?:https?|wss?|tcp)://([A-Za-z0-9][A-Za-z0-9.-]*)""")
PLACE = re.compile(r"""(?:^|\.)(?:example|test|invalid|localhost|local|lan|home|internal\.example)$|^(?:your|my|<|\$|\{)|target|victim|attacker|evil|callback|placeholder|dummy|fake|sample|xxx|foo|bar\.|host\.|server\.|api-server|domain\.""", re.I)
NEG = re.compile(r"\b(?:do not|don't|never|avoid|must not|should not|shouldn't|no direct|without reading|forbid|prohibit|block|deny|detect|flag|scan for|look for|pattern|e\.g\.|such as)\b", re.I)
def bad_host(h):
    h = h.lower().rstrip('.')
    try:
        ip = ipaddress.ip_address(h)
        return not (ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError: pass
    if HOOK.search(h): return True
    if '.' not in h or PLACE.search(h) or ALLOW.search(h): return False
    return True
def code_lines(t):
    out, fence = [], False
    for l in t.splitlines():
        s = l.strip()
        if s.startswith(('```', '~~~')): fence = not fence; continue
        if fence or l.startswith(('    ', '\t')) or '`' in s or s.startswith(('$', '>', '#!')): out.append(l)
    return out
WRITE = re.compile(r"""['"]w['"]|>\s*\S*(?:credentials|id_|shadow|config)|write_text|writeFileSync|\.pub\b""")
IPURL = re.compile(r"(?:https?|wss?|tcp)://(\d{1,3}(?:\.\d{1,3}){3})")
def code_ip(L):
    for l in L:
        for ip in IPURL.findall(l):
            if bad_host(ip): return ip
    return None
def scan(t):
    L = code_lines(t); sec = None; ex = None
    ip = code_ip(L)
    for l in L:
        m = SECRET.search(l)
        if m and not NEG.search(l) and not WRITE.search(l): sec = m.group(0).strip()[:80]; break
    if not sec: return None, None, ip
    consts = {n: h for n, h in CONST.findall(t) if bad_host(h)}
    for i, l in enumerate(L):
        if not SEND.search(l) or NEG.search(l): continue
        win = ' '.join(L[i:i + 4])
        hosts = [g for m in URL.finditer(win) for g in m.groups() if g]
        h = next((x for x in hosts if bad_host(x)), None)
        if not h:
            h = next((consts[n] for n in consts if re.search(r'\b' + re.escape(n) + r'\b', win)), None)
        if h: ex = h; break
    return sec, ex, ip
out = {'sid': [], 'secret_read': [], 'exfil_send': [], 'code_public_ip': []}
import pyarrow.compute as pc
need = pa.array(sorted(r[0] for r in c.execute("select sid from cand").fetchall()), pa.int64())
def texts():
    for part in sorted(glob.glob('out/full/text/part-*.parquet')):
        for bt in pq.ParquetFile(part).iter_batches(batch_size=4000, columns=['sid', 'content']):
            m = pc.is_in(bt.column(0), value_set=need)
            if pc.any(m).as_py():
                f = bt.filter(m); yield from zip(f.column(0).to_pylist(), f.column(1).to_pylist())
for sid, t in texts():
    s, e, ip = scan(t or '')
    if s or ip:
        out['sid'].append(sid); out['secret_read'].append(s); out['exfil_send'].append(e if s else None); out['code_public_ip'].append(ip)
pq.write_table(pa.table(out), 'out/full/risk2c.parquet')
T = pa.table(out).to_pandas(); print('secret_read', T.secret_read.notna().sum(), 'with exfil_send', T.exfil_send.notna().sum(), 'code_public_ip', T.code_public_ip.notna().sum())
