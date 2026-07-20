import sys, collections, time
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import numpy as np, pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import autolabel as AL

TRAIN_DAYS = ['0710','0711','0712','0713']
TEST_DAY = '0714'
SUBSAMPLE = 700_000
THRESH = 0.3
SM = 30  # 순도 스무딩(도메인 표본 적을 때 0.5로 수렴)

def canon(v):
    s = "" if pd.isna(v) else str(v); s=s.strip()
    if '미분류' in s: return "__unk__"
    s=s.lower()
    if s.endswith('.exe'): s=s[:-4]
    return s.replace(' ','_').replace('-','_')

def load(days):
    dfs=[]
    for d in days:
        f=f'/nmlab/99_sgs/01_datasets/2026.07.{d[2:]}/session_stat_lab{d}.csv'
        dfs.append(pd.read_csv(f, low_memory=False))
    return pd.concat(dfs, ignore_index=True)

print("load train...", flush=True)
tr = load(TRAIN_DAYS)
tr = AL.normalize_df(tr)
# 라벨 정규화(학습과 동일)
dmap = AL.__dict__.get('build_app_display_map') or __import__('pipeline').build_app_display_map
import pipeline
lab = pipeline.build_app_display_map(tr['task3'].astype(str).tolist())
tr['task3'] = tr['task3'].astype(str).map(lab).fillna(tr['task3'])
# unknown 제외
m = ~(tr['task3'].astype(str).str.contains('미분류', na=False) | (tr['task3'].astype(str)=='unknown') | (tr['task3'].astype(str)==''))
tr = tr[m]
if len(tr) > SUBSAMPLE:
    tr = tr.sample(n=SUBSAMPLE, random_state=42).reset_index(drop=True)
print(f"train rows={len(tr):,}", flush=True)

# 희소 클래스 제외(학습과 동일 기준)
vc = tr['task3'].value_counts()
keep = vc[vc >= AL.MIN_CLASS_N_DEFAULT].index
tr = tr[tr['task3'].isin(keep)].copy()
vc2 = tr['task3'].value_counts()
tr = tr[tr['task3'].isin(vc2[vc2>=2].index)].copy()
print(f"train after class filter={len(tr):,}, classes={tr['task3'].nunique()}", flush=True)

# ---- 도메인 prior(순도) 테이블: train에서 sni_base/dns_base -> 최빈앱 순도 ----
def purity_table(df, col):
    base = df[col].astype(str).str.strip().str.lower().map(AL.base_domain)
    tbl={}
    g = pd.DataFrame({'d':base,'y':df['task3'].values})
    g = g[g['d']!='']
    for dom, sub in g.groupby('d'):
        c = sub['y'].value_counts()
        top = c.iloc[0]; tot = c.sum()
        tbl[dom] = (top + SM*0.5) / (tot + SM)   # 스무딩된 순도
    return tbl
sni_tbl = purity_table(tr, 'tls_sni')
dns_tbl = purity_table(tr, 'dns_qry')
print(f"prior tables: sni={len(sni_tbl):,} dns={len(dns_tbl):,}", flush=True)

def add_prior(X, df):
    sb = df['tls_sni'].astype(str).str.strip().str.lower().map(AL.base_domain)
    db = df['dns_qry'].astype(str).str.strip().str.lower().map(AL.base_domain)
    X = X.copy()
    X['sni_prior'] = sb.map(sni_tbl).fillna(0.0).astype(float).values
    X['dns_prior'] = db.map(dns_tbl).fillna(0.0).astype(float).values
    return X

def train(Xtr, y, extra):
    cols = list(Xtr.columns)
    Xc, levels = AL.encode_cats_fit(Xtr.copy())
    idx_tr, idx_va = train_test_split(np.arange(len(Xc)), test_size=0.1, random_state=42, stratify=y)
    params = dict(objective="multiclass", metric="multi_error", n_estimators=500, learning_rate=0.05,
        num_leaves=63, min_child_samples=50, colsample_bytree=0.8, reg_lambda=15,
        min_sum_hessian_in_leaf=10, cat_smooth=100, cat_l2=50, max_cat_threshold=32,
        n_jobs=6, verbosity=-1, random_state=42)
    m = lgb.LGBMClassifier(**params)
    m.fit(Xc.iloc[idx_tr], y[idx_tr], eval_set=[(Xc.iloc[idx_va], y[idx_va])],
          eval_metric="multi_error", callbacks=[lgb.early_stopping(60, verbose=False)])
    return m, levels, cols

y = tr['task3'].to_numpy()
Xbase = AL.build_features(tr)
print("train BASELINE...", flush=True); t0=time.time()
m_b, lv_b, cols_b = train(Xbase, y, False)
print(f"  baseline done {time.time()-t0:.0f}s, best_it={m_b.best_iteration_}", flush=True)

Xpri = add_prior(Xbase, tr)
print("train +PRIOR...", flush=True); t0=time.time()
m_p, lv_p, cols_p = train(Xpri, y, True)
print(f"  +prior done {time.time()-t0:.0f}s, best_it={m_p.best_iteration_}", flush=True)

# ---- 테스트: 07/10~14 전부 (10~13=학습포함fit, 14=미학습) ----
def evalm(model, levels, cols, Xt, truth):
    Xe = AL.encode_cats_apply(Xt[cols].copy(), levels)
    proba = model.predict_proba(Xe)
    top = np.argmax(proba, axis=1); conf = proba[np.arange(len(proba)), top]
    pred = np.array([canon(c) for c in model.classes_[top]])
    labeled = conf >= THRESH
    corr = (pred == truth)
    unk = 1 - labeled.mean()
    overall = (labeled & corr).mean()
    acc_lab = corr[labeled].mean() if labeled.sum() else 0.0
    return unk, acc_lab, overall

ALL_DAYS = ['0710','0711','0712','0713','0714']
print("\n=== 07/10~14 전부 평가 (threshold 0.3) ===", flush=True)
print(f"{'날짜':<7}{'구분':<10}{'BASE 미분류/정답률':<24}{'+PRIOR 미분류/정답률':<24}", flush=True)
agg = {'b':[0,0,0], 'p':[0,0,0]}  # sum unk_n, correct_n, total (weighted)
for d in ALL_DAYS:
    te = AL.normalize_df(load([d]))
    truth = te['task3'].astype(str).map(canon).to_numpy()
    Xtb = AL.build_features(te); Xtp = add_prior(Xtb, te)
    ub,ab,ob = evalm(m_b, lv_b, cols_b, Xtb, truth)
    up,ap,op = evalm(m_p, lv_p, cols_p, Xtp, truth)
    tag = '학습포함' if d != TEST_DAY else '★미학습'
    n = len(te)
    agg['b'][0]+=ub*n; agg['b'][1]+=ob*n; agg['b'][2]+=n
    agg['p'][0]+=up*n; agg['p'][1]+=op*n; agg['p'][2]+=n
    print(f"07/{d[2:]:<4}{tag:<10}미분류{ub*100:5.2f}% 정답{ob*100:5.2f}%     미분류{up*100:5.2f}% 정답{op*100:5.2f}%", flush=True)
tb=agg['b'][2]
print(f"{'전체':<7}{'':<10}미분류{agg['b'][0]/tb*100:5.2f}% 정답{agg['b'][1]/tb*100:5.2f}%     미분류{agg['p'][0]/tb*100:5.2f}% 정답{agg['p'][1]/tb*100:5.2f}%", flush=True)
print("\n※ 07/10~13은 학습에 포함(fit), 07/14만 진짜 미학습 검증", flush=True)
print("DONE_EXP_PRIOR", flush=True)
