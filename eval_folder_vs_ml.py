import sys, collections
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import pandas as pd
import autolabel

MODEL = '/nmlab/99_sgs/03_ML/lab_dashboard_demo/models/autolabel_model_candidate_0710_0714_folder_normalized.pkl'
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5

UNKNOWN_ALIASES = {"미분류(자동)"}
def canon(v):
    s = "" if pd.isna(v) else str(v)
    s = s.strip()
    if s in UNKNOWN_ALIASES or '미분류' in s:
        return "__unknown__"
    s = s.lower()
    if s.endswith(".exe"):
        s = s[:-4]
    return s.replace(" ", "_").replace("-", "_")

print(f"모델 로드: {MODEL}", flush=True)
bundle = autolabel.load_bundle(MODEL)
print(f"클래스 {len(bundle['classes'])}종, threshold={THRESH}\n", flush=True)

days = ['0710', '0711', '0712', '0713', '0714']
tot_n = tot_exact = tot_norm = tot_unknown = 0
disagg = collections.Counter()

print(f"{'날짜':<8}{'세션':>10}{'일치(정규화)':>14}{'정확일치':>12}{'미분류':>10}", flush=True)
print("-" * 56, flush=True)
for mmdd in days:
    csv = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    df = pd.read_csv(csv, low_memory=False)
    for c in ('tls_sni', 'dns_qry', 'http_ua', 'http_uri'):
        if c in df.columns:
            df[c] = df[c].fillna('').astype(str)
    pred = autolabel.predict_df(bundle, df)
    final = autolabel.apply_threshold(pred, THRESH).astype(str)
    truth = df['task3'].astype(str)          # 폴더 기반 실측 라벨
    fc = truth.map(canon)
    pc = final.map(canon)
    n = len(df)
    exact = int((final == truth).sum())
    norm = int((pc == fc).sum())
    unknown = int((pc == "__unknown__").sum())
    tot_n += n; tot_exact += exact; tot_norm += norm; tot_unknown += unknown
    # 불일치(미분류 아닌 실제 오답) 집계
    mask = (pc != fc) & (pc != "__unknown__")
    for t, p in zip(fc[mask], pc[mask]):
        disagg[(t, p)] += 1
    print(f"{('07/'+mmdd[2:]):<8}{n:>10,}{norm/n*100:>13.2f}%{exact/n*100:>11.2f}%{unknown/n*100:>9.2f}%", flush=True)

print("-" * 56, flush=True)
print(f"{'전체':<8}{tot_n:>10,}{tot_norm/tot_n*100:>13.2f}%{tot_exact/tot_n*100:>11.2f}%{tot_unknown/tot_n*100:>9.2f}%", flush=True)

print("\n[상위 불일치] 폴더실측 → ML예측 (건수):", flush=True)
for (t, p), c in disagg.most_common(15):
    print(f"  {t:>22}  →  {p:<22}  {c:,}", flush=True)
