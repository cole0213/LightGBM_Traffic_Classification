#!/bin/bash
# LAB 노이즈 실험 2종 (원본=기존 bias_variance_results.json 그대로 사용).
#  clean : 시스템+측정인프라 전부 제거 → 실앱 46클래스
#  super : 측정인프라·unknown만 제거 + 시스템류는 __background__ 1클래스로 묶음 → 앱46+background=47
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; D="$BASE/02_dataset"
export N_JOBS="${N_JOBS:-6}" BV_SUB="${BV_SUB:-200000}"
LOG="$BASE/04_logs/lab_noise.log"; mkdir -p "$BASE/03_json" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log ">>> clean (실앱 전용, 노이즈 전부 제거)"
LAB_EXCLUDE_FILE="$D/lab_noise_labels.txt" \
  python3 -u "$CODE/bias_variance.py" LAB "$BASE/06_data/lab_full45_seq_v2_904k" "$BASE/03_json/bias_variance_lab_clean.json" --lab 2>&1 | tee -a "$LOG"

log ">>> super (background 1클래스로 묶음)"
LAB_EXCLUDE_FILE="$D/lab_drop_labels.txt" LAB_COLLAPSE_FILE="$D/lab_background_labels.txt" \
  python3 -u "$CODE/bias_variance.py" LAB "$BASE/06_data/lab_full45_seq_v2_904k" "$BASE/03_json/bias_variance_lab_super.json" --lab 2>&1 | tee -a "$LOG"

log "LAB 노이즈 실험 완료"
