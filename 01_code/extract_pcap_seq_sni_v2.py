#!/usr/bin/env python3
"""extract_pcap_sequences.py + 플로우별 SNI(tls.handshake.extensions_server_name) meta 추가."""
import argparse, csv, json, shutil, subprocess, time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

FIELDS = ['frame.time_epoch', 'frame.len', 'ip.src', 'ipv6.src', 'ip.dst', 'ipv6.dst', 'tcp.srcport', 'udp.srcport',
          'tcp.dstport', 'udp.dstport', 'tcp.stream', 'udp.stream', 'tcp.len', 'udp.length', 'tcp.window_size_value',
          'tcp.flags.syn', 'tcp.flags.ack', 'tcp.analysis.retransmission', 'tcp.analysis.fast_retransmission',
          'tls.handshake.extensions_server_name']  # index 19 = SNI
SUFFIXES = {'.pcap', '.pcapng', '.cap'}
def one(x): return x.split(',', 1)[0].strip() if x else ''
def num(x, t, d=0):
    try: return t(one(x))
    except (ValueError, TypeError): return d
def rows(bin, path, timeout=300, cap=0):
    cmd = [bin, '-n', '-r', str(path)]
    if cap > 0: cmd += ['-c', str(cap)]  # 앞 N패킷만 읽고 중단 → 초대용량(P2P 등) 파싱시간 급감. flow당 앞100패킷만 쓰므로 손실 적음
    cmd += ['-Y', 'tcp or udp', '-T', 'fields', '-E', 'header=n', '-E', 'separator=\t', '-E', 'quote=n', '-E', 'occurrence=f']
    cmd += [v for f in FIELDS for v in ('-e', f)]
    # 타임아웃 필수: 깨진 pcap 하나가 워커를 영원히 멈추는 것을 방지 (146만 규모 hang 원인)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf8', errors='replace', timeout=timeout)
    # truncated pcap: tshark가 대부분 파싱하고도 EOF에서 nonzero 반환 → stdout 있으면 파싱분 유지.
    # 진짜 실패(출력 0)만 예외. (ISCX pcap 다수가 끝부분 잘려있어 이 처리로 에러 대부분 사라짐)
    if p.returncode and not (p.stdout or '').strip():
        raise RuntimeError((p.stderr or '')[-500:] or f'tshark rc={p.returncode}, no output')
    for line in p.stdout.splitlines():
        r = line.split('\t'); yield r + [''] * (len(FIELDS) - len(r))
def key(r):
    tcp = bool(r[10]); proto = 'tcp' if tcp else 'udp'; src = one(r[2]) or one(r[3]); dst = one(r[4]) or one(r[5])
    a = (src, num(r[6] if tcp else r[7], int)); b = (dst, num(r[8] if tcp else r[9], int)); return (proto, a, b) if a <= b else (proto, b, a)
def packet(r):
    tcp = bool(r[10]); return (num(r[0], float), num(r[1], int), one(r[2]) or one(r[3]), num(r[12] if tcp else r[13], int), num(r[14], int, -1), num(r[15], int), num(r[16], int), int(bool(r[17] or r[18])))
def record(ps, k, path, root, n, sni='', label_depth=0):
    ps.sort(); client = next((p[2] for p in ps if p[5] and not p[6]), ps[0][2]); s = np.zeros(n, np.int16); d = np.zeros(n, np.int8); iat = np.zeros(n, np.float32); w = np.full(n, -1, np.int32); rt = np.zeros(n, np.uint8); pay = np.zeros(n, np.int16); mask = np.zeros(n, np.uint8); last = None
    for i, p in enumerate(ps[:n]):
        s[i] = np.clip(p[1], -32768, 32767); d[i] = 1 if p[2] == client else -1; iat[i] = 0 if last is None else max(0, (p[0] - last) * 1000); w[i] = p[4]; rt[i] = p[7]; pay[i] = np.clip(p[3], -32768, 32767); mask[i] = 1; last = p[0]
    ds = d[mask.astype(bool)]; runs = 0; longest = cur = 0; old = 0
    for x in ds:
        cur = cur + 1 if x == old else 1; runs += x != old; old = x; longest = max(longest, cur)
    rel = path.relative_to(root); meta = dict(pcap=str(rel), label=(rel.parts[label_depth] if len(rel.parts) > label_depth else (rel.parts[0] if rel.parts else '')), protocol=k[0], client_ip=client, endpoint_a=f'{k[1][0]}:{k[1][1]}', endpoint_b=f'{k[2][0]}:{k[2][1]}', sni=sni, packets_total=len(ps), packets_saved=int(mask.sum()), ts_first=round(float(ps[0][0]), 6), ts_last=round(float(ps[-1][0]), 6), duration_ms=round((ps[-1][0] - ps[0][0]) * 1000, 3), burst_count=runs, longest_burst=longest, up_ratio=round(float((ds > 0).mean()), 4), retrans_count=int(rt.sum()), mean_iat_ms=round(float(iat[1:mask.sum()].mean()) if mask.sum() > 1 else 0, 3)); return meta, (s, d, iat, w, rt, pay, mask)
def write(out, part, recs):
    a = list(zip(*[x[1] for x in recs])); base = out / f'sequences_part_{part:05d}'; np.savez_compressed(base.with_suffix('.npz'), packet_size=np.stack(a[0]), direction=np.stack(a[1]), iat_ms=np.stack(a[2]), tcp_window=np.stack(a[3]), retrans=np.stack(a[4]), payload_size=np.stack(a[5]), mask=np.stack(a[6]))
    with base.with_suffix('.csv').open('w', newline='', encoding='utf8') as f:
        o = csv.DictWriter(f, fieldnames=recs[0][0].keys()); o.writeheader(); o.writerows(x[0] for x in recs)
def process_pcap(spec):
    path, root, tshark, maximum, label_depth, tmo, cap = spec
    grouped = defaultdict(list); snis = {}
    try:
        for r in rows(tshark, path, tmo, cap):
            k = key(r); grouped[k].append(packet(r))
            if len(r) > 19 and one(r[19]) and not snis.get(k): snis[k] = one(r[19])
        return path, [record(ps, k, path, root, maximum, snis.get(k, ''), label_depth) for k, ps in grouped.items()], None
    except Exception as exc:
        return path, [], str(exc)
def main():
    a = argparse.ArgumentParser(); a.add_argument('--pcap-root', type=Path, required=True); a.add_argument('--out', type=Path, required=True); a.add_argument('--max-packets', type=int, default=100, choices=(20, 50, 100)); a.add_argument('--chunk-flows', type=int, default=5000); a.add_argument('--limit-pcaps', type=int, default=0); a.add_argument('--workers', type=int, default=1); a.add_argument('--tshark', default='tshark'); a.add_argument('--label-depth', type=int, default=0, help='pcap-root 기준 몇 번째 경로요소를 라벨로 쓸지 (LAB Week2: 날짜0/IP1/앱2 → 2)'); a.add_argument('--timeout', type=int, default=300, help='pcap당 tshark 타임아웃(초). 대용량 P2P/VoIP는 1800 권장'); a.add_argument('--cap-packets', type=int, default=0, help='pcap당 tshark가 읽을 최대 패킷수(-c). 0=제한없음. 초대용량(1GB+ P2P) 있으면 3000000 권장'); z = a.parse_args()
    if not shutil.which(z.tshark): a.error('tshark not found')
    root = z.pcap_root.resolve(); z.out.mkdir(parents=True, exist_ok=True)
    print('enumerating pcaps...', flush=True)
    files = [p for p in root.rglob('*') if p.suffix.lower() in SUFFIXES]; files.sort()
    if z.limit_pcaps: files = files[:z.limit_pcaps]
    total = len(files); print(f'total pcaps={total}', flush=True)
    recs = []; part = flows = errors = done = 0; err_list = []
    def flush():
        nonlocal recs, part
        if recs: write(z.out, part, recs); part += 1; recs = []
    # 146만 규모: 배치로 제출하고 as_completed(무순서)로 수집 → 한 파일이 느려도 전체가 안 막힘.
    BATCH = max(z.workers * 64, 2000)
    with ProcessPoolExecutor(max_workers=z.workers) as pool:
        for s in range(0, total, BATCH):
            futs = [pool.submit(process_pcap, (p, root, z.tshark, z.max_packets, z.label_depth, z.timeout, z.cap_packets)) for p in files[s:s + BATCH]]
            for fut in as_completed(futs):
                path, items, error = fut.result(); done += 1
                if error: errors += 1; err_list.append(f'{path}\t{error}')
                else:
                    for item in items:
                        recs.append(item); flows += 1
                        if len(recs) >= z.chunk_flows: flush()
                if done % 2000 == 0: print(f'[{done}/{total}] flows={flows} errors={errors}', flush=True)
    flush()
    if err_list: (z.out / 'errors.log').write_text('\n'.join(err_list), encoding='utf8')
    m = {'max_packets': z.max_packets, 'with_sni': True, 'pcaps_seen': total, 'flows_written': flows, 'parts': part, 'errors': errors, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}; (z.out / 'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf8'); print(json.dumps(m, ensure_ascii=False))
if __name__ == '__main__': main()
