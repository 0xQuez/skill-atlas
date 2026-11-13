"""Risk v2, pass b (DuckDB/RE2 over the text parts): cloud-metadata credential endpoints count as secret access, and
'sends data' (POST / data= / curl -d anywhere in the file) + a hard-coded non-allowlisted URL host anywhere counts as
post_unknown_host. Computed only for skills that touch secrets. Output: out/full/risk2b.parquet (sid, meta, send, hosts)."""
import duckdb, re, pyarrow as pa, pyarrow.parquet as pq
from risk_v2 import SECRET, ALLOW
c = duckdb.connect(); c.execute("SET memory_limit='1500MB'; SET threads=2; SET preserve_insertion_order=false")
SEC = SECRET.pattern.replace('(?!\\s+\\w)', '')   # RE2 has no lookahead; printenv variant handled loosely here
META = r'169\.254\.169\.254|169\.254\.170\.2|metadata\.google\.internal|/computeMetadata/v1'
SEND = r"""requests\.(post|put)|httpx\.(post|put)|\.post\(|urllib\.request\.Request\([^)]*data\s*=|urlopen\([^)]*data\s*=|data\s*=\s*json\.dumps|method\s*[:=]\s*['"]?(POST|PUT)|curl[^\n]{0,160}(\s-d\s|--data|\s-F\s|-X\s*POST|-T\s)|fetch\([^)]*method|axios\.post|XMLHttpRequest|sendBeacon|\bnc\s+[\w.]+\s+\d+|/dev/tcp/"""
import glob
rows = []
for part in sorted(glob.glob('out/full/text/part-*.parquet')):
  rows += c.execute(f"""SELECT sid, regexp_matches(content, '{META}') meta, regexp_matches(content, '{SEND.replace("'", "''")}') send,
    list_distinct(regexp_extract_all(content, 'https?://([A-Za-z0-9][A-Za-z0-9.-]*\\.[A-Za-z]{{2,}})', 1)) hosts
  FROM read_parquet('{part}')
  WHERE regexp_matches(content, '(?i)(' || '{SEC.replace("'", "''")}' || ')|{META}')""").fetchall()
print('candidates', len(rows))
def unknown(h):
    h = h.lower().rstrip('.')
    return not ALLOW.search(h) and not re.search(r'(^|\.)(example|test|invalid|localhost|local)$|^your|placeholder|<|\{', h)
out = {'sid': [], 'meta': [], 'send': [], 'unknown_hosts': []}
for sid, meta, send, hosts in rows:
    u = sorted({h for h in (hosts or []) if unknown(h)})[:5]
    out['sid'].append(sid); out['meta'].append(bool(meta)); out['send'].append(bool(send)); out['unknown_hosts'].append(','.join(u) or None)
pq.write_table(pa.table(out), 'out/full/risk2b.parquet')
t = pa.table(out).to_pandas(); print(t[['meta', 'send']].sum().to_dict(), 'with unknown host', t.unknown_hosts.notna().sum(), 'send & unknown', (t.send & t.unknown_hosts.notna()).sum())
