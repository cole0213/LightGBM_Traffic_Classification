import sys, numpy as np
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1')
import pandas as pd
import autolabel
import pipeline

MODEL = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/models/autolabel_model_candidate_0710_0714_folder_normalized.pkl'
bundle = autolabel.load_bundle(MODEL)

def canon(v):
    s = "" if pd.isna(v) else str(v)
    s = s.strip()
    if '미분류' in s: return "__unk__"
    s = s.lower()
    if s.endswith(".exe"): s = s[:-4]
    return s.replace(" ", "_").replace("-", "_")

confs, corrects = [], []
for mmdd in ['0710', '0711', '0712', '0713', '0714']:
    f = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    df = pd.read_csv(f, low_memory=False)
    for c in ('tls_sni', 'dns_qry', 'http_ua', 'http_uri'):
        if c in df.columns: df[c] = df[c].fillna('').astype(str)
    pred = autolabel.predict_df(bundle, df)
    conf = pd.to_numeric(pred['pred_conf'], errors='coerce').fillna(0).to_numpy()
    pl = pred['pred_label'].map(canon).to_numpy()
    # B와 동일: 폴더 실측에도 build_app_display_map 정규화 적용 후 canon
    traw = df['task3'].astype(str)
    tdmap = pipeline.build_app_display_map(traw.tolist())
    tr = traw.map(tdmap).fillna(traw).map(canon).to_numpy()
    confs.append(conf)
    corrects.append(pl == tr)
    print(f"  predicted {mmdd} ({len(df):,})", flush=True)

conf = np.concatenate(confs)
correct = np.concatenate(corrects)
N = len(conf)
print(f"\n총 세션: {N:,}\n", flush=True)
print(f"{'threshold':>10}{'미분류%':>10}{'라벨된것정답률':>16}{'전체정답률':>12}", flush=True)
print("-" * 50, flush=True)
best = None
for t in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    labeled = conf >= t
    nl = int(labeled.sum())
    unk = 1 - nl / N
    acc_lab = (correct[labeled].mean() if nl else 0.0)
    overall = (labeled & correct).sum() / N     # 전체 중 올바른 라벨을 받은 비율
    flag = ""
    if best is None or overall > best[1]:
        best = (t, overall)
    print(f"{t:>10.1f}{unk*100:>9.2f}%{acc_lab*100:>15.2f}%{overall*100:>11.2f}%", flush=True)
print("-" * 50, flush=True)
print(f"\n전체정답률 최대 지점: threshold={best[0]:.1f} (전체정답률 {best[1]*100:.2f}%)", flush=True)
print("현재 운영값 threshold=0.5 대비 비교용.", flush=True)
print("DONE_SWEEP", flush=True)
