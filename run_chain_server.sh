#!/bin/bash
# run_chain_server.sh — 리눅스 서버용 순차 ingest 체인
# 대상 날짜: 07.02 (이미 돌고 있음), 07.03, 07.05
# 로그 파일: /nmlab/99_sgs/lab_dashboard/_chain_server.log

LOG="/nmlab/99_sgs/lab_dashboard/_chain_server.log"
PYTHON="/usr/bin/python3"
PIPE="/nmlab/99_sgs/lab_dashboard/pipeline.py"
DSROOT="/nmlab/99_sgs/lab_dashboard/static/datasets"

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

wait_no_other_pipeline() {
    # We wait if there are MULTIPLE pipeline.py runs, or just sleep to let the first one proceed
    # Since we are starting the loop, let's wait until the currently running pipeline.py finishes.
    # Note: We grep for pipeline.py, but need to exclude this script's check
    while ps aux | grep -v grep | grep "pipeline.py" | grep -q -v "run_chain_server.sh"; do
        sleep 30
    done
}

log_msg "=== Server Ingest Chain Start ==="

# 1. Wait for lab0702 (which was started manually)
log_msg "Waiting for active lab0702 pipeline to finish..."
wait_no_other_pipeline
log_msg "lab0702 pipeline finished."

# 2. Run lab0703
log_msg "START lab0703 <- /mnt/x_root/data/99_KJM/auto_match_out_div/2026.07.03"
mkdir -p "$DSROOT/lab0703"
$PYTHON "$PIPE" --src /mnt/x_root/data/99_KJM/auto_match_out_div/2026.07.03 --key lab0703 --name "연구실 수집 2026-07-03" --workers 12 > "$DSROOT/lab0703/_pipeline.log" 2>&1
log_msg "END lab0703 exit=$?"

# 3. Run lab0705
log_msg "START lab0705 <- /mnt/x_root/data/99_KJM/auto_match_out_div/2026.07.05"
mkdir -p "$DSROOT/lab0705"
$PYTHON "$PIPE" --src /mnt/x_root/data/99_KJM/auto_match_out_div/2026.07.05 --key lab0705 --name "연구실 수집 2026-07-05" --workers 12 > "$DSROOT/lab0705/_pipeline.log" 2>&1
log_msg "END lab0705 exit=$?"

log_msg "=== Server Ingest Chain Done ==="
