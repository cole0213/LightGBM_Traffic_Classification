# -*- coding: utf-8 -*-
"""LightGBM IT_s 원인이 max_depth(leaf-wise 깊이)인지 격리 실험.
동일 데이터/params에서 max_depth만 바꿔 predict 시간 비교. XGBoost depth6는 참고선.
사용: DOMAIN_ONLY=1 python probe_lgbm_it.py CipherSpectrum <cipher_seq_dir> dummy.json
(3번째 인자 dummy는 tune_boosting import 요건 충족용, 안 씀)
"""
import os, sys, time
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
import lightgbm as lgb
from tune_boosting import load_xy  # NAME/SEQDIR/IS_LAB/SUB/DOMAIN_ONLY는 argv/env에서 상속

NJ = int(os.environ.get('N_JOBS', '4'))  # 튜닝 병행 중이니 작게

X, y = load_xy()
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, random_state=42, stratify=y)
print(f'rows={len(X)} classes={len(np.unique(y))} train={len(Xtr)} test={len(Xte)} NJ={NJ}', flush=True)


def lgbm_run(md, label):
    m = lgb.LGBMClassifier(objective='multiclass', n_estimators=300, num_leaves=63, max_depth=md,
                           learning_rate=.05, min_child_samples=30, colsample_bytree=.8, reg_lambda=10,
                           n_jobs=NJ, verbosity=-1, random_state=0)
    t = time.time(); m.fit(Xtr, ytr); ft = time.time() - t
    # predict 3회 평균(측정 안정화)
    its = []
    for _ in range(3):
        t = time.time(); p = m.predict(Xte); its.append(time.time() - t)
    f1 = f1_score(yte, p, average='macro', zero_division=0)
    # 실제 트리 최대깊이(leaf-wise가 얼마나 깊어졌나)
    dump = m.booster_.dump_model()
    def tree_depth(node, d=0):
        if 'leaf_index' in node: return d
        return max(tree_depth(node['left_child'], d + 1), tree_depth(node['right_child'], d + 1))
    depths = [tree_depth(t['tree_structure']) for t in dump['tree_info']]
    print(f'[LGBM {label:22s}] max_depth={md:>3} fit={ft:6.1f}s predict_IT={np.mean(its):6.2f}s '
          f'(min{min(its):.2f}) F1={f1*100:5.2f} 실제트리깊이 mean={np.mean(depths):.1f} max={max(depths)}', flush=True)


def xgb_run():
    try:
        import xgboost as xgb
    except Exception as e:
        print('xgboost 없음:', e, flush=True); return
    m = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=.05, reg_lambda=10, colsample_bytree=.8,
                          n_jobs=NJ, tree_method='hist', verbosity=0, random_state=0)
    t = time.time(); m.fit(Xtr, ytr); ft = time.time() - t
    its = []
    for _ in range(3):
        t = time.time(); p = m.predict(Xte); its.append(time.time() - t)
    f1 = f1_score(yte, p, average='macro', zero_division=0)
    print(f'[XGB  depth6(참고선)      ] max_depth=  6 fit={ft:6.1f}s predict_IT={np.mean(its):6.2f}s '
          f'(min{min(its):.2f}) F1={f1*100:5.2f}', flush=True)


lgbm_run(-1, 'unlimited(leaf-wise)')
lgbm_run(6, 'depth6')
xgb_run()
print('>>> probe 완료', flush=True)
