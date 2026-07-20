# -*- coding: utf-8 -*-
"""배포 모델 07/14 신뢰도 임계값(τ) 스윕 — τ별 미분류율·라벨확정정확도·전체정답률."""
import sys, os, json
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd
import autolabel, pipeline

def canon(v):
    s='' if pd.isna(v) else str(v).strip()
    if '미분류' in s: return '__unk__'
    s=s.lower()
    if s.endswith('.exe'): s=s[:-4]
    return s.replace(' ','_').replace('-','_')
def norm(raw):
    dm=pipeline.build_app_display_map(raw.astype(str).tolist())
    return raw.astype(str).map(dm).fillna(raw.astype(str)).map(canon)

df=autolabel.normalize_df(pd.read_csv('/nmlab/99_sgs/01_datasets/2026.07.14/session_stat_lab0714.csv',low_memory=False))
b=autolabel.load_bundle('models/autolabel_model.pkl')
X=autolabel.build_features(df)
Xe=autolabel.encode_cats_apply(X.copy(), b['cat_levels'])
cols=list(b['num_cols'])+list(b['cat_cols'])
proba=b['model'].predict_proba(Xe[cols]); classes=np.asarray(b['model'].classes_)
pred=pd.Series(classes[proba.argmax(1)]).map(canon).to_numpy(); conf=proba.max(1)
true=norm(df['task3']).to_numpy()
ok=true!='__unk__'; true=true[ok]; pred=pred[ok]; conf=conf[ok]
N=len(true)
rows=[]
for tau in [0.0,0.2,0.3,0.4,0.5,0.6,0.7,0.8]:
    lab=conf>=tau
    unrate=(1-lab.mean())*100
    acc_lab=(pred[lab]==true[lab]).mean()*100 if lab.sum() else float('nan')
    overall=((lab)&(pred==true)).mean()*100   # 미분류는 정답에서 제외
    rows.append({'tau':tau,'미분류율':round(unrate,2),'라벨확정정확도':round(acc_lab,2),'전체정답률':round(overall,2)})
    print('tau=%.1f  미분류=%5.2f%%  라벨정확도=%5.2f%%  전체정답률=%5.2f%%'%(tau,unrate,acc_lab,overall))
json.dump({'day':'2026.07.14','n':int(N),'sweep':rows}, open('thr_sweep_results.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('SAVED thr_sweep_results.json  (N=%d)'%N)
