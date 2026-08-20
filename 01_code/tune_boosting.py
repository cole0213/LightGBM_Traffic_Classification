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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdata  # bias_variance와 공유하는 로드/라벨링
from features import build_features  # 피처 조립(모듈화)

def _envset(envf, envc):  # 파일(# 주석무시) + 콤마 env 합쳐 소문자 set
    s = set()
    f = os.environ.get(envf)
    if f and os.path.exists(f): s |= {l.strip().lower() for l in open(f, encoding='utf-8') if l.strip() and not l.startswith('#')}
    s |= {l.strip().lower() for l in os.environ.get(envc, '').split(',') if l.strip()}
    return s

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
    """bias_variance와 '동일한' 로드/라벨/피처/전처리로 X, y(정수라벨) 생성.
    seqdata.load_labeled + build_features 공유 → FEAT_TRUNC(K30)·FEAT_SELECT(core)·라벨정제 동일 반영."""
    A, meta, ylab = seqdata.load_labeled(
        SEQDIR, IS_LAB,
        domain_only=(os.environ.get('DOMAIN_ONLY') == '1'),
        label_map=os.environ.get('LAB_LABEL_MAP'),
        lab_noise_file=os.environ.get('LAB_NOISE_FILE'),
        keep=_envset('LAB_KEEP_FILE', 'LAB_KEEP'),
        exclude=_envset('LAB_EXCLUDE_FILE', 'LAB_EXCLUDE'),
        collapse=_envset('LAB_COLLAPSE_FILE', 'LAB_COLLAPSE'),
        noise_file=os.environ.get('NOISE_FILE'),
        label_exclude=_envset('DOMAIN_EXCLUDE_FILE', 'DOMAIN_EXCLUDE'))
    ft = int(os.environ.get('FEAT_TRUNC', '0') or 0)   # 앞 K패킷(정본 K30)
    if ft:
        A = {k: v[:, :ft] for k, v in A.items()}
    fg = os.environ.get('FEAT_GROUPS')
    groups = [g.strip() for g in fg.split(',') if g.strip()] if fg else None
    sel = None
    sf = os.environ.get('FEAT_SELECT')                 # compact core(core60/100) 이름리스트
    if sf and os.path.exists(sf):
        sel = [l.strip() for l in open(sf, encoding='utf-8') if l.strip() and not l.startswith('#')]
    X, _names = build_features(A, meta, groups=groups, select=sel)
    # 전처리(=bias_variance.main): 서브샘플 → 희소클래스(≥max(10,B)) 제거 → 인코딩
    if SUB > 0 and len(X) > SUB:
        idx, _ = train_test_split(np.arange(len(X)), train_size=SUB, random_state=RNG, stratify=ylab); X, ylab = X[idx], ylab[idx]
    s = pd.Series(ylab); vc = s.value_counts(); ok = s.isin(vc[vc >= max(10, B_MIN)].index).to_numpy()
    X = X[ok]; y = LabelEncoder().fit_transform(ylab[ok])
    print(f'[{NAME}] tune X={X.shape} classes={len(np.unique(y))}', flush=True)
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
