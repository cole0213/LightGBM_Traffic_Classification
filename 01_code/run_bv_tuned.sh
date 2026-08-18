#!/bin/bash
# 튜닝 params 반영 bias-variance 재실행 → 03_json/bias_variance_tuned_results.json (원본 통일-params 표는 보존).
# 트리계(DT/RF/ET)는 통일값 그대로, 부스팅3만 boosting_best_params.json 값 사용.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"
OUT="$BASE/03_json/bias_variance_tuned_results.json"
export TUNED_PARAMS="$BASE/03_json/boosting_best_params.json"
export N_JOBS="${N_JOBS:-11}" BV_B="${BV_B:-15}"
# 동일조건 수집 원칙: 보고 표(F1/acc/bias/var/학습s/추론µs/mem)는 전 모델 CPU 단일 디바이스로 통일.
# GPU는 튜닝 탐색 때만 썼고(하이퍼값은 디바이스 무관), 8GB VRAM에선 CatBoost 다중클래스 GPU OOM이라 공통 디바이스 = CPU뿐.
# 셸 환경에서 GPU 플래그가 새어들지 않게 명시적으로 차단.
unset XGB_GPU CAT_GPU 2>/dev/null || true
# CatBoost 전면 제외(사용자 결정): 다중클래스 GPU OOM + 최하위 성능 + 동일조건(CPU) 통일 위해 비교에서 뺌.
# 전 데이터셋 5모델(DT/RF/ET/LightGBM/XGBoost)만 계산. ONLY 전역 적용.
FIVE='DecisionTree(단일),RandomForest(Bag),ExtraTrees(Bag),LightGBM(Boost),XGBoost(Boost)'
export ONLY="$FIVE"
LOG="$BASE/04_logs/bv_tuned.log"
mkdir -p "$BASE/03_json" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }
[ -f "$TUNED_PARAMS" ] || { log "ERROR: $TUNED_PARAMS 없음 — 먼저 run_tune_boosting.sh 실행"; exit 1; }

log "튜닝반영 BV 시작 (TUNED_PARAMS=$TUNED_PARAMS B=$BV_B)"
run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name"; python3 -u "$CODE/bias_variance.py" "$name" "$seq" "$OUT" $flag 2>&1 | tee -a "$LOG"; }

# Cipher/CSTNET = 도메인분류라 노이즈≈0(원본=클린) → 노이즈파일 불필요.
# LAB = 프로세스분류라 DNS/CDN/배경 노이즈 30% → 튜닝이 클린 기준이므로 여기도 클린 맞춤(LAB_NOISE_FILE).
export DOMAIN_ONLY=1; run CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" ""; unset DOMAIN_ONLY
# LAB_LABEL_MAP 필수 — bias_variance.py 기본경로가 SEQDIR.parent(=06_data) 밑을 보는데 실제 라벨맵은 루트 02_dataset/에 있음(폴더 재편 후 default 깨짐).
export BV_SUB=200000 LAB_LABEL_MAP="$BASE/02_dataset/lab_canon_label.csv" LAB_NOISE_FILE="$BASE/02_dataset/lab_seqmeta_noise_basenames.txt"; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB LAB_LABEL_MAP LAB_NOISE_FILE
run CSTNET "$BASE/06_data/canonical_cstnet_seq" ""
log "튜닝반영 BV 완료 -> $OUT"
