#!/bin/bash
# 클린 데이터 부스팅 튜닝: CSTNET(clean=원본, 노이즈0) + LAB week2 클린(노이즈 제거).
# LightGBM(CPU) ∥ XGBoost(GPU device=cuda). CatBoost 제외(8GB GPU 다중클래스 OOM; Cipher만 기존 완료).
# 결과 → 03_json/boosting_best_params.json 병합(Cipher 이미 있음). Optuna sqlite resume.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; J="$BASE/03_json"; D="$BASE/02_dataset"
OUT="$J/boosting_best_params.json"; LOG="$BASE/04_logs/tune_clean.log"
export N_JOBS="${N_JOBS:-11}"; TRIALS="${TRIALS:-60}"
mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }
python3 -c "import optuna" 2>/dev/null || python3 -m pip install -q optuna 2>&1 | tail -2

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

# run <name> <seqdir> <lab_flag> <extra_env...>
run(){ local name="$1" seq="$2" flag="$3"; shift 3; local extra="$*"
  ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name (LightGBM CPU ∥ XGBoost GPU)  extra=[$extra]"
  env $extra python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tc_${name}_lgb.json" $flag --trials "$TRIALS" --models lightgbm 2>&1 | tee -a "$LOG" &
  local cpu=$!
  env $extra XGB_GPU=1 python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_tc_${name}_xgb.json" $flag --trials "$TRIALS" --models xgboost 2>&1 | tee -a "$LOG" &
  local gpu=$!
  wait $cpu; wait $gpu
  merge "$J/_tc_${name}_lgb.json" "$J/_tc_${name}_xgb.json"
  log "<<< $name 병합"; }

run CSTNET "$BASE/06_data/canonical_cstnet_seq" "" ""
run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab" "BV_SUB=200000 LAB_NOISE_FILE=$D/lab_seqmeta_noise_basenames.txt"
log "클린 튜닝 완료 -> $OUT"
