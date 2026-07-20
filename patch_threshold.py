import io, time, shutil

P = "/nmlab/99_sgs/03_ML/lab_dashboard_demo/pipeline.py"
subs = [
    ('conf_threshold=0.5', 'conf_threshold=0.3'),
    ('"--conf-threshold", type=float, default=0.5', '"--conf-threshold", type=float, default=0.3'),
    ('신뢰도 임계(--conf-threshold, 기본 0.5)', '신뢰도 임계(--conf-threshold, 기본 0.3)'),
]
txt = io.open(P, encoding='utf-8').read()
if 'conf_threshold=0.3' in txt:
    print('이미 0.3 적용됨 — 건너뜀'); raise SystemExit(0)
bak = P + '.bak_thresh03_' + time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(P, bak); print('백업:', bak)
n = 0
for a, b in subs:
    c = txt.count(a)
    txt = txt.replace(a, b)
    print(f'  "{a[:40]}..." x{c}')
    n += c
io.open(P, 'w', encoding='utf-8').write(txt)
print(f'치환 {n}건 완료')
# 검증
v = io.open(P, encoding='utf-8').read()
print('남은 conf_threshold=0.5:', v.count('conf_threshold=0.5'),
      '| default=0.5(conf):', v.count('"--conf-threshold", type=float, default=0.5'))
