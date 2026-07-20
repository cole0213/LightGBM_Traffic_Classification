# -*- coding: utf-8 -*-
"""PEH 1,205 피처(feature_v3)로 5개 모델 벤치마크 재현.
데이터: /nmlab/98_PEH/98_xgb/00_csv/<dataset>/merged_features_label_*.csv
피처: 전체 1231컬럼 중 Label·meta5·noise20 제외 = 1205 traffic feature. 결측 '-'→NaN."""
import sys, os, gc, json, time, threading, pickle, re
import numpy as np, pandas as pd, psutil
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
import lightgbm as lgb, xgboost as xgb
import warnings; warnings.filterwarnings('ignore')

DATASET = os.environ.get('DS', '21_ISCX-VPN-2016')
CSV = os.environ.get('CSVFILE', f'/nmlab/98_PEH/98_xgb/00_csv/{DATASET}/merged_features_label_{DATASET}.csv')
OUT = os.environ.get('OUTFILE', '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/peh_compare_results.json')
NJ = 6; LE = None

def log(m): print(m, flush=True)
class Mem(threading.Thread):
    def __init__(s): super().__init__(daemon=True); s.stop=False; s.peak=0; s.p=psutil.Process()
    def run(s):
        while not s.stop:
            try: s.peak=max(s.peak,s.p.memory_info().rss)
            except: pass
            time.sleep(0.2)
def rf_size(m):
    try: return sum(t.tree_.node_count for t in m.estimators_)*48/1e6
    except: return float('nan')

def run(name, ctor, Xtr, ytr, Xte, yte_str, size_est=False):
    base=psutil.Process().memory_info().rss; ms=Mem(); ms.start()
    t0=time.time(); model=ctor(); model.fit(Xtr,ytr); ts=time.time()-t0
    ms.stop=True; ms.join(); peak=max(0,ms.peak-base)/1e6
    proba=model.predict_proba(Xte); cls=np.asarray(model.classes_); names=LE.classes_
    order=np.argsort(-proba,axis=1)
    top1=names[cls[order[:,0]]]; top3=names[cls[order[:,:3]]]
    acc1=float((top1==yte_str).mean())*100
    acc3=float(np.any(top3==yte_str[:,None],axis=1).mean())*100
    size=rf_size(model) if size_est else len(pickle.dumps(model))/1e6
    log(f'  [{name:13}] top1={acc1:5.2f}% top3={acc3:5.2f}% | train={ts:6.0f}s mem={peak:6.0f}MB size={size:6.0f}MB')
    del model,proba; gc.collect()
    return {'model':name,'top1':round(acc1,2),'top3':round(acc3,2),'train_s':round(ts,1),'peak_MB':round(peak),'size_MB':round(size,1)}

def main():
    global LE
    log(f'=== PEH 1205-feature 벤치마크 · {DATASET} ===')
    log('[load] reading CSV (na="-")...')
    t0=time.time()
    df=pd.read_csv(CSV, na_values=['-'], low_memory=False)
    log(f'  loaded {df.shape} in {time.time()-t0:.0f}s')
    meta=['Src_IP','Src_Port','Dst_IP','Dst_Port','Protocol']
    noise=[c for c in df.columns if re.match(r'^[A-E][a-g]_\d+$', c)]
    drop=set(['Label']+meta+noise)
    feat=[c for c in df.columns if c not in drop]
    log(f'  meta={len(meta)} noise={len(noise)} → features={len(feat)} (기대 1205)')
    y_str=df['Label'].astype(str).to_numpy()
    X=df[feat].apply(pd.to_numeric, errors='coerce').astype('float32')
    del df; gc.collect()
    # 희소클래스(<5) 제외 후 층화분할
    vc=pd.Series(y_str).value_counts(); keep=set(vc[vc>=5].index)
    m=np.array([v in keep for v in y_str]); X=X[m]; y_str=y_str[m]
    log(f'  after rare-class(<5) drop: rows={len(X):,} classes={len(keep)}')
    LE=LabelEncoder(); y=LE.fit_transform(y_str)
    Xtr,Xte,ytr,yte,ystr_tr,ystr_te=train_test_split(X,y,y_str,test_size=0.2,random_state=42,stratify=y)
    log(f'  train={len(Xtr):,} test={len(Xte):,}')
    # sklearn용 결측 채움(-999) + 스케일(MLP)
    Xtr_f=Xtr.fillna(-999.0); Xte_f=Xte.fillna(-999.0)
    scaler=StandardScaler().fit(Xtr_f)
    Xtr_s=scaler.transform(Xtr_f); Xte_s=scaler.transform(Xte_f)

    R=[]
    log('--- 학습 ---')
    R.append(run('LightGBM', lambda: lgb.LGBMClassifier(n_estimators=400,learning_rate=0.05,num_leaves=127,
        min_child_samples=30,reg_lambda=5,n_jobs=NJ,verbosity=-1,random_state=42), Xtr,ytr,Xte,ystr_te))
    R.append(run('XGBoost', lambda: xgb.XGBClassifier(n_estimators=300,max_depth=8,learning_rate=0.15,
        tree_method='hist',n_jobs=NJ,verbosity=0,random_state=42), Xtr,ytr,Xte,ystr_te))
    R.append(run('RandomForest', lambda: RandomForestClassifier(n_estimators=200,max_depth=35,max_samples=0.6,
        n_jobs=4,random_state=42), Xtr_f,ytr,Xte_f,ystr_te, size_est=True))
    R.append(run('DecisionTree', lambda: DecisionTreeClassifier(random_state=42), Xtr_f,ytr,Xte_f,ystr_te))
    R.append(run('MLP(neural)', lambda: MLPClassifier(hidden_layer_sizes=(256,128),max_iter=50,
        early_stopping=True,n_iter_no_change=6,random_state=42), Xtr_s,ytr,Xte_s,ystr_te))

    R.sort(key=lambda r:-r['top1'])
    log(f'\n============ 결과: {DATASET} · 1205 features · top1 내림차순 ============')
    log(f"{'모델':15}{'top1':>8}{'top3':>8}{'학습s':>8}{'메모리MB':>10}{'크기MB':>9}")
    for r in R:
        log(f"{r['model']:15}{r['top1']:>7.2f}%{r['top3']:>7.2f}%{r['train_s']:>8.0f}{r['peak_MB']:>10}{r['size_MB']:>9.0f}")
    json.dump({'dataset':DATASET,'n_features':len(feat),'results':R},
              open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    log('\nSAVED '+OUT); log('DONE_PEH_COMPARE')

if __name__=='__main__': main()
