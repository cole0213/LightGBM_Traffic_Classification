import io, os, time, shutil

APP = "/nmlab/99_sgs/03_ML/lab_dashboard_demo/app.py"
MARKER = "compare_report.html"        # 멱등성 체크
ANCHOR = "수집 폴더를 선택하면"          # 이 줄 뒤에 삽입

BUTTON = (
    '  <div style="margin-top:14px">'
    '<a href="/static/compare_report.html" target="_blank" '
    'style="display:inline-block;background:#1a2740;border:1px solid #2a3d56;'
    'color:#4db8ff;padding:8px 16px;border-radius:8px;text-decoration:none;'
    'font-size:14px;font-weight:600">📊 ML vs 폴더실측 비교 결과 보기</a></div>\n'
)

with io.open(APP, "r", encoding="utf-8") as f:
    lines = f.readlines()

if any(MARKER in ln for ln in lines):
    print("이미 버튼 있음 — 건너뜀")
    raise SystemExit(0)

bak = APP + ".bak_addbtn_" + time.strftime("%Y%m%d_%H%M%S")
shutil.copy2(APP, bak)
print("백업:", bak)

out = []
inserted = False
for ln in lines:
    out.append(ln)
    if (not inserted) and (ANCHOR in ln):
        out.append(BUTTON)
        inserted = True

if not inserted:
    print("앵커를 못 찾음 — 삽입 안 함")
    raise SystemExit(1)

with io.open(APP, "w", encoding="utf-8") as f:
    f.writelines(out)
print("버튼 삽입 완료")
