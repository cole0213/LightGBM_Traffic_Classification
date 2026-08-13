#!/bin/bash
# CSTNET·LAB 튜닝: LightGBM(CPU) ∥ XGBoost(GPU, device=cuda). CatBoost 제외(8GB GPU OOM, Cipher만 됨).
# Optuna sqlite resume → 이미 끝난 trial 유지(CSTNET LightGBM 60, XGBoost 35 등). 결과는 boosting_best_params.json에 병합.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; J="$BASE/03_json"
OUT="$J/boosting_best_params.json"; LOG="$BASE/04_logs/tune_xgbgpu.log"
export N_JOBS="${N_JOBS:-11}"; TRIALS="${TRIALS:-60}"
mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

merge(){ python3 -c "
import json,sys,os
base=sys.argv[1]; parts=sys.argv[2:]
d=json.load(open(base,encoding='utf-8')) if os.path.exists(base) else {}
for p in parts:
    if not os.path.exists(p): continue
    e=json.load(open(p,encoding='utf-8'))
    for name,mods in e.items(): d.setdefault(name,{}).update(mods)
json.dump(d,open(base,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('merged:',{k:list(v) for k,v in d.items()})
" "$OUT" "$@"; }

run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name  (LightGBM CPU ∥ XGBoost GPU)"
  python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tune_${name}_lgb.json" $flag --trials "$TRIALS" --models lightgbm 2>&1 | tee -a "$LOG" &
  local cpu=$!
  XGB_GPU=1 python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tune_${name}_xgb.json" $flag --trials "$TRIALS" --models xgboost 2>&1 | tee -a "$LOG" &
  local gpu=$!
  wait $cpu; wait $gpu
  merge "$J/_tune_${name}_lgb.json" "$J/_tune_${name}_xgb.json"
  log "<<< $name 병합 완료"; }

run CSTNET "$BASE/06_data/canonical_cstnet_seq" ""
export BV_SUB=200000; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB
log "완료 -> $OUT"
