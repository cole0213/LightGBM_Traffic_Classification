# -*- coding: utf-8 -*-
"""진득한 모델 비교: RF·XGB·LGB·MLP·DT (동일 50만 학습셋, 강한 설정).
정확도(top1/top3/macroF1) + 확신도 품질(ECE·고확신 정확도/커버리지) 측정.
+ Part B: LightGBM 전량 2M(GBM만 가능) 참조. 프로덕션 파일 미수정."""
import sys, os, gc, json, time, threading, pickle
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd, psutil
import autolabel, pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import f1_score
import lightgbm as lgb, xgboost as xgb
import warnings; warnings.filterwarnings('ignore')

DS='/nmlab/99_sgs/01_datasets'; APPDIR='/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
TRAIN=['0710','0711','0712','0713']; TEST='0714'
SUB=500_000; MIN_CLASS_N=20; NJ=6
LE=None   # LabelEncoder (전역)

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

def run(name, ctor, Xtr, ytr, Xte, truth, scale=False, scaler=None, rf=False):
    Xt,Xv=(scaler.transform(Xtr),scaler.transform(Xte)) if scale else (Xtr,Xte)
    base=psutil.Process().memory_info().rss; ms=Mem(); ms.start()
    t0=time.time(); model=ctor(); model.fit(Xt,ytr); ts=time.time()-t0
    ms.stop=True; ms.join(); peak=max(0,ms.peak-base)/1e6
    proba=model.predict_proba(Xv)
    cls=np.asarray(model.classes_)                 # proba 컬럼 → le 정수라벨
    names=LE.classes_                              # le 정수 → 문자열
    order=np.argsort(-proba,axis=1)
    to_str=lambda colidx: names[cls[colidx]]
    ok=(truth!='__unk__').to_numpy(); tv=truth[ok].values
    p1=to_str(order[:,0])[ok]
    acc1=float((p1==tv).mean())*100
    t3=to_str(order[:,:3])[ok]
    acc3=float(np.any(t3==tv[:,None],axis=1).mean())*100
    conf=proba[ok].max(1); correct=(p1==tv).astype(float); e=ece(conf,correct)
    def hc(thr):
        m=conf>=thr
        return (round(float((p1[m]==tv[m]).mean())*100,2) if m.sum() else float('nan'), round(float(m.mean())*100,2))
    a50,c50=hc(0.5); a80,c80=hc(0.8)
    mf1=float(f1_score(tv,p1,average='macro'))*100
    size=rf_size(model) if rf else len(pickle.dumps(model))/1e6
    log(f'  [{name:15}] top1={acc1:5.2f}% top3={acc3:5.2f}% mF1={mf1:5.1f} ECE={e:4.2f} | >=.5 acc={a50:5.2f}% cov={c50:5.1f}% | >=.8 acc={a80:5.2f}% cov={c80:5.1f}% | {ts:5.0f}s {peak:5.0f}MB {size:5.0f}MB')
    del model,proba; gc.collect()
    return {'model':name,'top1':round(acc1,2),'top3':round(acc3,2),'macroF1':round(mf1,2),'ECE':round(e,2),
            'acc@0.5':a50,'cov@0.5':c50,'acc@0.8':a80,'cov@0.8':c80,'train_s':round(ts,1),'peak_MB':round(peak),'size_MB':round(size,1)}

def main():
    global LE
    log(f'=== 진득한 비교 · train_sub={SUB:,} ===')
    def load(d): return autolabel.normalize_df(pd.read_csv(f'{DS}/2026.07.{d[2:]}/session_stat_lab{d}.csv',low_memory=False))
    tr=pd.concat([load(d) for d in TRAIN],ignore_index=True); te=load(TEST)
    y_all=norm(tr['task3']); truth=norm(te['task3'])
    Xtr_cat=autolabel.build_features(tr); Xte_cat=autolabel.build_features(te); del tr,te; gc.collect()
    keep=(y_all!='__unk__').to_numpy(); vc=y_all[keep].value_counts(); big=set(vc[vc>=MIN_CLASS_N].index)
    keep&=y_all.isin(big).to_numpy(); full_idx=np.flatnonzero(keep)
    Xtr_cat,levels=autolabel.encode_cats_fit(Xtr_cat); Xte_cat=autolabel.encode_cats_apply(Xte_cat.copy(),levels)
    catcols=list(levels.keys()); numcols=[c for c in Xtr_cat.columns if c not in catcols]
    def codes(Xc):
        M=pd.DataFrame(index=Xc.index)
        for c in numcols: M[c]=pd.to_numeric(Xc[c],errors='coerce').fillna(-999).replace([np.inf,-np.inf],-999)
        for c in catcols: M[c]=Xc[c].cat.codes.astype('int32')
        return M.astype('float32')
    Xte_num=codes(Xte_cat)
    LE=LabelEncoder(); LE.fit(y_all.iloc[full_idx])
    rng=np.random.RandomState(42); yk=y_all.iloc[full_idx].to_numpy(); sel=[]
    for c in np.unique(yk):
        ci=full_idx[yk==c]; n=max(2,int(round(len(ci)*SUB/len(full_idx)))); sel.append(rng.choice(ci,min(n,len(ci)),replace=False))
    sub=np.concatenate(sel)
    log(f'  full={len(full_idx):,} · sub={len(sub):,} · classes={len(big)} · test={len(truth):,}')
    Xtr_cat_s=Xtr_cat.iloc[sub].copy(); ytr_s=LE.transform(y_all.iloc[sub]); Xtr_num_s=codes(Xtr_cat_s)
    scaler=StandardScaler().fit(Xtr_num_s)

    R=[]
    log('--- Part A: 동일 50만 학습셋, 강한 설정 ---')
    R.append(run('LightGBM', lambda: lgb.LGBMClassifier(n_estimators=600,learning_rate=0.05,num_leaves=127,
        min_child_samples=50,reg_lambda=15,cat_l2=50,cat_smooth=100,n_jobs=NJ,verbosity=-1,random_state=42),
        Xtr_cat_s,ytr_s,Xte_cat,truth))
    R.append(run('XGBoost', lambda: xgb.XGBClassifier(n_estimators=300,max_depth=8,learning_rate=0.1,
        tree_method='hist',enable_categorical=True,n_jobs=NJ,verbosity=0,random_state=42),
        Xtr_cat_s,ytr_s,Xte_cat,truth))
    R.append(run('RandomForest', lambda: RandomForestClassifier(n_estimators=200,max_depth=30,max_samples=0.5,
        n_jobs=3,random_state=42), Xtr_num_s,ytr_s,Xte_num,truth,rf=True))
    R.append(run('DecisionTree', lambda: DecisionTreeClassifier(random_state=42), Xtr_num_s,ytr_s,Xte_num,truth))
    R.append(run('MLP(neural)', lambda: MLPClassifier(hidden_layer_sizes=(256,128),max_iter=60,
        early_stopping=True,n_iter_no_change=6,random_state=42), Xtr_num_s,ytr_s,Xte_num,truth,scale=True,scaler=scaler))

    del Xtr_num_s,Xtr_cat_s; gc.collect()
    log('--- Part B: LightGBM 전량 2M (GBM만 가능) ---')
    R.append(run('LightGBM_full2M', lambda: lgb.LGBMClassifier(n_estimators=500,learning_rate=0.05,num_leaves=63,
        min_child_samples=50,reg_lambda=15,cat_l2=50,cat_smooth=100,n_jobs=NJ,verbosity=-1,random_state=42),
        Xtr_cat.iloc[full_idx],LE.transform(y_all.iloc[full_idx]),Xte_cat,truth))

    R.sort(key=lambda r:-r['top1'])
    log('\n================ 결과 (07/14 평가, top1 내림차순) ================')
    log(f"{'모델':17}{'top1':>7}{'top3':>7}{'mF1':>6}{'ECE':>6}{'acc@.5':>8}{'cov@.5':>8}{'학습s':>7}{'크기MB':>8}")
    for r in R:
        log(f"{r['model']:17}{r['top1']:>6.2f}%{r['top3']:>6.2f}%{r['macroF1']:>6.1f}{r['ECE']:>6.2f}{r['acc@0.5']:>7.2f}%{r['cov@0.5']:>7.1f}%{r['train_s']:>7.0f}{r['size_MB']:>8.0f}")
    with open(f'{APPDIR}/deep_compare_results.json','w',encoding='utf-8') as f: json.dump(R,f,ensure_ascii=False,indent=2)
    log('\nSAVED deep_compare_results.json'); log('DONE_DEEP_COMPARE')

if __name__=='__main__': main()
