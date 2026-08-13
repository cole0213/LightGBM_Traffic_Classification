#!/bin/bash
# 튜닝 params 반영 bias-variance 재실행 → 03_json/bias_variance_tuned_results.json (원본 통일-params 표는 보존).
# 트리계(DT/RF/ET)는 통일값 그대로, 부스팅3만 boosting_best_params.json 값 사용.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"
OUT="$BASE/03_json/bias_variance_tuned_results.json"
export TUNED_PARAMS="$BASE/03_json/boosting_best_params.json"
export N_JOBS="${N_JOBS:-11}" BV_B="${BV_B:-15}"
LOG="$BASE/04_logs/bv_tuned.log"
mkdir -p "$BASE/03_json" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }
[ -f "$TUNED_PARAMS" ] || { log "ERROR: $TUNED_PARAMS 없음 — 먼저 run_tune_boosting.sh 실행"; exit 1; }

log "튜닝반영 BV 시작 (TUNED_PARAMS=$TUNED_PARAMS B=$BV_B)"
run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name"; python3 -u "$CODE/bias_variance.py" "$name" "$seq" "$OUT" $flag 2>&1 | tee -a "$LOG"; }

export DOMAIN_ONLY=1; run CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" ""; unset DOMAIN_ONLY
export BV_SUB=200000; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB
run CSTNET "$BASE/06_data/canonical_cstnet_seq" ""
log "튜닝반영 BV 완료 -> $OUT"
