#!/bin/bash
# week2·week3 LAB bias-variance, 통일 기준(seqmeta 노이즈). 5모델(CatBoost 제외), 순차(경합 방지).
#  1) week2 클린   2) week3 원본   3) week3 클린   (week2 원본은 기존 bias_variance_results.json)
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; D="$BASE/02_dataset"; J="$BASE/03_json"
export N_JOBS="${N_JOBS:-11}" BV_B=15 BV_SUB=200000
M='DecisionTree(단일),RandomForest(Bag),ExtraTrees(Bag),LightGBM(Boost),XGBoost(Boost)'
LOG="$BASE/04_logs/week_bv.log"; mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log ">>> week2 LAB 클린 (seqmeta 노이즈 30.3%)"
ONLY="$M" LAB_NOISE_FILE="$D/lab_seqmeta_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" LAB "$BASE/06_data/lab_full45_seq_v2_904k" "$J/bias_variance_lab_pipeclean.json" --lab 2>&1 | tee -a "$LOG"

log ">>> week3 원본 (노이즈 제거 전)"
ONLY="$M" LAB_LABEL_MAP="$D/week3_label.csv" \
  python3 -u "$CODE/bias_variance.py" week3 "$BASE/06_data/lab_week3_seq_100" "$J/bias_variance_week3_orig.json" --lab 2>&1 | tee -a "$LOG"

log ">>> week3 클린 (seqmeta 노이즈 30.7%)"
ONLY="$M" LAB_LABEL_MAP="$D/week3_label.csv" LAB_NOISE_FILE="$D/week3_seqmeta_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" week3 "$BASE/06_data/lab_week3_seq_100" "$J/bias_variance_week3_pipeclean.json" --lab 2>&1 | tee -a "$LOG"

log "week2·week3 BV 완료"
