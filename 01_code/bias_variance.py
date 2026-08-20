# -*- coding: utf-8 -*-
"""IME654 04 앙상블 러닝 — Bias-Variance 분해 실험.
세 데이터셋(CSTNET/CipherSpectrum/LAB)에 앙상블 계열 모델을 부트스트랩 반복학습하여
0-1 loss의 bias/variance 를 실측 분해한다. (Kohavi-Wolpert / Domingos)

  main 예측 = 부트스트랩 B개 예측의 최빈값
  bias(포인트) = 1 if main != 정답 else 0
  variance(포인트) = (B개 예측 중 main과 다른 비율)
  error ≈ bias + variance

피처 = seq789 (전부 수치 → 모든 모델 공정 비교, 범주형 인코딩 이슈 없음).
사용: python bias_variance.py <name> <seq_dir> <out_json> [--lab]
환경변수: BV_SUB(서브샘플 크기, 기본 0=전량), BV_B(부트스트랩 수, 기본 20), N_JOBS(기본 8), DOMAIN_ONLY(1=cipher 합쳐 도메인)
"""
import sys, os, json, time, resource
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
import lightgbm as lgb
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdata  # seq 로드 + 라벨링(모듈화, 하니스와 공유)
from features import build_features  # seq789 피처 조립(모듈화). 기본 전체그룹=기존과 bit-exact.

NAME = sys.argv[1]; SEQDIR = Path(sys.argv[2]); OUT = Path(sys.argv[3]); IS_LAB = '--lab' in sys.argv
SUB = int(os.environ.get('BV_SUB', '0'))   # 0 = 서브샘플 없이 전량 사용
B = int(os.environ.get('BV_B', '20'))
NJ = int(os.environ.get('N_JOBS', '8'))
ONLY = set(filter(None, os.environ.get('ONLY', '').split(',')))  # 예: ONLY=CatBoost(Boost) → 해당 모델만 계산, 나머지 기존 json 유지
TUNED = json.load(open(os.environ['TUNED_PARAMS'], encoding='utf-8')) if os.environ.get('TUNED_PARAMS') else {}  # Optuna 튜닝값(부스팅만)
def _tuned(mkey): return dict(TUNED.get(NAME, {}).get(mkey, {}).get('params', {}))  # 없으면 {} → 통일 기본값 유지
RNG = np.random.RandomState(42)

# ---------- seq789 피처 로드 (로드/라벨=seqdata, 피처조립=features 로 분리) ----------
def _envset(envf, envc):  # 파일(한 줄 1라벨, # 주석 무시) + 콤마 env 합쳐 소문자 set
    s = set()
    f = os.environ.get(envf)
    if f and os.path.exists(f): s |= {l.strip().lower() for l in open(f, encoding='utf-8') if l.strip() and not l.startswith('#')}
    s |= {l.strip().lower() for l in os.environ.get(envc, '').split(',') if l.strip()}
    return s

def load_seq789():
    A, meta, y = seqdata.load_labeled(
        SEQDIR, IS_LAB,
        domain_only=(os.environ.get('DOMAIN_ONLY') == '1'),
        label_map=os.environ.get('LAB_LABEL_MAP'),
        lab_noise_file=os.environ.get('LAB_NOISE_FILE'),
        keep=_envset('LAB_KEEP_FILE', 'LAB_KEEP'),
        exclude=_envset('LAB_EXCLUDE_FILE', 'LAB_EXCLUDE'),
        collapse=_envset('LAB_COLLAPSE_FILE', 'LAB_COLLAPSE'),
        noise_file=os.environ.get('NOISE_FILE'),
        label_exclude=_envset('DOMAIN_EXCLUDE_FILE', 'DOMAIN_EXCLUDE'))  # 최종라벨 제외(Cipher chacha20 오염 등)
    # FEAT_TRUNC=K → 앞 K패킷만 사용(정본 seq-core는 K30). per-packet 배열 슬라이스.
    ft = int(os.environ.get('FEAT_TRUNC', '0') or 0)
    if ft:
        A = {k: v[:, :ft] for k, v in A.items()}
    # FEAT_GROUPS(콤마구분)로 그룹 선택(예: flow,chan,cum,hist,quant=289 base). 없으면 전체 6그룹.
    fg = os.environ.get('FEAT_GROUPS')
    groups = [g.strip() for g in fg.split(',') if g.strip()] if fg else None
    # FEAT_SELECT=파일 → 그 이름리스트 컬럼만(compact core: core60/core100). 그룹은 base 전체 조립 후 필터.
    sel = None
    sf = os.environ.get('FEAT_SELECT')
    if sf and os.path.exists(sf):
        sel = [l.strip() for l in open(sf, encoding='utf-8') if l.strip() and not l.startswith('#')]
        if groups is None: groups = ['flow', 'chan', 'cum', 'hist', 'quant']  # 289 base(burst 제외)에서 골라냄
    X, names = build_features(A, meta, groups=groups, select=sel)
    if sel: print(f'[{NAME}] FEAT_SELECT {len(sel)}개 요청 → 실제 {X.shape[1]}개 피처', flush=True)
    return X, y   # 문자열 라벨 반환 (unknown 필터는 main에서)

def models():
    # 부스팅 3종은 통일 기본값 위에 TUNED(있으면) 덮어씀. 트리계(DT/RF/ET)는 항상 통일값.
    lgbm = dict(objective='multiclass', n_estimators=300, num_leaves=63, max_depth=6, learning_rate=.05, min_child_samples=30, colsample_bytree=.8, reg_lambda=10, n_jobs=NJ, verbosity=-1, random_state=0)
    lgbm.update(_tuned('LightGBM(Boost)'))
    return {
        'DecisionTree(단일)':  DecisionTreeClassifier(max_depth=None, random_state=0),
        'RandomForest(Bag)':   RandomForestClassifier(n_estimators=100, n_jobs=NJ, random_state=0),
        'ExtraTrees(Bag)':     ExtraTreesClassifier(n_estimators=100, n_jobs=NJ, random_state=0),
        'LightGBM(Boost)':     lgb.LGBMClassifier(**lgbm),
    }

def try_add(md):
    try:
        import xgboost as xgb
        xgbp = dict(n_estimators=300, max_depth=6, learning_rate=.05, reg_lambda=10, colsample_bytree=.8, n_jobs=NJ, tree_method='hist', verbosity=0, random_state=0)
        if os.environ.get('XGB_GPU') == '1': xgbp['device'] = 'cuda'  # GPU 가속(hist, CPU와 결과 거의 동일)
        xgbp.update(_tuned('XGBoost(Boost)')); md['XGBoost(Boost)'] = xgb.XGBClassifier(**xgbp)
    except Exception as e: print('xgboost 없음:', e, flush=True)
    try:
        from catboost import CatBoostClassifier
        catp = dict(iterations=300, depth=6, learning_rate=.05, l2_leaf_reg=10, rsm=.8, loss_function='MultiClass', thread_count=NJ, verbose=0, random_seed=0, allow_writing_files=False)
        catp.update(_tuned('CatBoost(Boost)')); md['CatBoost(Boost)'] = CatBoostClassifier(**catp)
    except Exception as e: print('catboost 없음:', e, flush=True)
    return md

def rss_mb(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)  # Linux: KB→MB

def bias_variance(model, Xtr, ytr, Xte, yte, boots, ncls):
    B = len(boots); n = len(Xte); P = np.empty((B, n), dtype=np.int32); ft = it = 0.0
    for b, bi in enumerate(boots):  # 모든 모델이 동일 부트스트랩 셋 사용 (공정 비교)
        t = time.time(); model.fit(Xtr[bi], ytr[bi]); ft += time.time() - t
        t = time.time(); pred = np.asarray(model.predict(Xte)).ravel(); it += time.time() - t  # ravel: CatBoost (n,1)→(n,)
        P[b] = pred.astype(np.int32)
    # main 예측 = 최빈값 (벡터화: 클래스별 카운트 argmax)
    cnt = np.zeros((n, ncls), dtype=np.int32)
    for b in range(B): cnt[np.arange(n), P[b]] += 1
    main = cnt.argmax(1).astype(np.int32)
    bias = float(np.mean(main != yte)); variance = float(np.mean(P != main[None, :])); error = float(np.mean(P != yte[None, :]))
    acc = float((main == yte).mean()); f1 = float(f1_score(yte, main, average='macro', zero_division=0))
    return dict(AC=round(acc * 100, 2), F1=round(f1 * 100, 2), bias=round(bias * 100, 2), variance=round(variance * 100, 2), error=round(error * 100, 2),
                fit_s=round(ft, 1), IT_s=round(it, 2), mem_MB=rss_mb())

def main():
    t0 = time.time(); X, ylab = load_seq789()
    print(f'[{NAME}] loaded rows={len(X)} feat={X.shape[1]}', flush=True)
    # unknown/DoH 제외 (DoH는 LAB canonical 키맵에서 이미 빠짐; 여기선 unknown 라벨 제거)
    UNK = {'', 'nan', 'none', 'unknown', 'unk', '__unk__'}
    okm = ~pd.Series(ylab).astype(str).str.strip().str.lower().isin(UNK).to_numpy()
    X, ylab = X[okm], ylab[okm]
    # (선택) 서브샘플 — BV_SUB>0 일 때만. 기본 0 = 전량
    if SUB > 0 and len(X) > SUB:
        idx, _ = train_test_split(np.arange(len(X)), train_size=SUB, random_state=42, stratify=ylab); X, ylab = X[idx], ylab[idx]
    # 희소 클래스(부트스트랩 안정성 위해 표본<max(10,B) 제거) 후 인코딩
    s = pd.Series(ylab); vc = s.value_counts(); ok = s.isin(vc[vc >= max(10, B)].index).to_numpy()
    X = X[ok]; y = LabelEncoder().fit_transform(ylab[ok]); ncls = int(len(np.unique(y)))
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, random_state=42, stratify=y)
    print(f'[{NAME}] BV용 rows={len(X)} classes={ncls} train={len(Xtr)} test={len(Xte)} B={B}', flush=True)
    boots = [RNG.randint(0, len(Xtr), len(Xtr)) for _ in range(B)]  # 부트스트랩 셋 1회 생성 → 전 모델 공유
    res = json.load(open(OUT, encoding='utf-8')) if OUT.exists() else {}
    prev = res.get(NAME, {}).get('models', {})  # 기존 모델 결과 보존 (ONLY 재실행 시 merge)
    r = {'rows_bv': int(len(X)), 'classes': ncls, 'B': B, 'feat': int(X.shape[1]), 'models': dict(prev)}
    mp = try_add(models())
    if ONLY: mp = {k: v for k, v in mp.items() if k in ONLY}  # 지정 모델만 계산
    for name, mdl in mp.items():
        try:
            bv = bias_variance(mdl, Xtr, ytr, Xte, yte, boots, ncls); r['models'][name] = bv
            print(f'  {name:22s} AC={bv["AC"]:5.2f} F1={bv["F1"]:5.2f} bias={bv["bias"]:5.2f} var={bv["variance"]:5.2f} err={bv["error"]:5.2f} IT={bv["IT_s"]:5.2f}s mem={bv["mem_MB"]}MB ({time.time()-t0:.0f}s)', flush=True)
        except Exception as e:
            print(f'  {name} 실패: {e}', flush=True)
        res[NAME] = r; json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    r['sec'] = round(time.time() - t0, 1); res[NAME] = r; json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'>>> {NAME} 완료 ({r["sec"]}s)', flush=True)

if __name__ == '__main__': main()
