# -*- coding: utf-8 -*-
"""부스팅 3종(LightGBM/XGBoost/CatBoost) 하이퍼파라미터 Optuna 튜닝.
- bias_variance.py와 '동일한 train/test 분할'(test=.3, seed42, stratify)을 재현하고, **train 부분에서만** 튜닝
  (train 내부 80/20 홀드아웃으로 macro-F1 평가) → BV test 누수 없음.
- 결과 best params를 03_json/boosting_best_params.json 에 dataset×model 키로 병합 저장.
사용: python tune_boosting.py <NAME> <seq_dir> <out_json> [--lab] [--trials N]
환경변수: BV_SUB(LAB 서브샘플, BV와 동일 20만 권장), N_JOBS, DOMAIN_ONLY(cipher).
"""
import sys, os, json, time
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
import optuna

NAME = sys.argv[1]; SEQDIR = Path(sys.argv[2]); OUT = Path(sys.argv[3]); IS_LAB = '--lab' in sys.argv
TRIALS = int(sys.argv[sys.argv.index('--trials') + 1]) if '--trials' in sys.argv else 50
# --models lightgbm,xgboost,catboost (기본 전체). CPU proc과 GPU proc 분리 실행용.
_MSEL = sys.argv[sys.argv.index('--models') + 1].lower() if '--models' in sys.argv else 'lightgbm,xgboost,catboost'
MODELS = set(m.strip() for m in _MSEL.split(',') if m.strip())
CAT_GPU = os.environ.get('CAT_GPU') == '1'  # CatBoost GPU 학습(rsm 미지원 → 검색 제외)
SUB = int(os.environ.get('BV_SUB', '0'))
NJ = int(os.environ.get('N_JOBS', '8'))
B_MIN = 15  # bias_variance와 동일한 희소클래스 필터 기준(max(10,B))
RNG = 42


def load_xy():
    """bias_variance.load_seq789 + main 전처리와 동일하게 X, y(정수라벨) 생성."""
    metas, packs = [], []
    for cf in sorted(SEQDIR.glob('sequences_part_*.csv')):
        z = np.load(cf.with_suffix('.npz')); metas.append(pd.read_csv(cf)); packs.append({k: z[k] for k in z.files})
    meta = pd.concat(metas, ignore_index=True)
    A = {k: np.concatenate([p[k] for p in packs], 0) for k in packs[0].keys()}
    N = len(meta)
    if IS_LAB:
        kmpath = os.environ.get('LAB_LABEL_MAP', str(SEQDIR.resolve().parent / '02_dataset' / 'lab_canon_label.csv'))
        km = pd.read_csv(kmpath); fn2t = dict(zip(km['filename'].astype(str), km['task3'].astype(str)))
        bn = meta['pcap'].astype(str).str.split('/').str[-1].str.split('\\').str[-1]
        lab = bn.map(fn2t)
        tmp = pd.DataFrame({'bn': bn, 'lab': lab, 'i': np.arange(N)})[lab.notna().to_numpy()].drop_duplicates('bn', keep='first')
        labc = tmp['lab'].astype(str).str.lower().str.replace(r'\.exe$', '', regex=True)
        nf = set()
        nff = os.environ.get('LAB_NOISE_FILE')
        if nff and os.path.exists(nff): nf = {l.strip() for l in open(nff, encoding='utf-8') if l.strip()}
        not_noise = (~tmp['bn'].isin(nf)).to_numpy() if nf else np.ones(len(tmp), bool)
        # class≥10은 노이즈 제거 후 개수로 (전 개수로 하면 1개짜리 클래스 남아 stratify 크래시)
        vc = labc[not_noise].value_counts(); keep = (not_noise & labc.isin(vc[vc >= 10].index).to_numpy())
        if nf: print(f'[LAB] 노이즈 {len(nf)}basename → 제거 {int(tmp["bn"].isin(nf).sum())}행', flush=True)
        idx = tmp['i'].to_numpy()[keep]
        meta = meta.iloc[idx].reset_index(drop=True); A = {k: v[idx] for k, v in A.items()}; N = len(meta)
        meta['label'] = labc.to_numpy()[keep]
    if not IS_LAB:  # 비-LAB: NOISE_FILE(basename) 노이즈 제거
        nff = os.environ.get('NOISE_FILE')
        if nff and os.path.exists(nff):
            nfset = {l.strip() for l in open(nff, encoding='utf-8') if l.strip()}
            bn2 = meta['pcap'].astype(str).str.split('/').str[-1].str.split('\\').str[-1]
            km2 = (~bn2.isin(nfset)).to_numpy()
            meta = meta[km2].reset_index(drop=True); A = {k: v[km2] for k, v in A.items()}; N = len(meta)
            print(f'[{NAME}] 노이즈 {len(nfset)}basename → 제거 {int((~km2).sum())}행', flush=True)
    m = A['mask'].astype(bool); size = A['packet_size'].astype('f4'); dire = A['direction'].astype('f4')
    iat = A['iat_ms'].astype('f4'); liat = np.log1p(iat); win = np.log1p(np.maximum(A['tcp_window'].astype('f4'), 0))
    ret = A['retrans'].astype('f4'); pay = A['payload_size'].astype('f4'); signed = size * dire
    def agg(a):
        x = np.where(m, a, np.nan); return np.column_stack([np.nanmean(x, 1), np.nanstd(x, 1), np.nanmin(x, 1), np.nanmax(x, 1), np.nansum(x, 1)])
    flow = np.column_stack([agg(size), agg(liat), agg(win), agg(pay), ret.sum(1), m.sum(1), (dire > 0).sum(1), (dire < 0).sum(1),
                            meta[['burst_count', 'longest_burst', 'up_ratio', 'duration_ms', 'mean_iat_ms']].to_numpy('f4')]).astype('f4')
    chan = np.column_stack([signed, liat, win, ret, pay * dire]).astype('f4')
    cum = np.column_stack([np.cumsum(dire * m, 1), np.cumsum(signed * m, 1)]).astype('f4')
    K = 8; bl = np.zeros((N, K), 'f4'); bm = np.zeros(N, 'f4'); bs = np.zeros(N, 'f4')
    for i in range(N):
        dd = dire[i][m[i]]
        if len(dd):
            idx2 = np.flatnonzero(np.diff(dd) != 0) + 1; runs = np.diff(np.concatenate(([0], idx2, [len(dd)])))
            bl[i, :min(K, len(runs))] = runs[:K]; bm[i] = runs.mean(); bs[i] = runs.std()
    burst = np.column_stack([bl, bm, bs]).astype('f4')
    bi = np.clip((np.abs(size) // 80).astype(int), 0, 19); up = (dire > 0) & m; dn = (dire < 0) & m
    hu = np.zeros((N, 20), 'f4'); hd = np.zeros((N, 20), 'f4')
    for b in range(20): hu[:, b] = ((bi == b) & up).sum(1); hd[:, b] = ((bi == b) & dn).sum(1)
    hist = np.column_stack([hu, hd]).astype('f4')
    def q(a): x = np.where(m, a, np.nan); return np.nanpercentile(x, [10, 25, 50, 75, 90], 1).T.astype('f4')
    quant = np.column_stack([q(iat), q(np.abs(size))]).astype('f4')
    X = np.nan_to_num(np.column_stack([flow, chan, cum, burst, hist, quant]).astype('f4'))
    lab = meta['label'].astype(str)
    if os.environ.get('DOMAIN_ONLY') == '1':
        lab = lab.str.split('_', n=2).str[-1]
    ylab = lab.to_numpy()
    # 전처리(=bias_variance.main): unknown 제거 → 서브샘플 → 희소클래스 제거 → 인코딩
    UNK = {'', 'nan', 'none', 'unknown', 'unk', '__unk__'}
    okm = ~pd.Series(ylab).astype(str).str.strip().str.lower().isin(UNK).to_numpy()
    X, ylab = X[okm], ylab[okm]
    if SUB > 0 and len(X) > SUB:
        idx, _ = train_test_split(np.arange(len(X)), train_size=SUB, random_state=RNG, stratify=ylab); X, ylab = X[idx], ylab[idx]
    s = pd.Series(ylab); vc = s.value_counts(); ok = s.isin(vc[vc >= max(10, B_MIN)].index).to_numpy()
    X = X[ok]; y = LabelEncoder().fit_transform(ylab[ok])
    return X, y


def make_objective(kind, Xtr, ytr):
    # train 내부 80/20 홀드아웃 (튜닝 전용, BV test와 무관)
    xi, xv, yi, yv = train_test_split(Xtr, ytr, test_size=.2, random_state=RNG, stratify=ytr)
    def objective(trial):
        if kind == 'LightGBM':
            import lightgbm as lgb
            p = dict(objective='multiclass', n_jobs=NJ, verbosity=-1, random_state=0, subsample_freq=1,
                     n_estimators=trial.suggest_int('n_estimators', 300, 1200, step=100),
                     num_leaves=trial.suggest_int('num_leaves', 15, 255),
                     max_depth=trial.suggest_int('max_depth', 3, 12),
                     learning_rate=trial.suggest_float('learning_rate', 1e-2, 3e-1, log=True),
                     min_child_samples=trial.suggest_int('min_child_samples', 5, 100),
                     colsample_bytree=trial.suggest_float('colsample_bytree', .5, 1.0),
                     subsample=trial.suggest_float('subsample', .5, 1.0),
                     reg_lambda=trial.suggest_float('reg_lambda', 1e-3, 30.0, log=True))
            model = lgb.LGBMClassifier(**p)
        elif kind == 'XGBoost':
            import xgboost as xgb
            p = dict(n_jobs=NJ, tree_method='hist', verbosity=0, random_state=0,
                     **({'device': 'cuda'} if os.environ.get('XGB_GPU') == '1' else {}),
                     n_estimators=trial.suggest_int('n_estimators', 300, 1200, step=100),
                     max_depth=trial.suggest_int('max_depth', 3, 12),
                     learning_rate=trial.suggest_float('learning_rate', 1e-2, 3e-1, log=True),
                     min_child_weight=trial.suggest_int('min_child_weight', 1, 20),
                     colsample_bytree=trial.suggest_float('colsample_bytree', .5, 1.0),
                     subsample=trial.suggest_float('subsample', .5, 1.0),
                     reg_lambda=trial.suggest_float('reg_lambda', 1e-3, 30.0, log=True))
            model = xgb.XGBClassifier(**p)
        else:  # CatBoost
            from catboost import CatBoostClassifier
            p = dict(loss_function='MultiClass', verbose=0, random_seed=0, allow_writing_files=False,
                     iterations=trial.suggest_int('iterations', 300, 1200, step=100),
                     depth=trial.suggest_int('depth', 4, 10),
                     learning_rate=trial.suggest_float('learning_rate', 1e-2, 3e-1, log=True),
                     l2_leaf_reg=trial.suggest_float('l2_leaf_reg', 1.0, 30.0, log=True))
            if CAT_GPU:  # GPU: rsm 미지원 + VRAM 8GB 맞춰 메모리 절감(Plain+낮은 border)
                p.update(task_type='GPU', devices='0', boosting_type='Plain', border_count=32, gpu_ram_part=0.85, max_ctr_complexity=1)
            else: p.update(thread_count=NJ, rsm=trial.suggest_float('rsm', .5, 1.0))
            model = CatBoostClassifier(**p)
        model.fit(xi, yi)
        pred = np.asarray(model.predict(xv)).ravel()
        return float(f1_score(yv, pred, average='macro', zero_division=0))
    return objective


def main():
    t0 = time.time()
    X, y = load_xy()
    Xtr, _Xte, ytr, _yte = train_test_split(X, y, test_size=.3, random_state=RNG, stratify=y)  # BV와 동일 분할, train만 사용
    print(f'[{NAME}] tune rows={len(X)} classes={len(np.unique(y))} train={len(Xtr)} trials={TRIALS}', flush=True)
    res = json.load(open(OUT, encoding='utf-8')) if OUT.exists() else {}
    res.setdefault(NAME, {})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    allk = [('LightGBM', 'LightGBM(Boost)'), ('XGBoost', 'XGBoost(Boost)'), ('CatBoost', 'CatBoost(Boost)')]
    for kind, mkey in [(k, m) for k, m in allk if k.lower() in MODELS]:
        st = time.time()
        storage = f'sqlite:///{OUT.parent}/optuna_{NAME}_{kind}.db'  # study별 db 분리 → CPU/GPU 프로세스 동시 실행 시 락 회피
        study = optuna.create_study(direction='maximize', study_name=f'{NAME}_{kind}', storage=storage, load_if_exists=True)
        study.optimize(make_objective(kind, Xtr, ytr), n_trials=TRIALS, show_progress_bar=False)
        res[NAME][mkey] = {'params': study.best_params, 'val_macro_f1': round(study.best_value * 100, 3), 'n_trials': len(study.trials)}
        json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'  {kind:9s} best_valF1={study.best_value*100:.3f} ({time.time()-st:.0f}s) params={study.best_params}', flush=True)
    print(f'>>> {NAME} 튜닝 완료 ({time.time()-t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
