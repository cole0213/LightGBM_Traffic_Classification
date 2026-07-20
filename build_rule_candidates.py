import sys, csv, collections
csv.field_size_limit(10**7)

def canon(s):
    s = str(s or '').strip()
    if not s:
        return ''
    s = s.lower()
    if s.endswith('.exe'):
        s = s[:-4]
    return s.replace(' ', '_').replace('-', '_')

TWO = {'co', 'or', 'ne', 'go', 'ac', 'com', 'net', 'org', 'edu', 'gov'}
def base_domain(h):
    h = str(h or '').strip().lower().rstrip('.')
    if not h or h.replace('.', '').isdigit():
        return ''
    parts = h.split('.')
    if len(parts) < 2:
        return ''
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in TWO:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])

days = ['0710', '0711', '0712', '0713', '0714']
sni = collections.defaultdict(collections.Counter)
dns = collections.defaultdict(collections.Counter)

for mmdd in days:
    f = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    with open(f, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            app = canon(row.get('task3'))
            if not app or app == 'unknown' or '미분류' in app:
                continue
            d = base_domain(row.get('tls_sni'))
            if d:
                sni[d][app] += 1
            d2 = base_domain(row.get('dns_qry'))
            if d2:
                dns[d2][app] += 1
    print(f"  scanned {mmdd}", flush=True)

def report(name, agg, minv=300, minp=0.90, topn=80):
    rows = []
    for dom, c in agg.items():
        tot = sum(c.values())
        app, cnt = c.most_common(1)[0]
        pur = cnt / tot
        if tot >= minv and pur >= minp:
            rows.append((tot, dom, app, pur))
    rows.sort(reverse=True)
    print(f"\n===== {name} 규칙 후보 (volume>={minv}, purity>={minp*100:.0f}%) — {len(rows)}개 =====", flush=True)
    print(f"  {'도메인':<36}{'→ 앱':<26}{'세션':>9}{'순도':>8}", flush=True)
    for tot, dom, app, pur in rows[:topn]:
        print(f"  {dom:<36}{app:<26}{tot:>9,}{pur*100:>7.1f}%", flush=True)

report("SNI", sni)
report("DNS", dns)
print("\nDONE_RULES", flush=True)
