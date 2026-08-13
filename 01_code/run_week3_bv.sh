#!/bin/bash
# week3 LAB bias-variance: 원본 → 클린. 통일 기준(seqmeta 노이즈), 5모델, 순차.
# ★ week2 클린 BV 끝난 뒤 실행 (동시 실행 금지 — CPU 경합).
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; D="$BASE/02_dataset"; J="$BASE/03_json"
export N_JOBS="${N_JOBS:-11}" BV_B=15 BV_SUB=200000 XGB_GPU="${XGB_GPU:-1}"  # XGBoost GPU(device=cuda) 기본 ON
M='DecisionTree(단일),RandomForest(Bag),ExtraTrees(Bag),LightGBM(Boost),XGBoost(Boost)'
LOG="$BASE/04_logs/week3_bv.log"; mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log ">>> week3 클린 (seqmeta 노이즈 30.7%)"
ONLY="$M" LAB_LABEL_MAP="$D/week3_label.csv" LAB_NOISE_FILE="$D/week3_seqmeta_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" week3 "$BASE/06_data/lab_week3_seq_100" "$J/bias_variance_week3_pipeclean.json" --lab 2>&1 | tee -a "$LOG"

log "week3 BV 완료"
