# -*- coding: utf-8 -*-
"""
lab_dashboard — 연구실 수집 트래픽 대시보드 (traffic_dashboard와 별도 앱, 기본 포트 5002)

기능:
  • 랜딩: 처리된 데이터셋 카드 + [새 데이터셋 추가] — 서버측 폴더 브라우저로 수집 폴더 선택
  • 추가 시 pipeline.py를 백그라운드 실행(자동 라벨링=폴더명, tshark 추출, data.json 생성)
    → 진행률 폴링 → 완료되면 카드 자동 등장
  • 데이터셋 화면은 traffic_dashboard ver2.0과 동일 엔진(static/dashboard.html + app.js)

실행: python app.py   (이 윈도우 PC에서 — tshark·Z: 접근 필요)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR / "static" / "datasets"
PIPELINE = BASE_DIR / "pipeline.py"

# 폴더 브라우저가 접근할 수 있는 루트 (env LAB_DATA_ROOTS 로 확장 가능, ; 구분)
DEFAULT_ROOTS = [
    r"X:\data\99_KJM\auto_match_out_div",
    r"Z:\data\99_KJM\auto_match_out_div",
]
ALLOWED_ROOTS = [p for p in (os.environ.get("LAB_DATA_ROOTS", "").split(";") if os.environ.get("LAB_DATA_ROOTS") else DEFAULT_ROOTS) if p]

app = Flask(__name__, static_folder="static", static_url_path="/static")

KEY_RE = re.compile(r"^[a-z0-9_]{2,32}$")
_procs = {}   # key -> Popen


def list_datasets():
    out = []
    if not DATASETS_DIR.is_dir():
        return out
    for d in sorted(DATASETS_DIR.iterdir()):
        if not d.is_dir():
            continue
        info = {}
        ip = d / "info.json"
        if ip.exists():
            try:
                info = json.loads(ip.read_text(encoding="utf-8"))
            except Exception:
                info = {}
        if not (d / "config.js").exists() and not info:
            continue
        out.append({
            "key": d.name,
            "name": info.get("name", d.name),
            "desc": info.get("desc", ""),
            "created": info.get("created", ""),
            "auto_label": bool(info.get("auto_label")),
            "ready": (d / "data.json").exists() and (d / "config.js").exists(),
        })
    return out


def list_jobs():
    jobs = []
    if not DATASETS_DIR.is_dir():
        return jobs
    for d in DATASETS_DIR.iterdir():
        jp = d / "_job.json"
        if not jp.exists():
            continue
        try:
            j = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        # 프로세스가 죽었는데 running으로 남은 잡 → stalled 표기
        if j.get("state") == "running":
            p = _procs.get(d.name)
            alive = p is not None and p.poll() is None
            if not alive and time.time() - j.get("updated", 0) > 180:
                j["state"] = "stalled"
        jobs.append(j)
    jobs.sort(key=lambda x: -(x.get("updated") or 0))
    return jobs


def safe_browse_path(raw):
    """허용 루트 밑의 실제 디렉토리만 통과."""
    if not raw:
        return None
    p = os.path.realpath(raw)
    for root in ALLOWED_ROOTS:
        r = os.path.realpath(root)
        try:
            if os.path.commonpath([p.lower(), r.lower()]) == r.lower() and os.path.isdir(p):
                return p
        except ValueError:      # 드라이브가 다르면 commonpath가 던짐
            continue
    return None


# ─────────────────────────────────────
# 랜딩
# ─────────────────────────────────────
LANDING_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>연구실 트래픽 대시보드</title>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Noto Sans KR', sans-serif; background: #0f1419; color: #e6edf3;
           display: flex; flex-direction: column; align-items: center;
           min-height: 100vh; margin: 0; padding: 48px 0; box-sizing: border-box; }
    h1 { font-size: 2rem; margin: 0 0 0.5rem; }
    .sub { opacity: 0.6; margin-bottom: 2.2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.4rem; max-width: 980px; width: 92%; }
    .card { background: #1a2028; border: 1px solid #2a3340; border-radius: 12px;
            padding: 1.6rem; text-decoration: none; color: inherit;
            transition: transform .15s, border-color .15s; position: relative; }
    .dataset-card { cursor: pointer; padding-right: 3.2rem; }
    .card:hover { transform: translateY(-4px); border-color: #00ffa3; }
    .card-name { font-size: 1.25rem; font-weight: 700; margin-bottom: .45rem; color: #00ffa3; }
    .card-desc { font-size: .88rem; opacity: .75; }
    .card-date { font-size: .72rem; opacity: .45; margin-top: .6rem; }
    .card.add { border-style: dashed; border-color: #3a4a5e; display: flex; flex-direction: column;
                align-items: center; justify-content: center; cursor: pointer; min-height: 130px; }
    .card.add:hover { border-color: #00d4ff; }
    .card.add .plus { font-size: 2.2rem; color: #00d4ff; line-height: 1; }
    .card.add .lbl { font-size: .9rem; opacity: .7; margin-top: .5rem; }
    .card.job { border-color: #2a5a8a; cursor: default; }
    .bar { height: 8px; background: #0c1420; border-radius: 4px; overflow: hidden; margin-top: .8rem; }
    .bar > div { height: 100%; background: linear-gradient(90deg, #00d4ff, #00ffa3); transition: width .5s; }
    .job-stat { font-size: .78rem; opacity: .7; margin-top: .45rem; font-variant-numeric: tabular-nums; }
    .job-err { color: #ff5e8a; }
    .delete-card { position: absolute; top: 12px; right: 12px; width: 30px; height: 30px;
                   border-radius: 50%; border: 1px solid #4a2a36; background: #251821;
                   color: #ff7b9b; font-size: 1.15rem; line-height: 1; cursor: pointer;
                   display: flex; align-items: center; justify-content: center; }
    .delete-card:hover { background: #3a1d2a; border-color: #ff5e8a; color: #ffd4df; }
    .ml-compare-btn { position: absolute; bottom: 12px; right: 12px;
                      background: #0f2a1e; border: 1px solid #1a5a3a; border-radius: 6px;
                      color: #00ffa3; font-size: .68rem; padding: 4px 9px; cursor: pointer;
                      font-family: 'Noto Sans KR', sans-serif; letter-spacing: .3px;
                      transition: background .15s, border-color .15s; white-space: nowrap; }
    .ml-compare-btn:hover { background: #163d29; border-color: #00ffa3; }
    /* modal */
    .ov { position: fixed; inset: 0; background: rgba(2,8,16,.65); display: none;
          align-items: center; justify-content: center; z-index: 100; }
    .ov.open { display: flex; }
    .panel { width: min(640px, 94vw); max-height: 86vh; overflow-y: auto; background: #141b24;
             border: 1px solid #2a3d56; border-radius: 14px; padding: 22px 24px; }
    .panel h2 { margin: 0 0 14px; font-size: 1.15rem; }
    .crumbs { font-size: .78rem; color: #6fa8cc; margin-bottom: 8px; word-break: break-all; }
    .crumbs span { cursor: pointer; } .crumbs span:hover { text-decoration: underline; }
    .flist { border: 1px solid #22334a; border-radius: 8px; max-height: 300px; overflow-y: auto;
             background: #0e1520; }
    .frow { display: flex; align-items: center; gap: 8px; padding: 7px 12px; font-size: .86rem;
            cursor: pointer; border-bottom: 1px solid #16202e; }
    .frow:hover { background: #16233490; }
    .frow .ico { opacity: .6; }
    .frow .cnt { margin-left: auto; font-size: .72rem; opacity: .5; }
    .field { margin-top: 14px; }
    .field label { display: block; font-size: .78rem; opacity: .65; margin-bottom: 4px; }
    .field input { width: 100%; box-sizing: border-box; background: #0e1520; color: #e6edf3;
                   border: 1px solid #2a3d56; border-radius: 6px; padding: 8px 10px; font-size: .9rem; }
    .btns { display: flex; gap: 10px; margin-top: 18px; justify-content: flex-end; }
    .btn { background: #1c2836; color: #cfe3f2; border: 1px solid #2f4a68; border-radius: 8px;
           padding: 9px 18px; font-size: .9rem; cursor: pointer; }
    .btn.primary { background: #0a4738; border-color: #00ffa3; color: #aef7dd; }
    .btn:disabled { opacity: .4; cursor: not-allowed; }
    .hint { font-size: .75rem; opacity: .55; margin-top: 10px; line-height: 1.5; }
    .msg { font-size: .82rem; margin-top: 10px; color: #ffb454; min-height: 1em; }
    /* ML 비교 모달 */
    .cmp-panel { width: min(780px, 96vw); max-height: 90vh; overflow-y: auto; background: #0f1923;
                 border: 1px solid #1a3a56; border-radius: 16px; padding: 28px 28px 24px; }
    .cmp-panel h2 { margin: 0 0 4px; font-size: 1.2rem; color: #e6edf3; }
    .cmp-subtitle { font-size: .78rem; color: #4a7a9b; margin-bottom: 20px; }
    .cmp-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
    .cmp-stat { flex: 1; min-width: 120px; background: #141f2e; border: 1px solid #1e3248;
                border-radius: 10px; padding: 14px 16px; }
    .cmp-stat .val { font-size: 1.5rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;
                     line-height: 1.1; margin-bottom: 4px; }
    .cmp-stat .lbl { font-size: .7rem; color: #4a7a9b; letter-spacing: .5px; text-transform: uppercase; }
    .cmp-section-title { font-size: .7rem; font-weight: 700; letter-spacing: 1.5px;
                         color: #4a7a9b; margin: 18px 0 8px; font-family: 'JetBrains Mono', monospace; }
    .cmp-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .cmp-table th { text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e3248;
                    color: #4a7a9b; font-weight: 600; font-size: .72rem; letter-spacing: .5px; }
    .cmp-table td { padding: 7px 8px; border-bottom: 1px solid #111c28; vertical-align: middle; }
    .cmp-table tr:hover td { background: #141f2e; }
    .cmp-table .bar-cell { width: 90px; }
    .cmp-bar-wrap { background: #0a1420; border-radius: 3px; height: 6px; overflow: hidden; }
    .cmp-bar-fill { height: 100%; border-radius: 3px;
                    background: linear-gradient(90deg, #ff6b8a, #ffb454); }
    .tag-folder { color: #ff8aa8; font-family: 'JetBrains Mono', monospace; font-size: .75rem; }
    .tag-ml { color: #ffd9a0; font-family: 'JetBrains Mono', monospace; font-size: .75rem; }
    .tag-arrow { color: #2a4a6a; margin: 0 4px; }
    .cmp-loading { text-align: center; padding: 40px 0; color: #4a7a9b; font-size: .9rem; }
    .cmp-close { float: right; background: none; border: none; color: #4a7a9b;
                 font-size: 1.4rem; cursor: pointer; line-height: 1; margin-top: -4px; }
    .cmp-close:hover { color: #e6edf3; }
  </style>
</head>
<body>
  <h1>🧪 연구실 트래픽 대시보드</h1>
  <div class="sub">수집 폴더를 선택하면 자동으로 라벨링·분석되어 카드가 추가됩니다</div>
  <div style="margin-top:18px"><a href="/static/compare_report.html" target="_blank" style="display:inline-flex;align-items:center;gap:10px;background:linear-gradient(90deg,#2563a8,#37d39b);color:#fff;padding:13px 24px;border-radius:10px;text-decoration:none;font-size:15px;font-weight:700;box-shadow:0 3px 14px rgba(55,211,155,.28)">📊 ML 자동라벨 성능 리포트<span style="font-weight:400;opacity:.9;font-size:12px">일치율 90.3% · threshold · 클래스 156종</span></a></div>
  <div class="grid" id="grid"></div>

  <div class="ov" id="ov">
    <div class="panel">
      <h2>새 데이터셋 추가</h2>
      <div class="crumbs" id="crumbs"></div>
      <div class="flist" id="flist"></div>
      <div class="field"><label>선택된 폴더</label><input id="selpath" readonly></div>
      <div style="display:flex;gap:10px;">
        <div class="field" style="flex:1;"><label>키 (영소문자·숫자·_)</label><input id="key" placeholder="lab0629"></div>
        <div class="field" style="flex:2;"><label>표시 이름</label><input id="name" placeholder="연구실 수집 2026-06-29"></div>
      </div>
      <div class="field" style="margin-top:12px;">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;opacity:1;font-size:.86rem;color:#ffd9a0;">
          <input id="autolabel" type="checkbox" style="width:auto;margin:0;">
          자동 라벨링(ML) — 폴더 라벨을 쓰지 않고 학습된 모델이 앱을 추론
        </label>
      </div>
      <div class="hint">날짜 폴더(호스트 전체) 또는 호스트 폴더 하나를 선택하세요. pcap 수에 따라 수 분~1시간 소요됩니다. 앱 라벨은 기본으로 수집기의 소켓-프로세스 매칭(폴더명)을 사용하며, 위 체크 시 ML 모델이 세션 통계만으로 추론합니다(앱 폴더 구조가 없는 pcap 폴더도 가능).</div>
      <div class="msg" id="msg"></div>
      <div class="btns">
        <button class="btn" onclick="closeOv()">취소</button>
        <button class="btn primary" id="go" onclick="startIngest()">가져오기 시작</button>
      </div>
    </div>
  </div>

  <!-- ML 비교 결과 모달 -->
  <div class="ov" id="cmp-ov">
    <div class="cmp-panel">
      <button class="cmp-close" onclick="closeCmp()">×</button>
      <h2 id="cmp-title">📊 ML 라벨 비교 결과</h2>
      <div class="cmp-subtitle" id="cmp-subtitle"></div>
      <div id="cmp-body"><div class="cmp-loading">⏳ 분석 중...</div></div>
    </div>
  </div>

<script>
function esc(s){ return String(s).replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c])); }
const SEP = String.fromCharCode(92);   // 단일 백슬래시 (이스케이프 지옥 회피)

async function refresh(){
  const [ds, jobs] = await Promise.all([
    fetch('/api/datasets').then(r=>r.json()),
    fetch('/api/jobs').then(r=>r.json()),
  ]);
  const grid = document.getElementById('grid');
  const readyKeys = new Set(ds.filter(d=>d.ready).map(d=>d.key));
  let html = '';
  for (const j of jobs){
    if (j.state === 'done') continue;
    if (j.state === 'running' && readyKeys.has(j.key)) continue;
    const pct = j.total ? Math.round(j.done / j.total * 100) : 0;
    const stage = j.state === 'error' ? `<span class="job-err">실패: ${esc(j.error||'원인 미상')}</span>`
      : (j.stage === 'extract' ? '세션 추출 중' : j.stage === 'infer' ? 'ML 앱 라벨 추론 중' : j.stage === 'generate' ? 'data.json 생성 중' : j.stage === 'scan' ? '폴더 스캔 중' : esc(j.stage||''))
        + (j.state === 'stalled' ? ' <span class="job-err">(중단됨?)</span>' : '');
    html += `<div class="card job"><button class="delete-card" title="삭제" data-name="${esc(j.name||j.key)}" onclick="deleteDataset('${esc(j.key)}',this.dataset.name,event)">×</button><div class="card-name" style="color:#00d4ff;">${esc(j.name||j.key)}</div>
      <div class="card-desc">${stage}</div>
      <div class="bar"><div style="width:${pct}%"></div></div>
      <div class="job-stat">${(j.done||0).toLocaleString()} / ${(j.total||0).toLocaleString()} (${pct}%)${j.errors ? ` · 오류 ${j.errors}`:''}${j.state==='running' && j.eta_sec ? ` · 약 ${Math.max(1,Math.ceil(j.eta_sec/60))}분 남음`:''}</div></div>`;
  }
  for (const d of ds){
    if (!d.ready) continue;
    const badge = d.auto_label ? ' <span style="font-size:.62rem;background:#4a3010;border:1px solid #8a5a20;color:#ffd9a0;border-radius:4px;padding:1px 6px;vertical-align:middle;">ML 라벨</span>' : '';
    const cmpBtn = d.auto_label
      ? `<button class="ml-compare-btn" onclick="openCmp('${esc(d.key)}','${esc(d.name)}',event)">📊 비교 결과</button>`
      : '';
    html += `<div class="card dataset-card" onclick="location.href='/${esc(d.key)}/'"><button class="delete-card" title="삭제" data-name="${esc(d.name)}" onclick="deleteDataset('${esc(d.key)}',this.dataset.name,event)">×</button><div class="card-name">${esc(d.name)}${badge}</div>
      <div class="card-desc">${esc(d.desc)}</div><div class="card-date">${esc(d.created)}</div>${cmpBtn}</div>`;
  }
  html += `<div class="card add" id="add-card"><div class="plus">＋</div><div class="lbl">새 데이터셋 추가 (폴더 선택)</div></div>`;
  grid.innerHTML = html;
  document.getElementById('add-card').addEventListener('click', openOv);
}

async function browse(path){
  const q = path ? ('?path=' + encodeURIComponent(path)) : '';
  const r = await fetch('/api/browse' + q);
  const d = await r.json();
  if (d.error){ document.getElementById('msg').textContent = d.error; return; }
  document.getElementById('selpath').value = d.path || '';

  // 경로 조각 내비게이션 (이벤트 위임 — 문자열 이스케이프 불필요)
  const cr = document.getElementById('crumbs');
  cr.innerHTML = '';
  if (!d.path){
    cr.textContent = '루트 선택';
  } else {
    const parts = d.path.split(SEP);
    let acc = '';
    parts.forEach((p, i) => {
      acc = acc ? acc + SEP + p : p;
      const target = acc;
      const sp = document.createElement('span');
      sp.textContent = p;
      sp.addEventListener('click', () => browse(target));
      cr.appendChild(sp);
      if (i < parts.length - 1){
        const sep = document.createElement('span');
        sep.textContent = ' › ';
        sep.style.opacity = '.4';
        sep.style.cursor = 'default';
        cr.appendChild(sep);
      }
    });
  }

  const fl = document.getElementById('flist');
  fl.innerHTML = '';
  const mkRow = (icon, label, onclick) => {
    const div = document.createElement('div');
    div.className = 'frow';
    div.innerHTML = `<span class="ico">${icon}</span> ${esc(label)}`;
    if (onclick) div.addEventListener('click', onclick);
    else { div.style.cursor = 'default'; div.style.opacity = '.5'; }
    fl.appendChild(div);
  };
  if (d.up !== null && d.up !== undefined)
    mkRow('↩', '..', () => browse(d.up || null));
  for (const e of d.dirs)
    mkRow('📁', e.name, () => browse(e.path));
  if (!d.dirs.length)
    mkRow('ℹ', '하위 폴더 없음 — 이 폴더를 가져올 수 있습니다', null);

  // 날짜 폴더면 key/name 자동 제안
  if (d.path){
    const base = d.path.split(SEP).pop();
    const m = base.match(/^(\\d{4})\\.(\\d{2})\\.(\\d{2})$/);
    if (m){
      document.getElementById('key').value = 'lab' + m[2] + m[3];
      document.getElementById('name').value = '연구실 수집 ' + m[1] + '-' + m[2] + '-' + m[3];
    }
  }
}

function openOv(){ document.getElementById('ov').classList.add('open'); document.getElementById('msg').textContent=''; browse(null); }
function closeOv(){ document.getElementById('ov').classList.remove('open'); }
function closeCmp(){ document.getElementById('cmp-ov').classList.remove('open'); }

async function openCmp(key, name, ev){
  if (ev){ ev.preventDefault(); ev.stopPropagation(); }
  document.getElementById('cmp-title').textContent = '📊 ML 라벨 비교 결과';
  document.getElementById('cmp-subtitle').textContent = name;
  document.getElementById('cmp-body').innerHTML = '<div class="cmp-loading">⏳ CSV 분석 중... (수십 초 소요될 수 있습니다)</div>';
  document.getElementById('cmp-ov').classList.add('open');
  try {
    const r = await fetch(`/api/ml_compare/${key}`);
    const d = await r.json();
    if (d.error){ document.getElementById('cmp-body').innerHTML = `<div class="cmp-loading" style="color:#ff8aa8">${esc(d.error)}</div>`; return; }
    renderCmp(d);
  } catch(e) {
    document.getElementById('cmp-body').innerHTML = `<div class="cmp-loading" style="color:#ff8aa8">오류: ${esc(String(e))}</div>`;
  }
}

function renderCmp(d){
  const agPct = d.agreement_pct != null ? d.agreement_pct.toFixed(1) + '%' : '-';
  const unkPct = d.unknown_pct != null ? d.unknown_pct.toFixed(1) + '%' : '-';
  const confVal = d.mean_conf != null ? (d.mean_conf * 100).toFixed(1) + '%' : '-';
  const maxCount = d.mismatches.length ? d.mismatches[0].count : 1;
  let rows = d.mismatches.map(m => {
    const pct = Math.round(m.count / maxCount * 100);
    return `<tr>
      <td><span class="tag-folder">${esc(m.folder)}</span><span class="tag-arrow">→</span><span class="tag-ml">${esc(m.ml)}</span></td>
      <td class="bar-cell"><div class="cmp-bar-wrap"><div class="cmp-bar-fill" style="width:${pct}%"></div></div></td>
      <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:.78rem;color:#c0d8f0;">${m.count.toLocaleString()}</td>
    </tr>`;
  }).join('');
  document.getElementById('cmp-body').innerHTML = `
    <div class="cmp-stat-row">
      <div class="cmp-stat"><div class="val" style="color:#00ffa3">${agPct}</div><div class="lbl">폴더 라벨 일치율</div></div>
      <div class="cmp-stat"><div class="val" style="color:#ffd9a0">${confVal}</div><div class="lbl">평균 예측 신뢰도</div></div>
      <div class="cmp-stat"><div class="val" style="color:#ff8aa8">${unkPct}</div><div class="lbl">미분류 비율 (τ<${esc(String(d.threshold))})</div></div>
      <div class="cmp-stat"><div class="val" style="color:#7fb8d8">${(d.sessions||0).toLocaleString()}</div><div class="lbl">총 세션 수</div></div>
    </div>
    <div class="cmp-section-title">FOLDER → ML 불일치 TOP ${d.mismatches.length} (폴더 라벨이 있는 세션만)</div>
    <table class="cmp-table">
      <thead><tr><th>폴더 라벨 → ML 예측</th><th>비율</th><th style="text-align:right">세션 수</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="font-size:.7rem;color:#2a4a6a;margin-top:14px;">* 폴더 라벨(task3_folder)과 ML 예측(task3)이 다른 경우만 집계 · 학습: ${esc(d.model_trained_at||'-')} · 모델 클래스 ${d.model_classes||'-'}개</div>
  `;
}

async function deleteDataset(key, name, ev){
  if (ev){ ev.preventDefault(); ev.stopPropagation(); }
  if (!confirm(`${name} 데이터셋을 삭제할까요?\nstatic/datasets/${key} 폴더가 삭제됩니다.`)) return;
  const r = await fetch('/api/delete_dataset', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ key }) });
  const d = await r.json();
  if (d.error){ alert(d.error); return; }
  refresh();
}

async function startIngest(){
  const path = document.getElementById('selpath').value;
  const key = document.getElementById('key').value.trim();
  const name = document.getElementById('name').value.trim() || key;
  const auto_label = document.getElementById('autolabel').checked;
  const msg = document.getElementById('msg');
  if (!path){ msg.textContent = '폴더를 선택하세요.'; return; }
  if (!/^[a-z0-9_]{2,32}$/.test(key)){ msg.textContent = '키는 영소문자/숫자/_ 2~32자.'; return; }
  document.getElementById('go').disabled = true;
  const r = await fetch('/api/ingest', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ path, key, name, auto_label }) });
  const d = await r.json();
  document.getElementById('go').disabled = false;
  if (d.error){ msg.textContent = d.error; return; }
  closeOv(); refresh();
}

refresh();
setInterval(refresh, 4000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(LANDING_HTML, roots=ALLOWED_ROOTS)


# ─────────────────────────────────────
# API
# ─────────────────────────────────────
@app.route("/api/datasets")
def api_datasets():
    return jsonify(list_datasets())


@app.route("/api/jobs")
def api_jobs():
    return jsonify(list_jobs())


@app.route("/api/browse")
def api_browse():
    raw = request.args.get("path", "")
    if not raw:
        # 루트 목록
        dirs = []
        for r in ALLOWED_ROOTS:
            if os.path.isdir(r):
                dirs.append({"name": r, "path": r, "pcaps": 0})
        return jsonify({"path": "", "up": None, "dirs": dirs})
    p = safe_browse_path(raw)
    if not p:
        return jsonify({"error": "허용되지 않았거나 존재하지 않는 경로입니다."})
    dirs = []
    try:
        with os.scandir(p) as it:
            for e in it:
                if e.is_dir() and not e.name.startswith("_"):
                    dirs.append({"name": e.name, "path": os.path.join(p, e.name), "pcaps": 0})
    except OSError as e:
        return jsonify({"error": f"폴더 읽기 실패: {e}"})
    dirs.sort(key=lambda x: x["name"])
    # 상위 경로 (허용 루트 위로는 못 올라감)
    up = os.path.dirname(p)
    if safe_browse_path(up) is None:
        up = ""     # 루트 목록으로
    return jsonify({"path": p, "up": up, "dirs": dirs[:300]})


@app.route("/api/ml_compare/<key>")
def api_ml_compare(key):
    """ML 자동 라벨 vs 폴더 라벨 불일치 Top-20을 반환."""
    if not KEY_RE.match(key):
        return jsonify({"error": "잘못된 키 형식입니다."}), 400
    ds_dir = DATASETS_DIR / key
    al_path = ds_dir / "_autolabel.json"
    if not al_path.exists():
        return jsonify({"error": "ML 자동 라벨링 데이터가 없습니다. (auto_label 모드로 추가된 데이터셋이 아닙니다)"}), 404
    try:
        al = json.loads(al_path.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify({"error": f"_autolabel.json 읽기 실패: {e}"}), 500

    # CSV에서 불일치 쌍 계산
    csv_candidates = list(ds_dir.glob("session_stat_*.csv"))
    mismatches = []
    if csv_candidates:
        try:
            import csv
            from collections import Counter
            csv_path = csv_candidates[0]
            counter = Counter()
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    folder = (row.get("task3_folder") or "").strip()
                    ml = (row.get("task3") or "").strip()
                    if folder and folder not in ("", "nan", "unknown") and folder != ml:
                        counter[(folder, ml)] += 1
            for (folder, ml), count in counter.most_common(20):
                mismatches.append({"folder": folder, "ml": ml, "count": count})
        except Exception as e:
            mismatches = [{"folder": "오류", "ml": str(e), "count": 0}]

    result = {
        "key": key,
        "sessions": al.get("sessions"),
        "unknown": al.get("unknown"),
        "unknown_pct": (al.get("unknown", 0) / max(1, al.get("sessions", 1)) * 100),
        "mean_conf": al.get("mean_conf"),
        "threshold": al.get("threshold"),
        "agreement_pct": (al.get("agreement_with_folder") or 0) * 100,
        "model_trained_at": al.get("model_trained_at"),
        "model_classes": al.get("model_classes"),
        "mismatches": mismatches,
    }
    return jsonify(result)


@app.route("/api/delete_dataset", methods=["POST"])
def api_delete_dataset():
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    if not KEY_RE.match(key):
        return jsonify({"error": "데이터셋 키 형식이 올바르지 않습니다."}), 400
    p = _procs.get(key)
    if p is not None and p.poll() is None:
        return jsonify({"error": f"'{key}' 작업이 실행 중입니다. 완료 또는 중단 후 삭제하세요."}), 409
    ds_dir = (DATASETS_DIR / key).resolve()
    base = DATASETS_DIR.resolve()
    try:
        if os.path.commonpath([str(base), str(ds_dir)]) != str(base):
            return jsonify({"error": "허용되지 않은 데이터셋 경로입니다."}), 400
    except ValueError:
        return jsonify({"error": "허용되지 않은 데이터셋 경로입니다."}), 400
    if not ds_dir.exists():
        return jsonify({"ok": True, "key": key, "deleted": False})
    shutil.rmtree(ds_dir)
    _procs.pop(key, None)
    return jsonify({"ok": True, "key": key, "deleted": True})


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    body = request.get_json(silent=True) or {}
    path = body.get("path", "")
    key = (body.get("key") or "").strip()
    name = (body.get("name") or key).strip()
    if not KEY_RE.match(key):
        return jsonify({"error": "키 형식 오류 (영소문자/숫자/_ 2~32자)"})
    src = safe_browse_path(path)
    if not src:
        return jsonify({"error": "허용되지 않았거나 존재하지 않는 폴더입니다."})
    out_dir = DATASETS_DIR / key
    if (out_dir / "data.json").exists():
        return jsonify({"error": f"'{key}' 데이터셋이 이미 있습니다. 다른 키를 쓰세요."})
    p = _procs.get(key)
    if p is not None and p.poll() is None:
        return jsonify({"error": f"'{key}' 작업이 이미 실행 중입니다."})
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(PIPELINE), "--src", src, "--key", key, "--name", name]
    if body.get("auto_label"):
        model = BASE_DIR / "models" / "autolabel_model.pkl"
        if not model.exists():
            return jsonify({"error": "자동 라벨링 모델이 없습니다. autolabel.py train으로 먼저 학습하세요."})
        cmd.append("--auto-label")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    flags = 0x08000000 if os.name == "nt" else 0     # CREATE_NO_WINDOW
    log = open(out_dir / "_pipeline.log", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env,
                            stdout=log, stderr=subprocess.STDOUT,
                            creationflags=flags)
    _procs[key] = proc
    return jsonify({"ok": True, "key": key, "pid": proc.pid})


# ─────────────────────────────────────
# 데이터셋 페이지 (traffic_dashboard ver2.0과 동일 방식)
# ─────────────────────────────────────
@app.route("/about/")
def about_page():
    return redirect("/")


@app.route("/<dataset>")
def dataset_page_redirect(dataset):
    if not (DATASETS_DIR / dataset / "config.js").exists():
        abort(404)
    return redirect(f"/{dataset}/")


@app.route("/<dataset>/")
def dataset_page(dataset):
    ds_dir = DATASETS_DIR / dataset
    if (ds_dir / "config.js").exists():
        return send_from_directory("static", "dashboard.html")
    abort(404)


@app.route("/<dataset>/<path:filename>")
def dataset_assets(dataset, filename):
    ds_dir = DATASETS_DIR / dataset
    if not ds_dir.is_dir():
        abort(404)
    return send_from_directory(str(ds_dir), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n  연구실 트래픽 대시보드 → http://localhost:{port}\n")
    app.run(host=host, port=port, debug=False)
