# -*- coding: utf-8 -*-
"""
backfill_sizes.py — 이미 처리된 데이터셋에 median_packet_size + size_fine_hist 주입.

pipeline.py 구버전(≤260703)으로 만든 데이터셋은 평균/최소/최대만 있고 중앙값·정밀
히스토그램이 없어 KPI 카드 MEDIAN이 0으로 표시된다. 이 스크립트는 원본 pcap을
frame.len **단일 필드**로만 고속 재패스(디세그먼트 OFF)해 (호스트,앱)별 크기 분포를
집계하고 data.json에 필드만 주입한다. (세션 CSV·다른 통계는 건드리지 않음)

pipeline.py 신버전으로 새로 넣는 데이터셋은 이 작업이 필요 없다(인라인 계산).

실행: python backfill_sizes.py --key lab0629 [--workers 12]
"""
import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import (DATASETS_DIR, scan_src, find_tshark,
                      median_from_counter, fine_hist_from_counter)

_TSHARK = None


def worker_init(tshark_path):
    global _TSHARK
    _TSHARK = tshark_path


def frame_lens(args):
    """pcap 1개 → (host, app, {frame.len: count}) 또는 (host, app, None)"""
    pcap_path, host, app = args
    cmd = [_TSHARK, "-r", pcap_path, "-n", "-T", "fields", "-e", "frame.len",
           "-o", "tcp.desegment_tcp_streams:FALSE",
           "-o", "tls.desegment_ssl_records:FALSE",
           "-o", "tls.desegment_ssl_application_data:FALSE"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=120)
    except Exception:
        return (host, app, None)
    if proc.returncode != 0:
        return (host, app, None)
    c = {}
    for tok in proc.stdout.split():
        try:
            n = int(tok)
        except ValueError:
            continue
        c[n] = c.get(n, 0) + 1
    return (host, app, c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    ds_dir = DATASETS_DIR / args.key
    info = json.loads((ds_dir / "info.json").read_text(encoding="utf-8"))
    src = Path(info["src"])
    dj_path = ds_dir / "data.json"
    data = json.loads(dj_path.read_text(encoding="utf-8"))

    tshark = find_tshark()
    if not tshark:
        sys.exit("tshark 없음")

    tasks, hosts = scan_src(src)
    total = len(tasks)
    print(f"[{args.key}] frame.len 재패스: {total:,} pcaps (src={src})")

    per_group = collections.defaultdict(collections.Counter)
    fails = 0
    t0 = time.time()
    with Pool(args.workers, initializer=worker_init, initargs=(tshark,)) as pool:
        for i, (host, app, c) in enumerate(pool.imap_unordered(frame_lens, tasks, chunksize=32), 1):
            if c is None:
                fails += 1
            else:
                per_group[(host, app)].update(c)
            if i % 5000 == 0 or i == total:
                rate = i / max(1e-9, time.time() - t0)
                print(f"  {i:,}/{total:,} ({rate:.0f}/s, 실패 {fails})", flush=True)

    # data.json 주입 (files[] 매칭키 = (service, app))
    bak = dj_path.with_suffix(".json.bak_presizes")
    if not bak.exists():
        shutil.copy2(dj_path, bak)
    injected = mismatch = 0
    for fe in data["files"]:
        c = per_group.get((fe["service"], fe["app"]))
        if not c:
            continue
        s = fe["stats"]
        n = sum(c.values())
        if n != s["packet_count"]:
            mismatch += 1     # 손상 pcap 재시도 결과 차이 등 — 주입은 진행(분포는 실측)
        s["median_packet_size"] = median_from_counter(c)
        s["size_fine_hist"] = fine_hist_from_counter(c)
        s["min_packet_size"] = min(c)
        s["max_packet_size"] = max(c)
        injected += 1

    dj_path.write_text(json.dumps(data, ensure_ascii=False, separators=(", ", ": ")),
                       encoding="utf-8")
    print(f"[{args.key}] DONE — files {injected}/{len(data['files'])} 주입, "
          f"패킷수 불일치 그룹 {mismatch}, pcap 실패 {fails}, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
