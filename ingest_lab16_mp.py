import sys, csv, time, os
sys.path.append('/nmlab/99_sgs/lab_dashboard')
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import pipeline

if len(sys.argv) < 2:
    print("usage: ingest_lab16_mp.py <MMDD e.g. 0710>")
    sys.exit(1)

MMDD = sys.argv[1]                           # e.g. "0711"
DATE_DIR = f"2026.{MMDD[:2]}.{MMDD[2:]}"     # e.g. "2026.07.11"
SRC = f"/mnt/auto_match_out_div/{DATE_DIR}"  # read-only CIFS mount of 188
KEY = f"lab{MMDD}"
WORKERS = int(os.environ.get("WORKERS", "8"))    # gentle on server16 (12 cores/15GB)
LIMIT = int(os.environ.get("LIMIT", "0"))        # >0 => smoke test (first N pcaps)

# 결과물은 사용자 지정 위치에 날짜별 폴더로 (Z:\nmlab\99_sgs\01_datasets == server16:/nmlab/99_sgs/01_datasets)
OUT_BASE = Path("/nmlab/99_sgs/01_datasets")
out_dir = OUT_BASE / DATE_DIR
out_dir.mkdir(parents=True, exist_ok=True)
job_path = out_dir / "_job.json"

def jstate(**kw):
    pipeline.write_job(job_path, key=KEY, name=f"연구실 수집 {DATE_DIR} (server16 mp)", src=SRC, **kw)

print(f"[MP16 {KEY}] scan 시작... (src={SRC}, out={out_dir}, workers={WORKERS}, limit={LIMIT})", flush=True)
jstate(state="running", stage="scan", done=0, total=0)
tasks, hosts, dropped_files = pipeline.scan_src(Path(SRC), auto=False)
if LIMIT > 0:
    tasks = tasks[:LIMIT]
total = len(tasks)
print(f"[MP16 {KEY}] scan 완료: {total:,} pcaps, hosts={sorted(hosts)}", flush=True)
jstate(state="running", stage="extract", done=0, total=total)

csv_path = out_dir / f"session_stat_{KEY}.csv"
errors = []
t0 = time.time()

with open(csv_path, "w", encoding="utf-8-sig", newline="") as cf:
    w = csv.DictWriter(cf, fieldnames=pipeline.OUT_COLUMNS, extrasaction="ignore")
    w.writeheader()
    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        for i, (status, payload) in enumerate(executor.map(pipeline.process_pcap, tasks, chunksize=64), 1):
            if status == "OK":
                w.writerow(payload)
            else:
                errors.append(payload)
            if i % 2000 == 0 or i == total:
                rate = i / max(1e-9, time.time() - t0)
                eta = int((total - i) / max(rate, 1e-9))
                jstate(state="running", stage="extract", done=i, total=total,
                       errors=len(errors), eta_sec=eta)
                print(f"[MP16 {KEY}] {i:,}/{total:,} ({rate:.1f}/s, eta {eta}s, errors={len(errors)})", flush=True)

jstate(state="done", stage="extract", done=total, total=total, errors=len(errors))
print(f"[MP16 {KEY}] 완료: ok={total-len(errors):,} err={len(errors):,} ({time.time()-t0:.0f}s) -> {csv_path}", flush=True)
if errors:
    with open(out_dir / "_errors.log", "w", encoding="utf-8") as ef:
        for e in errors[:2000]:
            ef.write(e + "\n")
