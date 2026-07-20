import csv, collections
csv.field_size_limit(10**7)

def canon(s):
    s = str(s or '').strip()
    if not s: return ''
    s = s.lower()
    if s.endswith('.exe'): s = s[:-4]
    return s.replace(' ', '_').replace('-', '_')

TWO = {'co','or','ne','go','ac','com','net','org','edu','gov'}
def base_domain(h):
    h = str(h or '').strip().lower().rstrip('.')
    if not h or h.replace('.', '').isdigit(): return ''
    p = h.split('.')
    if len(p) < 2: return ''
    if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in TWO: return '.'.join(p[-3:])
    return '.'.join(p[-2:])

TARGETS = {'codex','chatgpt','notion','claude','spotify','steam','discord',
           'kakaotalk','riotclient','leagueclient','microsoft_teams','antigravity','comet','genspark_claw'}

sni_glob = collections.defaultdict(collections.Counter)   # domain -> app counts (전역 순도용)
app_sni  = collections.defaultdict(collections.Counter)   # app -> its SNI domains

for mmdd in ['0710','0711','0712','0713','0714']:
    f = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    with open(f, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            app = canon(row.get('task3'))
            if not app or app == 'unknown' or '미분류' in app: continue
            d = base_domain(row.get('tls_sni'))
            if not d: continue
            sni_glob[d][app] += 1
            if app in TARGETS:
                app_sni[app][d] += 1
    print(f"  scanned {mmdd}", flush=True)

print("\n===== 타깃 앱별 SNI 시그니처 (도메인 · 이앱건수 · 전역지배앱/순도) =====", flush=True)
for app in sorted(TARGETS):
    doms = app_sni.get(app)
    if not doms:
        print(f"\n[{app}] SNI 세션 없음/희소", flush=True); continue
    tot = sum(doms.values())
    print(f"\n[{app}] SNI 보유 {tot:,}건, 상위 도메인:", flush=True)
    for dom, c in doms.most_common(8):
        g = sni_glob[dom]; gt = sum(g.values()); ga, gc = g.most_common(1)[0]
        flag = "★고유" if (ga == app and gc/gt >= 0.9) else ("~공유" if ga == app else f"→{ga}")
        print(f"    {dom:<30}{c:>7,}건  | 전역 {ga}/{gc/gt*100:.0f}% [{flag}]", flush=True)
print("\nDONE_RULES2", flush=True)
