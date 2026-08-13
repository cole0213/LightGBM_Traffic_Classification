#!/bin/bash
# 파이프라인 노이즈 제거 후 bias-variance 재측정 (3데이터셋). 원본 결과는 보존, *_pipeclean.json 로 별도 저장.
set -uo pipefail
BASE="${BASE:-$(pwd)}"; CODE="$BASE/01_code"; D="$BASE/02_dataset"; J="$BASE/03_json"
export N_JOBS="${N_JOBS:-8}" BV_B="${BV_B:-15}"
LOG="$BASE/04_logs/noise_bv.log"; mkdir -p "$J" "$BASE/04_logs"
log(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

log ">>> CipherSpectrum (noise 14.6% 제거)"
DOMAIN_ONLY=1 NOISE_FILE="$D/cipher_pipeline_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" CipherSpectrum "$BASE/06_data/canonical_cipherspec_seq_v2" "$J/bias_variance_cipher_pipeclean.json" 2>&1 | tee -a "$LOG"

log ">>> CSTNET (noise ~0%)"
NOISE_FILE="$D/cstnet_pipeline_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" CSTNET "$BASE/06_data/canonical_cstnet_seq" "$J/bias_variance_cstnet_pipeclean.json" 2>&1 | tee -a "$LOG"

log ">>> LAB (noise 30.3% 제거, 20만 서브샘플)"
BV_SUB=200000 LAB_NOISE_FILE="$D/lab_pipeline_noise_basenames.txt" \
  python3 -u "$CODE/bias_variance.py" LAB "$BASE/06_data/lab_full45_seq_v2_904k" "$J/bias_variance_lab_pipeclean.json" --lab 2>&1 | tee -a "$LOG"

log "노이즈 BV 완료"
