# -*- coding: utf-8 -*-
"""DoH 앱-귀속 개선 실험 (2x2): 문맥강화(1) x DoH전용 서브모델(2).
프로덕션 autolabel.py/pipeline.py는 수정하지 않고 import만 함.
LODO: 07/10~13 학습 -> 07/14 DoH 세션 평가. 정규화 일관 채점."""
import sys, os, gc, json, time
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import autolabel, pipeline

APPDIR = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
DS = '/nmlab/99_sgs/01_datasets'
TRAIN_DAYS = ['0710', '0711', '0712', '0713']
TEST_DAY = '0714'
N_JOBS = int(os.environ.get('N_JOBS', '6'))

# 문맥강화 피처 이름 (in-process 로 CAT/NUM 목록에 등록 — 파일은 안 건드림)
ENR_CAT = ['ctx_dom_bin60']
ENR_NUM = ['ctx_ndom_bin60', 'ctx_nsess_bin60']
autolabel.CAT_COLS = list(autolabel.CAT_COLS) + ENR_CAT   # encode_cats_fit 가 인식하도록

PARAMS = dict(objective='multiclass', metric='multi_error',
              n_estimators=500, learning_rate=0.05, num_leaves=63,
              min_child_samples=50, colsample_bytree=0.8, reg_lambda=15,
              min_sum_hessian_in_leaf=10, cat_smooth=100, cat_l2=50,
              max_cat_threshold=32, n_jobs=N_JOBS, verbosity=-1, random_state=42)
MIN_CLASS_N = getattr(autolabel, 'MIN_CLASS_N_DEFAULT', 30)


def log(m):
    print(m, flush=True)


def canon(v):
    s = '' if pd.isna(v) else str(v).strip()
    if '미분류' in s:
        return '__unk__'
    s = s.lower()
    if s.endswith('.exe'):
        s = s[:-4]
    return s.replace(' ', '_').replace('-', '_')


def norm_labels(raw_series):
    """task3 raw -> build_app_display_map 정규화 -> canon 공간."""
    dmap = pipeline.build_app_display_map(raw_series.astype(str).tolist())
    disp = raw_series.astype(str).map(dmap).fillna(raw_series.astype(str))
    return disp.map(canon)


def enrich_cols(df):
    """같은 호스트(task2) 60초 버킷 문맥. 관측 도메인만 사용(라벨 누출 없음)."""
    sni = df['tls_sni'].fillna('').astype(str).str.strip().str.lower()
    dns = df['dns_qry'].fillna('').astype(str).str.strip().str.lower()
    dom = sni.where(sni != '', dns).map(autolabel.base_domain)
    host = df['task2'].fillna('').astype(str)
    ts = pd.to_numeric(df['ts_first'], errors='coerce')
    binid = (ts // 60).fillna(-1).astype('int64')
    g = pd.DataFrame({'h': host.values, 'b': binid.values, 'd': dom.values},
                     index=df.index)
    ne = g[g['d'] != '']
    # 버킷별 최빈 도메인 (벡터화: (h,b,d) 카운트 -> 최대)
    vc = ne.groupby(['h', 'b', 'd']).size().reset_index(name='n')
    vc = vc.sort_values('n').drop_duplicates(['h', 'b'], keep='last')
    mode = vc.set_index(['h', 'b'])['d']
    ndom = ne.groupby(['h', 'b'])['d'].nunique()
    nsess = g.groupby(['h', 'b']).size()
    idx = pd.MultiIndex.from_arrays([g['h'].values, g['b'].values])
    out = pd.DataFrame(index=df.index)
    out['ctx_dom_bin60'] = mode.reindex(idx).fillna('').to_numpy()
    out['ctx_ndom_bin60'] = ndom.reindex(idx).fillna(0).to_numpy()
    out['ctx_nsess_bin60'] = nsess.reindex(idx).fillna(0).to_numpy()
    return out


def train_lgb(X, y, tag):
    y = np.asarray(y)
    vc = pd.Series(y).value_counts()
    keep = set(vc[vc >= MIN_CLASS_N].index)
    m = np.array([v in keep for v in y])
    X, y = X.iloc[m].copy(), y[m]
    vc2 = pd.Series(y).value_counts()   # 층화 위해 <2 제거
    keep2 = set(vc2[vc2 >= 2].index)
    m2 = np.array([v in keep2 for v in y])
    X, y = X.iloc[m2].copy(), y[m2]
    Xe, lv = autolabel.encode_cats_fit(X)
    itr, iva = train_test_split(np.arange(len(Xe)), test_size=0.1,
                                random_state=42, stratify=y)
    t0 = time.time()
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(Xe.iloc[itr], y[itr], eval_set=[(Xe.iloc[iva], y[iva])],
              eval_metric='multi_error',
              callbacks=[lgb.early_stopping(60, verbose=False)])
    log(f'   [{tag}] fit {time.time()-t0:.0f}s · rows={len(Xe):,} · '
        f'classes={len(model.classes_)} · best_it={model.best_iteration_}')
    return model, lv


def predict_top1(model, levels, X):
    Xe = autolabel.encode_cats_apply(X.copy(), levels)
    proba = model.predict_proba(Xe)
    top = np.argmax(proba, axis=1)
    cls = np.asarray(model.classes_)
    return pd.Series(cls[top], index=X.index), proba[np.arange(len(top)), top]


def acc(pred_norm, truth_norm, mask):
    """mask 영역에서 truth!=__unk__ 인 것만 채점."""
    t = truth_norm[mask]
    p = pred_norm[mask]
    ok = t != '__unk__'
    if ok.sum() == 0:
        return float('nan'), 0
    return float((p[ok].values == t[ok].values).mean()) * 100, int(ok.sum())


def main():
    log(f'=== DoH 실험 시작 · n_jobs={N_JOBS} · min_class_n={MIN_CLASS_N} ===')

    # ---- 로드 & 라벨/마스크 추출 후 raw 해제 ----
    def load(day):
        p = f'{DS}/2026.07.{day[2:]}/session_stat_lab{day}.csv'
        d = pd.read_csv(p, low_memory=False)
        return autolabel.normalize_df(d)

    log('[load] train...')
    tr_raw = pd.concat([load(d) for d in TRAIN_DAYS], ignore_index=True)
    log(f'   train rows={len(tr_raw):,}')
    te_raw = load(TEST_DAY)
    log(f'   test  rows={len(te_raw):,}')

    def doh_mask(d):
        return d['L7'].astype(str).str.contains('DoH_DoT', na=False).to_numpy()

    doh_tr = doh_mask(tr_raw)
    doh_te = doh_mask(te_raw)
    log(f'   DoH train={int(doh_tr.sum()):,} · DoH test={int(doh_te.sum()):,}')

    # 학습 라벨: unknown/미분류 제외 + 정규화(canon)
    y_tr_full = norm_labels(tr_raw['task3'])
    truth_te = norm_labels(te_raw['task3'])
    valid_tr = (y_tr_full != '__unk__').to_numpy()

    # ---- 피처 빌드 (base 는 1번만, enrich 도 1번만) ----
    log('[feat] base build (train)...')
    t0 = time.time()
    Xtr_b = autolabel.build_features(tr_raw)
    Xte_b = autolabel.build_features(te_raw)
    log(f'   base done {time.time()-t0:.0f}s')
    log('[feat] enrich build...')
    t0 = time.time()
    enr_tr = enrich_cols(tr_raw)
    enr_te = enrich_cols(te_raw)
    log(f'   enrich done {time.time()-t0:.0f}s')
    del tr_raw, te_raw
    gc.collect()

    Xtr_e = pd.concat([Xtr_b, enr_tr], axis=1)
    Xte_e = pd.concat([Xte_b, enr_te], axis=1)

    y_tr = y_tr_full.to_numpy()
    results = {}

    # baseline (no-train): DoH test 다수클래스
    tvc = truth_te[doh_te]
    tvc = tvc[tvc != '__unk__']
    maj = tvc.value_counts()
    results['majority_baseline'] = {
        'doh_acc': round(float(maj.iloc[0] / maj.sum()) * 100, 2),
        'majority_class': maj.index[0], 'doh_scored_n': int(maj.sum())}

    def run_global(X, Xte, tag):
        m, lv = train_lgb(X.iloc[valid_tr], y_tr[valid_tr], tag)
        pred, _ = predict_top1(m, lv, Xte)
        a_all, n_all = acc(pred, truth_te, np.ones(len(Xte), bool))
        a_doh, n_doh = acc(pred, truth_te, doh_te)
        del m
        gc.collect()
        return {'overall_acc': round(a_all, 2), 'overall_n': n_all,
                'doh_acc': round(a_doh, 2), 'doh_n': n_doh}

    def run_sub(X, Xte, tag):
        sel = valid_tr & doh_tr
        m, lv = train_lgb(X.iloc[sel], y_tr[sel], tag)
        pred, _ = predict_top1(m, lv, Xte.iloc[doh_te])
        # doh_te 영역만 채점
        pr = pd.Series('__na__', index=Xte.index)
        pr.iloc[np.flatnonzero(doh_te)] = pred.values
        a_doh, n_doh = acc(pr, truth_te, doh_te)
        del m
        gc.collect()
        return {'doh_acc': round(a_doh, 2), 'doh_n': n_doh}

    log('\n[run] (off/off) baseline global ...')
    results['1_base_offoff'] = run_global(Xtr_b, Xte_b, 'base')
    log('[run] (on/off) app1 = global + context ...')
    results['2_app1_context'] = run_global(Xtr_e, Xte_e, 'app1')
    log('[run] (off/on) app2 = DoH submodel ...')
    results['3_app2_submodel'] = run_sub(Xtr_b, Xte_b, 'app2')
    log('[run] (on/on) app1+2 = submodel + context ...')
    results['4_app1p2_both'] = run_sub(Xtr_e, Xte_e, 'app1+2')

    log('\n================ 결과 요약 (07/14 DoH 평가) ================')
    mb = results['majority_baseline']
    log(f"[참조] 다수클래스 베이스라인: {mb['doh_acc']}% "
        f"(항상 '{mb['majority_class']}' 예측, n={mb['doh_scored_n']:,})")
    log(f"{'config':<26}{'DoH정확도':>12}{'전체정확도':>12}")
    log('-' * 50)
    order = ['1_base_offoff', '2_app1_context', '3_app2_submodel', '4_app1p2_both']
    for k in order:
        r = results[k]
        oa = r.get('overall_acc', '—')
        log(f"{k:<26}{str(r['doh_acc'])+'%':>12}{(str(oa)+'%' if oa!='—' else '—'):>12}")

    with open(f'{APPDIR}/doh_exp_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log('\nSAVED doh_exp_results.json')
    log('DONE_DOH_EXP')


if __name__ == '__main__':
    main()
