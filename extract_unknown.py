import sys, os
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import pandas as pd
import autolabel

MODEL = '/nmlab/99_sgs/03_ML/lab_dashboard_demo/models/autolabel_model_candidate_0710_0714_folder_normalized.pkl'
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
OUTDIR = '/nmlab/99_sgs/01_datasets/_ml_unknown'
os.makedirs(OUTDIR, exist_ok=True)

bundle = autolabel.load_bundle(MODEL)
UNK = autolabel.UNKNOWN_LABEL
print(f"모델 로드 · UNKNOWN_LABEL='{UNK}' · threshold={THRESH}", flush=True)

days = ['0710', '0711', '0712', '0713', '0714']
tot = tot_unk = 0
print(f"\n{'날짜':<8}{'전체세션':>12}{'미분류':>12}{'비율':>9}", flush=True)
print('-' * 42, flush=True)
for mmdd in days:
    csv = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    df = pd.read_csv(csv, low_memory=False)
    for c in ('tls_sni', 'dns_qry', 'http_ua', 'http_uri'):
        if c in df.columns:
            df[c] = df[c].fillna('').astype(str)
    pred = autolabel.predict_df(bundle, df)
    final = autolabel.apply_threshold(pred, THRESH)
    mask = (final == UNK)
    sub = df.loc[mask].copy()
    # 왜 미분류인지 파악용: 모델이 그나마 가장 근접했던 추정 + 신뢰도
    sub['ml_top_guess'] = pred.loc[mask, 'pred_label']
    sub['ml_top_conf'] = pred.loc[mask, 'pred_conf'].round(4)
    sub['ml_2nd_guess'] = pred.loc[mask, 'pred_2nd']
    sub['ml_2nd_conf'] = pred.loc[mask, 'pred_2nd_conf'].round(4)
    out = os.path.join(OUTDIR, f'unknown_lab{mmdd}.csv')
    sub.to_csv(out, index=False, encoding='utf-8-sig')
    n, u = len(df), int(mask.sum())
    tot += n; tot_unk += u
    print(f"{('07/'+mmdd[2:]):<8}{n:>12,}{u:>12,}{u/n*100:>8.2f}%   -> {out}", flush=True)

print('-' * 42, flush=True)
print(f"{'전체':<8}{tot:>12,}{tot_unk:>12,}{tot_unk/tot*100:>8.2f}%", flush=True)

# 미분류 세션에서 모델이 그나마 가장 근접했던 앱 상위 (무엇이 애매한지)
print("\n[미분류 세션의 모델 근접 추정 상위 15]", flush=True)
import glob, collections
cnt = collections.Counter()
for f in glob.glob(os.path.join(OUTDIR, 'unknown_lab*.csv')):
    d = pd.read_csv(f, low_memory=False)
    if 'ml_top_guess' in d.columns:
        cnt.update(d['ml_top_guess'].astype(str).tolist())
for k, v in cnt.most_common(15):
    print(f"  {k:<26}{v:,}", flush=True)
print("DONE_EXTRACT_UNKNOWN", flush=True)
