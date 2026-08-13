#!/bin/bash
# CatBoost만 추가 실행 (기존 5모델 결과는 merge로 보존).
# CatBoost 다중클래스 부트스트랩 B=15 → 느림(특히 CSTNET 120클래스). 순서: Cipher → LAB → CSTNET.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"
OUT="$BASE/03_json/bias_variance_results.json"
LOG="$BASE/04_logs/bias_variance_catboost.log"
export N_JOBS="${N_JOBS:-11}" BV_B="${BV_B:-15}" ONLY="CatBoost(Boost)"
mkdir -p "$BASE/03_json" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log "catboost 설치 확인"
python3 -c "import catboost" 2>/dev/null || python3 -m pip install -q catboost 2>&1 | tail -2

log "CatBoost Bias-Variance 시작 (ONLY=$ONLY B=$BV_B)"
run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name"; python3 -u "$CODE/bias_variance.py" "$name" "$seq" "$OUT" $flag 2>&1 | tee -a "$LOG"; }

export DOMAIN_ONLY=1; run CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" ""; unset DOMAIN_ONLY
export BV_SUB=200000; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB
run CSTNET "$BASE/06_data/canonical_cstnet_seq" ""

log "CatBoost 완료 -> $OUT"
