#!/bin/bash
# 부스팅 3종 Optuna 튜닝, 3데이터셋. CPU(LightGBM+XGBoost) ∥ GPU(CatBoost) 동시 실행 → 벽시계 단축.
# 결과 → 03_json/boosting_best_params.json (resume 가능: optuna sqlite per study).
# 순서 Cipher(빠름) → CSTNET → LAB(가장 김). TRIALS 환경변수(기본 60).
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; J="$BASE/03_json"
OUT="$J/boosting_best_params.json"
LOG="$BASE/04_logs/tune_boosting.log"
export N_JOBS="${N_JOBS:-11}"; TRIALS="${TRIALS:-60}"
mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

python3 -c "import optuna" 2>/dev/null || python3 -m pip install -q optuna 2>&1 | tail -2
log "튜닝 시작 (TRIALS=$TRIALS, CPU LGB+XGB ∥ GPU CatBoost)"

merge(){ python3 -c "
import json,sys,os
base=sys.argv[1]; parts=sys.argv[2:]
d=json.load(open(base,encoding='utf-8')) if os.path.exists(base) else {}
for p in parts:
    if not os.path.exists(p): continue
    e=json.load(open(p,encoding='utf-8'))
    for name,mods in e.items(): d.setdefault(name,{}).update(mods)
json.dump(d,open(base,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
" "$OUT" "$@"; }

run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name (CPU LGB+XGB ∥ GPU CatBoost)"
  # CPU 프로세스: LightGBM+XGBoost
  python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tune_${name}_cpu.json" $flag --trials "$TRIALS" --models lightgbm,xgboost 2>&1 | tee -a "$LOG" &
  local cpu=$!
  # GPU 프로세스: CatBoost
  CAT_GPU=1 python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tune_${name}_gpu.json" $flag --trials "$TRIALS" --models catboost 2>&1 | tee -a "$LOG" &
  local gpu=$!
  wait $cpu; wait $gpu
  merge "$J/_tune_${name}_cpu.json" "$J/_tune_${name}_gpu.json"
  log "<<< $name 병합 완료"; }

export DOMAIN_ONLY=1; run CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" ""; unset DOMAIN_ONLY
run CSTNET "$BASE/06_data/canonical_cstnet_seq" ""
export BV_SUB=200000; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB
log "튜닝 완료 -> $OUT"
