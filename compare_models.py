# -*- coding: utf-8 -*-
"""모델 비교 실험: 동일 피처/학습셋/평가셋으로 여러 모델 학습 → 정확도·속도·효율 비교.
'왜 LightGBM인가'를 수치로 증명. 프로덕션 파일 미수정(import 재사용)."""
import sys, os, gc, json, time, threading, pickle
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd, psutil
import autolabel, pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
import lightgbm as lgb, xgboost as xgb
import warnings; warnings.filterwarnings('ignore')

DS = '/nmlab/99_sgs/01_datasets'
APPDIR = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
TRAIN_DAYS = ['0710', '0711', '0712', '0713']
TEST_DAY = '0714'
SUBSAMPLE = 250_000          # 공정·처리시간 위해 모든 모델 동일 서브샘플
MIN_CLASS_N = 20
NJ = 6


def log(m): print(m, flush=True)


def canon(v):
    s = '' if pd.isna(v) else str(v).strip()
    if '미분류' in s: return '__unk__'
    s = s.lower()
    if s.endswith('.exe'): s = s[:-4]
    return s.replace(' ', '_').replace('-', '_')


def norm_labels(raw):
    dmap = pipeline.build_app_display_map(raw.astype(str).tolist())
    return raw.astype(str).map(dmap).fillna(raw.astype(str)).map(canon)


class MemSampler(threading.Thread):
    def __init__(self): super().__init__(daemon=True); self.stop=False; self.peak=0; self.p=psutil.Process()
    def run(self):
        while not self.stop:
            try: self.peak=max(self.peak, self.p.memory_info().rss)
            except Exception: pass
            time.sleep(0.15)


def run_model(name, ctor, Xtr, ytr, Xte, truth, decode, needs_scale=False, scaler=None):
    Xt, Xv = Xtr, Xte
    if needs_scale:
        Xt = scaler.transform(Xtr); Xv = scaler.transform(Xte)
    base = psutil.Process().memory_info().rss
    ms = MemSampler(); ms.start()
    t0 = time.time()
    model = ctor()
    model.fit(Xt, ytr)
    train_s = time.time() - t0
    ms.stop = True; ms.join()
    peak_mb = max(0, ms.peak - base) / 1e6
    t1 = time.time(); pred = model.predict(Xv); infer_s = time.time() - t1
    pred_lbl = decode(pred)
    ok = truth != '__unk__'
    acc = float((pred_lbl[ok] == truth[ok].values).mean()) * 100
    try: size_mb = len(pickle.dumps(model)) / 1e6
    except Exception: size_mb = float('nan')
    ncls = len(getattr(model, 'classes_', []))
    log(f'  [{name:16}] acc={acc:5.2f}% · train={train_s:6.1f}s · infer={infer_s:5.1f}s · mem={peak_mb:6.0f}MB · size={size_mb:6.1f}MB · cls={ncls}')
    del model; gc.collect()
    return {'model': name, 'acc': round(acc, 2), 'train_s': round(train_s, 1),
            'infer_s': round(infer_s, 1), 'peak_mem_MB': round(peak_mb), 'size_MB': round(size_mb, 1), 'n_classes': ncls}


def main():
    log(f'=== 모델 비교 · subsample={SUBSAMPLE:,} · min_class_n={MIN_CLASS_N} ===')
    def load(d): return autolabel.normalize_df(pd.read_csv(f'{DS}/2026.07.{d[2:]}/session_stat_lab{d}.csv', low_memory=False))
    tr = pd.concat([load(d) for d in TRAIN_DAYS], ignore_index=True)
    te = load(TEST_DAY)
    log(f'  train={len(tr):,} test={len(te):,}')
    ytr_all = norm_labels(tr['task3']); truth = norm_labels(te['task3'])
    Xtr_cat = autolabel.build_features(tr); Xte_cat = autolabel.build_features(te)
    del tr, te; gc.collect()

    # 학습 대상: unknown 제외 + 희소클래스 제외 + 서브샘플(층화)
    keep = (ytr_all != '__unk__').to_numpy()
    vc = ytr_all[keep].value_counts(); big = set(vc[vc >= MIN_CLASS_N].index)
    keep &= ytr_all.isin(big).to_numpy()
    idx = np.flatnonzero(keep)
    rng = np.random.RandomState(42)
    if len(idx) > SUBSAMPLE:
        # 층화 근사: 클래스별 비율 유지 샘플
        y_keep = ytr_all.iloc[idx].to_numpy()
        sel = []
        for c in np.unique(y_keep):
            ci = idx[y_keep == c]; n = max(2, int(round(len(ci) * SUBSAMPLE / len(idx))))
            sel.append(rng.choice(ci, min(n, len(ci)), replace=False))
        idx = np.concatenate(sel)
    log(f'  학습 서브샘플={len(idx):,} · 클래스={len(big)}')

    Xtr_cat = Xtr_cat.iloc[idx].copy(); ytr = ytr_all.iloc[idx].to_numpy()
    # 범주형 레벨 고정(train fit → test apply): 네이티브(category dtype) 버전
    Xtr_cat, levels = autolabel.encode_cats_fit(Xtr_cat)
    Xte_cat2 = autolabel.encode_cats_apply(Xte_cat.copy(), levels)
    catcols = list(levels.keys()); numcols = [c for c in Xtr_cat.columns if c not in catcols]

    # 정수코드 numeric 버전(sklearn용): 범주→코드, 수치→fillna
    def to_codes(Xc):
        M = pd.DataFrame(index=Xc.index)
        for c in numcols: M[c] = pd.to_numeric(Xc[c], errors='coerce').fillna(-999).replace([np.inf,-np.inf],-999)
        for c in catcols: M[c] = Xc[c].cat.codes.astype('int32')   # 미지=-1
        return M.astype('float32')
    Xtr_num = to_codes(Xtr_cat); Xte_num = to_codes(Xte_cat2)

    # 라벨 인코딩(공통 int y)
    le = LabelEncoder(); ytr_e = le.fit_transform(ytr)
    def decode(p): return le.classes_[p]
    scaler = StandardScaler().fit(Xtr_num)

    LGB_P = dict(n_estimators=300, learning_rate=0.08, num_leaves=63, min_child_samples=50,
                 reg_lambda=15, cat_l2=50, cat_smooth=100, n_jobs=NJ, verbosity=-1, random_state=42)
    results = []
    # 1) LightGBM (네이티브 범주형)
    results.append(run_model('LightGBM', lambda: lgb.LGBMClassifier(**LGB_P), Xtr_cat, ytr_e, Xte_cat2, truth, decode))
    # 2) XGBoost (네이티브 범주형)
    results.append(run_model('XGBoost', lambda: xgb.XGBClassifier(
        n_estimators=150, max_depth=8, learning_rate=0.15, tree_method='hist',
        enable_categorical=True, n_jobs=NJ, verbosity=0, random_state=42),
        Xtr_cat, ytr_e, Xte_cat2, truth, decode))
    # 3) HistGradientBoosting (정수코드)
    results.append(run_model('HistGradBoost', lambda: HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, max_leaf_nodes=63, random_state=42),
        Xtr_num, ytr_e, Xte_num, truth, decode))
    # 4) RandomForest (정수코드)
    results.append(run_model('RandomForest', lambda: RandomForestClassifier(
        n_estimators=150, max_depth=32, n_jobs=NJ, random_state=42),
        Xtr_num, ytr_e, Xte_num, truth, decode))
    # 5) DecisionTree (정수코드)
    results.append(run_model('DecisionTree', lambda: DecisionTreeClassifier(max_depth=40, random_state=42),
        Xtr_num, ytr_e, Xte_num, truth, decode))
    # 6) LogisticRegression (스케일)
    results.append(run_model('LogisticReg', lambda: LogisticRegression(
        max_iter=120, n_jobs=NJ, C=1.0, tol=1e-3), Xtr_num, ytr_e, Xte_num, truth, decode, needs_scale=True, scaler=scaler))
    # 7) MLP (신경망, 스케일)
    results.append(run_model('MLP(neural)', lambda: MLPClassifier(
        hidden_layer_sizes=(128,), max_iter=30, early_stopping=True, random_state=42),
        Xtr_num, ytr_e, Xte_num, truth, decode, needs_scale=True, scaler=scaler))

    results.sort(key=lambda r: -r['acc'])
    log('\n================ 모델 비교 결과 (07/14, LODO) ================')
    log(f"{'모델':16}{'정확도':>8}{'학습(s)':>9}{'추론(s)':>8}{'메모리MB':>9}{'크기MB':>8}")
    for r in results:
        log(f"{r['model']:16}{r['acc']:>7.2f}%{r['train_s']:>9.1f}{r['infer_s']:>8.1f}{r['peak_mem_MB']:>9}{r['size_MB']:>8.1f}")
    with open(f'{APPDIR}/model_compare_results.json', 'w', encoding='utf-8') as f:
        json.dump({'subsample': int(len(idx)), 'test_day': TEST_DAY, 'results': results}, f, ensure_ascii=False, indent=2)
    log('\nSAVED model_compare_results.json')
    log('DONE_MODEL_COMPARE')


if __name__ == '__main__':
    main()
