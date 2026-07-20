# -*- coding: utf-8 -*-
import json, html

CD = json.load(open('/nmlab/99_sgs/01_datasets/_class_dist.json', encoding='utf-8'))
total = CD['total']; nclass = CD['n_classes']; classes = CD['classes']
maxs = classes[0]['sessions'] if classes else 1

per_day = [("07/10",538176,86.48,20.94,4.56),("07/11",458699,83.58,23.65,5.60),
           ("07/12",464257,84.29,24.58,6.03),("07/13",552792,87.89,23.04,4.98),
           ("07/14",262111,88.45,21.45,4.58)]
TOT = ("전체",2276035,86.02,22.79,5.17)

# threshold sweep: (thr, 미분류%, 라벨정답률%, 전체정답률%)
sweep = [(0.0,0.00,88.30,88.30),(0.2,0.02,88.31,88.29),(0.3,0.40,88.54,88.18),
         (0.4,2.29,89.51,87.46),(0.5,5.17,90.71,86.02),(0.6,9.39,92.14,83.49),
         (0.7,13.90,93.24,80.28),(0.8,20.30,94.24,75.11)]

mism = [("riotclient","riot_client",48749,"표기 차이(동일 앱)","tag"),
        ("unknown","google_chrome",13856,"미분류를 ML이 추정","mut"),
        ("google_chrome","svchost",13717,"브라우저↔시스템 혼동","mut"),
        ("svchost","google_chrome",11362,"시스템↔브라우저 혼동","mut"),
        ("system","servicemapcollector",9161,"",""),("notion","svchost",5911,"",""),
        ("svchost","notion",5264,"",""),("svchost","visual_studio",4167,"",""),
        ("microsoft_edge","google_chrome",3898,"브라우저 계열","mut"),
        ("microsoft_edge","svchost",3616,"",""),("servicemapcollector","system",3047,"",""),
        ("claude","svchost",2639,"",""),("svchost","spotify",2557,"",""),
        ("system","svchost",2508,"",""),("visual_studio","svchost",2472,"","")]

def e(s): return html.escape(str(s))

# 날짜별 행
day_rows = ""
for d,s,ag,ex,uk in per_day:
    day_rows += f'<tr><td class="l">{d}</td><td class="num">{s:,}</td><td><div style="display:flex;align-items:center;gap:10px"><div class="bar"><i style="width:{ag}%"></i></div><span class="num">{ag:.2f}%</span></div></td><td class="num">{ex:.2f}%</td><td class="num">{uk:.2f}%</td></tr>'
d,s,ag,ex,uk = TOT
day_rows += f'<tr class="total"><td class="l">{d}</td><td class="num">{s:,}</td><td><div style="display:flex;align-items:center;gap:10px"><div class="bar"><i style="width:{ag}%"></i></div><span class="num">{ag:.2f}%</span></div></td><td class="num">{ex:.2f}%</td><td class="num">{uk:.2f}%</td></tr>'

# 불일치 행
mis_rows = ""
for f,m,c,note,cls in mism:
    tag = f'<span class="tag">{e(note)}</span>' if cls=="tag" else (f'<span style="color:var(--mut)">{e(note)}</span>' if note else "")
    mis_rows += f'<tr><td class="l mono">{e(f)}</td><td class="arrow">→</td><td class="l mono">{e(m)}</td><td class="num">{c:,}</td><td class="l">{tag}</td></tr>'

# threshold sweep 행
sweep_rows = ""
for thr,unk,accl,ov in sweep:
    cls = ' class="total"' if thr==0.3 else ''
    mark = ' <span class="tag" style="background:rgba(55,211,155,.15);color:var(--good);border-color:rgba(55,211,155,.35)">적용</span>' if thr==0.3 else (' <span style="color:var(--mut);font-size:11px">이전</span>' if thr==0.5 else '')
    sweep_rows += f'<tr{cls}><td class="l num">{thr:.1f}{mark}</td><td class="num">{unk:.2f}%</td><td class="num">{accl:.2f}%</td><td class="num">{ov:.2f}%</td></tr>'

# 클래스별 세션 수 행 (전체)
cls_rows = ""
for i,c in enumerate(classes,1):
    w = c['sessions']/maxs*100
    cls_rows += f'<tr><td class="num" style="color:var(--mut)">{i}</td><td class="l mono">{e(c["app"])}</td><td class="num">{c["sessions"]:,}</td><td class="num">{c["pct"]:.2f}%</td><td style="width:160px"><div class="bar"><i style="width:{w:.2f}%"></i></div></td></tr>'

HTML = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ML 라벨 vs 폴더 실측 비교 (07/10~14)</title>
<style>
:root{{--bg:#0d1420;--card:#141d2e;--card2:#1a2740;--line:#26344d;--tx:#e6eef8;--mut:#8aa0bd;--acc:#4db8ff;--good:#37d39b;--warn:#ffcf5c;--mono:'JetBrains Mono',ui-monospace,Consolas,monospace;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;line-height:1.5}}
.wrap{{max-width:980px;margin:0 auto;padding:32px 20px 60px}} h1{{font-size:24px;margin:0 0 4px}}
.sub{{color:var(--mut);font-size:14px;margin-bottom:24px}}
.hero{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:28px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;flex:1;min-width:150px}}
.kpi .n{{font-size:32px;font-weight:700;font-family:var(--mono)}} .kpi .l{{color:var(--mut);font-size:13px;margin-top:2px}}
.good{{color:var(--good)}} .warn{{color:var(--warn)}} .acc{{color:var(--acc)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:22px}}
h2{{font-size:16px;margin:0 0 14px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line)}}
th{{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}}
td.l,th.l{{text-align:left}} tr:last-child td{{border-bottom:none}}
tr.total td{{font-weight:700;border-top:2px solid var(--acc);background:var(--card2)}}
.bar{{position:relative;height:8px;background:var(--card2);border-radius:99px;overflow:hidden;min-width:90px}}
.bar>i{{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#37d39b,#4db8ff);border-radius:99px}}
.num{{font-family:var(--mono)}} .mono{{font-family:var(--mono)}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;background:rgba(255,207,92,.15);color:var(--warn);border:1px solid rgba(255,207,92,.3)}}
.arrow{{color:var(--mut)}} .note{{color:var(--mut);font-size:13px;margin-top:10px}} .note b{{color:var(--tx)}}
ul.notes{{margin:8px 0 0;padding-left:18px;color:var(--mut);font-size:13.5px}} ul.notes li{{margin:5px 0}} ul.notes b{{color:var(--tx)}}
.scroll{{max-height:520px;overflow-y:auto;border:1px solid var(--line);border-radius:8px}}
.scroll table th{{position:sticky;top:0;background:var(--card2)}}
.foot{{color:var(--mut);font-size:12px;margin-top:26px;text-align:center}}
</style></head><body><div class="wrap">
<h1>📊 ML 자동 라벨 vs 폴더 실측 비교</h1>
<div class="sub">연구실 트래픽 · 2026-07-10 ~ 07-14 · 신규 모델 <span class="mono">candidate_0710_0714_folder_normalized</span></div>
<div class="hero">
  <div class="kpi"><div class="n good">86.0<span style="font-size:20px">%</span></div><div class="l">전체 일치율(정규화)</div></div>
  <div class="kpi"><div class="n mono">{total:,}</div><div class="l">비교 세션 수 (5일)</div></div>
  <div class="kpi"><div class="n mono warn">5.2<span style="font-size:20px">%</span></div><div class="l">미분류율</div></div>
  <div class="kpi"><div class="n mono acc">{nclass}</div><div class="l">클래스 수 (모델 학습 133)</div></div>
</div>
<div class="card"><h2>날짜별 일치율</h2>
<table><thead><tr><th class="l">날짜</th><th>세션</th><th class="l" style="width:180px">일치율(정규화)</th><th>정확일치</th><th>미분류</th></tr></thead><tbody>{day_rows}</tbody></table>
<div class="note"><b>정확일치</b>가 낮은 이유: 모델은 정규화 라벨(<span class="mono">google_chrome</span>)을 출력하는데 폴더 실측은 원형(<span class="mono">Google_Chrome</span>·<span class="mono">chrome.exe</span>)이라 문자열이 정확히 안 맞음 → <b>정규화 일치율(86%)이 실제 성능 지표</b>.</div></div>

<div class="card"><h2>임계값(threshold) 트레이드오프 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">미분류 vs 정답률</span></h2>
<table><thead><tr><th class="l">threshold</th><th>미분류%</th><th>라벨된 것 정답률</th><th>전체 정답률</th></tr></thead><tbody>{sweep_rows}</tbody></table>
<div class="note"><b>전체 정답률(=커버리지×정확도)</b>은 낮은 임계값에서 최대. 기존 0.5는 5.17%를 미분류로 감추지만 그 예측도 88% 맞았음 → <b>0.3으로 낮추면 미분류 5.17%→0.40%, 전체 정답률 86.02%→88.18%로 둘 다 개선</b>. 낯선 앱 보류(안전장치)는 유지하려고 0(전부 라벨) 대신 0.3 채택. <b>threshold 0.3 적용됨.</b></div></div>

<div class="card"><h2>클래스별 세션 수 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">전체 {nclass}종 (앱/프로세스 단위)</span></h2>
<div class="scroll"><table><thead><tr><th>#</th><th class="l">클래스 (앱/프로세스)</th><th>세션 수</th><th>비율</th><th class="l">비중</th></tr></thead><tbody>{cls_rows}</tbody></table></div>
<div class="note">폴더 실측(task3) 기준, 학습과 동일하게 표시명 정규화 적용. 상위 4종(svchost·Chrome·System·ServiceMapCollector)이 전체의 약 66%. 세션 수가 적은 희소 클래스(하위)는 모델 학습에서 제외되어 실제 학습 클래스는 133종.</div></div>

<div class="card"><h2>상위 불일치 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">폴더실측 → ML예측</span></h2>
<table><thead><tr><th class="l">폴더 실측</th><th></th><th class="l">ML 예측</th><th>건수</th><th class="l">비고</th></tr></thead><tbody>{mis_rows}</tbody></table></div>

<div class="card"><h2>해석 &amp; 참고</h2><ul class="notes">
<li>최대 불일치 <b>riotclient → riot_client(48,749건)</b>은 <b>표기 차이(같은 앱)</b> → 보정 시 실질 일치율 <b>약 88%</b>.</li>
<li>남은 오차는 <b>브라우저 계열(chrome/edge)</b> + <b>시스템 프로세스(svchost/system)</b> 구분 영역에 집중.</li>
<li>07/10~14는 학습에 쓴 날들이라 <b>fit 기준</b> — 미학습일 일반화는 보수적으로 볼 것.</li>
<li><b>미분류 ≠ 불일치</b>: 미분류=신뢰도&lt;0.5로 라벨 보류, 불일치=라벨은 달았으나 실측과 다름.</li>
</ul></div>
<div class="foot">생성: 2026-07-15 · lab_dashboard_demo · 비교표는 threshold 0.5 기준 · 운영 threshold 0.3 적용</div>
</div></body></html>'''

open('/nmlab/99_sgs/03_ML/lab_dashboard_demo/static/compare_report.html','w',encoding='utf-8').write(HTML)
print(f"WROTE report · classes={nclass} · total={total:,}")
