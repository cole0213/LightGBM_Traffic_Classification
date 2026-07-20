# -*- coding: utf-8 -*-
"""배포 모델로 07/14 예측 → 정답(task3)≠예측 상위 혼동 쌍 집계 (혼동사례 슬라이드용)."""
import sys, os, json
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd
import autolabel, pipeline
from collections import Counter

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
m=b['model']
proba=m.predict_proba(Xe[cols]); classes=np.asarray(m.classes_)
pred=classes[proba.argmax(1)]; conf=proba.max(1)
true=norm(df['task3']).to_numpy()
predn=pd.Series(pred).map(canon).to_numpy()

ok=true!='__unk__'
true=true[ok]; predn=predn[ok]; conf=conf[ok]
# threshold 0.3 적용: 미달은 미분류로 간주(혼동에서 제외)
labeled = conf>=0.3
mism = labeled & (true!=predn)
pairs=Counter()
for t,p_ in zip(true[mism], predn[mism]):
    a,b2=sorted([t,p_]); pairs[(a,b2)]+=1   # 방향 무시 쌍
print('총 세션(라벨확정):',int(labeled.sum()),' 오분류:',int(mism.sum()),
      ' 정확도:%.2f%%'%((true[labeled]==predn[labeled]).mean()*100))
print('=== 상위 혼동 쌍 (양방향 합산) ===')
for (a,b2),c in pairs.most_common(10):
    print('  %6d  %s  ↔  %s'%(c,a,b2))
json.dump([{'pair':[a,b2],'n':c} for (a,b2),c in pairs.most_common(12)],
          open('confusion_pairs.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('SAVED confusion_pairs.json')
