#!/bin/bash
# IME654 04 앙상블 — Bias-Variance 분해, 세 데이터셋. LAB baseline 끝난 뒤 실행 권장.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"
OUT="$BASE/03_json/bias_variance_results.json"
LOG="$BASE/04_logs/bias_variance.log"
export N_JOBS="${N_JOBS:-8}" BV_SUB="${BV_SUB:-0}" BV_B="${BV_B:-15}"   # BV_SUB=0 → 전량, B=15
mkdir -p "$BASE/03_json" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log "xgboost/catboost 설치 확인"
python3 -c "import xgboost,catboost" 2>/dev/null || python3 -m pip install -q xgboost catboost 2>&1 | tail -2

log "Bias-Variance 시작 (SUB=$BV_SUB, B=$BV_B)"
run(){ local name="$1" seq="$2" flag="${3:-}"; ls "$seq"/sequences_part_*.csv >/dev/null 2>&1 || { log "[SKIP] $name"; return; }
  log ">>> $name"; python3 -u "$CODE/bias_variance.py" "$name" "$seq" "$OUT" $flag 2>&1 | tee -a "$LOG"; }
# 파라미터 통일(lr .05·reg 10) · 순서: Cipher → LAB → CSTNET
export DOMAIN_ONLY=1; run CipherSpectrum  "$BASE/06_data/canonical_cipherspec_seq_v2" ""; unset DOMAIN_ONLY   # cipher 합쳐 도메인 42클래스
export BV_SUB=200000; run LAB "$BASE/06_data/lab_full45_seq_v2_904k" "--lab"; unset BV_SUB   # LAB 878k → 20만 서브샘플
run CSTNET          "$BASE/06_data/canonical_cstnet_seq"        ""

log "완료 -> $OUT"
python3 -c "
import json;d=json.load(open('$OUT'))
for ds,v in d.items():
    print('==',ds,'(rows=%d cls=%d B=%d) =='%(v['rows_bv'],v['classes'],v['B']))
    for mn,mv in v['models'].items(): print('  %-22s AC=%5.2f F1=%5.2f bias=%5.2f var=%5.2f err=%5.2f IT=%5.2fs mem=%dMB'%(mn,mv['AC'],mv['F1'],mv['bias'],mv['variance'],mv['error'],mv['IT_s'],mv['mem_MB']))
" 2>/dev/null || true
