# -*- coding: utf-8 -*-
"""정규화 강화 실험: codex/spotify 과적합 pocket 억제 효과 측정.
base(현행 파라미터) vs reg(강한 정규화)로 글로벌 모델 2개 학습,
07/14 DoH 세션에서 top-1 정확도 + 'codex/spotify 오분류' 조성 비교.
프로덕션 파일 수정 안 함."""
import sys, os, gc, json, time
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import numpy as np, pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import autolabel, pipeline

DS = '/nmlab/99_sgs/01_datasets'
APPDIR = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1'
TRAIN_DAYS = ['0710', '0711', '0712', '0713']
TEST_DAY = '0714'
N_JOBS = int(os.environ.get('N_JOBS', '6'))
MIN_CLASS_N = getattr(autolabel, 'MIN_CLASS_N_DEFAULT', 5)
NONSENSE = {'codex', 'spotify'}   # canon 공간

BASE_P = dict(objective='multiclass', metric='multi_error', n_estimators=500,
              learning_rate=0.05, num_leaves=63, min_child_samples=50,
              colsample_bytree=0.8, reg_lambda=15, min_sum_hessian_in_leaf=10,
              cat_smooth=100, cat_l2=50, max_cat_threshold=32,
              n_jobs=N_JOBS, verbosity=-1, random_state=42)
# 강한 정규화: 큰 리프 최소표본 + 적은 num_leaves + 강한 cat 정규화 = 얇은 소수클래스 pocket 억제
REG_P = dict(BASE_P, num_leaves=31, min_child_samples=400, reg_lambda=40,
             cat_l2=200, cat_smooth=300, max_cat_threshold=16,
             min_sum_hessian_in_leaf=20)


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


def norm_labels(raw):
    dmap = pipeline.build_app_display_map(raw.astype(str).tolist())
    disp = raw.astype(str).map(dmap).fillna(raw.astype(str))
    return disp.map(canon)


def train_lgb(X, y, params, tag):
    y = np.asarray(y)
    vc = pd.Series(y).value_counts()
    keep = set(vc[vc >= MIN_CLASS_N].index)
    m = np.array([v in keep for v in y]); X, y = X.iloc[m].copy(), y[m]
    vc2 = pd.Series(y).value_counts(); keep2 = set(vc2[vc2 >= 2].index)
    m2 = np.array([v in keep2 for v in y]); X, y = X.iloc[m2].copy(), y[m2]
    Xe, lv = autolabel.encode_cats_fit(X)
    itr, iva = train_test_split(np.arange(len(Xe)), test_size=0.1,
                                random_state=42, stratify=y)
    t0 = time.time()
    model = lgb.LGBMClassifier(**params)
    model.fit(Xe.iloc[itr], y[itr], eval_set=[(Xe.iloc[iva], y[iva])],
              eval_metric='multi_error',
              callbacks=[lgb.early_stopping(60, verbose=False)])
    log(f'   [{tag}] fit {time.time()-t0:.0f}s · rows={len(Xe):,} · '
        f'classes={len(model.classes_)} · best_it={model.best_iteration_}')
    return model, lv


def evaluate(model, lv, Xte, truth, doh_mask, tag):
    Xe = autolabel.encode_cats_apply(Xte.copy(), lv)
    proba = model.predict_proba(Xe)
    cls = np.asarray(model.classes_)
    pred = pd.Series(cls[np.argmax(proba, axis=1)], index=Xte.index)
    # 전체
    ok_all = truth != '__unk__'
    acc_all = float((pred[ok_all].values == truth[ok_all].values).mean()) * 100
    # DoH
    d = doh_mask & (truth != '__unk__').to_numpy()
    pt, tt = pred[d], truth[d]
    acc_doh = float((pt.values == tt.values).mean()) * 100
    wrong = pt.values != tt.values
    pw = pt.values[wrong]
    n_doh = int(d.sum()); n_wrong = int(wrong.sum())
    nonsense_pred = int(np.isin(pt.values, list(NONSENSE)).sum())
    nonsense_wrong = int(np.isin(pw, list(NONSENSE)).sum())
    plausible = {'svchost', 'google_chrome', 'microsoft_edge', 'system'}
    plausible_wrong = int(np.isin(pw, list(plausible)).sum())
    from collections import Counter
    wrong_top = Counter(pw).most_common(8)
    log(f'   [{tag}] DoH acc={acc_doh:.2f}% · overall={acc_all:.2f}% · '
        f'codex/spotify로 예측={nonsense_pred:,}(그중오답 {nonsense_wrong:,}) · '
        f'오답중 다수클래스={plausible_wrong:,}/{n_wrong:,}')
    return {'tag': tag, 'doh_acc': round(acc_doh, 2), 'overall_acc': round(acc_all, 2),
            'doh_n': n_doh, 'doh_wrong': n_wrong,
            'pred_as_codex_spotify': nonsense_pred,
            'pred_as_codex_spotify_wrong': nonsense_wrong,
            'wrong_into_majority': plausible_wrong,
            'wrong_pred_top': [[k, int(v)] for k, v in wrong_top]}


def main():
    log(f'=== 정규화 실험 · n_jobs={N_JOBS} ===')

    def load(day):
        p = f'{DS}/2026.07.{day[2:]}/session_stat_lab{day}.csv'
        return autolabel.normalize_df(pd.read_csv(p, low_memory=False))

    log('[load] ...')
    tr = pd.concat([load(d) for d in TRAIN_DAYS], ignore_index=True)
    te = load(TEST_DAY)
    doh_te = te['L7'].astype(str).str.contains('DoH_DoT', na=False).to_numpy()
    log(f'   train={len(tr):,} test={len(te):,} DoH_test={int(doh_te.sum()):,}')
    y_tr = norm_labels(tr['task3'])
    truth_te = norm_labels(te['task3'])
    valid = (y_tr != '__unk__').to_numpy()
    log('[feat] build...')
    t0 = time.time()
    Xtr = autolabel.build_features(tr)
    Xte = autolabel.build_features(te)
    log(f'   feat {time.time()-t0:.0f}s')
    del tr, te; gc.collect()
    yv = y_tr.to_numpy()

    results = {}
    for tag, params in [('base', BASE_P), ('reg', REG_P)]:
        log(f'[run] {tag} 학습...')
        m, lv = train_lgb(Xtr.iloc[valid], yv[valid], params, tag)
        results[tag] = evaluate(m, lv, Xte, truth_te, doh_te, tag)
        results[tag]['params'] = {k: params[k] for k in
                                  ('num_leaves', 'min_child_samples', 'reg_lambda',
                                   'cat_l2', 'cat_smooth', 'max_cat_threshold')}
        del m; gc.collect()

    log('\n============ 정규화 실험 결과 (07/14 DoH) ============')
    log(f"{'config':<8}{'DoH정확도':>10}{'전체':>9}{'codex/spotify오분류':>20}{'오답→다수클래스':>16}")
    for tag in ('base', 'reg'):
        r = results[tag]
        log(f"{tag:<8}{str(r['doh_acc'])+'%':>10}{str(r['overall_acc'])+'%':>9}"
            f"{r['pred_as_codex_spotify_wrong']:>18,}{r['wrong_into_majority']:>16,}")
    with open(f'{APPDIR}/reg_doh_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log('\nSAVED reg_doh_results.json')
    log('DONE_REG_EXP')


if __name__ == '__main__':
    main()
