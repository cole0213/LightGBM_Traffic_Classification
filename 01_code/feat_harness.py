# -*- coding: utf-8 -*-
"""피처 실험 harness — expand/compress용 빠르고 공정한 측정자(尺).

측정: 3데이터셋 각각 고정seed 80/20 stratified split + 튜닝 LightGBM 1개 + macro-F1.
      full BV(B=15) 안 돌리고 단일 split 로 피처셋 하나를 몇 분에 평가. 3데이터셋 일관성이 노이즈 가드.
      데이터는 데이터셋당 1회 로드+서브샘플 후 메모리 캐시 → 그 위에서 그룹 조합만 바꿔 재조립(빠름).

모드:
  importance : full 789 LightGBM 학습 → feature importance(gain) 랭킹 + 그룹별 합계. → 03_json/feat_importance.json
  ablation   : 그룹 조합별 macro-F1 표(full / leave-one-out / solo / stats-only / seq-only). → 03_json/feat_ablation.json
  eval       : --groups 로 임의 그룹조합 하나 평가(콤마구분).

사용: python feat_harness.py <mode> [--groups g1,g2,...] [--datasets Cipher,CSTNET,LAB]
환경변수: N_JOBS(기본 11), HARNESS_LAB_SUB(LAB 서브샘플, 기본 200000), TUNED_PARAMS(기본 03_json/boosting_best_params.json)
작성일 2026-08-18
"""
import sys, os, json, time, argparse
from pathlib import Path
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, accuracy_score
import lightgbm as lgb
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdata
from features import build_features, DEFAULT_ORDER

BASE = Path(__file__).resolve().parent.parent
NJ = int(os.environ.get('N_JOBS', '11'))
LAB_SUB = int(os.environ.get('HARNESS_LAB_SUB', '200000'))
TUNED_PATH = os.environ.get('TUNED_PARAMS', str(BASE / '03_json' / 'boosting_best_params.json'))
RNG_SEED = 42

# 데이터셋 레지스트리 — display이름: 로드 파라미터 + tuned json 키
DATASETS = {
    'Cipher': dict(json_key='CipherSpectrum', seqdir='06_data/canonical_cipherspec_seq_v2',
                   is_lab=False, domain_only=True, sub=0, label_exclude=['chacha20']),  # chacha20=암호명 오염라벨 제외 → 41도메인
    'CSTNET': dict(json_key='CSTNET', seqdir='06_data/canonical_cstnet_seq',
                   is_lab=False, domain_only=False, sub=0),
    'LAB':    dict(json_key='LAB', seqdir='06_data/lab_full45_seq_v2_904k',
                   is_lab=True, domain_only=False, sub=LAB_SUB,
                   label_map='02_dataset/lab_canon_label.csv',
                   lab_noise_file='02_dataset/lab_seqmeta_noise_basenames.txt',
                   label_exclude=['unknown']),  # unknown=라벨 못붙인 flow 제외(측정도구는 유지=옵션A)
}

_TUNED = json.load(open(TUNED_PATH, encoding='utf-8')) if os.path.exists(TUNED_PATH) else {}


def lgbm_params(json_key):
    """튜닝 LightGBM params(고정 尺). 없으면 통일 기본값."""
    p = dict(objective='multiclass', n_estimators=300, num_leaves=63, max_depth=6, learning_rate=.05,
             min_child_samples=30, colsample_bytree=.8, reg_lambda=10, n_jobs=NJ, verbosity=-1, random_state=0)
    p.update(_TUNED.get(json_key, {}).get('LightGBM(Boost)', {}).get('params', {}))
    p['n_jobs'] = NJ
    return p


_CACHE = {}  # ds이름 → (A_sub, meta_sub, y_sub) 캐시 (1회 로드+서브샘플)

def get_data(ds):
    """데이터셋 로드+서브샘플(1회) 후 캐시. 이후 그룹조합만 바꿔 build_features 재사용."""
    if ds in _CACHE:
        return _CACHE[ds]
    c = DATASETS[ds]
    kw = dict(domain_only=c['domain_only'])
    if c.get('label_exclude'):
        kw['label_exclude'] = c['label_exclude']
    if c['is_lab']:
        kw.update(label_map=str(BASE / c['label_map']), lab_noise_file=str(BASE / c['lab_noise_file']))
    t = time.time()
    A, meta, y = seqdata.load_labeled(str(BASE / c['seqdir']), c['is_lab'], **kw)
    # 서브샘플(라벨 stratify, 고정seed) — 그룹조합 간 동일 행 보장 위해 여기서 1회
    if c['sub'] and len(y) > c['sub']:
        idx = np.arange(len(y))
        keep, _ = train_test_split(idx, train_size=c['sub'], stratify=y, random_state=RNG_SEED)
        A = {k: v[keep] for k, v in A.items()}; meta = meta.iloc[keep].reset_index(drop=True); y = y[keep]
    print(f'[{ds}] 로드 rows={len(y)} classes={len(set(y))} ({time.time()-t:.0f}s)', flush=True)
    _CACHE[ds] = (A, meta, y)
    return _CACHE[ds]


def eval_groups(ds, groups):
    """ds에서 groups 피처조합으로 단일 split macro-F1/acc. groups=None → 전체 789."""
    A, meta, y = get_data(ds)
    X, names = build_features(A, meta, groups=groups)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=RNG_SEED)
    t = time.time()
    clf = lgb.LGBMClassifier(**lgbm_params(DATASETS[ds]['json_key']))
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    f1 = f1_score(yte, pred, average='macro', zero_division=0) * 100
    acc = accuracy_score(yte, pred) * 100
    print(f'  [{ds}] groups={groups or "ALL"} d={X.shape[1]} F1={f1:.2f} Acc={acc:.2f} ({time.time()-t:.0f}s)', flush=True)
    return dict(f1=round(f1, 3), acc=round(acc, 3), dim=int(X.shape[1]))


def run_importance(datasets):
    out = {}
    for ds in datasets:
        A, meta, y = get_data(ds)
        X, names = build_features(A, meta, groups=None)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=RNG_SEED)
        clf = lgb.LGBMClassifier(**lgbm_params(DATASETS[ds]['json_key']), importance_type='gain')
        clf.fit(Xtr, ytr)
        imp = clf.feature_importances_.astype(float)
        imp = imp / (imp.sum() + 1e-12)  # 정규화(합=1)
        order = np.argsort(-imp)
        # 그룹별 합계
        grp = {}
        for nm, v in zip(names, imp):
            g = nm.split('_')[0]
            grp[g] = grp.get(g, 0.0) + float(v)
        top = [(names[i], round(float(imp[i]), 5)) for i in order[:50]]
        out[ds] = dict(top50=top, group_sum={k: round(v, 4) for k, v in sorted(grp.items(), key=lambda x: -x[1])})
        print(f'[{ds}] 그룹 importance합: ' + ', '.join(f'{k}={v:.3f}' for k, v in out[ds]['group_sum'].items()), flush=True)
        print(f'  top10: ' + ', '.join(nm for nm, _ in top[:10]), flush=True)
    json.dump(out, open(BASE / '03_json' / 'feat_importance.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('저장 -> 03_json/feat_importance.json', flush=True)


def run_ablation(datasets):
    G = DEFAULT_ORDER  # flow chan cum burst hist quant
    specs = {'ALL': None}
    for g in G: specs[f'-{g}'] = [x for x in G if x != g]      # leave-one-out
    for g in G: specs[f'only_{g}'] = [g]                        # solo
    specs['stats_only'] = ['flow', 'burst', 'hist', 'quant']   # 시퀀스펼침(chan,cum) 뺀 통계요약
    specs['seq_only'] = ['chan', 'cum']                        # 시퀀스펼침만
    out = {}
    for ds in datasets:
        out[ds] = {}
        for name, grp in specs.items():
            try:
                out[ds][name] = eval_groups(ds, grp)
            except Exception as e:
                print(f'  [{ds}] {name} 실패: {e}', flush=True)
                out[ds][name] = dict(error=str(e))
            json.dump(out, open(BASE / '03_json' / 'feat_ablation.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('저장 -> 03_json/feat_ablation.json', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['importance', 'ablation', 'eval'])
    ap.add_argument('--groups', default=None, help='eval모드: 콤마구분 그룹(예 flow,quant)')
    ap.add_argument('--datasets', default='Cipher,CSTNET,LAB')
    a = ap.parse_args()
    datasets = [d.strip() for d in a.datasets.split(',') if d.strip()]
    if a.mode == 'importance':
        run_importance(datasets)
    elif a.mode == 'ablation':
        run_ablation(datasets)
    elif a.mode == 'eval':
        grp = [g.strip() for g in a.groups.split(',')] if a.groups else None
        for ds in datasets: eval_groups(ds, grp)


if __name__ == '__main__':
    main()
