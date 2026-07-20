import pandas as pd
import pickle
import os
import sys
import glob

sys.path.append('/nmlab/99_sgs/lab_dashboard')
from pipeline import build_app_display_map
from autolabel import train_model

# 07/10~14 신규 추출만 (task3 자체가 폴더 기반 실측 라벨)
csv_files = sorted(glob.glob('/nmlab/99_sgs/01_datasets/2026.07.1[0-4]/session_stat_*.csv'))
N_JOBS = int(os.environ.get("N_JOBS", "6"))   # 서버 부하 완화: 12코어 중 6개만 사용

print(f"[RETRAIN 1014] 학습 파일 {len(csv_files)}개 (n_jobs={N_JOBS}):", flush=True)
for f in csv_files:
    print("   -", f, flush=True)

dfs = []
for f in csv_files:
    df = pd.read_csv(f, low_memory=False)
    dfs.append(df)
    print(f"   loaded {os.path.basename(os.path.dirname(f))}: {len(df):,}", flush=True)

all_df = pd.concat(dfs, ignore_index=True)
del dfs
print(f"[RETRAIN 1014] 총 결합 세션: {len(all_df):,}", flush=True)

# task3_folder 있으면 우선, 없으면 task3 (신규 데이터는 task3가 이미 실측)
all_df['task3_train'] = all_df['task3']
if 'task3_folder' in all_df.columns:
    fl = all_df['task3_folder']
    valid = (fl.notna() & (fl.astype(str).str.strip() != '')
             & (fl.astype(str) != 'unknown')
             & (~fl.astype(str).str.contains('미분류', na=False)))
    all_df.loc[valid, 'task3_train'] = fl[valid]
    print(f"[RETRAIN 1014] task3_folder로 대체된 행: {int(valid.sum()):,}", flush=True)
else:
    print("[RETRAIN 1014] task3_folder 컬럼 없음 (task3가 실측 정답)", flush=True)

unk = (all_df['task3_train'].isna()
       | (all_df['task3_train'] == 'unknown')
       | (all_df['task3_train'].astype(str).str.contains('미분류', na=False)))
train_df = all_df.loc[~unk].copy()
del all_df
print(f"[RETRAIN 1014] 학습 대상 (unknown {int(unk.sum()):,} 제외): {len(train_df):,}", flush=True)

n0 = train_df['task3_train'].nunique()
dmap = build_app_display_map(train_df['task3_train'].astype(str).tolist())
train_df['task3'] = train_df['task3_train'].astype(str).map(dmap).fillna(train_df['task3_train'])
n1 = train_df['task3'].nunique()
print(f"[RETRAIN 1014] 라벨 정규화: {n0} -> {n1} 클래스", flush=True)

for c in ('tls_sni', 'dns_qry', 'http_ua'):
    if c in train_df.columns:
        train_df[c] = train_df[c].fillna('').astype(str)

print("[RETRAIN 1014] train_model 구동 (n_jobs 제한)...", flush=True)
bundle = train_model(train_df, n_jobs=N_JOBS)

model_dir = '/nmlab/99_sgs/lab_dashboard/models'
os.makedirs(model_dir, exist_ok=True)
model_path = os.path.join(model_dir, 'autolabel_model_candidate_0710_0714_folder_normalized.pkl')
with open(model_path, 'wb') as f:
    pickle.dump(bundle, f)
print(f"[RETRAIN 1014] 저장 완료: {model_path}", flush=True)
print(f"[RETRAIN 1014] 클래스 수: {len(bundle.get('classes', []))}", flush=True)
