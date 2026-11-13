"""Body-only embeddings for skills in embedding-only pairs: strip YAML frontmatter, embed the first 1500 chars of the body,
MiniLM-L6-v2, max_seq_length 128, fp16. Output out/full/body_emb.npz (sid, emb) + body_lang.parquet (sid, script, lang guess)."""
import re, glob, time, numpy as np, pandas as pd, pyarrow.parquet as pq, torch
torch.set_num_threads(8)
from sentence_transformers import SentenceTransformer
t0=time.time()
e=pd.read_parquet('out/full/_emb_only_pairs.parquet'); need=np.unique(np.r_[e.sid_a.values,e.sid_b.values])
FM=re.compile(r'^\ufeff?\s*---\s*\n.*?\n---\s*(\n|$)',re.S)
def body(t): t=t or ''; m=FM.match(t); return (t[m.end():] if m else t).strip()
rows=[]
for f in sorted(glob.glob('out/full/text/part-*.parquet')):
    d=pq.read_table(f,columns=['sid','content']).to_pandas(); d=d[d.sid.isin(need)]
    rows.append(pd.DataFrame({'sid':d.sid.values,'body':[body(x)[:1500] for x in d.content]}))
B=pd.concat(rows).sort_values('sid').reset_index(drop=True); print('bodies',len(B),round(time.time()-t0),'s',flush=True)
# cheap language signal: dominant script + stopword vote for Latin-script languages
SW={'en':' the and to of is for with you this that are ','es':' el la de que y los las para con una es ','de':' der die und das ist nicht mit zu den für ',
    'fr':' le la les des et est pour une dans pas ','pt':' o a de que e do da para com não uma ','it':' il di che e la per non una sono ','id':' dan yang untuk dengan ini tidak '}
SWS={k:set(v.split()) for k,v in SW.items()}
def lang(t):
    s=t[:1500]; n=len(s) or 1
    cjk=len(re.findall(r'[\u4e00-\u9fff]',s)); kana=len(re.findall(r'[\u3040-\u30ff]',s)); hang=len(re.findall(r'[\uac00-\ud7af]',s))
    cyr=len(re.findall(r'[\u0400-\u04ff]',s)); ar=len(re.findall(r'[\u0600-\u06ff]',s))
    for k,v in (('ja',kana),('ko',hang),('zh',cjk),('ru',cyr),('ar',ar)):
        if v/n>0.05: return k
    w=re.findall(r'[a-zà-ÿ]+',s.lower()); sc={k:sum(1 for x in w if x in v) for k,v in SWS.items()}
    k=max(sc,key=sc.get); return k if sc[k]>=3 else 'unk'
B['lang']=[lang(x) for x in B.body]; B[['sid','lang']].to_parquet('out/full/body_lang.parquet',index=False)
print(B.lang.value_counts().head(10).to_dict(),flush=True)
m=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device='cpu'); m.max_seq_length=128
E=np.zeros((len(B),384),np.float16); CH=20000
for i in range(0,len(B),CH):
    E[i:i+CH]=m.encode(B.body.iloc[i:i+CH].tolist(),batch_size=64,normalize_embeddings=True,show_progress_bar=False).astype(np.float16)
    print(time.strftime('%H:%M:%S'),min(i+CH,len(B)),'/',len(B),round((min(i+CH,len(B)))/(time.time()-t0),1),'/s',flush=True)
np.savez('out/full/body_emb.npz',sid=B.sid.values.astype(np.int32),emb=E); print('DONE',round(time.time()-t0),'s',flush=True)
