import sys, collections, json
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import pandas as pd
import autolabel
import pipeline

MODEL = '/nmlab/99_sgs/03_ML/lab_dashboard_demo/models/autolabel_model_candidate_0710_0714_folder_normalized.pkl'
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3   # 적용된 운영 threshold

def canon(v):
    s = "" if pd.isna(v) else str(v); s = s.strip()
    if '미분류' in s: return "__unk__"
    s = s.lower()
    if s.endswith(".exe"): s = s[:-4]
    return s.replace(" ", "_").replace("-", "_")

bundle = autolabel.load_bundle(MODEL)
print(f"모델 로드 · threshold={THRESH} (라벨 정규화 일관 채점)\n", flush=True)

days = ['0710', '0711', '0712', '0713', '0714']
tot_n = tot_norm = tot_unk = 0
disagg = collections.Counter()
per_day = {}
print(f"{'날짜':<7}{'세션':>10}{'일치율(정규화일관)':>18}{'미분류':>9}", flush=True)
print("-" * 46, flush=True)
for mmdd in days:
    csv = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    df = pd.read_csv(csv, low_memory=False)
    for c in ('tls_sni', 'dns_qry', 'http_ua', 'http_uri'):
        if c in df.columns: df[c] = df[c].fillna('').astype(str)
    pred = autolabel.predict_df(bundle, df)
    final = autolabel.apply_threshold(pred, THRESH).astype(str)   # 모델 라벨(정규화 공간) 또는 미분류
    # 폴더 실측에 동일 정규화 적용 (모델과 같은 build_app_display_map 공간으로)
    truth_raw = df['task3'].astype(str)
    dmap = pipeline.build_app_display_map(truth_raw.tolist())
    truth_norm = truth_raw.map(dmap).fillna(truth_raw)
    fc = truth_norm.map(canon)
    pc = final.map(canon)
    n = len(df)
    norm = int((pc == fc).sum())
    unk = int((pc == "__unk__").sum())
    tot_n += n; tot_norm += norm; tot_unk += unk
    per_day[mmdd] = (n, norm / n * 100, unk / n * 100)
    mask = (pc != fc) & (pc != "__unk__")
    for t, p in zip(fc[mask], pc[mask]):
        disagg[(t, p)] += 1
    print(f"07/{mmdd[2:]:<4}{n:>10,}{norm/n*100:>17.2f}%{unk/n*100:>8.2f}%", flush=True)

print("-" * 46, flush=True)
print(f"{'전체':<7}{tot_n:>10,}{tot_norm/tot_n*100:>17.2f}%{tot_unk/tot_n*100:>8.2f}%", flush=True)
print("\n[상위 불일치] 폴더실측 → ML예측 (정규화 일관 후):", flush=True)
for (t, p), c in disagg.most_common(15):
    print(f"  {t:>26} -> {p:<26} {c:,}", flush=True)

# 리포트 갱신용 저장
out = {"threshold": THRESH, "total": tot_n,
       "overall_agree": round(tot_norm / tot_n * 100, 2),
       "overall_unknown": round(tot_unk / tot_n * 100, 2),
       "per_day": {k: {"sessions": v[0], "agree": round(v[1], 2), "unknown": round(v[2], 2)} for k, v in per_day.items()},
       "mismatches": [{"folder": t, "ml": p, "count": c} for (t, p), c in disagg.most_common(15)]}
with open('/nmlab/99_sgs/01_datasets/_compare_v2.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\nSAVED _compare_v2.json", flush=True)
print("DONE_EVAL_V2", flush=True)
