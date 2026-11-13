"""Profile the GitSkills sample. Writes charts to out/ and stats to out/profile.json"""
import sqlite3, json, re, collections
import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
DB='data/agent_skills_sample.db'; c=sqlite3.connect(DB)
q=lambda s: pd.read_sql(s,c)
S={}
a=q("select repo_full_name,path,filename,location_class,file_sha,dedup_primary,content_fetched,content_sha_ok,frontmatter_valid,name,description,body_chars,length(content) clen,sibling_count,has_scripts,has_references,composition_truncated,history_fetched,first_commit_at,last_commit_at,commit_count,discovered_at from artifacts")
r=q("select * from repos")
S['artifacts_rows']=len(a); S['distinct_sha']=int(a.file_sha.nunique()); S['dedup_primary']=int((a.dedup_primary==1).sum())
S['repos']=len(r); S['owners']=int(r.owner.nunique())
p=a[a.dedup_primary==1].copy()
S['primaries_with_content']=int(p.clen.notna().sum()); S['content_sha_ok']=p.content_sha_ok.value_counts(dropna=False).to_dict()
S['exact_dup_occurrence_pct']=round(100*(1-S['distinct_sha']/len(a)),1)
cp=a.groupby('file_sha').size(); S['copies_dist']={'singleton':int((cp==1).sum()),'2-9':int(((cp>=2)&(cp<10)).sum()),'10-99':int(((cp>=10)&(cp<100)).sum()),'100+':int((cp>=100).sum()),'max':int(cp.max())}
S['location_class']=a.location_class.value_counts().to_dict()
S['filename_top']=a.filename.value_counts().head(8).to_dict()
S['frontmatter_valid']=p.frontmatter_valid.value_counts(dropna=False).to_dict()
S['has_name']=int(p.name.fillna('').str.strip().ne('').sum()); S['has_description']=int(p.description.fillna('').str.strip().ne('').sum())
d=p.description.fillna('').str.len(); S['desc_len_median']=float(d[d>0].median()); S['desc_lt_40']=int(((d>0)&(d<40)).sum())
S['body_chars']=p.body_chars.describe(percentiles=[.1,.25,.5,.75,.9,.99]).round(0).to_dict()
S['has_scripts']=int(p.has_scripts.fillna(0).sum()); S['has_references']=int(p.has_references.fillna(0).sum())
S['composition_truncated']=int(p.composition_truncated.fillna(0).sum())
S['history_fetched']=int(a.history_fetched.sum())
S['first_commit_range']=[a.first_commit_at.min(),a.first_commit_at.max()]
S['repo_nulls']={k:int(v) for k,v in r.isna().sum().items()}
S['repo_lang_top']=r.language.value_counts().head(12).to_dict()
S['repo_license_top']=r.license.fillna('NONE').value_counts().head(10).to_dict()
S['stars']=r.stars.describe(percentiles=[.5,.9,.99]).round(0).to_dict(); S['repos_100plus_stars']=int((r.stars>=100).sum())
S['top_repos_by_files']=a.repo_full_name.value_counts().head(10).to_dict()
a['owner']=a.repo_full_name.str.split('/').str[0]
S['top_owners_by_files']=a.owner.value_counts().head(10).to_dict()
S['top_repos_by_stars']=r.sort_values('stars',ascending=False).head(10)[['full_name','stars']].values.tolist()
nm=p.name.fillna('').str.strip().str.lower(); S['top_names']=nm[nm!=''].value_counts().head(20).to_dict()
S['distinct_names']=int(nm[nm!=''].nunique())
# topics: words from names/descriptions
stop=set("the a an and or to of for in on with use when this that is are be it as by from your you skill skills using any user should can into via at".split())
w=collections.Counter()
for t in (p.name.fillna('')+' '+p.description.fillna('')).str.lower():
    for x in set(re.findall(r'[a-z][a-z0-9\-]{2,}',t)):
        if x not in stop: w[x]+=1
S['top_terms']=dict(w.most_common(30))
json.dump(S,open('out/profile.json','w'),indent=1,default=str)
print(json.dumps(S,indent=1,default=str))
# charts
plt.figure(figsize=(8,4)); bc=p.body_chars.dropna(); bc=bc[bc>0]
plt.hist(np.log10(bc),bins=60,color='#4a6'); plt.xlabel('log10(body chars)'); plt.ylabel('distinct skills'); plt.title('SKILL.md body length (13k distinct, sample)'); plt.tight_layout(); plt.savefig('out/body_length.png',dpi=120)
plt.figure(figsize=(8,4)); a.owner.value_counts().head(15)[::-1].plot.barh(color='#46a'); plt.title('Top owners by SKILL.md file occurrences'); plt.tight_layout(); plt.savefig('out/top_owners.png',dpi=120)
plt.figure(figsize=(8,4)); r.language.fillna('None').value_counts().head(12)[::-1].plot.barh(color='#a64'); plt.title('Repo primary language'); plt.tight_layout(); plt.savefig('out/languages.png',dpi=120)
plt.figure(figsize=(6,4)); fm=pd.Series({'valid frontmatter':(p.frontmatter_valid==1).sum(),'has name':S['has_name'],'has description':S['has_description'],'has scripts':S['has_scripts'],'has references':S['has_references']})/len(p)*100
fm.plot.bar(color='#6a4'); plt.ylabel('% of distinct skills'); plt.xticks(rotation=25,ha='right'); plt.title('Frontmatter & bundle completeness'); plt.tight_layout(); plt.savefig('out/completeness.png',dpi=120)
plt.figure(figsize=(8,4)); pd.Series(S['top_names']).head(15)[::-1].plot.barh(color='#a4a'); plt.title('Most common skill names (distinct contents)'); plt.tight_layout(); plt.savefig('out/top_names.png',dpi=120)
plt.figure(figsize=(7,4)); plt.hist(np.log10(cp),bins=40,log=True,color='#888'); plt.xlabel('log10(copies per distinct content)'); plt.title('Exact-copy distribution'); plt.tight_layout(); plt.savefig('out/copies.png',dpi=120)
