#!/bin/bash
# 정본 seq-core 299(K30, 6그룹) 재튜닝 — 기존 789 튜닝값 대체.
# LightGBM(CPU) ∥ XGBoost(GPU device=cuda). CatBoost 제외.
# 결과 → 03_json/boosting_best_params_core.json (789용 boosting_best_params.json 은 보존).
# optuna db 는 TUNE_TAG=_core 로 분리(789 study 안 섞임). 튜닝은 BV_SUB=200000 서브샘플(params는 전량 BV에 재사용).
# 전량 클린·전 데이터셋(Cipher/CSTNET/LAB). N100/N60 compact 은 이 값 재사용(별도 튜닝 안 함).
# 작성일 2026-08-19
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; J="$BASE/03_json"; D="$BASE/02_dataset"
OUT="$J/boosting_best_params_core.json"; LOG="$BASE/04_logs/tune_core.log"
export N_JOBS="${N_JOBS:-11}"; TRIALS="${TRIALS:-60}"
export FEAT_TRUNC=30            # 정본 K30 = 299피처로 튜닝
export TUNE_TAG=_core           # optuna db 분리
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
  log ">>> $name 299 재튜닝 (LightGBM CPU ∥ XGBoost GPU)  extra=[$extra]"
  env $extra python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_core_${name}_lgb.json" $flag --trials "$TRIALS" --models lightgbm 2>&1 | tee -a "$LOG" &
  local cpu=$!
  env $extra XGB_GPU=1 python3 -u "$CODE/tune_boosting.py" "$name" "$seq" "$J/_core_${name}_xgb.json" $flag --trials "$TRIALS" --models xgboost 2>&1 | tee -a "$LOG" &
  local gpu=$!
  wait $cpu; wait $gpu
  merge "$J/_core_${name}_lgb.json" "$J/_core_${name}_xgb.json"
  log "<<< $name 병합"; }

run CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" "" "DOMAIN_ONLY=1 DOMAIN_EXCLUDE=chacha20"
run CSTNET         "$BASE/06_data/canonical_cstnet_seq"        "" ""
run LAB            "$BASE/06_data/lab_full45_seq_v2_904k"      "--lab" "BV_SUB=200000 LAB_LABEL_MAP=$D/lab_canon_label.csv LAB_NOISE_FILE=$D/lab_seqmeta_noise_basenames.txt DOMAIN_EXCLUDE=unknown"
log "299 재튜닝 완료 -> $OUT"
