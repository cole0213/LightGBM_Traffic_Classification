#!/bin/bash
# 정본 피처 최종 full BV — 3설정(299 / N100 / N60) × 3데이터셋 × 5모델 × B=15.
# core 튜닝값(boosting_best_params_core.json, FEAT_TRUNC=30 기준) 사용. 트리계 통일, 부스팅 튜닝.
# 전 모델 CPU 단일 디바이스, CatBoost 제외. LAB만 BV_SUB=200000(feasibility), Cipher/CSTNET 전량.
# 3설정 전부 동일 데이터(같은 서브샘플 seed·클래스≥15·split·부트스트랩) → 피처만 다름 = 통제비교.
# 출력: bias_variance_core_{299,N100,N60}.json. 작성일 2026-08-20
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; J="$BASE/03_json"; D="$BASE/02_dataset"
export TUNED_PARAMS="$J/boosting_best_params_core.json"
export N_JOBS="${N_JOBS:-11}" BV_B="${BV_B:-15}" FEAT_TRUNC=30
export ONLY='DecisionTree(단일),RandomForest(Bag),ExtraTrees(Bag),LightGBM(Boost),XGBoost(Boost)'
unset XGB_GPU CAT_GPU 2>/dev/null || true
LOG="$BASE/04_logs/bv_core.log"; mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }
[ -f "$TUNED_PARAMS" ] || { log "ERROR: $TUNED_PARAMS 없음"; exit 1; }

# run_ds <name> <seq> <flag> <out> <extra_env...>
run_ds(){ local name="$1" seq="$2" flag="$3" out="$4"; shift 4; local extra="$*"
  ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> [$out] $name  extra=[$extra]"
  env $extra python3 -u "$CODE/bias_variance.py" "$name" "$seq" "$out" $flag 2>&1 | tee -a "$LOG"; }

# run_setting <tag> <select_env>  (select_env: 빈 문자열=299, 아니면 FEAT_SELECT=...)
run_setting(){ local tag="$1" sel="$2"; local OUT="$J/bias_variance_core_${tag}.json"
  log "========== 설정 $tag ($sel) → $OUT =========="
  run_ds CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" "" "$OUT" "DOMAIN_ONLY=1 DOMAIN_EXCLUDE=chacha20 $sel"
  run_ds CSTNET "$BASE/06_data/canonical_cstnet_seq" "" "$OUT" "$sel"
  run_ds LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab" "$OUT" "BV_SUB=200000 LAB_LABEL_MAP=$D/lab_canon_label.csv LAB_NOISE_FILE=$D/lab_seqmeta_noise_basenames.txt DOMAIN_EXCLUDE=unknown $sel"
  log "<<< 설정 $tag 완료 -> $OUT"; }

run_setting 299 ""
run_setting N100 "FEAT_SELECT=$D/core100_features.txt"
run_setting N60 "FEAT_SELECT=$D/core60_features.txt"
log "전체 full BV 완료 (299/N100/N60)"
