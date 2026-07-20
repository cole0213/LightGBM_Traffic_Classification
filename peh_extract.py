# -*- coding: utf-8 -*-
"""07/11~14 KJM pcap에서 PEH 1211피처(feature.py) 추출 — 앱별 층화 12만 샘플.
라벨=앱 폴더명. 결과 CSV를 5모델 벤치마크에 사용."""
import os, sys, re, time, random, warnings
import multiprocessing as mp
from collections import defaultdict
warnings.filterwarnings('ignore')
sys.path.append('/nmlab/98_PEH')

BASE = '/mnt/x_root/data/99_KJM/auto_match_out_div'
DAYS = ['2026.07.11', '2026.07.12', '2026.07.13', '2026.07.14']
TARGET = 120000
WORKERS = int(os.environ.get('WORKERS', '4'))   # 서버 부하 완화: 워커 수 제한
OUT = '/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/peh1205_lab.csv'
TS = re.compile(r'__\d{8}_\d{6}_\d+\.pcap$')

def list_dayhost(args):
    day, host = args; res = []
    hp = os.path.join(BASE, day, host)
    try: apps = os.listdir(hp)
    except Exception: return res
    for app in apps:
        ap = os.path.join(hp, app)
        try: files = os.listdir(ap)
        except Exception: continue
        for f in files:
            if TS.search(f):
                res.append((os.path.join(ap, f), app))
    return res

def extract_chunk(chunk):
    import feature, pandas as pd
    rows = []
    for path, label in chunk:
        try:
            pk = feature.rdpcap(path, count=1000)   # 대형 세션 메모리 폭증 방지 (피처는 최대 30패킷+100벡터만 사용)
        except Exception:
            continue
        try:
            flows = feature.process_packet(pk)
            if not flows: continue
            dfs = [feature.extract_meta(flows, label), feature.extract_header(flows),
                   feature.extract_flag(flows), feature.extract_scalar1(flows),
                   feature.extract_scalar2(flows), feature.extract_vector(flows)]
            rd = pd.concat(dfs, axis=1)
            rd.replace([float('inf'), float('-inf')], feature.MISSING, inplace=True)
            rd.fillna(feature.MISSING, inplace=True)
            for _, r in rd.iterrows():
                rows.append(r.to_dict())
        except Exception:
            continue
    return rows

def main():
    import pandas as pd
    t0 = time.time()
    tasks = []
    for day in DAYS:
        dp = os.path.join(BASE, day)
        try: hosts = os.listdir(dp)
        except Exception: continue
        for h in hosts: tasks.append((day, h))
    print(f'[enum] {len(tasks)} (day,host) dirs', flush=True)
    paths = []
    with mp.Pool(WORKERS) as pool:
        for i, r in enumerate(pool.imap_unordered(list_dayhost, tasks), 1):
            paths.extend(r)
            if i % 5 == 0 or i == len(tasks):
                print(f'  enum {i}/{len(tasks)} · total {len(paths):,} ({time.time()-t0:.0f}s)', flush=True)
    print(f'[enum] total real-session pcaps: {len(paths):,} ({time.time()-t0:.0f}s)', flush=True)

    byapp = defaultdict(list)
    for p, a in paths: byapp[a].append(p)
    total = len(paths); rng = random.Random(42); sel = []
    for a, lst in byapp.items():
        q = min(len(lst), round(TARGET * len(lst) / total))
        if q > 0:
            sel.extend((p, a) for p in rng.sample(lst, q))
    rng.shuffle(sel)
    print(f'[sample] apps={len(byapp)} selected={len(sel):,}', flush=True)

    chunks = [sel[i:i+150] for i in range(0, len(sel), 150)]
    master = None; n = 0
    with open(OUT, 'w', newline='', encoding='utf-8') as out, mp.Pool(WORKERS) as pool:
        for rows in pool.imap_unordered(extract_chunk, chunks):
            if not rows: continue
            df = pd.DataFrame(rows)
            if master is None:
                master = list(df.columns)
                df.to_csv(out, index=False, header=True)
            else:
                df = df.reindex(columns=master, fill_value='-')
                df.to_csv(out, index=False, header=False)
            n += len(df)
            if n % 6000 < 150:
                print(f'  extracted {n:,}/{len(sel):,} ({time.time()-t0:.0f}s)', flush=True)
    print(f'[DONE] {n:,} rows · {len(master)} cols → {OUT} ({time.time()-t0:.0f}s)', flush=True)
    print('DONE_PEH_EXTRACT', flush=True)

if __name__ == '__main__':
    main()
