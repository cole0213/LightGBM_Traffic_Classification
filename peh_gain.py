# -*- coding: utf-8 -*-
"""1205 피처 LightGBM gain 중요도 분석 — S11 차트 + S7 재작성 근거.
peh_compare.py와 동일 데이터·분할·LightGBM config. gain 중요도를 개별/피처군별로 집계."""
import os, gc, json, time, re
import numpy as np, pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import lightgbm as lgb
import warnings; warnings.filterwarnings('ignore')

CSV = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/peh1205_lab.csv'
OUT = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/peh_gain_results.json'

def log(m): print(m, flush=True)

def family(c):
    if c.startswith(('ip_','tcp_','udp_')): return 'header(L3/L4)'
    if c.startswith('flag'): return 'flag(TCP)'
    if c.upper().startswith('PSD'): return 'PSD(주파수 스펙트럼)'
    if c.upper().startswith('IAT'): return 'IAT(패킷 도착간격)'
    return 'scalar(통계량)'

t0=time.time()
log('[load] reading CSV...')
df=pd.read_csv(CSV, na_values=['-'], low_memory=False)
log(f'  loaded {df.shape} in {time.time()-t0:.0f}s')
meta=['Src_IP','Src_Port','Dst_IP','Dst_Port','Protocol']
noise=[c for c in df.columns if re.match(r'^[A-E][a-g]_\d+$', c)]
drop=set(['Label']+meta+noise)
feat=[c for c in df.columns if c not in drop]
log(f'  features={len(feat)}')
y_str=df['Label'].astype(str).to_numpy()
X=df[feat].apply(pd.to_numeric, errors='coerce').astype('float32')
del df; gc.collect()
vc=pd.Series(y_str).value_counts(); keep=set(vc[vc>=5].index)
m=np.array([v in keep for v in y_str]); X=X[m]; y_str=y_str[m]
LE=LabelEncoder(); y=LE.fit_transform(y_str)
Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=0.2,random_state=42,stratify=y)
log(f'  train={len(Xtr):,} classes={len(keep)} → training LightGBM (gain)...')

clf=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.05,num_leaves=127,
    min_child_samples=30,reg_lambda=5,n_jobs=4,verbosity=-1,random_state=42)
clf.fit(Xtr,ytr)
log(f'  trained in {time.time()-t0:.0f}s')

gain=clf.booster_.feature_importance(importance_type='gain').astype(float)
total=gain.sum()
pairs=sorted(zip(feat,gain), key=lambda x:-x[1])
top30=[{'feat':f,'gain_pct':round(g/total*100,3)} for f,g in pairs[:30]]

# cumulative: how many features to reach 50/80/90/95%
cum=0; marks={}
for k,(f,g) in enumerate(pairs,1):
    cum+=g/total*100
    for thr in [50,80,90,95]:
        if thr not in marks and cum>=thr: marks[thr]=k

fam={}
for f,g in zip(feat,gain):
    fam[family(f)]=fam.get(family(f),0)+g
fam_pct={k:round(v/total*100,2) for k,v in sorted(fam.items(), key=lambda x:-x[1])}

res={'n_features':len(feat),'n_classes':len(keep),
     'top30':top30,'features_to_reach':marks,'family_gain_pct':fam_pct}
json.dump(res, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
log('\n=== FAMILY gain% ===')
for k,v in fam_pct.items(): log(f'  {k:24} {v:5.1f}%')
log('\n=== TOP 15 features ===')
for d in top30[:15]: log(f"  {d['feat']:22} {d['gain_pct']:5.2f}%")
log(f"\n상위 몇개로 gain 80% 도달: {marks.get(80)}개 / 전체 {len(feat)}")
log('SAVED '+OUT); log('DONE_PEH_GAIN')
