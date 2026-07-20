# -*- coding: utf-8 -*-
import json, html

CD = json.load(open('/nmlab/99_sgs/01_datasets/_class_dist.json', encoding='utf-8'))
CV = json.load(open('/nmlab/99_sgs/01_datasets/_compare_v2.json', encoding='utf-8'))
total = CD['total']; nclass = CD['n_classes']; classes = CD['classes']
maxs = classes[0]['sessions'] if classes else 1
agree = CV['overall_agree']; unk = CV['overall_unknown']

def e(s): return html.escape(str(s))

# 날짜별 (v2: 정규화 일관 채점, threshold 0.3)
order = ['0710','0711','0712','0713','0714']
day_rows = ""
for d in order:
    v = CV['per_day'][d]
    day_rows += f'<tr><td class="l">07/{d[2:]}</td><td class="num">{v["sessions"]:,}</td><td><div style="display:flex;align-items:center;gap:10px"><div class="bar"><i style="width:{v["agree"]}%"></i></div><span class="num">{v["agree"]:.2f}%</span></div></td><td class="num">{v["unknown"]:.2f}%</td></tr>'
day_rows += f'<tr class="total"><td class="l">전체</td><td class="num">{CV["total"]:,}</td><td><div style="display:flex;align-items:center;gap:10px"><div class="bar"><i style="width:{agree}%"></i></div><span class="num">{agree:.2f}%</span></div></td><td class="num">{unk:.2f}%</td></tr>'

sweep = [(0.0,0.00,90.44,90.44),(0.2,0.02,90.45,90.44),(0.3,0.40,90.69,90.33),
         (0.4,2.29,91.70,89.60),(0.5,5.17,92.97,88.16),(0.6,9.39,94.51,85.63),
         (0.7,13.90,95.72,82.41),(0.8,20.30,96.90,77.23)]
sweep_rows = ""
for thr,u,al,ov in sweep:
    cls = ' class="total"' if thr==0.3 else ''
    mk = ' <span class="tag" style="background:rgba(55,211,155,.15);color:var(--good);border-color:rgba(55,211,155,.35)">적용</span>' if thr==0.3 else (' <span style="color:var(--mut);font-size:11px">이전</span>' if thr==0.5 else '')
    sweep_rows += f'<tr{cls}><td class="l num">{thr:.1f}{mk}</td><td class="num">{u:.2f}%</td><td class="num">{al:.2f}%</td><td class="num">{ov:.2f}%</td></tr>'

mis_rows = ""
for m in CV['mismatches']:
    note = "브라우저↔시스템" if {m['folder'],m['ml']} & {'svchost','system'} and {m['folder'],m['ml']} & {'google_chrome','microsoft_edge'} else ("브라우저 계열" if {m['folder'],m['ml']}<= {'google_chrome','microsoft_edge'} else ("미분류→추정" if m['folder']=='unknown' else ""))
    nt = f'<span style="color:var(--mut)">{e(note)}</span>' if note else ""
    mis_rows += f'<tr><td class="l mono">{e(m["folder"])}</td><td class="arrow">→</td><td class="l mono">{e(m["ml"])}</td><td class="num">{m["count"]:,}</td><td class="l">{nt}</td></tr>'

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
<div class="sub">연구실 트래픽 · 2026-07-10 ~ 07-14 · 모델 <span class="mono">candidate_0710_0714</span> · threshold 0.3 · 라벨 정규화 일관 채점</div>
<div class="hero">
  <div class="kpi"><div class="n good">{agree:.1f}<span style="font-size:20px">%</span></div><div class="l">전체 일치율</div></div>
  <div class="kpi"><div class="n mono">{total:,}</div><div class="l">비교 세션 수 (5일)</div></div>
  <div class="kpi"><div class="n mono good">{unk:.2f}<span style="font-size:20px">%</span></div><div class="l">미분류율 (τ=0.3)</div></div>
  <div class="kpi"><div class="n mono acc">{nclass}</div><div class="l">클래스 수 (모델 학습 133)</div></div>
</div>
<div class="card"><h2>날짜별 일치율 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">정규화 일관 채점 · threshold 0.3</span></h2>
<table><thead><tr><th class="l">날짜</th><th>세션</th><th class="l" style="width:200px">일치율</th><th>미분류</th></tr></thead><tbody>{day_rows}</tbody></table>
<div class="note">폴더 실측·ML 예측 모두 동일 정규화(<span class="mono">build_app_display_map</span>) 적용 후 비교 → 표기 차이(riotclient/riot_client 등) 아티팩트 제거. 기존 채점(86.0%) 대비 <b>90.3%</b>로 정정.</div></div>

<div class="card"><h2>임계값(threshold) 트레이드오프</h2>
<table><thead><tr><th class="l">threshold</th><th>미분류%</th><th>라벨된 것 정답률</th><th>전체 정답률</th></tr></thead><tbody>{sweep_rows}</tbody></table>
<div class="note">모든 수치는 날짜별 표와 동일 기준(정규화 일관 채점). 0.5는 5.17%를 미분류로 감췄지만 그 예측도 대부분 맞았음 → <b>0.3으로 낮춰 미분류 5.17%→0.40%, 전체정답률 88.16%→90.33% 개선</b>. 낯선 앱 보류(안전장치) 위해 0 대신 0.3 채택.</div></div>

<div class="card"><h2>클래스별 세션 수 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">전체 {nclass}종 (앱/프로세스 단위)</span></h2>
<div class="scroll"><table><thead><tr><th>#</th><th class="l">클래스 (앱/프로세스)</th><th>세션 수</th><th>비율</th><th class="l">비중</th></tr></thead><tbody>{cls_rows}</tbody></table></div>
<div class="note">폴더 실측(task3) 기준, 표시명 정규화 적용. 상위 4종(svchost·Chrome·System·ServiceMapCollector)이 약 66%. 희소 클래스는 학습 제외 → 실제 학습 클래스 133종.</div></div>

<div class="card"><h2>상위 불일치 &nbsp;<span style="color:var(--mut);font-weight:400;font-size:13px">폴더실측 → ML예측 (정규화 일관 후)</span></h2>
<table><thead><tr><th class="l">폴더 실측</th><th></th><th class="l">ML 예측</th><th>건수</th><th class="l">비고</th></tr></thead><tbody>{mis_rows}</tbody></table>
<div class="note">표기 아티팩트 제거 후 남은 불일치는 전부 <b>브라우저 계열(chrome↔edge)</b> + <b>시스템 프로세스(svchost/system)</b> 혼동 — 트래픽만으론 구분이 어려운 물리적 한계 영역.</div></div>

<div class="card"><h2>개선 이력 (ver 0.1)</h2><ul class="notes">
<li><b>C · threshold 0.5→0.3</b>: 미분류 5.17%→0.40%, 전체정답률 향상. (적용됨)</li>
<li><b>B · 정규화 일관 채점</b>: 표기 아티팩트(riotclient 등) 제거 → 일치율 86.0%→<b>90.3%</b>.</li>
<li><b>A · 도메인 규칙 / prior 피처</b>: 효과 미미(도메인이 크롬과 공유 + 이미 피처로 사용 중). 미학습일 +0.01%p → 미채택.</li>
<li>남은 오차(브라우저/시스템 혼동)는 물리적 한계 — 큰 향상엔 더 다양한 학습 데이터/새 피처(JA3 등) 필요.</li>
<li>⚠️ 07/10~14는 학습 포함(fit) — 진짜 미학습일 일반화는 <b>약 80%</b>로 보수적으로 볼 것.</li>
</ul></div>
<div class="foot">생성: 2026-07-15 · lab_dashboard_demo · threshold 0.3 · 정규화 일관 채점</div>
</div></body></html>'''

open('/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/static/compare_report.html','w',encoding='utf-8').write(HTML)
print(f"WROTE report v2 · agree={agree}% unk={unk}% classes={nclass}")
