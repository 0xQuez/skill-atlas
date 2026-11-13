"""White-hat security tags: legit offensive-security / red-team / pentest / CTF / forensics skills.
Tag only; verdicts and risk are NOT changed. Out: out/full/white_hat.parquet (sid, white_hat_kind, evidence), white_hat_stats.json
Rule: skill is tagged if
  (a) its own name/description has a strong offensive-security term, or
  (b) it sits in a white-hat repo (curated list, or repo description says red team / pentest / CTF / DFIR ...) AND
      its own name/description has a broader security term.
Skills on the harmful-collection list (malicious_source) are never tagged; that category wins."""
import duckdb, json, re, sys
OUT = 'out/full'
CURATED = ['AeonDave/malskill', 'grisuno/LazyOwn', 'dazeb/ai-supply-chain-lab', 'jeffbryner/find_evil_hackathon',
           'vinayvobbili/find-evil', 'WooYoungSang/warvis-findEvil']
# strong offensive terms: tools and offensive actions (still need a security word, see OFFV)
STRONG = (r"(?i)(\bpen[- ]?test|penetration[- ]test|\bred[- ]?team|offensive[- ]?(security|sec\b|tool|operat)|\bctf\b|capture[- ]the[- ]flag|"
          r"bug[- ]bounty|privilege[- ]escalation|\bprivesc\b|reverse[- ]shell|bind[- ]shell|post[- ]exploitation|lateral[- ]movement|"
          r"\bexploit(s|ation)? (vulnerab|framework|dev|chain|writ|the |a |with|of )|\bmetasploit|\bmsfvenom|\bsqlmap\b|burp ?suite|\bnmap\b|\bhashcat\b|john the ripper|"
          r"\bmimikatz|bloodhound|kerberoast|\bimpacket|\bc2 (server|framework|infra|channel)|command[- ]and[- ]control|\bimplants?\b|"
          r"ethical[- ]hack|white[- ]?hat hack|\bhack ?the ?box|tryhackme|\boscp\b|adversary[- ]emulation|attack[- ]simulation|"
          r"\bphishing[- ](simulation|campaign|kit)|payload[- ]generat|shellcode|malware[- ]analys|reverse[- ]engineer(ing|s)? (\.net |android |ios )?(malware|binar|firmware))")
# security vocabulary (no bare "security": too generic)
OFFV = (r"(?i)(hack|attack|exploit|vulnerab|vuln\b|payload|recon|pentest|penetration|capture the flag|ctf (challenge|competition|solver|writeup|write-up|pwn|web|misc|crypto|rev)|writeups?|pwn|malware|\bc2\b|implant|reverse shell|bind shell|webshell|web shell|shellcode|(sql|command|prompt|process|code|header|nosql|ldap|template|dll) injection|xss|\bsqli\b|ssrf|csrf|\brce\b|cve|"
        r"privesc|privilege escalat|escalate privileges|bypass|evasion|credential (theft|harvest|dump|stuff|access|spray)|ntlm|kerberos|active directory|brute|sniff|phish|enumerat|fuzz|forensic|\bioc|exfil|persistence (mechanism|technique)|establish persistence|"
        r"lateral movement|rootkit|backdoor|osint|adversaries|attacker|offensive|red[- ]team (engagement|operat|exercise|assess)|intercept(ing)? (traffic|proxy|request)|password crack|hash crack|cracking|metasploit|burp|nmap|"
        r"auth/lab|lab/ctf|authori[sz]ed (test|assess|engage|use))")
REPO_DESC = (r"(?i)(red[- ]?team|pen[- ]?test|penetration test|offensive[- ]?(security|sec\b|tool)|\bctf\b|bug[- ]bounty|ethical hack|"
             r"hacking (tool|lab|skill)|exploit (dev|framework|kit)|\bdfir\b|digital forensic|threat[- ]hunt|malware analys|adversary emulation|c2 framework)")
# defensive work (detect, harden, comply) is not white-hat unless it also does offensive actions
DEF = r"(?i)(\bdetect|detection|harden|remediat|monitor|\bdefen[cs]|defensive|complian|benchmark|guardrail|\bpolicy|policies|secure[- ]coding|code review|security review|best practice|prevent|security controls|\\baudit)"
OFF_ACT = (r"(?i)(pen[- ]?test|penetration[- ]test|\bctf\b|capture the flag|exploit (vulnerab|the |a |them|misconf)|exploitation (with|of|framework)|attack path|"
           r"payload|bypass|reverse shell|\bc2\b|implant|metasploit|sqlmap|burp|bug bounty|kerberoast|offensive|lateral movement|post-exploitation|red[- ]team (engagement|operat|exercise)|auth/lab|auth assessment|lab/ctf|evasion|enumeration of|exploitation tool|firmware extraction)")
# defensive skill names (detect, harden, review, comply ...): never white-hat, whatever the description says
NAME_DEF = (r"(?i)^(detect|implement|hunt|deploy|harden|monitor|configur|review|audit|secur|prevent|protect|scan|creat|design|manag|respond|triag|investigat|threat[- ]model)"
            r"|(review|reviewer|scanner|audit|auditor|correlation|siem|honeytoken|honeypot|policy|policies|control|controls|compliance|hardening|detection|defen[cs]e|defender|guard|sentinel|shield)$"
            r"|^[A-Z]{2}-\d|^cis-|^(ID|PR|DE|RS|RC|GV)\.|^anti-")
NOT_SECURITY_OWNERS = ['Klotzkette', 'membranedev']

REPO_NAME = r"(?i)/.*(pen-?test|redteam|red-team|offensive|hacktricks|bug-?bounty|\bctf|ctf[-_]|exploit|hacking|xss|osint|kali|writeups?|sec_skill|security-skills)"

def heads():
    """content[:3000] for skills with no usable name/description (CTF write-ups etc.)."""
    import os, glob, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
    f = f'{OUT}/white_hat_heads.parquet'
    if os.path.exists(f): return f
    need = pa.array([r[0] for r in duckdb.sql(f"select skill_id from '{OUT}/verdicts_compact.parquet' where length(trim(coalesce(name,'')||coalesce(description,'')))<8").fetchall()], pa.int32())
    out = []
    for part in sorted(glob.glob(f'{OUT}/text/part-*.parquet')):
        for b in pq.ParquetFile(part).iter_batches(columns=['sid', 'content'], batch_size=2000):
            m = pc.is_in(b.column(0), value_set=need)
            if pc.any(m).as_py():
                t = b.filter(m)
                out.append(pa.table({'sid': t.column(0), 'head': pc.utf8_slice_codeunits(t.column(1), 0, 3000)}))
    pq.write_table(pa.concat_tables(out), f)
    return f

def main():
    hf = heads()
    c = duckdb.connect(); c.sql("set memory_limit='2GB'; set temp_directory='/tmp/duck'")
    c.sql(f"attach '{OUT}/atlas.duckdb' as a (read_only)")
    c.sql(f"create temp table wr as select full_name repo, case when full_name in ({','.join(repr(x) for x in CURATED)}) then 'curated' else 'repo_description_or_name' end why "
          f"from a.repos where full_name in ({','.join(repr(x) for x in CURATED)}) or regexp_matches(coalesce(description,''), '{REPO_DESC}') or regexp_matches(full_name, '{REPO_NAME}')")
    c.sql(f"""create temp table cand as
      select v.skill_id sid, v.rep_repo, v.top_repo, coalesce(nullif(trim(coalesce(v.name,'')),''), trim(regexp_extract(coalesce(h.head,''), 'name:[ \t]*([^\r\n]+)', 1))) nm,
        case when length(trim(coalesce(v.name,'')||coalesce(v.description,'')))<8 then coalesce(h.head,'') else coalesce(v.name,'')||' — '||coalesce(v.description,'') end txt
      from '{OUT}/verdicts_compact.parquet' v left join '{hf}' h on h.sid=v.skill_id
      where v.skill_id not in (select sid from '{OUT}/malicious_source.parquet')""")
    c.sql(f"""create temp table wh as
      select sid, rep_repo, top_repo, txt, nm,
        regexp_matches(txt, '{STRONG}') and regexp_matches(txt, '{OFFV}') strong,
        (rep_repo in (select repo from wr) or top_repo in (select repo from wr)) in_repo,
        regexp_matches(txt, '{OFFV}') broad,
        regexp_matches(txt, '{DEF}') and not regexp_matches(txt, '{OFF_ACT}') defo,
        coalesce(regexp_extract(txt, '{STRONG}', 0), '') term
      from cand where (regexp_matches(txt, '{STRONG}') or rep_repo in (select repo from wr) or top_repo in (select repo from wr))
        and split_part(rep_repo,'/',1) not in ({','.join(repr(x) for x in NOT_SECURITY_OWNERS)})""")
    c.sql(f"""create temp table tagged as
      select sid, case when regexp_matches(txt, '(?i)(dfir|forensic|threat[- ]hunt|malware[- ]analys|incident response|sift|sleuth|\\bioc|triage|artifact)')
                        and not regexp_matches(txt, '{OFF_ACT}') then 'forensics' else 'offensive' end white_hat_kind,
        case when strong then 'term: '||lower(term) else '' end ||
        case when in_repo then (case when strong then '; ' else '' end)||'white-hat repo: '||coalesce((select repo from wr where repo=rep_repo),(select repo from wr where repo=top_repo)) else '' end evidence,
        rep_repo, txt
      from wh where not defo and not regexp_matches(nm, '{NAME_DEF}') and (strong or (in_repo and broad))""")
    c.sql(f"copy (select sid, white_hat_kind, evidence from tagged order by sid) to '{OUT}/white_hat.parquet' (format parquet)")
    s = {'skills_tagged': c.sql("select count(*) from tagged").fetchall()[0][0],
         'by_kind': dict(c.sql("select white_hat_kind, count(*) from tagged group by 1").fetchall()),
         'by_rule': dict(c.sql("select case when evidence like 'term:%' and evidence like '%repo:%' then 'term+repo' when evidence like 'term:%' then 'term only' else 'repo+broad' end, count(*) from tagged group by 1").fetchall()),
         'white_hat_repos_listed': c.sql("select count(*) from wr").fetchall()[0][0],
         'repos_with_tagged_skills': c.sql("select count(distinct rep_repo) from tagged").fetchall()[0][0],
         'curated': CURATED,
         'curated_counts': dict(c.sql(f"select rep_repo, count(*) from tagged where rep_repo in ({','.join(repr(x) for x in CURATED)}) group by 1").fetchall()),
         'repo_skills_not_tagged_sample': c.sql("select rep_repo, left(txt,100) from wh where in_repo and not broad and not strong limit 8").fetchall()}
    v = c.sql(f"select verdict, count(*) from '{OUT}/verdicts_compact.parquet' where skill_id in (select sid from tagged) group by 1").fetchall()
    s['verdicts_of_tagged'] = dict(v)
    s['high_risk_tagged'] = c.sql(f"select count(*) from '{OUT}/scores.parquet' where risk>=40 and sid in (select sid from tagged)").fetchall()[0][0]
    s['newly_high_tagged'] = c.sql(f"select count(*) from '{OUT}/scores.parquet' where risk>=40 and risk_v1<40 and sid in (select sid from tagged)").fetchall()[0][0]
    s['newly_high_outside_malicious'] = c.sql(f"select count(*) from '{OUT}/scores.parquet' where risk>=40 and risk_v1<40 and sid not in (select sid from '{OUT}/malicious_source.parquet')").fetchall()[0][0]
    json.dump(s, open(f'{OUT}/white_hat_stats.json', 'w'), indent=1, default=str)
    print(json.dumps(s, indent=1, default=str))
    c.sql("copy (select sid, white_hat_kind, evidence, rep_repo, left(txt,160) txt from tagged order by hash(sid*7) limit 60) to '/tmp/wh_sample.csv'")

if __name__ == '__main__' and len(sys.argv) == 1: main()

WHITE_HAT_NOTE = ("white-hat security tool: a legit offensive-security / pentest / CTF / forensics skill that does dangerous things on purpose. "
                  "Use only for authorised security work. Verdict and risk score are unchanged by this tag.")

def apply(path=f'{OUT}/verdicts_compact.parquet'):
    """Add white_hat (bool), white_hat_kind, category ('white_hat_security' or NULL) to the verdict output.
    Streams row groups with pyarrow (row order kept) and replaces the file atomically."""
    import os, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
    w = pq.read_table(f'{OUT}/white_hat.parquet')
    ids, kinds = w.column('sid').cast(pa.int64()), w.column('white_hat_kind')
    pf = pq.ParquetFile(path); tmp = path + '.tmp'; wr = None; n = 0
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i)
        for x in ('white_hat', 'white_hat_kind', 'category'):
            if x in t.column_names: t = t.drop_columns([x])
        idx = pc.index_in(t.column('skill_id').cast(pa.int64()), value_set=ids)
        hit = pc.is_valid(idx)
        t = t.append_column('white_hat', hit).append_column('white_hat_kind', pc.take(kinds, idx)) \
             .append_column('category', pc.if_else(hit, pa.scalar('white_hat_security'), pa.scalar(None, pa.string())))
        n += pc.sum(hit).as_py() or 0
        if wr is None: wr = pq.ParquetWriter(tmp, t.schema, compression='zstd')
        wr.write_table(t, row_group_size=100000)
    wr.close(); os.replace(tmp, path)
    print('applied', n, pf.metadata.num_rows)

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'apply': apply()
