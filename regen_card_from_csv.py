import sys, os, csv, json, collections
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import pipeline

csv.field_size_limit(10**7)
DEMO = '/nmlab/99_sgs/03_ML/lab_dashboard_demo'
DSDIR = os.path.join(DEMO, 'static', 'datasets')
TZ = 9

MMDD = sys.argv[1]                 # e.g. 0710
mm, dd = MMDD[:2], MMDD[2:]
DATEDOT = f"2026.{mm}.{dd}"
DATEDASH = f"2026-{mm}-{dd}"
KEY = f"lab{MMDD}"
CSVF = f"/nmlab/99_sgs/01_datasets/{DATEDOT}/session_stat_{KEY}.csv"
NAME = f"연구실 수집 {DATEDASH}"
SRC = f"/nmlab/99_sgs/01_datasets/{DATEDOT}"
outdir = os.path.join(DSDIR, KEY)
os.makedirs(outdir, exist_ok=True)

def num(x, cast=int, d=0):
    try:
        return cast(float(x)) if x not in (None, '', '-') else d
    except (ValueError, TypeError):
        return d

# pass1: 고유 task3 라벨 + 호스트 수집
print(f"[{KEY}] pass1 스캔...", flush=True)
labels = set(); hosts = set()
with open(CSVF, encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        labels.add(str(row.get('task3', '')))
        h = row.get('task2') or '-'
        if h != '-':
            hosts.add(h)
dmap = pipeline.build_app_display_map(labels)
n_hosts = len(hosts) or 1
print(f"[{KEY}] labels={len(labels)} hosts={n_hosts}", flush=True)

# pass2: 스트리밍으로 rows 생성 (패킷크기 분포는 평균값 근사)
def gen():
    with open(CSVF, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            pkt = num(row.get('pkt_count'))
            byt = num(row.get('payload_size'))
            fb = num(row.get('frame_bytes'))
            # 패킷별 크기 분포는 CSV에 없음 → 추정하지 않고 비워둠(데이터 없음)
            sizebins = [0] * len(pipeline.PSIZE_LABELS)
            t3 = str(row.get('task3', ''))
            yield {
                'task2': row.get('task2') or '-',
                'task3': dmap.get(t3, t3),
                'pkt_count': pkt, 'payload_size': byt, 'frame_bytes': fb,
                'L3': row.get('L3') or 'ipv4', 'L4': row.get('L4') or '',
                'L7': row.get('L7') or '-',
                'src_ip': row.get('src_ip') or '-', 'dst_ip': row.get('dst_ip') or '-',
                'src_port': row.get('src_port') or '-', 'dst_port': row.get('dst_port') or '-',
                'ts_first': row.get('ts_first') or 0, 'ts_last': row.get('ts_last') or 0,
                'tls_sni': row.get('tls_sni') or '', 'http_uri': row.get('http_uri') or '',
                'dns_qry': row.get('dns_qry') or '', 'http_ua': row.get('http_ua') or '',
                '_fmin': None, '_fmax': 0,
                '_size_bins': sizebins,
                '_sizes': collections.Counter(),
            }

print(f"[{KEY}] build_datajson...", flush=True)
data = pipeline.build_datajson(gen(), KEY, NAME, SRC, TZ)
data['meta']['dropped_flows'] = 0
data['meta']['dropped_packets'] = 0
data['meta']['match_coverage'] = None

tmp = os.path.join(outdir, 'data.json.tmp')
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(", ", ": "))
os.replace(tmp, os.path.join(outdir, 'data.json'))

with open(os.path.join(outdir, 'config.js'), 'w', encoding='utf-8') as f:
    f.write(pipeline.CONFIG_TMPL.format(key=KEY, name=NAME,
            label_note="NMLab 자동 수집(소켓-프로세스 매칭)"))

n_sessions = data['summary']['all']['tcp_sessions'] + data['summary']['all']['udp_sessions']
with open(os.path.join(outdir, 'collection.html'), 'w', encoding='utf-8') as f:
    f.write(pipeline.COLLECTION_TMPL.format(src=SRC, hosts=n_hosts, sessions=n_sessions,
            generated=data['meta']['generated_at'][:10], coverage_li=""))

info = {
    "key": KEY, "name": NAME,
    "desc": f"세션 {n_sessions:,} · 앱 {len(data['by_app'])}종 · 호스트 {n_hosts}대",
    "src": SRC, "created": data['meta']['generated_at'],
    "sessions": n_sessions, "apps": len(data['by_app']),
    "auto_label": False, "dropped_flows": 0, "dropped_packets": 0, "coverage": None,
}
with open(os.path.join(outdir, 'info.json'), 'w', encoding='utf-8') as f:
    json.dump(info, f, ensure_ascii=False, indent=1)

print(f"[{KEY}] DONE sessions={n_sessions:,} apps={len(data['by_app'])} -> {outdir}", flush=True)
