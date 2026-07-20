import io, time, shutil, re

APP = "/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/app.py"
txt = io.open(APP, encoding='utf-8').read()

NEW = ('  <div style="margin-top:18px"><a href="/static/compare_report.html" target="_blank" '
       'style="display:inline-flex;align-items:center;gap:10px;'
       'background:linear-gradient(90deg,#2563a8,#37d39b);color:#fff;padding:13px 24px;'
       'border-radius:10px;text-decoration:none;font-size:15px;font-weight:700;'
       'box-shadow:0 3px 14px rgba(55,211,155,.28)">📊 ML 자동라벨 성능 리포트'
       '<span style="font-weight:400;opacity:.9;font-size:12px">일치율 90.3% · threshold · 클래스 156종</span>'
       '</a></div>\n')

# 기존 버튼 div(어떤 형태든 compare_report.html 포함한 한 줄) 교체
pat = re.compile(r'^\s*<div style="margin-top:[^"]*"><a href="/static/compare_report\.html".*?</div>\n', re.M)
m = pat.search(txt)
if not m:
    print("기존 버튼 라인 못 찾음 — 중단"); raise SystemExit(1)
bak = APP + '.bak_btn2_' + time.strftime('%Y%m%d_%H%M%S')
shutil.copy2(APP, bak); print('백업:', bak)
txt = pat.sub(NEW, txt, count=1)
io.open(APP, 'w', encoding='utf-8').write(txt)
print('버튼 교체 완료')
print('확인:', 'compare_report.html' in txt, '| 리포트 텍스트:', 'ML 자동라벨 성능 리포트' in txt)
