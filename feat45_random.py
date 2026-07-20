# -*- coding: utf-8 -*-
"""45피처 벤치마크 (랜덤분할판) — 1205 벤치마크(peh_compare)와 '같은 프로토콜'로 비교용.
07/11~14 session_stat 풀 → 45피처 → 라벨정규화 → rare<5 제외 → ~12만 층화표본 → 랜덤 80/20 →
peh_compare와 '동일한 5모델 설정'으로 top1/top3/macroF1/ECE/acc@thr 측정.
※ 채점방식(랜덤분할)·모델설정을 1205와 맞춤. 단 추출경로/라벨공간/행은 다르므로 정밀 apples-to-apples는 아님(덱에 명시)."""
import sys, os, gc, json, time, threading, pickle
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd, psutil
import autolabel, pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import f1_score
import lightgbm as lgb, xgboost as xgb
import warnings; warnings.filterwarnings('ignore')

DS='/nmlab/99_sgs/01_datasets'; APPDIR='/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
DAYS=['0711','0712','0713','0714']
TARGET=120_000; MIN_CLASS_N=5; NJ=6
LE=None

def log(m): print(m,flush=True)
def canon(v):
    s='' if pd.isna(v) else str(v).strip()
    if '미분류' in s: return '__unk__'
    s=s.lower()
    if s.endswith('.exe'): s=s[:-4]
    return s.replace(' ','_').replace('-','_')
def norm(raw):
    dm=pipeline.build_app_display_map(raw.astype(str).tolist())
    return raw.astype(str).map(dm).fillna(raw.astype(str)).map(canon)
def ece(conf,correct,bins=15):
    ed=np.linspace(0,1,bins+1); e=0.0
    for i in range(bins):
        m=(conf>ed[i])&(conf<=ed[i+1])
        if m.sum(): e+=abs(conf[m].mean()-correct[m].mean())*m.sum()
    return e/len(conf)*100

class Mem(threading.Thread):
    def __init__(s): super().__init__(daemon=True); s.stop=False; s.peak=0; s.p=psutil.Process()
    def run(s):
        while not s.stop:
            try: s.peak=max(s.peak,s.p.memory_info().rss)
            except: pass
            time.sleep(0.2)
def rf_size(model):
    try: return sum(t.tree_.node_count for t in model.estimators_)*48/1e6
    except: return float('nan')

def run(name, ctor, Xtr, ytr, Xte, yte_str, scale=False, scaler=None, rf=False):
    Xt,Xv=(scaler.transform(Xtr),scaler.transform(Xte)) if scale else (Xtr,Xte)
    base=psutil.Process().memory_info().rss; ms=Mem(); ms.start()
    t0=time.time(); model=ctor(); model.fit(Xt,ytr); ts=time.time()-t0
    ms.stop=True; ms.join(); peak=max(0,ms.peak-base)/1e6
    proba=model.predict_proba(Xv); cls=np.asarray(model.classes_); names=LE.classes_
    order=np.argsort(-proba,axis=1)
    p1=names[cls[order[:,0]]]; t3=names[cls[order[:,:3]]]
    acc1=float((p1==yte_str).mean())*100
    acc3=float(np.any(t3==yte_str[:,None],axis=1).mean())*100
    conf=proba.max(1); correct=(p1==yte_str).astype(float); e=ece(conf,correct)
    def hc(thr):
        m=conf>=thr
        return (round(float((p1[m]==yte_str[m]).mean())*100,2) if m.sum() else float('nan'), round(float(m.mean())*100,2))
    a50,c50=hc(0.5); a80,c80=hc(0.8)
    mf1=float(f1_score(yte_str,p1,average='macro'))*100
    size=rf_size(model) if rf else len(pickle.dumps(model))/1e6
    log(f'  [{name:15}] top1={acc1:5.2f}% top3={acc3:5.2f}% mF1={mf1:5.1f} ECE={e:4.2f} | >=.5 acc={a50:5.2f}% cov={c50:5.1f}% | {ts:5.0f}s {peak:5.0f}MB {size:5.0f}MB')
    del model,proba; gc.collect()
    return {'model':name,'top1':round(acc1,2),'top3':round(acc3,2),'macroF1':round(mf1,2),'ECE':round(e,2),
            'acc@0.5':a50,'cov@0.5':c50,'acc@0.8':a80,'cov@0.8':c80,'train_s':round(ts,1),'peak_MB':round(peak),'size_MB':round(size,1)}

def main():
    global LE
    log(f'=== 45피처 랜덤분할 벤치마크 (1205와 동일 프로토콜) · target={TARGET:,} ===')
    def load(d): return autolabel.normalize_df(pd.read_csv(f'{DS}/2026.07.{d[2:]}/session_stat_lab{d}.csv',low_memory=False))
    df=pd.concat([load(d) for d in DAYS],ignore_index=True)
    log(f'  pooled {len(df):,} sessions from {DAYS}')
    y_all=norm(df['task3'])
    X_cat=autolabel.build_features(df); del df; gc.collect()
    keep=(y_all!='__unk__').to_numpy(); vc=y_all[keep].value_counts(); big=set(vc[vc>=MIN_CLASS_N].index)
    keep&=y_all.isin(big).to_numpy(); idx=np.flatnonzero(keep)
    # ~12만 층화표본
    rng=np.random.RandomState(42); yk=y_all.iloc[idx].to_numpy(); sel=[]
    for c in np.unique(yk):
        ci=idx[yk==c]; n=max(2,int(round(len(ci)*TARGET/len(idx)))); sel.append(rng.choice(ci,min(n,len(ci)),replace=False))
    sub=np.concatenate(sel)
    log(f'  after rare<{MIN_CLASS_N} + subsample: rows={len(sub):,} classes={len(big)}')
    Xc=X_cat.iloc[sub].reset_index(drop=True); ys=y_all.iloc[sub].reset_index(drop=True)
    LE=LabelEncoder(); yenc=LE.fit_transform(ys)
    # 랜덤 80/20 (peh_compare와 동일: test_size=0.2, rs=42, stratify)
    tr_i,te_i=train_test_split(np.arange(len(sub)),test_size=0.2,random_state=42,stratify=yenc)
    yte_str=ys.to_numpy()[te_i]; ytr=yenc[tr_i]
    # 범주형: train에서 fit → apply (LGB/XGB용 category dtype)
    Xtr_cat=Xc.iloc[tr_i].copy(); Xte_cat=Xc.iloc[te_i].copy()
    Xtr_cat,levels=autolabel.encode_cats_fit(Xtr_cat); Xte_cat=autolabel.encode_cats_apply(Xte_cat,levels)
    catcols=list(levels.keys()); numcols=[c for c in Xtr_cat.columns if c not in catcols]
    def codes(Xcc):
        M=pd.DataFrame(index=Xcc.index)
        for c in numcols: M[c]=pd.to_numeric(Xcc[c],errors='coerce').fillna(-999).replace([np.inf,-np.inf],-999)
        for c in catcols: M[c]=Xcc[c].cat.codes.astype('int32')
        return M.astype('float32')
    Xtr_num=codes(Xtr_cat); Xte_num=codes(Xte_cat)
    scaler=StandardScaler().fit(Xtr_num)
    log(f'  train={len(tr_i):,} test={len(te_i):,} · cat={len(catcols)} num={len(numcols)}')

    R=[]
    log('--- 학습 (peh_compare와 동일 모델설정) ---')
    R.append(run('LightGBM', lambda: lgb.LGBMClassifier(n_estimators=400,learning_rate=0.05,num_leaves=127,
        min_child_samples=30,reg_lambda=5,n_jobs=NJ,verbosity=-1,random_state=42), Xtr_cat,ytr,Xte_cat,yte_str))
    R.append(run('XGBoost', lambda: xgb.XGBClassifier(n_estimators=300,max_depth=8,learning_rate=0.15,
        tree_method='hist',enable_categorical=True,n_jobs=NJ,verbosity=0,random_state=42), Xtr_cat,ytr,Xte_cat,yte_str))
    R.append(run('RandomForest', lambda: RandomForestClassifier(n_estimators=200,max_depth=35,max_samples=0.6,
        n_jobs=4,random_state=42), Xtr_num,ytr,Xte_num,yte_str,rf=True))
    R.append(run('DecisionTree', lambda: DecisionTreeClassifier(random_state=42), Xtr_num,ytr,Xte_num,yte_str))
    R.append(run('MLP(neural)', lambda: MLPClassifier(hidden_layer_sizes=(256,128),max_iter=50,
        early_stopping=True,n_iter_no_change=6,random_state=42), Xtr_num,ytr,Xte_num,yte_str,scale=True,scaler=scaler))

    R.sort(key=lambda r:-r['top1'])
    log('\n============ 45피처 랜덤분할 결과 · top1 내림차순 ============')
    log(f"{'모델':15}{'top1':>7}{'top3':>7}{'mF1':>6}{'ECE':>6}{'학습s':>7}{'memMB':>7}{'MB':>6}")
    for r in R:
        log(f"{r['model']:15}{r['top1']:>6.2f}%{r['top3']:>6.2f}%{r['macroF1']:>6.1f}{r['ECE']:>6.2f}{r['train_s']:>7.0f}{r['peak_MB']:>7}{r['size_MB']:>6.0f}")
    json.dump({'protocol':'random80/20 stratified','days':DAYS,'n_features':45,'results':R},
              open(f'{APPDIR}/feat45_random_results.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    log('\nSAVED feat45_random_results.json'); log('DONE_FEAT45_RANDOM')

if __name__=='__main__': main()
