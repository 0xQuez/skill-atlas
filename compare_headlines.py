"""MinHash-only (out/full/minhash_only/headline.json) vs combined (out/full/headline.json) -> out/full/headline_compare.json"""
import json
A=json.load(open('out/full/minhash_only/headline.json')); B=json.load(open('out/full/headline.json'))
K=['embedded','minhash_pairs','emb_pairs','emb_only_pairs','pairs_total','clusters','skills_in_clusters','near_copy_rate_distinct_pct','redundant_distinct_beyond_exact',
   'families_after_exact_and_near','file_rows_redundant_pct_exact_or_near','largest_cluster','clusters_cross_repo','clusters_cross_owner']
C={k:{'minhash_only':A.get(k),'combined':B.get(k)} for k in K}
C['slop_without']={'minhash_only':A.get('slop',{}).get('without_slop'),'combined':B.get('slop',{}).get('without_slop')}
C['verdicts']={'minhash_only_v1_canonical_stale':A.get('verdicts',{}).get('verdict_distribution'),'minhash_only_v3_canonical':{'use':1194165,'ignore':539518,'caution':144298},'combined_unrefined_v3':{'use':1149873,'ignore':588498,'caution':139610},'combined':B.get('verdicts',{}).get('verdict_distribution')}
json.dump(C,open('out/full/headline_compare.json','w'),indent=1); print(json.dumps(C,indent=1))
