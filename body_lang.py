"""Stricter body language guess (v2) for skills in embedding-only pairs -> out/full/body_lang.parquet.
Non-Latin script share > 5% of the first 1500 body chars -> ja/ko/zh/ru/ar. Otherwise stopword vote over en/es/de/fr/pt/it/id
on prose only (code blocks and inline code removed); winner needs >= 5 hits and >= 2x the runner-up, else 'unk'."""
import re, glob, numpy as np, pandas as pd, pyarrow.parquet as pq
e=pd.read_parquet('out/full/_emb_only_pairs.parquet'); need=np.unique(np.r_[e.sid_a.values,e.sid_b.values])
FM=re.compile(r'^\ufeff?\s*---\s*\n.*?\n---\s*(\n|$)',re.S); CODE=re.compile(r'```.*?```|`[^`]*`',re.S)
SW={'en':'the and to of is for with you this that are','es':'el la de que y los las para con una es','de':'der die und das ist nicht mit zu den für',
    'fr':'le la les des et est pour une dans pas','pt':'o a de que e do da para com não uma','it':'il di che e la per non una sono','id':'dan yang untuk dengan ini tidak'}
SWS={k:set(v.split()) for k,v in SW.items()}
def lang(t):
    m=FM.match(t or ''); s=((t[m.end():] if m else t) or '')[:3000]; s=CODE.sub(' ',s)[:1500]; n=len(s) or 1
    for k,pat in (('ja','[\u3040-\u30ff]'),('ko','[\uac00-\ud7af]'),('zh','[\u4e00-\u9fff]'),('ru','[\u0400-\u04ff]'),('ar','[\u0600-\u06ff]')):
        if len(re.findall(pat,s))/n>0.05: return k
    w=re.findall(r'[a-zà-ÿ]+',s.lower()); sc=sorted(((sum(1 for x in w if x in v),k) for k,v in SWS.items()),reverse=True)
    return sc[0][1] if sc[0][0]>=5 and sc[0][0]>=2*max(1,sc[1][0]) else 'unk'
out=[]
for f in sorted(glob.glob('out/full/text/part-*.parquet')):
    d=pq.read_table(f,columns=['sid','content']).to_pandas(); d=d[d.sid.isin(need)]
    out.append(pd.DataFrame({'sid':d.sid.values,'lang':[lang(x) for x in d.content]}))
L=pd.concat(out); L.to_parquet('out/full/body_lang.parquet',index=False); print(L.lang.value_counts().head(12).to_dict())
