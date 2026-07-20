# -*- coding: utf-8 -*-
"""모델 비교 2차: 1차에서 OOM으로 못 돈 나머지 4종(RF/DT/LR/MLP)만 메모리 안전 설정으로.
LightGBM/XGBoost/HistGradBoost 3종은 1차 로그에서 확보(별도 병합)."""
import sys, os, gc, json, time, threading, pickle
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd, psutil
import autolabel, pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
import warnings; warnings.filterwarnings('ignore')

DS='/nmlab/99_sgs/01_datasets'; APPDIR='/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
TRAIN_DAYS=['0710','0711','0712','0713']; TEST_DAY='0714'
SUBSAMPLE=250_000; MIN_CLASS_N=20; NJ=3

def log(m): print(m, flush=True)
def canon(v):
    s='' if pd.isna(v) else str(v).strip()
    if '미분류' in s: return '__unk__'
    s=s.lower()
    if s.endswith('.exe'): s=s[:-4]
    return s.replace(' ','_').replace('-','_')
def norm_labels(raw):
    dmap=pipeline.build_app_display_map(raw.astype(str).tolist())
    return raw.astype(str).map(dmap).fillna(raw.astype(str)).map(canon)

class MemSampler(threading.Thread):
    def __init__(self): super().__init__(daemon=True); self.stop=False; self.peak=0; self.p=psutil.Process()
    def run(self):
        while not self.stop:
            try: self.peak=max(self.peak,self.p.memory_info().rss)
            except Exception: pass
            time.sleep(0.15)

def run_model(name,ctor,Xtr,ytr,Xte,truth,decode,scale=False,scaler=None):
    Xt,Xv=(scaler.transform(Xtr),scaler.transform(Xte)) if scale else (Xtr,Xte)
    base=psutil.Process().memory_info().rss; ms=MemSampler(); ms.start()
    t0=time.time(); model=ctor(); model.fit(Xt,ytr); train_s=time.time()-t0
    ms.stop=True; ms.join(); peak=max(0,ms.peak-base)/1e6
    t1=time.time(); pred=model.predict(Xv); infer_s=time.time()-t1
    pl=decode(pred); ok=truth!='__unk__'; acc=float((pl[ok]==truth[ok].values).mean())*100
    try: size=len(pickle.dumps(model))/1e6
    except Exception: size=float('nan')
    log(f'  [{name:16}] acc={acc:5.2f}% · train={train_s:6.1f}s · infer={infer_s:5.1f}s · mem={peak:6.0f}MB · size={size:6.1f}MB · cls={len(getattr(model,"classes_",[]))}')
    del model; gc.collect()
    return {'model':name,'acc':round(acc,2),'train_s':round(train_s,1),'infer_s':round(infer_s,1),'peak_mem_MB':round(peak),'size_MB':round(size,1)}

def main():
    log(f'=== 모델 비교 2차(RF/DT/LR/MLP) · subsample={SUBSAMPLE:,} ===')
    def load(d): return autolabel.normalize_df(pd.read_csv(f'{DS}/2026.07.{d[2:]}/session_stat_lab{d}.csv',low_memory=False))
    tr=pd.concat([load(d) for d in TRAIN_DAYS],ignore_index=True); te=load(TEST_DAY)
    ytr_all=norm_labels(tr['task3']); truth=norm_labels(te['task3'])
    Xtr_cat=autolabel.build_features(tr); Xte_cat=autolabel.build_features(te); del tr,te; gc.collect()
    keep=(ytr_all!='__unk__').to_numpy(); vc=ytr_all[keep].value_counts(); big=set(vc[vc>=MIN_CLASS_N].index)
    keep&=ytr_all.isin(big).to_numpy(); idx=np.flatnonzero(keep); rng=np.random.RandomState(42)
    if len(idx)>SUBSAMPLE:
        yk=ytr_all.iloc[idx].to_numpy(); sel=[]
        for c in np.unique(yk):
            ci=idx[yk==c]; n=max(2,int(round(len(ci)*SUBSAMPLE/len(idx)))); sel.append(rng.choice(ci,min(n,len(ci)),replace=False))
        idx=np.concatenate(sel)
    Xtr_cat=Xtr_cat.iloc[idx].copy(); ytr=ytr_all.iloc[idx].to_numpy()
    Xtr_cat,levels=autolabel.encode_cats_fit(Xtr_cat); Xte_cat=autolabel.encode_cats_apply(Xte_cat.copy(),levels)
    catcols=list(levels.keys()); numcols=[c for c in Xtr_cat.columns if c not in catcols]
    def codes(Xc):
        M=pd.DataFrame(index=Xc.index)
        for c in numcols: M[c]=pd.to_numeric(Xc[c],errors='coerce').fillna(-999).replace([np.inf,-np.inf],-999)
        for c in catcols: M[c]=Xc[c].cat.codes.astype('int32')
        return M.astype('float32')
    Xtr=codes(Xtr_cat); Xte=codes(Xte_cat); del Xtr_cat,Xte_cat; gc.collect()
    le=LabelEncoder(); ytr_e=le.fit_transform(ytr); decode=lambda p: le.classes_[p]
    scaler=StandardScaler().fit(Xtr)
    log(f'  서브샘플={len(idx):,} · 클래스={len(big)}')
    R=[]
    R.append(run_model('RandomForest',lambda: RandomForestClassifier(n_estimators=100,max_depth=22,max_samples=0.5,n_jobs=NJ,random_state=42),Xtr,ytr_e,Xte,truth,decode))
    R.append(run_model('DecisionTree',lambda: DecisionTreeClassifier(max_depth=40,random_state=42),Xtr,ytr_e,Xte,truth,decode))
    R.append(run_model('LogisticReg',lambda: LogisticRegression(max_iter=100,tol=1e-3,C=1.0),Xtr,ytr_e,Xte,truth,decode,scale=True,scaler=scaler))
    R.append(run_model('MLP(neural)',lambda: MLPClassifier(hidden_layer_sizes=(128,),max_iter=30,early_stopping=True,random_state=42),Xtr,ytr_e,Xte,truth,decode,scale=True,scaler=scaler))
    with open(f'{APPDIR}/model_compare_results2.json','w',encoding='utf-8') as f: json.dump({'results':R},f,ensure_ascii=False,indent=2)
    log('\n결과:'); [log(f"  {r['model']:16} acc={r['acc']}% train={r['train_s']}s mem={r['peak_mem_MB']}MB") for r in R]
    log('SAVED model_compare_results2.json'); log('DONE_MODEL_COMPARE2')

if __name__=='__main__': main()
