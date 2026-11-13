"""Quality & risk v0 at full scale (same rules as risk.py prototype, minus the noisy 'silently' pattern).
Reads out/full/text/part-*.parquet + skills meta; writes out/full/scores.parquet (sid, quality, risk, n_domains, risk_flags)."""
import re, glob, os, time, numpy as np, pandas as pd, pyarrow.parquet as pq
from multiprocessing import Pool
R={'pipe_to_shell':(r'(curl|wget)[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b',30),'rm_rf':(r'\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r',10),
 'sudo':(r'\bsudo\s+\w',8),'chmod_777_or_x':(r'chmod\s+(777|\+x)',5),'base64_decode':(r'base64\s+(-d|--decode)|atob\(|b64decode',12),
 'eval_exec':(r'\beval\s*\(|\bexec\s*\(|os\.system\(|subprocess\.(run|Popen|call)\(.{0,80}shell\s*=\s*True',8),
 'secret_literal':(r'(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)',35),
 'reads_secrets':(r'(~/\.ssh|id_rsa|\.aws/credentials|\.env\b|keychain|/etc/passwd|printenv|os\.environ)',8),
 'exfil_post':(r'curl\s+[^\n]{0,120}(-d|--data|-F|-X\s*POST)[^\n]{0,120}https?://',10),
 'prompt_injection_lang':(r'ignore (all )?(previous|prior|above) instructions|do not (tell|inform) the user|without (asking|telling) the user',15),
 'disable_safety':(r'--dangerously-skip-permissions|--no-verify|--yolo|bypass(ing)? (permission|approval|sandbox)',10),
 'raw_ip_url':(r'https?://\d{1,3}(\.\d{1,3}){3}',10)}
RC={k:(re.compile(p,re.I),w) for k,(p,w) in R.items()}
URL=re.compile(r'https?://([^\s/)\]>"\'`:]+)'); SLUG=re.compile(r'[a-z0-9][a-z0-9\-]{1,63}')
TRIG=re.compile(r'\b(use (this )?when|when (the )?user|trigger|use for|invoke)\b',re.I)
H3=re.compile(r'^#{1,3} ',re.M); H=re.compile(r'^#',re.M); LST=re.compile(r'^\s*(\d+\.|[-*]) ',re.M)
def work(args):
    f,meta=args; d=pq.read_table(f,columns=['sid','name','description','content']).to_pandas().merge(meta,on='sid',how='left'); out=[]
    for r in d.itertuples():
        t=r.content if isinstance(r.content,str) else ''; desc=r.description.strip() if isinstance(r.description,str) else ''; name=r.name.strip() if isinstance(r.name,str) else ''
        flags=[k for k,(p,w) in RC.items() if p.search(t)]
        doms={m.lower() for m in URL.findall(t)}
        risk=min(100,sum(RC[k][1] for k in flags)+min(10,len(doms)//3)+(5 if r.has_scripts==1 else 0))
        q=(15 if r.frontmatter_valid==1 else 0)+(10 if SLUG.fullmatch(name) else (4 if name else 0))
        L=len(desc); q+=20 if 60<=L<=1024 else (10 if 20<=L<60 else (5 if L>1024 else 0))
        q+=10 if TRIG.search(desc) else 0
        b=r.body_chars or 0; q+=15 if 800<=b<=20000 else (8 if 300<=b<800 or 20000<b<=50000 else 0)
        q+=10 if len(H3.findall(t))>=3 else (5 if H.search(t) else 0)
        q+=10 if LST.search(t) else 0; q+=5 if '```' in t else 0; q+=5 if (r.has_references==1 or r.has_scripts==1) else 0
        out.append((r.sid,q,risk,len(doms),','.join(flags)))
    return pd.DataFrame(out,columns=['sid','quality','risk','n_domains','risk_flags'])
if __name__=='__main__':
    t0=time.time()
    meta=pq.read_table('out/full/skills_meta_raw.parquet',columns=['sid','frontmatter_valid','body_chars','has_scripts','has_references']).to_pandas()
    parts=sorted(glob.glob('out/full/text/part-*.parquet')); res=[]
    with Pool(int(os.environ.get('SC_PROCS','3'))) as p:
        for i,df in enumerate(p.imap_unordered(work,[(f,meta) for f in parts])): res.append(df); print(i,len(df),round(time.time()-t0),'s',flush=True)
    S=pd.concat(res).sort_values('sid'); S.to_parquet('out/full/scores.parquet',index=False); print('DONE',len(S),round(time.time()-t0),'s')
