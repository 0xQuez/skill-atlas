"""Quality & risk heuristic v0 over distinct skills. quality 0-100 (higher better), risk 0-100 (higher riskier)."""
import sqlite3, re, json, sys
import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
N=int(sys.argv[1]) if len(sys.argv)>1 else 5000
c=sqlite3.connect('data/agent_skills_sample.db')
df=pd.read_sql(f"""select a.file_sha,a.repo_full_name,a.path,a.name,a.description,a.content,a.frontmatter_valid,a.body_chars,
 a.has_scripts,a.has_references,a.sibling_count,(select count(*) from artifacts b where b.file_sha=a.file_sha) copies,r.stars,r.license
 from artifacts a left join repos r on r.full_name=a.repo_full_name where a.dedup_primary=1 order by a.file_sha limit {N}""",c)
for col in ("name","description","content"): df[col]=df[col].fillna("").astype(str)
R={ # risk patterns: (regex, weight)
 'pipe_to_shell':(r'(curl|wget)[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b',30),
 'rm_rf':(r'\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r',10),
 'sudo':(r'\bsudo\s+\w',8),
 'chmod_777_or_x_download':(r'chmod\s+(777|\+x)',5),
 'base64_decode_exec':(r'base64\s+(-d|--decode)|atob\(|b64decode',12),
 'eval_exec':(r'\beval\s*\(|\bexec\s*\(|os\.system\(|subprocess\.(run|Popen|call)\(.{0,80}shell\s*=\s*True',8),
 'secret_literal':(r'(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)',35),
 'reads_secrets':(r'(~/\.ssh|id_rsa|\.aws/credentials|\.env\b|keychain|/etc/passwd|printenv|os\.environ)',8),
 'exfil_post':(r'curl\s+[^\n]{0,120}(-d|--data|-F|-X\s*POST)[^\n]{0,120}https?://',10),
 'prompt_injection_lang':(r'ignore (all )?(previous|prior|above) instructions|do not (tell|inform) the user|without (asking|telling) the user',15),
 'disable_safety':(r'--dangerously-skip-permissions|--no-verify|--yolo|bypass(ing)? (permission|approval|sandbox)',10),
 'raw_ip_url':(r'https?://\d{1,3}(\.\d{1,3}){3}',10),
}
URL=re.compile(r'https?://[^\s)\]>"\'`]+')
rows=[]
for r in df.itertuples():
    t=r.content or ''; desc=(r.description or '').strip(); name=(r.name or '').strip()
    hits={k:len(re.findall(p,t,re.I)) for k,(p,w) in R.items()}
    urls=URL.findall(t); doms={re.sub(r'^https?://([^/:]+).*',r'\1',u).lower() for u in urls}
    risk=sum(w for k,(p,w) in R.items() if hits[k]) + min(10,len(doms)//3) + (5 if r.has_scripts else 0)
    risk=min(100,risk)
    q=0
    q+=15 if r.frontmatter_valid==1 else 0
    q+=10 if re.fullmatch(r'[a-z0-9][a-z0-9\-]{1,63}',name or '') else (4 if name else 0)
    L=len(desc); q+= 20 if 60<=L<=1024 else (10 if 20<=L<60 else (5 if L>1024 else 0))
    q+= 10 if re.search(r'\b(use (this )?when|when (the )?user|trigger|use for|invoke)\b',desc,re.I) else 0
    b=r.body_chars or 0; q+= 15 if 800<=b<=20000 else (8 if 300<=b<800 or 20000<b<=50000 else 0)
    q+= 10 if len(re.findall(r'^#{1,3} ',t,re.M))>=3 else (5 if re.search(r'^#',t,re.M) else 0)
    q+= 10 if re.search(r'^\s*(\d+\.|[-*]) ',t,re.M) else 0
    q+= 5 if '```' in t else 0
    q+= 5 if (r.has_references or r.has_scripts) else 0
    rows.append(dict(file_sha=r.file_sha,repo=r.repo_full_name,path=r.path,name=name,desc=desc[:140],stars=r.stars,copies=r.copies,
        quality=q,risk=risk,n_domains=len(doms),**{f'r_{k}':v for k,v in hits.items()}))
o=pd.DataFrame(rows); o.to_csv('out/scores_v0.csv',index=False)
summ={'n':len(o),'quality':o.quality.describe(percentiles=[.1,.25,.5,.75,.9]).round(1).to_dict(),
 'risk':o.risk.describe(percentiles=[.5,.75,.9,.99]).round(1).to_dict(),
 'risk_eq_0':int((o.risk==0).sum()),'risk_ge_20':int((o.risk>=20).sum()),'risk_ge_40':int((o.risk>=40).sum()),
 'flag_counts':{k:int((o[f'r_{k}']>0).sum()) for k in R},
 'skills_with_external_urls':int((o.n_domains>0).sum()),
 'corr_quality_logstars':round(float(np.corrcoef(o.quality,np.log1p(o.stars.fillna(0)))[0,1]),3),
 'corr_quality_logcopies':round(float(np.corrcoef(o.quality,np.log1p(o.copies))[0,1]),3)}
print(json.dumps(summ,indent=1))
json.dump(summ,open('out/scores_v0_summary.json','w'),indent=1)
cols=['name','repo','quality','risk','stars','copies']
print('\nTOP quality (risk<10):\n',o[o.risk<10].sort_values(['quality','stars'],ascending=False).head(6)[cols].to_string())
print('\nBOTTOM quality:\n',o.sort_values(['quality','stars']).head(6)[cols+['desc']].to_string())
fl=[f'r_{k}' for k in R]
top=o.sort_values('risk',ascending=False).head(8)
print('\nTOP risk:\n',top[cols].to_string()); print(top[fl].to_string())
fig,ax=plt.subplots(1,2,figsize=(10,4))
ax[0].hist(o.quality,bins=20,color='#4a6'); ax[0].set_title(f'Quality v0 (n={len(o)})')
ax[1].hist(o.risk,bins=20,color='#c44',log=True); ax[1].set_title('Risk v0 (log count)')
plt.tight_layout(); plt.savefig('out/scores_v0.png',dpi=120)
