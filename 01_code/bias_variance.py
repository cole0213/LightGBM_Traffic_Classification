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

NAME = sys.argv[1]; SEQDIR = Path(sys.argv[2]); OUT = Path(sys.argv[3]); IS_LAB = '--lab' in sys.argv
SUB = int(os.environ.get('BV_SUB', '0'))   # 0 = 서브샘플 없이 전량 사용
B = int(os.environ.get('BV_B', '20'))
NJ = int(os.environ.get('N_JOBS', '8'))
ONLY = set(filter(None, os.environ.get('ONLY', '').split(',')))  # 예: ONLY=CatBoost(Boost) → 해당 모델만 계산, 나머지 기존 json 유지
TUNED = json.load(open(os.environ['TUNED_PARAMS'], encoding='utf-8')) if os.environ.get('TUNED_PARAMS') else {}  # Optuna 튜닝값(부스팅만)
def _tuned(mkey): return dict(TUNED.get(NAME, {}).get(mkey, {}).get('params', {}))  # 없으면 {} → 통일 기본값 유지
RNG = np.random.RandomState(42)

# ---------- seq789 피처 로드 ----------
def load_seq789():
    metas, packs = [], []
    for cf in sorted(SEQDIR.glob('sequences_part_*.csv')):
        z = np.load(cf.with_suffix('.npz')); metas.append(pd.read_csv(cf)); packs.append({k: z[k] for k in z.files})
    meta = pd.concat(metas, ignore_index=True)
    A = {k: np.concatenate([p[k] for p in packs], 0) for k in packs[0].keys()}
    N = len(meta)
    if IS_LAB:  # canonical: filename→task3 라벨 조인 + 중복제거 + 클래스≥10
        kmpath = os.environ.get('LAB_LABEL_MAP', str(SEQDIR.resolve().parent / '02_dataset' / 'lab_canon_label.csv'))
        km = pd.read_csv(kmpath); fn2t = dict(zip(km['filename'].astype(str), km['task3'].astype(str)))
        bn = meta['pcap'].astype(str).str.split('/').str[-1].str.split('\\').str[-1]
        lab = bn.map(fn2t)
        tmp = pd.DataFrame({'bn': bn, 'lab': lab, 'i': np.arange(N)})[lab.notna().to_numpy()].drop_duplicates('bn', keep='first')
        labc = tmp['lab'].astype(str).str.lower().str.replace(r'\.exe$', '', regex=True)
        def _loadset(envf, envc):  # 파일(한 줄 1라벨) + 콤마 env 합쳐 소문자 set
            s = set()
            f = os.environ.get(envf)
            if f and os.path.exists(f): s |= {l.strip().lower() for l in open(f, encoding='utf-8') if l.strip() and not l.startswith('#')}
            s |= {l.strip().lower() for l in os.environ.get(envc, '').split(',') if l.strip()}
            return s
        exc = _loadset('LAB_EXCLUDE_FILE', 'LAB_EXCLUDE')      # 완전 제거(측정도구·unknown 등)
        col = _loadset('LAB_COLLAPSE_FILE', 'LAB_COLLAPSE')    # background 1클래스로 묶기(슈퍼클래스 실험)
        if col:
            nb = int(labc.isin(col).sum()); labc = labc.mask(labc.isin(col), '__background__')
            print(f'[LAB] background 묶음 {len(col)}라벨 → {nb}행 = __background__', flush=True)
        # 파이프라인 노이즈(prism04 조인) basename 제거 — LAB_NOISE_FILE(한 줄 1 basename)
        nf = set()
        nff = os.environ.get('LAB_NOISE_FILE')
        if nff and os.path.exists(nff): nf = {l.strip() for l in open(nff, encoding='utf-8') if l.strip()}
        not_noise = ~tmp['bn'].isin(nf) if nf else pd.Series(True, index=tmp.index)
        # class≥10은 노이즈/제외 적용 '후' 잔존 개수로 계산해야 함(전 개수로 하면 노이즈 빼고 1개 남는 클래스가 stratify 크래시)
        surv = (~labc.isin(exc)).to_numpy() & not_noise.to_numpy()
        vc = labc[surv].value_counts(); keep = (surv & labc.isin(vc[vc >= 10].index).to_numpy())
        if exc: print(f'[LAB] 라벨노이즈 제외 {len(exc)}라벨 → 제거 {int((labc.isin(exc)).sum())}행', flush=True)
        if nf: print(f'[LAB] 파이프라인노이즈 {len(nf)}basename → 매칭제거 {int(tmp["bn"].isin(nf).sum())}행', flush=True)
        idx = tmp['i'].to_numpy()[keep]
        meta = meta.iloc[idx].reset_index(drop=True); A = {k: v[idx] for k, v in A.items()}; N = len(meta)
        meta['label'] = labc.to_numpy()[keep]
    if not IS_LAB:  # 비-LAB(CSTNET/Cipher): NOISE_FILE(basename) 파이프라인 노이즈 제거
        nff = os.environ.get('NOISE_FILE')
        if nff and os.path.exists(nff):
            nfset = {l.strip() for l in open(nff, encoding='utf-8') if l.strip()}
            bn = meta['pcap'].astype(str).str.split('/').str[-1].str.split('\\').str[-1]
            km = ~bn.isin(nfset)
            print(f'[{NAME}] 파이프라인노이즈 {len(nfset)}basename → 제거 {int((~km).sum())}행 / {len(meta)}', flush=True)
            meta = meta[km.to_numpy()].reset_index(drop=True); A = {k: v[km.to_numpy()] for k, v in A.items()}; N = len(meta)
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
    if os.environ.get('DOMAIN_ONLY') == '1':  # CipherSpectrum: none_<cipher>_<domain> → <domain> (cipher 합침)
        lab = lab.str.split('_', n=2).str[-1]
    return X, lab.to_numpy()   # 문자열 라벨 반환 (unknown 필터는 main에서)

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
