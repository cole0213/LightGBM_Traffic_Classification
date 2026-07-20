// =========================================================
// ISCX Dashboard v2 · Frontend Logic (Korean)
// =========================================================

const COLORS = {
  accent: '#00ffa3', accent2: '#00d4ff', warn: '#ffb454',
  danger: '#ff5e8a', purple: '#c792ea',
  grid: '#2a3344', fg0: '#e6edf3', fg1: '#b1bac4', fg2: '#6e7681',
  clsA: '#ffb454', clsB: '#00d4ff', clsC: '#00ffa3',
};
const PALETTE = [COLORS.accent, COLORS.accent2, COLORS.warn, COLORS.purple, COLORS.danger, '#5eead4', '#facc15', '#fb7185'];

Chart.defaults.color = COLORS.fg2;
Chart.defaults.borderColor = COLORS.grid;
Chart.defaults.font.family = "'Noto Sans KR', 'Space Grotesk', sans-serif";
Chart.defaults.font.size = 11;

// datalabels 플러그인은 명시적으로 사용할 때만 활성화 (전역 등록은 안 함)
const DataLabels = window.ChartDataLabels;

// =========================================================
// 데이터셋 설정 — config.js가 window.DASHBOARD_CONFIG로 주입 (없으면 iscx 기본값)
// =========================================================
const CFG = window.DASHBOARD_CONFIG || {};
const _merge = (base, over) => Object.assign({}, base, over || {});
// 그룹축 용어 (예: VPN/Non-VPN → Tor/non-Tor). config.group으로 교체
const GROUP_ON  = (CFG.group && CFG.group.on)  || 'VPN';
const GROUP_OFF = (CFG.group && CFG.group.off) || 'Non-VPN';
// 공격/정상 데이터셋(group.attack:true)은 공격=빨강·정상=초록으로 통일. 그 외(VPN/Tor 등)는 기존 색.
const GROUP_ATTACK    = !!(CFG.group && CFG.group.attack);
const GROUP_ON_COLOR  = GROUP_ATTACK ? COLORS.danger : COLORS.purple;   // ON(공격) = 빨강
const GROUP_OFF_COLOR = GROUP_ATTACK ? COLORS.accent : COLORS.accent2;  // OFF(정상) = 초록
const TAG_ON  = GROUP_ATTACK ? 'tag-attack' : 'tag-vpn';
const TAG_OFF = GROUP_ATTACK ? 'tag-normal' : 'tag-nonvpn';
// field_stats 등 데이터 키 (예: vpn/non_vpn → tor/non_tor). config.group.onKey/offKey로 교체
const GROUP_KEY_ON  = (CFG.group && CFG.group.onKey)  || 'vpn';
const GROUP_KEY_OFF = (CFG.group && CFG.group.offKey) || 'non_vpn';
const _fsKey = (g) => g === 'vpn' ? GROUP_KEY_ON : g === 'non_vpn' ? GROUP_KEY_OFF : g;

// =========================================================
// 상태
// =========================================================
const state = {
  data: null,
  task: 'All',
  cls: 'All',
  subSelection: null,
  vpnMode: 'all',
  search: '',
  sortKey: 'packets',
  sortDir: 'desc',
  ipFilter: null,
  chartScale: 'linear',   // linear | log | percent (비교 차트 스케일)
  protoLayer: 'L7',       // L2 | L3 | L4 | L7 | all (프로토콜 분포 계층)
  protoMetric: 'sessions', // sessions | packets (프로토콜 분포 단위)
  appMetric: 'sessions',  // sessions | packets (상위 앱 단위)
  localIpMetric: 'sessions',  // sessions | packets (상위 로컬 IP 단위)
  remoteIpMetric: 'sessions', // sessions | packets (상위 리모트 IP 단위)
  portMetric: 'sessions',     // sessions | packets (상위 목적지 포트 단위)
  sessLenProto: 'all',        // all | tcp | udp (세션 길이 분포 프로토콜)
  durProto: 'all',            // all | tcp | udp (세션 지속시간 프로토콜)
  sbyteProto: 'all',          // all | tcp | udp (세션당 바이트 분포 프로토콜)
  thruProto: 'all',           // all | tcp | udp (세션 처리율 분포 프로토콜)
  sessionProto: 'all',        // all | tcp | udp (총 세션 KPI 카드 토글)
  encKpiProto: 'all',         // all | tcp | udp (세션 암호화 KPI 프로토콜)
  chartPct: {},               // 차트별 값/비율(%) 모드 (key: 차트명)
  fsVpn: 'overall',          // 네트워크 식별자: overall | vpn | non_vpn
  fsField: 'dns_qry',        // 네트워크 식별자: tls_sni | http_uri | dns_qry | http_ua
  appCmpOpen: false,         // 앱 비교 테이블 표시 여부
  appCmpMode: 'app',         // 'app' | 'service'
  appCmpSelected: null,      // Set<string> — 선택된 앱 목록 (data 로드 후 초기화)
  appCmpServiceSelected: null, // Set<string> — 선택된 서비스 목록
  tlSel: {},                 // 타임라인 표시 행 선택 (섹션명 -> Set<label> | null=기본 top-N)
};

// IP → 폴더 인덱스 (검색용)
const ipIndex = new Map();   // 'ip' -> [{ folder, count }, ...]
const charts = {};

// =========================================================
// 한글 라벨
// =========================================================
const SERVICE_LABEL = _merge({
  voip: 'VoIP', streaming: '스트리밍', chat: '채팅', email: '이메일',
  browsing: '웹브라우징', file_transfer: '파일전송', p2p: 'P2P',
  unknown: '기타',
}, CFG.serviceLabels);
const CLASS_LABEL = _merge({
  All: '전체',
  A_realtime: '실시간 (A)',
  B_interactive: '상호작용 (B)',
  C_bulk: '대용량 (C)',
}, CFG.classLabels);
const CLASS_SHORT = _merge({
  A_realtime: 'A', B_interactive: 'B', C_bulk: 'C',
}, CFG.classShort);
const CLASS_TAG = _merge({ A_realtime: 'A', B_interactive: 'B', C_bulk: 'C', unknown: 'unknown' }, CFG.classTag);
const CLASS_NAME_KO = _merge({
  A_realtime:    '실시간',
  B_interactive: '상호작용',
  C_bulk:        '대용량',
}, CFG.classNameKo);
const TASK_LABEL = _merge({
  All: '전체', VPN: 'VPN', Service: '서비스', App: '앱',
}, CFG.taskLabels);
// '분석 영역'의 VPN 버튼/표시 라벨도 그룹 용어로 (config.group.label 우선)
if (CFG.group && CFG.group.label) TASK_LABEL.VPN = CFG.group.label;

function fmtNum(n) {
  if (n == null) return '—';
  return Math.round(n).toLocaleString();
}
// 차트 축 눈금 전용: 자리수 절약을 위해 K/M/B 약식 표기 유지
function fmtAxis(n) {
  if (n == null) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return Math.round(n).toLocaleString();
}
function fmtBytes(n) {
  if (n == null) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  // 천단위 콤마 적용 (예: 1,200 B / 13.66 MB)
  const num = i === 0 ? Math.round(n).toLocaleString() : n.toFixed(2).toLocaleString();
  // toFixed 결과의 정수부에도 콤마
  if (i === 0) return num + ' B';
  const [int, dec] = n.toFixed(2).split('.');
  return Number(int).toLocaleString() + '.' + dec + ' ' + u[i];
}

// =========================================================
// 데이터 필터링 / 집계
// =========================================================
function filteredFiles() {
  if (!state.data) return [];
  return state.data.files.filter(f => {
    if (state.cls !== 'All' && f.class !== state.cls) return false;
    if (state.task === 'VPN' && !f.vpn) return false;
    if (state.task === 'Service' && state.subSelection && f.service !== state.subSelection) return false;
    if (state.task === 'App'     && state.subSelection && f.app     !== state.subSelection) return false;
    if (state.vpnMode === 'vpn' && !f.vpn) return false;
    if (state.vpnMode === 'non_vpn' && f.vpn) return false;
    // IP 필터: 해당 폴더의 top_local_ips에 검색 IP가 있어야 통과
    if (state.ipFilter) {
      const ips = (f.stats.top_local_ips || []).map(([ip]) => ip);
      if (!ips.includes(state.ipFilter)) return false;
    }
    return true;
  });
}

/**
 * 테이블 전용 필터링 (검색 + 정렬 추가)
 */
function tableFiles() {
  let files = filteredFiles();
  // 검색
  if (state.search) {
    const q = state.search.toLowerCase();
    files = files.filter(f =>
      f.filename.toLowerCase().includes(q) ||
      f.app.toLowerCase().includes(q) ||
      f.service.toLowerCase().includes(q) ||
      (f.class || '').toLowerCase().includes(q)
    );
  }
  // 정렬
  const getKey = (f) => {
    switch (state.sortKey) {
      case 'filename':   return f.filename;
      case 'vpn':        return f.vpn ? 1 : 0;
      case 'app':        return f.app;
      case 'service':    return f.service;
      case 'class':      return f.class;
      case 'pcap_count': return f.pcap_count || 1;
      case 'packets':    return f.stats.packet_count;
      case 'bytes':      return f.stats.total_bytes;
      case 'sessions':   return sessTotal(f.stats);
      default:           return 0;
    }
  };
  files = [...files].sort((a, b) => {
    const ka = getKey(a), kb = getKey(b);
    if (typeof ka === 'string') {
      return state.sortDir === 'asc' ? ka.localeCompare(kb) : kb.localeCompare(ka);
    }
    return state.sortDir === 'asc' ? ka - kb : kb - ka;
  });
  return files;
}

function currentStats() {
  return aggregateStats(filteredFiles().map(f => f.stats));
}

// 세션 총계 = TCP + UDP + 기타(other_sessions: GRE·ICMP 등 비-TCP/UDP 세션 — iot2023 등 일부 데이터셋만 보유)
function sessTotal(s) {
  if (!s) return 0;
  return (s.tcp_sessions || 0) + (s.udp_sessions || 0) + (s.other_sessions || 0);
}

function aggregateStats(statsList) {
  if (!statsList.length) {
    return {
      packet_count: 0, total_bytes: 0, avg_packet_size: 0,
      min_packet_size: 0, max_packet_size: 0, median_packet_size: 0,
      tcp_packets: 0, udp_packets: 0, other_packets: 0,
      tcp_sessions: 0, udp_sessions: 0, other_sessions: 0,
      local_sessions: null, remote_sessions: null,
      protocols: {}, top_local_ips: [], top_remote_ips: [],
      top_src_ports: [], top_dst_ports: [],
      packet_size_histogram: { edges: [], counts: [] },
      session_length_histogram: { labels: ['1','2','3-5','6-10','11-50','51-100','101-500','500+'], counts: [0,0,0,0,0,0,0,0] },
      protocol_layers: { L2: {}, L3: {}, L4: {}, L7: {} },
      sessions_by_l7: {},
      sessions_by_layer: { L2: {}, L3: {}, L4: {}, L7: {} },
    };
  }
  const agg = {
    packet_count:  statsList.reduce((a, s) => a + s.packet_count, 0),
    total_bytes:   statsList.reduce((a, s) => a + s.total_bytes, 0),
    tcp_packets:   statsList.reduce((a, s) => a + s.tcp_packets, 0),
    udp_packets:   statsList.reduce((a, s) => a + s.udp_packets, 0),
    other_packets: statsList.reduce((a, s) => a + s.other_packets, 0),
    tcp_sessions:  statsList.reduce((a, s) => a + s.tcp_sessions, 0),
    udp_sessions:  statsList.reduce((a, s) => a + s.udp_sessions, 0),
    other_sessions: statsList.reduce((a, s) => a + (s.other_sessions || 0), 0),
    max_packet_size: Math.max(0, ...statsList.map(s => s.max_packet_size || 0)),
    min_packet_size: Math.min(...statsList.map(s => s.min_packet_size || Infinity)),
    // frame_bytes: pcap 실측 프레임 바이트 합(있는 데이터셋만). 있으면 평균 패킷 크기를 실측 프레임 기준으로.
    frame_bytes:   statsList.reduce((a, s) => a + (s.frame_bytes || 0), 0),
  };
  if (!isFinite(agg.min_packet_size)) agg.min_packet_size = 0;
  agg.avg_packet_size = agg.frame_bytes
    ? Math.round(agg.frame_bytes / agg.packet_count)
    : (agg.packet_count ? Math.round(agg.total_bytes / agg.packet_count) : 0);

  // 세션 유형수 (재생성된 data.json에만 존재)
  for (const key of ['unicast_sessions', 'multicast_sessions', 'broadcast_sessions',
                     'local_sessions', 'remote_sessions']) {
    const any = statsList.some(s => s[key] != null);
    agg[key] = any ? statsList.reduce((a, s) => a + (s[key] || 0), 0) : null;
  }

  const proto = {};
  for (const s of statsList) for (const [k, v] of Object.entries(s.protocols || {})) proto[k] = (proto[k] || 0) + v;
  agg.protocols = proto;

  for (const key of ['top_local_ips', 'top_remote_ips', 'top_src_ports', 'top_dst_ports',
                     'top_local_ips_sessions', 'top_remote_ips_sessions', 'top_dst_ports_sessions']) {
    const m = {};
    for (const s of statsList) for (const [item, c] of (s[key] || [])) m[item] = (m[item] || 0) + c;
    agg[key] = Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 10);
  }

  agg.packet_size_histogram = mergeHistograms(statsList);

  // 고정 구간 패킷 크기 분포 합산 (재생성 data.json에만 존재) — 모든 폴더 동일 구간
  {
    let labels = null;
    const sums = {};
    for (const st of statsList) {
      const pb = st.packet_size_bins;
      if (pb && pb.labels && pb.counts) {
        if (!labels) labels = pb.labels.slice();
        pb.labels.forEach((l, i) => { sums[l] = (sums[l] || 0) + (pb.counts[i] || 0); });
      }
    }
    agg.packet_size_bins = labels ? { labels, counts: labels.map(l => sums[l] || 0) } : null;
  }

  // 세션 지속시간·세션당 바이트·처리율 분포 합산 — 전체/TCP/UDP (재생성 data.json에만 존재)
  for (const key of ['flow_duration_hist', 'flow_duration_hist_tcp', 'flow_duration_hist_udp',
                     'session_bytes_hist', 'session_bytes_hist_tcp', 'session_bytes_hist_udp',
                     'throughput_hist', 'throughput_hist_tcp', 'throughput_hist_udp']) {
    let labels = null;
    const sums = {};
    for (const st of statsList) {
      const h = st[key];
      if (h && h.labels && h.counts) {
        if (!labels) labels = h.labels.slice();
        h.labels.forEach((l, i) => { sums[l] = (sums[l] || 0) + (h.counts[i] || 0); });
      }
    }
    agg[key] = labels ? { labels, counts: labels.map(l => sums[l] || 0) } : null;
  }

  // 세션 암호화 분류 합산 — 세션수/패킷수 · 전체/TCP/UDP (재생성 data.json에만 존재)
  for (const key of ['encryption_sessions', 'encryption_packets',
                     'encryption_sessions_tcp', 'encryption_sessions_udp',
                     'encryption_packets_tcp', 'encryption_packets_udp']) {
    let labels = null;
    const sums = {};
    for (const st of statsList) {
      const h = st[key];
      if (h && h.labels && h.counts) {
        if (!labels) labels = h.labels.slice();
        h.labels.forEach((l, i) => { sums[l] = (sums[l] || 0) + (h.counts[i] || 0); });
      }
    }
    agg[key] = labels ? { labels, counts: labels.map(l => sums[l] || 0) } : null;
  }

  // median: 단일 폴더는 추출 시 계산한 정확값, 여러 폴더는 정밀 히스토그램(8B폭) 병합 후 보간.
  // (정밀 히스토그램이 없는 옛 데이터는 기존 20구간 근사로 폴백)
  if (statsList.length === 1 && typeof statsList[0].median_packet_size === 'number' && statsList[0].median_packet_size > 0) {
    agg.median_packet_size = statsList[0].median_packet_size;
  } else {
    const fine = mergeFineHist(statsList);
    agg.median_packet_size = fine
      ? medianFromFineHist(fine, agg.packet_count)
      : approxMedianFromHistogram(agg.packet_size_histogram, agg.packet_count);
  }

  // 세션 길이 분포 합산 (#9) — data.json의 labels를 그대로 사용 (8버킷 등)
  let slhLabels = null;
  const slhMap = {};
  for (const st of statsList) {
    const slh = st.session_length_histogram;
    if (slh && slh.labels && slh.counts) {
      if (!slhLabels) slhLabels = slh.labels.slice();
      slh.labels.forEach((lab, i) => { slhMap[lab] = (slhMap[lab] || 0) + (slh.counts[i] || 0); });
    }
  }
  if (!slhLabels) slhLabels = ['1', '2', '3-5', '6-10', '11-50', '51-100', '101-500', '500+'];
  agg.session_length_histogram = {
    labels: slhLabels,
    counts: slhLabels.map(l => slhMap[l] || 0),
  };

  // 세션 길이 분포 TCP/UDP 분리 합산 (재생성 data.json에만 존재)
  for (const key of ['session_length_histogram_tcp', 'session_length_histogram_udp']) {
    const map = {};
    let present = false;
    for (const st of statsList) {
      const h = st[key];
      if (h && h.labels && h.counts) {
        present = true;
        h.labels.forEach((lab, i) => { map[lab] = (map[lab] || 0) + (h.counts[i] || 0); });
      }
    }
    agg[key] = present ? { labels: slhLabels, counts: slhLabels.map(l => map[l] || 0) } : null;
  }

  // 프로토콜 계층(L2/L3/L4/L7) 합산 (#6) — 새 data.json에만 존재
  const layers = { L2: {}, L3: {}, L4: {}, L7: {} };
  for (const st of statsList) {
    const pl = st.protocol_layers;
    if (!pl) continue;
    for (const layer of ['L2', 'L3', 'L4', 'L7']) {
      for (const [k, v] of Object.entries(pl[layer] || {})) {
        layers[layer][k] = (layers[layer][k] || 0) + v;
      }
    }
  }
  agg.protocol_layers = layers;

  // 세션별 L7 분류 합산 (#7 포트 기반) — 정확한 세션 분포
  const sessL7 = {};
  for (const st of statsList) {
    for (const [k, v] of Object.entries(st.sessions_by_l7 || {})) {
      sessL7[k] = (sessL7[k] || 0) + v;
    }
  }
  agg.sessions_by_l7 = sessL7;

  // 세션별 계층 분류 합산 (#6 세션 단위) — 모든 계층 세션수
  const sessLayer = { L2: {}, L3: {}, L4: {}, L7: {} };
  for (const st of statsList) {
    const sbl = st.sessions_by_layer;
    if (!sbl) continue;
    for (const L of ['L2', 'L3', 'L4', 'L7']) {
      for (const [k, v] of Object.entries(sbl[L] || {})) {
        sessLayer[L][k] = (sessLayer[L][k] || 0) + v;
      }
    }
  }
  agg.sessions_by_layer = sessLayer;
  return agg;
}

/**
 * 히스토그램에서 median 근사 (bin 내 선형 보간).
 * 정확한 median은 추출 시점에 packet_sizes 전체를 정렬해야 가능하지만,
 * data.json에는 히스토그램만 있으므로 근사값으로 표시.
 */
function approxMedianFromHistogram(h, totalCount) {
  if (!h || !h.edges || h.edges.length < 2 || !totalCount) return 0;
  const half = totalCount / 2;
  let cum = 0;
  for (let i = 0; i < h.counts.length; i++) {
    const c = h.counts[i];
    if (cum + c >= half) {
      const lo = h.edges[i], hi = h.edges[i + 1];
      const frac = c > 0 ? (half - cum) / c : 0;
      return lo + frac * (hi - lo);
    }
    cum += c;
  }
  return h.edges[h.edges.length - 1];
}

// 정밀 고정구간 히스토그램(step, max, counts[max/step + overflow 1]) 병합 (동일 구간이라 단순 합)
function mergeFineHist(statsList) {
  let step = null, max = null, counts = null;
  for (const s of statsList) {
    const f = s.size_fine_hist;
    if (!f || !f.counts) continue;
    if (!counts) { step = f.step; max = f.max; counts = f.counts.slice(); }
    else if (f.step === step && f.max === max && f.counts.length === counts.length) {
      for (let i = 0; i < counts.length; i++) counts[i] += f.counts[i];
    }
  }
  return counts ? { step, max, counts } : null;
}

// 정밀 히스토그램에서 median (구간 내 선형보간; overflow 구간이면 max 반환). 오차 ≤ step(8B).
function medianFromFineHist(f, totalCount) {
  if (!f || !f.counts || !totalCount) return 0;
  const overflowIdx = f.max / f.step;
  const half = totalCount / 2;
  let cum = 0;
  for (let i = 0; i < f.counts.length; i++) {
    const c = f.counts[i];
    if (cum + c >= half) {
      if (i >= overflowIdx) return f.max;
      const lo = i * f.step;
      const frac = c > 0 ? (half - cum) / c : 0;
      return Math.round(lo + frac * f.step);
    }
    cum += c;
  }
  return f.max;
}

function mergeHistograms(statsList) {
  const hists = statsList.map(s => s.packet_size_histogram).filter(h => h && h.edges && h.edges.length);
  if (!hists.length) return { edges: [], counts: [] };

  const lo = Math.min(...hists.map(h => h.edges[0]));
  const hi = Math.max(...hists.map(h => h.edges[h.edges.length - 1]));
  const bins = 20;
  if (lo === hi) {
    return { edges: [lo, hi], counts: [hists.reduce((a, h) => a + h.counts.reduce((x, y) => x + y, 0), 0)] };
  }
  const width = (hi - lo) / bins;
  const edges = Array.from({ length: bins + 1 }, (_, i) => lo + i * width);
  const counts = new Array(bins).fill(0);

  for (const h of hists) {
    for (let i = 0; i < h.counts.length; i++) {
      const mid = (h.edges[i] + h.edges[i + 1]) / 2;
      const idx = Math.min(Math.max(Math.floor((mid - lo) / width), 0), bins - 1);
      counts[idx] += h.counts[i];
    }
  }
  return { edges, counts };
}

// =========================================================
// 차트 헬퍼
// =========================================================
function makeOrUpdate(id, config) {
  const el = document.getElementById(id);
  if (!el) return;

  // ── 모든 막대(bar) 차트의 막대 폭을 동일하게 고정 ──
  // 값이 1M이든 10M이든 막대 두께는 같고 길이만 다르게 (보기 편하게)
  if (config.type === 'bar' && config.data && Array.isArray(config.data.datasets)) {
    // 가로 막대(indexAxis:'y')인지 판별
    const horizontal = config.options && config.options.indexAxis === 'y';
    for (const ds of config.data.datasets) {
      // 세로 막대만 두께 고정. 가로 막대는 차트 높이에 맞춰 자동 분배(겹침 방지)
      if (!horizontal && ds.maxBarThickness == null) ds.maxBarThickness = 38;
    }
    // 카테고리/막대 점유율
    config.options = config.options || {};
    config.options.datasets = config.options.datasets || {};
    config.options.datasets.bar = Object.assign(
      // 가로막대: 카테고리 점유 60%(=막대 간 간격 넉넉), 막대끼리는 70%
      { categoryPercentage: horizontal ? 0.6 : 0.7, barPercentage: horizontal ? 0.7 : 0.85 },
      config.options.datasets.bar || {}
    );
  }

  // 이 캔버스에 이미 붙어있는 차트가 있으면 모두 정리 (Chart.js 내부 레지스트리 포함)
  if (charts[id]) {
    charts[id].destroy();
    delete charts[id];
  }
  const existing = (typeof Chart.getChart === 'function') ? Chart.getChart(el) : null;
  if (existing) existing.destroy();

  const plugins = config.plugins || [];
  charts[id] = new Chart(el.getContext('2d'), { ...config, plugins });
}

/**
 * 비교 차트의 스케일 모드별 옵션 빌더
 * @param {Array<{label, data, color}>} series - 시리즈 배열
 * @param {Array} categories - 카테고리 라벨
 * @param {Object} opts - { axis: 'x'|'y', unit: '패킷' }
 */
function buildComparisonChart(series, categories, opts = {}) {
  const axis = opts.axis || 'x';   // 'x' = 세로 막대, 'y' = 가로 막대
  const unit = opts.unit || '';
  const scale = state.chartScale;

  // 퍼센트 모드: 각 카테고리 안에서 시리즈 합을 100%로
  let datasets;
  if (scale === 'percent') {
    datasets = series.map(s => ({
      label: s.label,
      data: s.data.map((v, i) => {
        const total = series.reduce((a, ss) => a + (ss.data[i] || 0), 0);
        return total > 0 ? (v / total) * 100 : 0;
      }),
      backgroundColor: s.color,
      borderRadius: 4,
      _raw: s.data,   // 원본 (툴팁용)
    }));
  } else {
    datasets = series.map(s => ({
      label: s.label,
      data: s.data,
      backgroundColor: s.color,
      borderRadius: 4,
    }));
  }

  const isHorizontal = axis === 'y';
  const valueAxis = isHorizontal ? 'x' : 'y';
  const labelAxis = isHorizontal ? 'y' : 'x';

  const scaleConfig = {};
  scaleConfig[labelAxis] = {
    stacked: scale === 'percent',
    grid: { display: false },
    ticks: {
      color: COLORS.fg1,
      font: { weight: 600, size: 10 },
      // 세로막대(x축 라벨)에서 항목이 많으면 회전시켜 겹침 방지
      maxRotation: (!isHorizontal && categories.length > 6) ? 50 : 0,
      minRotation: (!isHorizontal && categories.length > 6) ? 45 : 0,
      autoSkip: false,
    },
  };
  scaleConfig[valueAxis] = {
    stacked: scale === 'percent',
    grid: { color: COLORS.grid },
    ticks: {
      color: COLORS.fg2,
      callback: (v) => scale === 'percent' ? v + '%' : fmtAxis(v),
    },
  };
  if (scale === 'log') {
    scaleConfig[valueAxis].type = 'logarithmic';
  }
  if (scale === 'percent') {
    scaleConfig[valueAxis].max = 100;
    scaleConfig[valueAxis].min = 0;
  }
  if (scale === 'linear') {
    // 0부터 시작 + 균일한 눈금 간격 (#2)
    const maxVal = Math.max(0, ...series.flatMap(s => s.data.map(v => v || 0)));
    const rough = maxVal / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(rough || 1)));
    const norm = rough / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
    scaleConfig[valueAxis].type = 'linear';
    scaleConfig[valueAxis].beginAtZero = true;
    scaleConfig[valueAxis].min = 0;
    // 막대 끝 라벨 잘림 방지: 최대값이 눈금에 딱 맞으면 한 칸 더 여유 (가로·세로 공통)
    let yMax = Math.ceil(maxVal / step) * step;
    if (yMax <= maxVal * 1.08) yMax += step;
    scaleConfig[valueAxis].max = yMax;
    scaleConfig[valueAxis].ticks.stepSize = step;
  }

  return {
    type: 'bar',
    data: { labels: categories, datasets },
    options: {
      indexAxis: axis,
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: isHorizontal ? 70 : (scale !== 'log' ? 12 : 0), top: 24 } },
      plugins: {
        legend: { position: 'bottom', labels: { color: COLORS.fg1, padding: 10, boxWidth: 10, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (scale === 'percent') {
                const raw = ctx.dataset._raw ? ctx.dataset._raw[ctx.dataIndex] : ctx.parsed[valueAxis];
                return `${ctx.dataset.label}: ${ctx.parsed[valueAxis].toFixed(1)}% (${fmtNum(raw)} ${unit})`;
              }
              return `${ctx.dataset.label}: ${fmtNum(ctx.parsed[valueAxis])} ${unit}`;
            },
          },
        },
        datalabels: {
          display: (ctx) => {
            // 작은 값도 보이게 — 0 아닌 값만 표시
            const v = ctx.dataset.data[ctx.dataIndex];
            return v != null && v !== 0;
          },
          anchor: scale === 'percent' ? 'center' : 'end',
          align: scale === 'percent' ? 'center' : 'end',
          clamp: true, clip: false,
          color: COLORS.fg0,
          font: { weight: 600, size: 9 },
          formatter: (v, ctx) => {
            if (scale === 'percent') {
              return v >= 5 ? v.toFixed(0) + '%' : '';  // 5% 미만은 숨김
            }
            return fmtNum(v);
          },
        },
      },
      scales: scaleConfig,
    },
    plugins: [DataLabels],
  };
}

// =========================================================
// 상단 / KPI / 메타 / 사이드바 카운트
// =========================================================
// 총 세션 카드: 선택된 프로토콜(전체/TCP/UDP)에 따라 값·상세 갱신
function renderSessionsCard(s) {
  s = s || currentStats();
  const proto = state.sessionProto || 'all';
  const tcpPkts = s.tcp_packets || 0;
  const udpPkts = s.udp_packets || 0;
  const otherPkts = s.other_packets || 0;
  let sessions, pkts;
  if (proto === 'tcp')      { sessions = s.tcp_sessions || 0; pkts = tcpPkts; }
  else if (proto === 'udp') { sessions = s.udp_sessions || 0; pkts = udpPkts; }
  else                      { sessions = sessTotal(s); pkts = tcpPkts + udpPkts + otherPkts; }
  const perSession = sessions ? Math.round(pkts / sessions) : 0;
  document.getElementById('kpi-sessions').textContent = fmtNum(sessions);
  document.getElementById('kpi-sessions-sub').textContent = sessions
    ? `패킷 ${fmtNum(pkts)} · 세션당 패킷 ${perSession.toLocaleString()}`
    : '—';
}

function renderTop() {
  const s = currentStats();

  renderSessionsCard(s);

  // 총 바이트: "1.23 GB" 주, "1,234,567,890 B" 부
  document.getElementById('kpi-bytes').textContent = fmtBytes(s.total_bytes);
  document.getElementById('kpi-bytes-sub').textContent =
    (s.total_bytes || 0).toLocaleString() + ' B';

  // 패킷 크기 — mean(메인) / min · median · max(서브)
  document.getElementById('kpi-avg').textContent = fmtNum(s.avg_packet_size || 0) + ' B';
  document.getElementById('kpi-min').textContent = fmtNum(s.min_packet_size || 0) + ' B';
  document.getElementById('kpi-median').textContent = fmtNum(s.median_packet_size || 0) + ' B';
  document.getElementById('kpi-max').textContent = fmtNum(s.max_packet_size || 0) + ' B';

  // 세션 암호화 비율 — 암호화 / 평문 / 미상 · 전체/TCP/UDP 토글
  // (counts 순서는 [암호화, 평문, 미상]). 비율(%)과 세션수를 함께 표시.
  const encProto = state.encKpiProto || 'all';
  const enc = encProto === 'tcp' ? s.encryption_sessions_tcp
            : encProto === 'udp' ? s.encryption_sessions_udp
            : s.encryption_sessions;
  const encEl = document.getElementById('kpi-enc');
  const setEnc = (pctId, nId, pctTxt, nTxt) => {
    const p = document.getElementById(pctId); if (p) p.textContent = pctTxt;
    const n = document.getElementById(nId);   if (n) n.textContent = nTxt;
  };
  if (enc && enc.counts && enc.counts.length) {
    const encrypted = enc.counts[0] || 0;
    const plain     = enc.counts[1] || 0;
    const unknown   = enc.counts[2] || 0;
    const encTotal  = encrypted + plain + unknown;
    const pct = (v) => encTotal ? (v / encTotal * 100).toFixed(1) + '%' : '0%';
    if (encEl) encEl.textContent = pct(encrypted);
    setEnc('kpi-enc-encrypted', 'kpi-enc-encrypted-n', pct(encrypted), fmtNum(encrypted));
    setEnc('kpi-enc-plain',     'kpi-enc-plain-n',     pct(plain),     fmtNum(plain));
    setEnc('kpi-enc-unknown',   'kpi-enc-unknown-n',   pct(unknown),   fmtNum(unknown));
  } else {
    if (encEl) encEl.textContent = '—';
    setEnc('kpi-enc-encrypted', 'kpi-enc-encrypted-n', '—', '—');
    setEnc('kpi-enc-plain',     'kpi-enc-plain-n',     '—', '—');
    setEnc('kpi-enc-unknown',   'kpi-enc-unknown-n',   '—', '—');
  }

  document.getElementById('av-task').textContent  = TASK_LABEL[state.task] || state.task;
  const avCls = document.getElementById('av-class');
  if (avCls) avCls.textContent = CLASS_LABEL[state.cls] || state.cls;
  let detail = state.subSelection || '—';
  if (state.task === 'Service' && state.subSelection) detail = SERVICE_LABEL[state.subSelection] || state.subSelection;
  // IP 필터가 활성이면 detail에 추가 표시
  if (state.ipFilter) {
    detail = (detail === '—' ? '' : detail + ' · ') + `IP: ${state.ipFilter}`;
  }
  document.getElementById('av-detail').textContent = detail;
}

function renderMeta() {
  const m = state.data.meta;
  document.getElementById('meta-folders').textContent = m.total_folders;
  document.getElementById('meta-pcaps').textContent   = m.total_pcaps;
  const sa = state.data.summary.all;
  document.getElementById('meta-packets').textContent =
    fmtNum(sa.packet_count != null ? sa.packet_count
      : (sa.tcp_packets || 0) + (sa.udp_packets || 0) + (sa.other_packets || 0));
  document.getElementById('dataset-meta').textContent = `폴더 ${m.total_folders}개 · PCAP ${m.total_pcaps}개`;

  // 앱 개수 배지 (by_app 키 = 데이터셋의 고유 앱 수)
  const appCount = Object.keys(state.data.by_app).length;
  document.getElementById('class-count-badge').textContent = `${appCount}개 앱`;

  document.getElementById('footer-meta').textContent =
    `${m.dataset} · ${TASK_LABEL[state.task]} / ${CLASS_LABEL[state.cls]}` +
    (state.subSelection ? ` / ${state.subSelection}` : '');
}

function renderClassCounts() {
  // 트래픽 그룹(A/B/C) 필터 버튼 제거됨 — 요소 있을 때만 갱신
  const elAll = document.getElementById('class-count-All');
  if (elAll) elAll.textContent = state.data.files.length;
  for (const cls of ['A_realtime', 'B_interactive', 'C_bulk']) {
    const el = document.getElementById(`class-count-${cls}`);
    if (el) el.textContent = state.data.files.filter(f => f.class === cls).length;
  }
}

// =========================================================
// ★ All 비교 섹션 (전체 영역에서만 보임)
// =========================================================
function renderComparisonSection() {
  const section = document.getElementById('comparison-section');
  // task=All일 때만 표시
  if (state.task !== 'All') {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  // 클래스 필터 적용한 파일 풀
  const pool = state.data.files.filter(f => state.cls === 'All' || f.class === state.cls);

  // 공격 데이터셋(group.attack): [종합비교(전체폭)] / [정상 | 공격]만.
  //   서비스별 트래픽 분포·앱별 트래픽 순위 카드는 제거.
  const _atk = !!(CFG.group && CFG.group.attack);
  const _cardOf = id => { const c = document.getElementById(id); return c ? c.closest('.chart-card') : null; };
  if (_atk) {
    const vpnCard = _cardOf('cmp-vpn-packets'); if (vpnCard) { vpnCard.classList.remove('span-3'); vpnCard.classList.add('cmp-full'); }
    const svcCard = _cardOf('cmp-service'); if (svcCard) svcCard.style.display = 'none';
    const appCard = _cardOf('cmp-app');     if (appCard) appCard.style.display = 'none';
  }

  renderCmpVpn(pool);
  renderCmpNormal(pool);
  renderCmpAttack(pool);
  if (!_atk) {          // 공격 데이터셋은 서비스별·앱별 카드 제거
    renderCmpService(pool);
    renderCmpApp(pool);
  }
  renderCmpClass();
  renderCmpBaseline(pool);
}

// =========================================================
// 앱 / 서비스 트래픽 비교 테이블
// =========================================================
function renderAppCmpTable() {
  const section = document.getElementById('app-cmp-section');
  if (!state.appCmpOpen || !state.data) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const isService = state.appCmpMode === 'service';
  const byDict    = isService ? state.data.by_service : state.data.by_app;
  const selected  = isService ? state.appCmpServiceSelected : state.appCmpSelected;
  const getLabelFn = isService ? (k) => SERVICE_LABEL[k] || k : (k) => k;

  // 타이틀 갱신
  const titleEl = document.getElementById('app-cmp-title');
  if (titleEl) titleEl.textContent = isService ? `🗂 ${CFG.serviceTaskName || '서비스'}별 트래픽 비교` : `📱 ${CFG.appTaskName || '앱'}별 트래픽 비교`;

  // 패킷수 내림차순 정렬
  const allKeys = Object.keys(byDict).sort((a, b) => byDict[b].packet_count - byDict[a].packet_count);

  // 토글 버튼 렌더
  const bar = document.getElementById('app-cmp-toggle-bar');
  bar.innerHTML = allKeys.map(k => {
    const active = selected.has(k);
    return `<button class="app-toggle-btn${active ? ' active' : ''}" data-key="${k}">${getLabelFn(k)}</button>`;
  }).join('');
  bar.querySelectorAll('.app-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.key;
      if (selected.has(k)) { selected.delete(k); btn.classList.remove('active'); }
      else                  { selected.add(k);    btn.classList.add('active'); }
      _renderAppCmpTableBody(allKeys, byDict, selected, getLabelFn);
    });
  });

  _renderAppCmpTableBody(allKeys, byDict, selected, getLabelFn);
}

function _renderAppCmpTableBody(allKeys, byDict, selected, getLabelFn) {
  const cols = allKeys.filter(k => selected.has(k));
  const wrap = document.getElementById('app-cmp-table-wrap');

  if (!cols.length) {
    wrap.innerHTML = '<div class="app-cmp-no-apps">항목을 하나 이상 선택하세요.</div>';
    return;
  }

  const rows = [
    { label: '패킷 수', getValue: k => byDict[k].packet_count,                                           fmt: fmtNum   },
    { label: '세션 수', getValue: k => sessTotal(byDict[k]),    fmt: fmtNum   },
    { label: '바이트',  getValue: k => byDict[k].total_bytes,                                             fmt: fmtBytes },
  ];

  const CHUNK = 15;
  const buildTable = (chunk) => {
    let html = '<table class="app-cmp-table"><thead><tr><th class="row-label">지표</th>';
    html += chunk.map(k => `<th>${getLabelFn(k)}</th>`).join('');
    html += '</tr></thead><tbody>';
    for (const row of rows) {
      html += `<tr><td class="row-label">${row.label}</td>`;
      html += chunk.map(k => `<td>${row.fmt(row.getValue(k))}</td>`).join('');
      html += '</tr>';
    }
    html += '</tbody></table>';
    return html;
  };

  let html = '';
  for (let i = 0; i < cols.length; i += CHUNK) {
    const chunk = cols.slice(i, i + CHUNK);
    if (i > 0) html += '<div class="app-cmp-table-gap"></div>';
    html += buildTable(chunk);
  }
  wrap.innerHTML = html;
}

// 1. VPN vs Non-VPN 종합 비교 — 단위별 3개 패널 (패킷 / 세션 / 바이트)
function renderCmpVpn(pool) {
  if (!CFG.group) {  // 그룹축 없으면 'X vs Y 종합 비교' 카드 숨김
    const _t = document.getElementById('brand-cmp-vpn-title');
    const _card = _t && _t.closest('.chart-card'); if (_card) _card.style.display = 'none';
    return;
  }
  const vpn    = aggregateStats(pool.filter(f =>  f.vpn).map(f => f.stats));
  const nonVpn = aggregateStats(pool.filter(f => !f.vpn).map(f => f.stats));

  const panels = [
    {
      id: 'cmp-vpn-packets',
      cats: ['패킷'],
      nonVpnData: [(nonVpn.tcp_packets || 0) + (nonVpn.udp_packets || 0) + (nonVpn.other_packets || 0)],
      vpnData:    [(vpn.tcp_packets || 0) + (vpn.udp_packets || 0) + (vpn.other_packets || 0)],
      unit: '패킷',
    },
    {
      id: 'cmp-vpn-sessions',
      // 비-TCP/UDP 세션(GRE·ICMP 등)이 있는 데이터셋만 '기타' 막대 추가
      cats: ((vpn.other_sessions || 0) + (nonVpn.other_sessions || 0)) > 0 ? ['TCP', 'UDP', '기타'] : ['TCP', 'UDP'],
      nonVpnData: ((vpn.other_sessions || 0) + (nonVpn.other_sessions || 0)) > 0
        ? [nonVpn.tcp_sessions, nonVpn.udp_sessions, nonVpn.other_sessions || 0]
        : [nonVpn.tcp_sessions, nonVpn.udp_sessions],
      vpnData:    ((vpn.other_sessions || 0) + (nonVpn.other_sessions || 0)) > 0
        ? [vpn.tcp_sessions, vpn.udp_sessions, vpn.other_sessions || 0]
        : [vpn.tcp_sessions, vpn.udp_sessions],
      unit: '세션',
    },
    {
      id: 'cmp-vpn-bytes',
      cats: ['MB'],
      nonVpnData: [Math.round(nonVpn.total_bytes / 1e6)],
      vpnData:    [Math.round(vpn.total_bytes / 1e6)],
      unit: 'MB',
    },
  ];

  for (const p of panels) {
    const series = [
      { label: GROUP_OFF, data: p.nonVpnData, color: GROUP_OFF_COLOR },
      { label: GROUP_ON,  data: p.vpnData,    color: GROUP_ON_COLOR },
    ];
    const config = buildComparisonChart(series, p.cats, { axis: 'x', unit: p.unit });
    makeOrUpdate(p.id, config);
  }
}

// 헬퍼: 비교 카드의 제목/부제 갱신 (canvas id로 카드 찾음)
function _setCmpCardHead(canvasId, title, sub) {
  const c = document.getElementById(canvasId); if (!c) return;
  const card = c.closest('.chart-card'); if (!card) return;
  const h = card.querySelector('h3'); if (h && title != null) h.textContent = title;
  const s = card.querySelector('.chart-sub'); if (s && sub != null) s.textContent = sub;
}

// 2. 서비스별 트래픽 분포
function renderCmpService(pool) {
  // 균등 수집 데이터셋(cipher 등): 모든 값이 동일 → 비교 대신 '균등 수집' 요약 표현
  if (CFG.uniformComparison) {
    const sessionOf = (files) => sessTotal(aggregateStats(files.map(f => f.stats)));
    const svcKeys = [...new Set(pool.map(f => f.service))];
    const perSuite = svcKeys.map(s => sessionOf(pool.filter(f => f.service === s)));
    const labels = svcKeys.map(s => SERVICE_LABEL[s] || s);
    const per = perSuite.length ? Math.max(...perSuite) : 0;
    const total = perSuite.reduce((a, b) => a + b, 0);
    const uniform = perSuite.length > 0 && perSuite.every(v => v === per);
    const svcName = CFG.serviceTaskName || '서비스';
    const palette = [COLORS.accent2, COLORS.purple, COLORS.accent, COLORS.warn, COLORS.danger];
    const colors = labels.map((_, i) => palette[i % palette.length]);
    _setCmpCardHead('cmp-service', `${svcName}별 트래픽 분포`, `${svcName} 분포 (세션 개수)`);
    const canvas = document.getElementById('cmp-service');
    if (!canvas) return;
    const body = canvas.parentElement;
    if (charts['cmp-service']) { charts['cmp-service'].destroy(); delete charts['cmp-service']; }
    body.style.cssText = 'display:flex;align-items:center;gap:40px;height:180px;min-height:180px;flex:0 0 auto;padding:8px 24px;box-sizing:border-box;';
    body.innerHTML = `
      <div style="width:260px;height:150px;flex-shrink:0;position:relative;"><canvas id="cmp-service"></canvas></div>
      <div>
        <div style="font-size:14px;font-weight:700;color:#c8e6ff;margin-bottom:10px;">${svcName}별 ${uniform ? '균등 수집' : '트래픽 분포'}</div>
        <div style="font-size:12px;color:#6b9aba;line-height:2.1;">
          ${svcKeys.length}개 ${svcName} ${uniform ? '모두 동일하게' : '기준'}<br>
          <span style="color:#00ffa3;font-weight:600;">${per.toLocaleString()}개 세션</span>${uniform ? '씩 균등 수집' : ' (최대)'}<br>
          <span style="font-size:11px;color:#4a7a9b;">총 ${total.toLocaleString()} 세션</span>
        </div>
        <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;">
          ${labels.map((l, i) => `<span style="font-size:11px;color:${colors[i]};font-weight:600;">■ ${l}</span>`).join('')}
        </div>
      </div>`;
    const nc = document.getElementById('cmp-service');
    charts['cmp-service'] = new Chart(nc.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [{ data: perSuite, backgroundColor: colors, borderRadius: 6, barThickness: 48 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          datalabels: { display: true, color: '#000000', font: { weight: 700, size: 12 }, formatter: v => v.toLocaleString(), anchor: 'center', align: 'center' },
          tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y.toLocaleString()} 세션` } },
        },
        scales: { x: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { size: 10 } } }, y: { display: false, beginAtZero: true, max: (per || 1) * 1.4 } },
      },
      plugins: [DataLabels],
    });
    return;
  }

  const services = [...new Set(pool.map(f => f.service))].sort((a, b) => {
    const order = ['voip', 'streaming', 'chat', 'email', 'browsing', 'file_transfer', 'p2p'];
    return order.indexOf(a) - order.indexOf(b);
  });

  const sessionOf = (files) => {
    const a = aggregateStats(files.map(f => f.stats));
    return sessTotal(a);
  };
  const vpnData    = services.map(svc => sessionOf(pool.filter(f =>  f.vpn && f.service === svc)));
  const nonVpnData = services.map(svc => sessionOf(pool.filter(f => !f.vpn && f.service === svc)));

  const series = CFG.group ? [
    { label: GROUP_OFF, data: nonVpnData, color: GROUP_OFF_COLOR },
    { label: GROUP_ON,  data: vpnData,    color: GROUP_ON_COLOR },
  ] : [
    { label: '세션', data: services.map(svc => sessionOf(pool.filter(f => f.service === svc))), color: COLORS.accent2 },
  ];
  const labels = services.map(s => SERVICE_LABEL[s] || s);
  const config = buildComparisonChart(series, labels, { axis: 'x', unit: '세션' });
  makeOrUpdate('cmp-service', config);
}

// 2-b. 공격별 트래픽 분포 (공격/정상 데이터셋에서 빈 서비스 카드 자리에 표시)
function renderCmpAttack(pool) {
  const card = document.getElementById('cmp-attack-card');
  if (!card) return;
  if (!(CFG.group && CFG.group.attack)) { card.style.display = 'none'; return; }  // 공격 데이터셋만
  const sess = {};
  pool.filter(f => f.vpn).forEach(f => {
    sess[f.app] = (sess[f.app] || 0) + (sessTotal(f.stats));
  });
  let entries = Object.entries(sess).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]);
  if (!entries.length) { card.style.display = 'none'; return; }
  card.style.display = '';

  const labels = entries.map(e => e[0]);
  const raw = entries.map(e => e[1]);
  const total = raw.reduce((a, b) => a + b, 0) || 1;
  const pct = state.chartScale === 'percent';
  const data = pct ? raw.map(v => +(v / total * 100).toFixed(2)) : raw;

  makeOrUpdate('cmp-attack', {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: GROUP_ON_COLOR, borderRadius: 3, _raw: raw }] },
    options: {
      indexAxis: 'y',   // 가로 막대
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 44 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${raw[ctx.dataIndex].toLocaleString()}세션 (${(raw[ctx.dataIndex] / total * 100).toFixed(1)}%)` } },
        datalabels: {
          anchor: 'end', align: 'end', clamp: true,
          color: COLORS.fg1, font: { size: 10, weight: 600 },
          formatter: (v, ctx) => pct ? v + '%' : raw[ctx.dataIndex].toLocaleString(),
        },
      },
      scales: {
        x: { beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: v => pct ? v + '%' : fmtAxis(v) } },
        y: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { size: 10 } } },
      },
    },
    plugins: [DataLabels],
  });
}

// 2-c. 정상 트래픽 분포 (공격 데이터셋: 좌측 '정상' 박스)
//   정상 앱이 여럿(ustc·etri2)이면 앱별 세션 분포, 단일(cic benign)이면 L7 프로토콜별 분포.
function renderCmpNormal(pool) {
  const card = document.getElementById('cmp-normal-card');
  if (!card) return;
  if (!(CFG.group && CFG.group.attack)) { card.style.display = 'none'; return; }
  const normalFiles = pool.filter(f => !f.vpn);
  const normalApps = [...new Set(normalFiles.map(f => f.app))];
  // 표시 방식: config.cmpNormalMode 우선('app'|'l7'), 없으면 정상 앱 수로 자동
  //   (cic는 benign 외 unlabeled까지 잡혀 앱수>1이므로 'l7' 명시 필요)
  const mode = CFG.cmpNormalMode || (normalApps.length > 1 ? 'app' : 'l7');
  let labels, raw, sub;
  if (mode === 'app') {
    // 정상 앱별 세션 분포 (ustc·etri2)
    const sess = {};
    normalFiles.forEach(f => { sess[f.app] = (sess[f.app] || 0) + (sessTotal(f.stats)); });
    const entries = Object.entries(sess).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]);
    labels = entries.map(e => e[0]); raw = entries.map(e => e[1]);
    sub = `정상 ${CFG.appTaskName || '앱'}별 세션 비중`;
  } else {
    // 정상이 단일(cic benign): L7 프로토콜별 세션 분포
    const proto = {};
    normalFiles.forEach(f => { const sl = f.stats.sessions_by_l7 || {}; for (const k in sl) proto[k] = (proto[k] || 0) + sl[k]; });
    const entries = Object.entries(proto).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 12);
    labels = entries.map(e => e[0]); raw = entries.map(e => e[1]);
    sub = '정상 트래픽 L7 프로토콜별 세션 비중';
  }
  if (!labels.length) { card.style.display = 'none'; return; }
  card.style.display = '';
  _setCmpCardHead('cmp-normal', '정상 트래픽 분포', sub);
  const total = raw.reduce((a, b) => a + b, 0) || 1;
  const pct = state.chartScale === 'percent';
  const data = pct ? raw.map(v => +(v / total * 100).toFixed(2)) : raw;

  makeOrUpdate('cmp-normal', {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: GROUP_OFF_COLOR, borderRadius: 3, _raw: raw }] },
    options: {
      indexAxis: 'y',   // 가로 막대
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 44 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${raw[ctx.dataIndex].toLocaleString()}세션 (${(raw[ctx.dataIndex] / total * 100).toFixed(1)}%)` } },
        datalabels: {
          anchor: 'end', align: 'end', clamp: true,
          color: COLORS.fg1, font: { size: 10, weight: 600 },
          formatter: (v, ctx) => pct ? v + '%' : raw[ctx.dataIndex].toLocaleString(),
        },
      },
      scales: {
        x: { beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: v => pct ? v + '%' : fmtAxis(v) } },
        y: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { size: 10 } } },
      },
    },
    plugins: [DataLabels],
  });
}

// 3. 앱별 트래픽 순위
function renderCmpApp(pool) {
  // 균등 수집 데이터셋(cipher 등): 모든 도메인 동일 → 막대 1개 + '균등 수집' 설명
  if (CFG.uniformComparison) {
    const sessionOf = (files) => sessTotal(aggregateStats(files.map(f => f.stats)));
    const numSuites = new Set(pool.map(f => f.service)).size;
    const total = sessionOf(pool);
    const domSess = {}; pool.forEach(f => { domSess[f.app] = (domSess[f.app] || 0) + (sessTotal(f.stats)); });
    const domVals = Object.values(domSess);
    const numDomains = domVals.length;
    const domUniform = numDomains > 0 && domVals.every(v => v === domVals[0]);
    const perDomain = domUniform ? domVals[0] : (numDomains ? Math.round(total / numDomains) : 0);
    const perCell = numSuites ? Math.round(perDomain / numSuites) : 0;
    const appName = CFG.appTaskName || '앱';
    const svcName = CFG.serviceTaskName || '서비스';
    _setCmpCardHead('cmp-app', `${appName}별 트래픽 순위`, `전체 ${appName} · 세션 개수`);
    const canvas = document.getElementById('cmp-app');
    if (!canvas) return;
    const body = canvas.parentElement;
    if (charts['cmp-app']) { charts['cmp-app'].destroy(); delete charts['cmp-app']; }
    const card = body.closest('.chart-card'); if (card) card.style.gridColumn = '1 / -1';
    body.style.cssText = 'display:flex;align-items:center;gap:40px;height:180px;min-height:180px;flex:0 0 auto;padding:8px 24px;box-sizing:border-box;';
    body.innerHTML = `
      <div style="width:160px;height:150px;flex-shrink:0;position:relative;"><canvas id="cmp-app"></canvas></div>
      <div>
        <div style="font-size:14px;font-weight:700;color:#c8e6ff;margin-bottom:10px;">${domUniform ? `전 ${appName} 균등 수집` : `${appName}별 트래픽 분포`}</div>
        <div style="font-size:12px;color:#6b9aba;line-height:2.1;">
          ${domUniform
            ? `수집 대상 <span style="color:#00d4ff;font-weight:600;">${numDomains}개 ${appName}</span> 전체에 동일하게<br>
               <span style="color:#00ffa3;font-weight:600;">${perDomain.toLocaleString()}개 세션</span>씩 균등 수집<br>
               <span style="font-size:11px;color:#4a7a9b;">${svcName}별 ${perCell.toLocaleString()} 세션 × ${numSuites}종 = ${perDomain.toLocaleString()}</span>`
            : `수집 대상 <span style="color:#00d4ff;font-weight:600;">${numDomains}개 ${appName}</span> · 총 <span style="color:#00ffa3;font-weight:600;">${total.toLocaleString()} 세션</span><br>
               <span style="font-size:11px;color:#4a7a9b;">${appName}당 평균 ${perDomain.toLocaleString()} 세션</span>`}
        </div>
      </div>`;
    const nc = document.getElementById('cmp-app');
    charts['cmp-app'] = new Chart(nc.getContext('2d'), {
      type: 'bar',
      data: { labels: [domUniform ? `${appName}당` : `${appName} 평균`], datasets: [{ data: [perDomain], backgroundColor: COLORS.purple, borderRadius: 6, barThickness: 64 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          datalabels: { display: true, color: '#071a10', font: { weight: 700, size: 13 }, formatter: v => v.toLocaleString(), anchor: 'center', align: 'center' },
          tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y.toLocaleString()} 세션` } },
        },
        scales: { x: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { size: 11 } } }, y: { display: false, beginAtZero: true, max: (perDomain || 1) * 1.4 } },
      },
      plugins: [DataLabels],
    });
    return;
  }

  const appsSet = new Map();
  for (const f of pool) {
    const cur = appsSet.get(f.app) || { vpn: 0, non: 0 };
    const sess = sessTotal(f.stats);
    if (f.vpn) cur.vpn += sess;
    else       cur.non += sess;
    appsSet.set(f.app, cur);
  }
  const apps = [...appsSet.entries()]
    .sort((a, b) => (b[1].vpn + b[1].non) - (a[1].vpn + a[1].non))
    .slice(0, 12);

  const series = CFG.group ? [
    { label: GROUP_OFF, data: apps.map(([, v]) => v.non), color: GROUP_OFF_COLOR },
    { label: GROUP_ON,  data: apps.map(([, v]) => v.vpn), color: GROUP_ON_COLOR },
  ] : [
    { label: '세션', data: apps.map(([, v]) => v.vpn + v.non), color: COLORS.accent2 },
  ];
  const labels = apps.map(([app]) => app);
  const config = buildComparisonChart(series, labels, { axis: 'x', unit: '세션' });

  // 세로 막대: 전체 폭 사용 + 적당한 고정 높이 (가로처럼 길지 않게)
  const canvas = document.getElementById('cmp-app');
  if (canvas) {
    const body = canvas.parentElement;
    body.style.flex = '0 0 auto';
    body.style.height = '420px';
    body.style.minHeight = '420px';
    body.style.width = '100%';
    body.style.alignSelf = 'stretch';
    // 카드를 그리드 전체 폭으로 강제
    const card = body.closest('.chart-card');
    if (card) {
      card.style.gridColumn = '1 / -1';
    }
    canvas.style.width = '';
    canvas.style.height = '';
  }
  makeOrUpdate('cmp-app', config);
  requestAnimationFrame(() => { if (charts['cmp-app']) charts['cmp-app'].resize(); });
}

// 4. 클래스별 트래픽 특성 — #5 피드백으로 카드 삭제됨 (캔버스 없으면 skip)
function renderCmpClass() {
  if (!document.getElementById('cmp-class')) return;
  const classes = ['A_realtime', 'B_interactive', 'C_bulk'];
  const labels = classes.map(c => CLASS_LABEL[c]);

  const packetData = classes.map(c => (state.data.by_class[c] || {}).packet_count || 0);
  const avgSizeData = classes.map(c => (state.data.by_class[c] || {}).avg_packet_size || 0);

  makeOrUpdate('cmp-class', {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: '총 패킷 수',
          data: packetData,
          backgroundColor: [COLORS.clsA, COLORS.clsB, COLORS.clsC],
          borderRadius: 6,
          yAxisID: 'y',
          datalabels: {
            anchor: 'end', align: 'end',
            color: COLORS.fg0, font: { weight: 700, size: 11 },
            formatter: (v) => fmtNum(v),
          },
        },
        {
          label: '평균 패킷 크기 (Bytes)',
          data: avgSizeData,
          type: 'line',
          borderColor: COLORS.warn,
          backgroundColor: COLORS.warn,
          tension: 0.3,
          pointRadius: 5,
          pointHoverRadius: 7,
          yAxisID: 'y1',
          datalabels: {
            anchor: 'end', align: 'top',
            color: COLORS.warn, font: { weight: 700, size: 11 },
            formatter: (v) => Math.round(v) + 'B',
            offset: 6,
          },
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: 24 } },
      plugins: {
        legend: { position: 'bottom', labels: { color: COLORS.fg1, padding: 10, boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.type === 'line') return `${ctx.dataset.label}: ${Math.round(ctx.parsed.y)} B`;
              return `${ctx.dataset.label}: ${fmtNum(ctx.parsed.y)}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { weight: 600 } } },
        y:  { position: 'left',  grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: v => fmtAxis(v) }, title: { display: true, text: '패킷 수', color: COLORS.fg2 } },
        y1: { position: 'right', grid: { display: false },     ticks: { color: COLORS.warn,   callback: v => v + 'B' }, title: { display: true, text: '평균 크기', color: COLORS.warn } },
      },
    },
    plugins: [DataLabels],
  });
}

// ─── ISCX VPN 2016 전체 기준 데이터 ───────────────────────────────
const ISCX_BASELINE = {
  label: 'ISCX VPN 2016',
  l4_sessions: { TCP: 7165, UDP: 298098 },
  l7_sessions: { '기타 UDP': 277914, 'DNS': 19886, 'TLS/HTTPS': 3397, '기타 TCP': 2266, 'HTTP': 1359, 'QUIC': 229, 'SSH': 114, 'NTP': 76 },
  l4_packets:  { TCP: 13660223, UDP: 12209506, '기타': 406297 },
};

function renderCmpBaseline(pool) {
  if (!document.getElementById('cmp-base-l4')) return;

  const poolStats = aggregateStats(pool.map(f => f.stats));
  const curName = (state.data && state.data.meta && state.data.meta.name) || '현재 데이터셋';
  const C_CUR  = COLORS.accent;
  const C_BASE = COLORS.accent2;

  function pctOf(obj) {
    const t = Object.values(obj).reduce((a, b) => a + b, 0) || 1;
    const r = {};
    for (const [k, v] of Object.entries(obj)) r[k] = v / t * 100;
    return r;
  }

  // 1. L4 세션 비율 (TCP / UDP)
  const L4K = ['TCP', 'UDP'];
  const sl4 = ((poolStats.sessions_by_layer || {}).L4) || {};
  const curL4 = pctOf(Object.fromEntries(L4K.map(k => [k, sl4[k] || 0])));
  const basL4 = pctOf(ISCX_BASELINE.l4_sessions);
  makeOrUpdate('cmp-base-l4', buildComparisonChart([
    { label: curName,             data: L4K.map(k => +((curL4[k] || 0).toFixed(2))), color: C_CUR  },
    { label: ISCX_BASELINE.label, data: L4K.map(k => +((basL4[k] || 0).toFixed(2))), color: C_BASE },
  ], L4K, { axis: 'x', unit: '%' }));

  // 2. L7 세션 비율 (고정 8개 키)
  const L7K = ['기타 UDP', 'DNS', 'TLS/HTTPS', '기타 TCP', 'HTTP', 'QUIC', 'SSH', 'NTP'];
  const sl7 = ((poolStats.sessions_by_layer || {}).L7) || {};
  const curL7 = pctOf(Object.fromEntries(L7K.map(k => [k, sl7[k] || 0])));
  const basL7 = pctOf(ISCX_BASELINE.l7_sessions);
  makeOrUpdate('cmp-base-l7', buildComparisonChart([
    { label: curName,             data: L7K.map(k => +((curL7[k] || 0).toFixed(2))), color: C_CUR  },
    { label: ISCX_BASELINE.label, data: L7K.map(k => +((basL7[k] || 0).toFixed(2))), color: C_BASE },
  ], L7K, { axis: 'x', unit: '%' }));

  // 3. L4 패킷 비율 (TCP / UDP / 기타)
  const L4PK = ['TCP', 'UDP', '기타'];
  const pl4 = ((poolStats.protocol_layers || {}).L4) || {};
  const curP = pctOf(Object.fromEntries(L4PK.map(k => [k, pl4[k] || 0])));
  const basP = pctOf(ISCX_BASELINE.l4_packets);
  makeOrUpdate('cmp-base-pkt', buildComparisonChart([
    { label: curName,             data: L4PK.map(k => +((curP[k] || 0).toFixed(2))), color: C_CUR  },
    { label: ISCX_BASELINE.label, data: L4PK.map(k => +((basP[k] || 0).toFixed(2))), color: C_BASE },
  ], L4PK, { axis: 'x', unit: '%' }));
}

// =========================================================
// 일반 차트 (모든 영역)
// =========================================================
function renderCharts() {
  const s = currentStats();

  // 값/비율(%) 표시 — 차트별 독립 (state.chartPct[key])
  const PCT = state.chartPct || (state.chartPct = {});
  const toPct = (arr) => { const t = arr.reduce((a, b) => a + (b || 0), 0) || 1; return arr.map(v => (v || 0) / t * 100); };
  const bData = (pct, arr) => pct ? toPct(arr) : arr;             // 데이터 변환
  const bDL = (pct) => pct ? (v => v >= 0.1 ? v.toFixed(1) + '%' : '') : (v => fmtNum(v));  // 데이터라벨
  const bAxis = (pct) => pct ? (v => v + '%') : fmtAxis;          // 값축 눈금
  const bTip = (pct, v, unit) => pct ? `${v.toFixed(1)}%` : `${fmtNum(v)} ${unit}`;  // 툴팁

  // 1. Protocol Distribution — L2/L3/L4/L7/전체 × 세션수/패킷수 토글 (#6)
  const layer = state.protoLayer || 'L7';
  const metric = state.protoMetric || 'sessions';
  const src = (metric === 'packets' ? s.protocol_layers : s.sessions_by_layer) || {};
  let proto;
  const hasLayerData = ['L2', 'L3', 'L4', 'L7'].some(L => src[L] && Object.keys(src[L]).length);
  if (layer === 'all' && hasLayerData) {
    const merged = [];
    for (const L of ['L2', 'L3', 'L4', 'L7']) {
      for (const [k, v] of Object.entries(src[L] || {})) merged.push([`${L}:${k}`, v]);
    }
    proto = merged.sort((a, b) => b[1] - a[1]);
  } else if (layer !== 'all' && src[layer] && Object.keys(src[layer]).length) {
    proto = Object.entries(src[layer]).sort((a, b) => b[1] - a[1]);
  } else {
    // 폴백: 계층 데이터 없는 옛 data.json
    const fb = metric === 'sessions' && s.sessions_by_l7 && Object.keys(s.sessions_by_l7).length
      ? s.sessions_by_l7
      : (s.protocols || {});
    proto = Object.entries(fb).sort((a, b) => b[1] - a[1]);
  }
  const metricLabel = metric === 'packets' ? '패킷' : '세션';
  const pProto = !!PCT.protocols;

  // 세로 막대: 전체폭 카드라 높이를 명시적으로 줘야 보임 (다른 차트와 비슷하게)
  const protoCanvas = document.getElementById('chart-protocols');
  if (protoCanvas) {
    const pbody = protoCanvas.parentElement;
    pbody.style.height = '300px';
    pbody.style.minHeight = '300px';
    pbody.style.width = '100%';
  }
  // ── 물결 압축 막대 ──
  const _protoRawVals = proto.map(e => e[1]);
  const _protoLabels  = proto.map(e => e[0]);

  // 세션수 + L7: 지배적 막대 단독 압축 (기타 UDP·DNS 등 동적)
  const _isSessionsL7  = metric === 'sessions' && layer === 'L7';
  const _isSessionsAll = metric === 'sessions' && layer === 'all';
  let _compressLabel   = null;  // 단일 라벨 압축
  let _compressMinVal  = null;  // 이 값 이상인 막대 전부 압축

  if (_isSessionsL7 && !pProto && proto.length > 1) {
    const dominant = proto[0]; // 이미 내림차순 정렬
    if (dominant[1] / (proto[1][1] || 1) > 2.5) _compressLabel = dominant[0];
  } else if (_isSessionsAll && !pProto) {
    const ipv6Entry = proto.find(e => e[0] === 'L3:IPv6');
    if (ipv6Entry) _compressMinVal = ipv6Entry[1];
  }

  // 일반 절벽 감지 (명시적 압축 아닌 경우)
  const _protoSorted = [..._protoRawVals].sort((a, b) => b - a);
  let _cliffIdx = -1, _maxCliffRatio = 1;
  for (let i = 0; i < _protoSorted.length - 1; i++) {
    const r = _protoSorted[i] / (_protoSorted[i + 1] || 1);
    if (r > _maxCliffRatio) { _maxCliffRatio = r; _cliffIdx = i + 1; }
  }

  // 압축 여부 판단 헬퍼 (세 케이스 통일)
  const _isBarCompressed = (v, i) =>
    _compressLabel  ? _protoLabels[i] === _compressLabel :
    _compressMinVal ? v >= _compressMinVal :
    v > (protoCap || 0);

  const doBrokenBar = !pProto && (
    _compressLabel  ? true :
    _compressMinVal ? proto.some(e => e[1] >= _compressMinVal) :
    (_cliffIdx > 0 && _maxCliffRatio > 3)
  );
  let protoCap = null;
  if (doBrokenBar) {
    if (_compressLabel) {
      const otherVals = _protoRawVals.filter((_, i) => _protoLabels[i] !== _compressLabel);
      const maxOther = Math.max(...otherVals, 1);
      const raw = maxOther * 1.6;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      protoCap = Math.ceil(raw / mag) * mag;
    } else if (_compressMinVal) {
      const otherVals = _protoRawVals.filter(v => v < _compressMinVal);
      const maxOther = Math.max(...otherVals, 1);
      const raw = maxOther * 1.6;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      protoCap = Math.ceil(raw / mag) * mag;
    } else {
      const firstSmall = _protoSorted[_cliffIdx];
      const raw = firstSmall * 1.6;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      protoCap = Math.ceil(raw / mag) * mag;
    }
  }

  // 압축 막대: 실제 비율이 반영되도록 값을 리맵핑해서 Chart.js에 넘김
  // [minCompressed, maxCompressed] → [protoCap*1.15, protoCap*1.55]
  const _compressedVals = doBrokenBar
    ? _protoRawVals.filter((v, i) => _isBarCompressed(v, i))
    : [];
  const _cMin = _compressedVals.length ? Math.min(..._compressedVals) : 0;
  const _cMax = _compressedVals.length ? Math.max(..._compressedVals) : 0;
  const _cRange = _cMax - _cMin;

  let _remappedData = _protoRawVals.slice();
  let _remappedMax = doBrokenBar ? protoCap : null;
  if (doBrokenBar && protoCap) {
    const remapLo = protoCap * 1.15;
    const remapHi = protoCap * 1.55;
    _remappedData = _protoRawVals.map((v, i) => {
      if (!_isBarCompressed(v, i)) return v;
      if (_cRange === 0) return (remapLo + remapHi) / 2;
      return remapLo + (v - _cMin) / _cRange * (remapHi - remapLo);
    });
    _remappedMax = remapHi * 1.08; // 데이터라벨 공간 확보
  }

  const brokenBarPlugin = {
    id: 'brokenBarProto',
    afterDatasetsDraw(chart) {
      if (!doBrokenBar || !protoCap) return;
      const { ctx, chartArea } = chart;
      const bg = '#161b22';

      chart.data.datasets[0]?.data.forEach((val, i) => {
        if (!_isBarCompressed(_protoRawVals[i], i)) return;
        const meta = chart.getDatasetMeta(0);
        const bar = meta.data[i];
        if (!bar) return;

        const bx = bar.x;
        const bw = Math.max(bar.width || 0, 14);
        const x0 = bx - bw / 2, x1 = bx + bw / 2;

        // 막대 실제 픽셀 높이로 파형 위치 계산 (막대를 7:3으로 나눠 위에서 3 위치)
        const barTopPx  = bar.y;
        const barBotPx  = chartArea.bottom;
        const barHpx    = barBotPx - barTopPx;
        const waveY     = barTopPx + 0.3 * barHpx;
        const amp = 6, gapH = 12, N = 80;
        const w1Y = waveY - gapH / 2;
        const w2Y = waveY + gapH / 2;

        // 부드러운 단일 사이클 (~) 물결
        function wavePts(cy) {
          const pts = [];
          for (let j = 0; j <= N; j++) {
            const x = x0 + (x1 - x0) * (j / N);
            const y = cy + amp * Math.sin((j / N) * Math.PI * 2);
            pts.push([x, y]);
          }
          return pts;
        }

        const w1 = wavePts(w1Y);
        const w2 = wavePts(w2Y);

        // 두 물결 사이를 배경색으로 채움
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(w1[0][0], w1[0][1]);
        for (const [x, y] of w1) ctx.lineTo(x, y);
        for (let k = w2.length - 1; k >= 0; k--) ctx.lineTo(w2[k][0], w2[k][1]);
        ctx.closePath();
        ctx.fillStyle = bg;
        ctx.fill();
        ctx.restore();

        // 위쪽 물결선
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(w1[0][0], w1[0][1]);
        for (const [x, y] of w1.slice(1)) ctx.lineTo(x, y);
        ctx.strokeStyle = '#b1bac4';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();

        // 아래쪽 물결선
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(w2[0][0], w2[0][1]);
        for (const [x, y] of w2.slice(1)) ctx.lineTo(x, y);
        ctx.strokeStyle = '#b1bac4';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
      });
    },
  };
  makeOrUpdate('chart-protocols', {
    type: 'bar',
    data: {
      labels: proto.map(e => e[0]),
      datasets: [{
        data: bData(pProto, _remappedData),
        backgroundColor: proto.map((_, i) => PALETTE[i % PALETTE.length]),
        borderRadius: 4,
        maxBarThickness: 48,
      }],
    },
    options: {
      // 세로 막대 (indexAxis 'x' = 기본)
      responsive: true, maintainAspectRatio: false,
      animation: false,
      layout: { padding: { top: 24 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          bodyFont: { size: 11 },
          callbacks: {
            // 압축 막대는 리맵핑 값이 아닌 실제 값 표시
            label: (ctx) => bTip(pProto, _protoRawVals[ctx.dataIndex], metricLabel),
          },
        },
        datalabels: {
          anchor: 'end', align: 'end', clamp: true, clip: false,
          color: COLORS.fg0, font: { weight: 600, size: 10 },
          // 압축 막대는 리맵핑 값이 아닌 실제 값 표시
          formatter: (v, ctx) => bDL(pProto)(_protoRawVals[ctx.dataIndex]),
        },
      },
      scales: {
        // x축: 프로토콜 이름 (회전시켜 다 보이게)
        x: {
          type: 'category',
          offset: true,
          grid: { display: false },
          ticks: {
            color: COLORS.fg1, font: { weight: 600, size: 11 },
            maxRotation: proto.length > 5 ? 45 : 0,
            minRotation: proto.length > 5 ? 45 : 0,
            autoSkip: false,
          },
        },
        y: {
          type: 'linear', beginAtZero: true,
          max: doBrokenBar ? _remappedMax : undefined,
          grid: { color: COLORS.grid },
          ticks: {
            color: COLORS.fg2,
            // 압축 구간(protoCap 초과) 눈금 숨김
            callback: (v) => (doBrokenBar && protoCap && v > protoCap) ? null : bAxis(pProto)(v),
          },
        },
      },
    },
    plugins: [DataLabels, brokenBarPlugin],
  });

  // (로컬 vs 리모트 도넛 제거됨 — 프로토콜 분포가 전체 폭 사용)

  // 3. 세션 유형 — 유니캐스트(실제 통신) / 멀티캐스트 / 브로드캐스트
  const uniSess = s.unicast_sessions || 0;
  const mcastSess = s.multicast_sessions || 0;
  const bcastSess = s.broadcast_sessions || 0;
  const epTotal = uniSess + mcastSess + bcastSess;
  const epSub = document.getElementById('ep-metric-sub');
  if (epSub) epSub.textContent = '세션수 기준';
  makeOrUpdate('chart-endpoints', {
    type: 'doughnut',
    data: {
      labels: ['유니캐스트', '멀티캐스트', '브로드캐스트'],
      datasets: [{
        data: [uniSess, mcastSess, bcastSess],
        backgroundColor: [COLORS.accent, COLORS.warn, COLORS.purple],
        borderColor: COLORS.grid, borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: {
        legend: { position: 'bottom', labels: { color: COLORS.fg1, padding: 10, boxWidth: 10, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed;
              const pct = epTotal ? (v / epTotal * 100).toFixed(1) : 0;
              return `${ctx.label}: ${fmtNum(v)} 세션 (${pct}%)`;
            },
          },
        },
      },
    },
  });

  // 4. Packet Size Histogram — 고정 구간(작은 패킷 별도) 우선, 없으면 기존 히스토그램
  let binLabels, binCounts;
  if (s.packet_size_bins && s.packet_size_bins.counts) {
    const SIZE_LABEL = {
      '40-79': '40–79B', '80-159': '80–159B', '160-319': '160–319B', '320-639': '320–639B',
      '640-1279': '640–1279B', '1280-2559': '1.3–2.6KB', '2560-5119': '2.6–5.1KB', '5120+': '5.1KB+',
    };
    const rl = s.packet_size_bins.labels, rc = s.packet_size_bins.counts;
    // 0-19B는 헤더보다 작아 항상 0 → 20-39B와 합쳐 ≤39B 한 칸으로
    binLabels = ['≤39B'];
    binCounts = [(rc[0] || 0) + (rc[1] || 0)];
    for (let i = 2; i < rl.length; i++) { binLabels.push(SIZE_LABEL[rl[i]] || rl[i]); binCounts.push(rc[i]); }
  } else {
    const h = s.packet_size_histogram;
    binLabels = h.edges.slice(0, -1).map((e, i) => {
      const lo = Math.round(e);
      const hi = Math.round(h.edges[i + 1]);
      if (hi < 1500) return `${lo}-${hi}B`;
      if (hi < 10000) return `${(lo/1000).toFixed(1)}-${(hi/1000).toFixed(1)}KB`;
      return `${Math.round(lo/1000)}-${Math.round(hi/1000)}KB`;
    });
    binCounts = h.counts;
  }
  const pSizes = !!PCT.sizes;
  makeOrUpdate('chart-sizes', {
    type: 'bar',
    data: {
      labels: binLabels,
      datasets: [{
        data: bData(pSizes, binCounts),
        backgroundColor: 'rgba(0, 255, 163, 0.7)',
        borderColor: COLORS.accent, borderWidth: 1, borderRadius: 3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: 22 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => `크기: ${items[0].label}`,
            label: (ctx) => bTip(pSizes, ctx.parsed.y, '패킷'),
          },
        },
        datalabels: {
          display: (ctx) => {
            const v = ctx.dataset.data[ctx.dataIndex];
            return v != null && v > 0;
          },
          anchor: 'end', align: 'end',
          color: COLORS.fg0, font: { weight: 600, size: 9 },
          formatter: bDL(pSizes),
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: COLORS.fg2, maxRotation: 45, minRotation: 30,
            font: { size: 9 },
          },
        },
        y: {
          type: 'linear',
          beginAtZero: true,
          grid: { color: COLORS.grid },
          ticks: { color: COLORS.fg2, callback: bAxis(pSizes) },
          title: { display: true, text: '패킷 수', color: COLORS.fg2, font: { size: 10 } },
        },
      },
    },
    plugins: [DataLabels],
  });

  // 4-2. 세션 길이 분포 (#9) — 세션 안에 패킷이 몇 개씩 있는지 · 전체/TCP/UDP
  const sessLenProto = state.sessLenProto || 'all';
  const slhTcp = s.session_length_histogram_tcp;
  const slhUdp = s.session_length_histogram_udp;
  const slh = sessLenProto === 'tcp' && slhTcp ? slhTcp
    : sessLenProto === 'udp' && slhUdp ? slhUdp
    : s.session_length_histogram;
  const slhColor = sessLenProto === 'tcp' ? 'rgba(0, 255, 163, 0.7)'
    : sessLenProto === 'udp' ? 'rgba(255, 180, 84, 0.7)'
    : 'rgba(199, 146, 234, 0.7)';
  const slhBorder = sessLenProto === 'tcp' ? COLORS.accent
    : sessLenProto === 'udp' ? COLORS.warn
    : COLORS.purple;
  const pSessLen = !!PCT.sesslen;
  if (slh && slh.counts) {
    makeOrUpdate('chart-session-length', {
      type: 'bar',
      data: {
        labels: slh.labels,
        datasets: [{
          data: bData(pSessLen, slh.counts),
          backgroundColor: slhColor,
          borderColor: slhBorder, borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 22 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => `세션당 패킷 ${items[0].label}개`,
              label: (ctx) => bTip(pSessLen, ctx.parsed.y, '세션'),
            },
          },
          datalabels: {
            display: (ctx) => {
              const v = ctx.dataset.data[ctx.dataIndex];
              return v != null && v > 0;
            },
            anchor: 'end', align: 'end',
            color: COLORS.fg0, font: { weight: 600, size: 10 },
            formatter: bDL(pSessLen),
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: COLORS.fg2, font: { size: 10 } },
            title: { display: true, text: '세션당 패킷 개수', color: COLORS.fg2, font: { size: 10 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.grid },
            ticks: { color: COLORS.fg2, callback: bAxis(pSessLen) },
            title: { display: true, text: '세션 개수', color: COLORS.fg2, font: { size: 10 } },
          },
        },
      },
      plugins: [DataLabels],
    });
  }

  // 6. Top Local IPs (가로 막대 + 끝에 값) — 세션수/패킷수 토글
  const localUseSess = (state.localIpMetric || 'sessions') === 'sessions'
    && s.top_local_ips_sessions && s.top_local_ips_sessions.length;
  const localUnit = localUseSess ? '세션' : '패킷';
  const localIps = (localUseSess ? s.top_local_ips_sessions : s.top_local_ips).slice(0, 10);
  const pLocal = !!PCT.local;
  makeOrUpdate('chart-local', {
    type: 'bar',
    data: {
      labels: localIps.map(([ip]) => ip),
      datasets: [{
        data: bData(pLocal, localIps.map(([, c]) => c)),
        backgroundColor: localIps.map((_, i) => i === 0 ? COLORS.purple : COLORS.purple + '88'),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 60 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => bTip(pLocal, ctx.parsed.x, localUnit) } },
        datalabels: {
          display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
          anchor: 'end', align: 'end',
          color: COLORS.fg0, font: { weight: 600, size: 10 },
          formatter: bDL(pLocal),
        },
      },
      scales: {
        x: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pLocal) } },
        y: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
      },
    },
    plugins: [DataLabels],
  });

  // 7. Top Remote IPs (가로 막대 + 끝에 값) — 세션수/패킷수 토글
  const remoteUseSess = (state.remoteIpMetric || 'sessions') === 'sessions'
    && s.top_remote_ips_sessions && s.top_remote_ips_sessions.length;
  const remoteUnit = remoteUseSess ? '세션' : '패킷';
  const remoteIps = (remoteUseSess ? s.top_remote_ips_sessions : s.top_remote_ips).slice(0, 10);
  const pRemote = !!PCT.remote;
  makeOrUpdate('chart-remote', {
    type: 'bar',
    data: {
      labels: remoteIps.map(([ip]) => ip),
      datasets: [{
        data: bData(pRemote, remoteIps.map(([, c]) => c)),
        backgroundColor: remoteIps.map((_, i) => i === 0 ? COLORS.accent : COLORS.accent + '88'),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 60 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => bTip(pRemote, ctx.parsed.x, remoteUnit) } },
        datalabels: {
          display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
          anchor: 'end', align: 'end',
          color: COLORS.fg0, font: { weight: 600, size: 10 },
          formatter: bDL(pRemote),
        },
      },
      scales: {
        x: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pRemote) } },
        y: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
      },
    },
    plugins: [DataLabels],
  });

  // 7. Top Destination Ports (세로 막대 + 위에 값) — 세션수/패킷수 토글
  const portUseSess = (state.portMetric || 'sessions') === 'sessions'
    && s.top_dst_ports_sessions && s.top_dst_ports_sessions.length;
  const portUnit = portUseSess ? '세션' : '패킷';
  const ports = (portUseSess ? s.top_dst_ports_sessions : s.top_dst_ports).slice(0, 10);
  const pPort = !!PCT.ports;
  makeOrUpdate('chart-ports', {
    type: 'bar',
    data: {
      labels: ports.map(([p]) => p),
      datasets: [{
        data: bData(pPort, ports.map(([, c]) => c)),
        backgroundColor: COLORS.warn,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: 18 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => bTip(pPort, ctx.parsed.y, portUnit) } },
        datalabels: {
          display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
          anchor: 'end', align: 'end',
          color: COLORS.fg0, font: { weight: 600, size: 9 },
          formatter: bDL(pPort),
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { family: "'JetBrains Mono', monospace" } } },
        y: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pPort) } },
      },
    },
    plugins: [DataLabels],
  });

  // 8. Top Apps (가로 막대 + 값 라벨) — 세션수/패킷수 토글
  const appMetric = state.appMetric || 'sessions';
  const appUnit = appMetric === 'packets' ? '패킷' : '세션';
  const appAgg = {};
  for (const f of filteredFiles()) {
    const v = appMetric === 'packets'
      ? f.stats.packet_count
      : sessTotal(f.stats);
    appAgg[f.app] = (appAgg[f.app] || 0) + v;
  }
  const topApps = Object.entries(appAgg).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const pApp = !!PCT.apps;
  makeOrUpdate('chart-apps', {
    type: 'bar',
    data: {
      labels: topApps.map(e => e[0]),
      datasets: [{
        data: bData(pApp, topApps.map(e => e[1])),
        backgroundColor: topApps.map((_, i) => PALETTE[i % PALETTE.length]),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 60 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => bTip(pApp, ctx.parsed.x, appUnit) } },
        datalabels: {
          display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
          anchor: 'end', align: 'end',
          color: COLORS.fg0, font: { weight: 600, size: 10 },
          formatter: bDL(pApp),
        },
      },
      scales: {
        x: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pApp) } },
        y: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { weight: 600 } } },
      },
    },
    plugins: [DataLabels],
  });

  // 9. 세션 지속시간 분포 (유니캐스트 세션) — 전체/TCP/UDP + 값/비율 토글
  const durProto = state.durProto || 'all';
  const fdhTcp = s.flow_duration_hist_tcp;
  const fdhUdp = s.flow_duration_hist_udp;
  const fdh = durProto === 'tcp' && fdhTcp ? fdhTcp
    : durProto === 'udp' && fdhUdp ? fdhUdp
    : s.flow_duration_hist;
  const fdhColor = durProto === 'tcp' ? 'rgba(0, 255, 163, 0.7)'
    : durProto === 'udp' ? 'rgba(255, 180, 84, 0.7)'
    : 'rgba(94, 234, 212, 0.7)';
  const fdhBorder = durProto === 'tcp' ? COLORS.accent
    : durProto === 'udp' ? COLORS.warn
    : '#5eead4';
  if (fdh && fdh.counts) {
    const pDur = !!PCT.flowdur;
    makeOrUpdate('chart-flow-duration', {
      type: 'bar',
      data: {
        labels: fdh.labels,
        datasets: [{
          data: bData(pDur, fdh.counts),
          backgroundColor: fdhColor,
          borderColor: fdhBorder, borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (it) => `지속시간 ${it[0].label}`, label: (ctx) => bTip(pDur, ctx.parsed.y, '세션') } },
          datalabels: {
            display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
            anchor: 'end', align: 'end',
            color: COLORS.fg0, font: { weight: 600, size: 9 },
            formatter: bDL(pDur),
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: COLORS.fg1, font: { size: 10 } } },
          y: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pDur) } },
        },
      },
      plugins: [DataLabels],
    });
  }

  // 11. 세션당 바이트 분포 — 한 세션이 주고받은 총 바이트 · 전체/TCP/UDP + 값/비율 토글
  const sbyteProto = state.sbyteProto || 'all';
  const sbh = sbyteProto === 'tcp' && s.session_bytes_hist_tcp ? s.session_bytes_hist_tcp
    : sbyteProto === 'udp' && s.session_bytes_hist_udp ? s.session_bytes_hist_udp
    : s.session_bytes_hist;
  const sbhColor = sbyteProto === 'tcp' ? 'rgba(0, 255, 163, 0.7)'
    : sbyteProto === 'udp' ? 'rgba(255, 180, 84, 0.7)'
    : 'rgba(0, 212, 255, 0.7)';
  const sbhBorder = sbyteProto === 'tcp' ? COLORS.accent
    : sbyteProto === 'udp' ? COLORS.warn
    : COLORS.accent2;
  if (sbh && sbh.counts) {
    const pSbyte = !!PCT.sbyte;
    makeOrUpdate('chart-session-bytes', {
      type: 'bar',
      data: {
        labels: sbh.labels,
        datasets: [{
          data: bData(pSbyte, sbh.counts),
          backgroundColor: sbhColor,
          borderColor: sbhBorder, borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 22 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (it) => `세션 크기 ${it[0].label}`, label: (ctx) => bTip(pSbyte, ctx.parsed.y, '세션') } },
          datalabels: {
            display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
            anchor: 'end', align: 'end',
            color: COLORS.fg0, font: { weight: 600, size: 9 },
            formatter: bDL(pSbyte),
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: COLORS.fg2, font: { size: 10 } },
               title: { display: true, text: '세션당 총 바이트', color: COLORS.fg2, font: { size: 10 } } },
          y: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pSbyte) },
               title: { display: true, text: '세션 개수', color: COLORS.fg2, font: { size: 10 } } },
        },
      },
      plugins: [DataLabels],
    });
  }

  // 12. 세션 처리율 분포 (B/s) — 총 바이트/지속시간 · 전체/TCP/UDP + 값/비율 토글
  const thruProto = state.thruProto || 'all';
  const thh = thruProto === 'tcp' && s.throughput_hist_tcp ? s.throughput_hist_tcp
    : thruProto === 'udp' && s.throughput_hist_udp ? s.throughput_hist_udp
    : s.throughput_hist;
  const thhColor = thruProto === 'tcp' ? 'rgba(0, 255, 163, 0.7)'
    : thruProto === 'udp' ? 'rgba(255, 180, 84, 0.7)'
    : 'rgba(199, 146, 234, 0.7)';
  const thhBorder = thruProto === 'tcp' ? COLORS.accent
    : thruProto === 'udp' ? COLORS.warn
    : COLORS.purple;
  if (thh && thh.counts) {
    const pThru = !!PCT.thru;
    makeOrUpdate('chart-throughput', {
      type: 'bar',
      data: {
        labels: thh.labels,
        datasets: [{
          data: bData(pThru, thh.counts),
          backgroundColor: thhColor,
          borderColor: thhBorder, borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 22 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (it) => `처리율 ${it[0].label}`, label: (ctx) => bTip(pThru, ctx.parsed.y, '세션') } },
          datalabels: {
            display: (ctx) => ctx.dataset.data[ctx.dataIndex] != null && ctx.dataset.data[ctx.dataIndex] !== 0,
            anchor: 'end', align: 'end',
            color: COLORS.fg0, font: { weight: 600, size: 9 },
            formatter: bDL(pThru),
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: COLORS.fg2, font: { size: 10 } },
               title: { display: true, text: '세션 처리율 (B/s)', color: COLORS.fg2, font: { size: 10 } } },
          y: { type: 'linear', beginAtZero: true, grid: { color: COLORS.grid }, ticks: { color: COLORS.fg2, callback: bAxis(pThru) },
               title: { display: true, text: '세션 개수', color: COLORS.fg2, font: { size: 10 } } },
        },
      },
      plugins: [DataLabels],
    });
  }

  // 13. 네트워크 식별자 Top 20 (tls_sni / http_uri / dns_qry / http_ua)
  renderFieldStats();
}

// ──────────────────────────────────────────────────────────
// 네트워크 식별자 Top 20 차트
// ──────────────────────────────────────────────────────────
function renderFieldStats() {
  const fs = state.data.field_stats;
  if (!fs || !fs.summary || !Object.keys(fs.summary).length) {
    const n = document.getElementById('fieldstat-note');
    if (n) n.innerHTML = '<span style="opacity:.65;">이 데이터셋은 네트워크 식별자(SNI·DNS·URI·UA) 데이터가 없습니다 — 추후 추가 예정</span>';
    if (charts['chart-field-stats']) { charts['chart-field-stats'].destroy(); delete charts['chart-field-stats']; }
    return;
  }

  const FIELD_LABEL = { tls_sni: 'TLS SNI', http_uri: 'HTTP URI', dns_qry: 'DNS Query', http_ua: 'HTTP User-Agent' };
  const FIELD_DESC  = {
    dns_qry:  'DNS 조회 도메인 — 클라이언트가 쿼리한 호스트명 (평문, 암호화 무관)',
    tls_sni:  'TLS SNI — HTTPS 핸드셰이크 시 노출되는 대상 도메인',
    http_uri: 'HTTP 요청 URI — 평문 HTTP 세션의 요청 경로',
    http_ua:  'HTTP User-Agent — 브라우저·클라이언트 애플리케이션 식별 문자열',
  };
  let fld    = state.fsField  || 'dns_qry';
  const grp  = state.fsVpn    || 'overall';
  const descEl = document.getElementById('fieldstat-desc');
  if (descEl) descEl.textContent = FIELD_DESC[fld] || '';
  const PCT  = state.chartPct || {};
  const pFS  = !!PCT.fieldstat;

  // 현재 task/선택에 맞는 field_stats 섹션 결정
  let src = null;
  const task = state.task;
  const sub  = state.subSelection;
  if ((task === 'App') && sub && fs.by_app && fs.by_app[sub]) {
    src = fs.by_app[sub][_fsKey(grp)];
  } else if ((task === 'Service') && sub && fs.by_service && fs.by_service[sub]) {
    src = fs.by_service[sub][_fsKey(grp)];
  } else if (task === 'VPN') {
    src = (fs.summary || {})[GROUP_KEY_ON];
  } else {
    src = (fs.summary || {})[_fsKey(grp)];
  }

  // 선택 필드가 비어있으면 데이터 있는 필드로 자동 전환 (TLS 전용 데이터셋은 dns_qry가 비어있음)
  const _fieldArr = (f) => { const r = src && src[f]; return Array.isArray(r) ? r : (r && Array.isArray(r.top) ? r.top : (r && typeof r === 'object' ? Object.entries(r) : [])); };
  if (!_fieldArr(fld).length) {
    const _alt = ['tls_sni', 'dns_qry', 'http_uri', 'http_ua'].find(f => _fieldArr(f).length);
    if (_alt) {
      fld = _alt; state.fsField = _alt;
      document.querySelectorAll('#fieldstat-field-toggle .layer-btn').forEach(b => b.classList.toggle('active', b.dataset.fsfield === _alt));
      if (descEl) descEl.textContent = FIELD_DESC[fld] || '';
    }
  }

  // field_stats 항목 형식 호환: 배열 [[label,count]...] / {top:[...]} / {label:count} 모두 지원
  const _raw = src && src[fld];
  let entries = [];
  if (Array.isArray(_raw)) entries = _raw;
  else if (_raw && Array.isArray(_raw.top)) entries = _raw.top;
  else if (_raw && typeof _raw === 'object') entries = Object.entries(_raw).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    const note = document.getElementById('fieldstat-note');
    if (note) note.textContent = '해당 조건에서 데이터 없음';
    return;
  }

  const total = entries.reduce((s, e) => s + e[1], 0);
  const labels = entries.map(e => e[0]);
  const values = entries.map(e => e[1]);

  const note = document.getElementById('fieldstat-note');
  if (note) {
    const vpnLabel = { overall: '전체', vpn: GROUP_ON, non_vpn: GROUP_OFF }[grp] || grp;
    note.textContent = `${FIELD_LABEL[fld]} · ${vpnLabel} · 값 있는 세션 ${total.toLocaleString()}개 중 Top ${entries.length}`;
  }

  const bData2 = pFS ? values.map(v => total ? +(v / total * 100).toFixed(2) : 0) : values;

  makeOrUpdate('chart-field-stats', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: bData2,
        backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
        borderRadius: 3,
        maxBarThickness: 22,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      animation: false,
      layout: { padding: { right: 80 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = values[ctx.dataIndex];
              const pct = total ? (v / total * 100).toFixed(1) : 0;
              return pFS ? `${ctx.parsed.x.toFixed(2)}%` : `${v.toLocaleString()} 세션 (${pct}%)`;
            },
          },
        },
        datalabels: {
          anchor: 'end', align: 'end', clip: false, clamp: false,
          color: COLORS.fg0, font: { weight: 600, size: 10 },
          formatter: (v, ctx) => {
            const raw = values[ctx.dataIndex];
            return pFS ? v.toFixed(1) + '%' : raw.toLocaleString();
          },
        },
      },
      scales: {
        x: {
          type: 'linear', beginAtZero: true,
          grid: { color: COLORS.grid },
          ticks: { color: COLORS.fg2, callback: (v) => pFS ? v + '%' : fmtAxis(v) },
        },
        y: {
          grid: { display: false },
          ticks: {
            color: COLORS.fg1, font: { size: 10 },
            // 긴 라벨 자르기
            callback: (v, i) => {
              const lbl = labels[i] || '';
              return lbl.length > 45 ? lbl.slice(0, 43) + '…' : lbl;
            },
          },
        },
      },
    },
    plugins: [DataLabels],
  });
}

// =========================================================
// 수집 타임라인
// =========================================================
function renderTimeline() {
  const container = document.getElementById('timeline-body');
  const noteEl    = document.getElementById('timeline-note');
  if (!container) return;

  const tl = state.data.timeline;
  if (!tl || !tl.dates || !tl.dates.length) { const _emptyMsg = CFG.timelineNote || '수집 타임라인(날짜별 수집량) 데이터가 없습니다 — 추후 추가 예정'; container.innerHTML = `<div style="padding:22px 10px;opacity:.6;font-size:13px;">${_emptyMsg}</div>`; if (noteEl) noteEl.textContent = '—'; return; }

  const MONTH_ABBR = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  const LABEL_W = 110, PAD_L = 12, PAD_R = 20;
  const ROW_H = 28, MID_AXIS_H = 64, SEC_PAD = 16, DIV_H = 8, BREAK_W = 56;

  // ── 모드 자동 선택: 큰 공백이 전체 기간의 15% 미만이면 '연속'(압축X, :5000 방식), 아니면 '세그먼트'(압축O) ──
  // config.timelineMode 로 강제 지정 가능
  const GAP_DAYS = (CFG && CFG.timelineGapDays != null) ? CFG.timelineGapDays : 18;
  const sortedDates = [...tl.dates].sort();
  const _spanDays = Math.max(1, (new Date(sortedDates[sortedDates.length - 1]) - new Date(sortedDates[0])) / 86400000);
  let _maxGap = 0;
  for (let i = 1; i < sortedDates.length; i++) _maxGap = Math.max(_maxGap, (new Date(sortedDates[i]) - new Date(sortedDates[i - 1])) / 86400000);
  const _tlMode = CFG.timelineMode || (_maxGap < 0.15 * _spanDays ? 'continuous' : 'segmented');
  const SEGS = [];
  if (_tlMode === 'continuous') {
    SEGS.push({ s: sortedDates[0], e: sortedDates[sortedDates.length - 1] });   // 전체를 한 구간으로 (압축 없음)
  } else {
    let segS = sortedDates[0], prev = sortedDates[0];
    for (let i = 1; i < sortedDates.length; i++) {
      if ((new Date(sortedDates[i]) - new Date(prev)) / 86400000 > GAP_DAYS) { SEGS.push({ s: segS, e: prev }); segS = sortedDates[i]; }
      prev = sortedDates[i];
    }
    SEGS.push({ s: segS, e: prev });
  }
  SEGS.forEach(seg => {
    seg.startDt = new Date(seg.s); seg.endDt = new Date(seg.e);
    seg.monthLbl = MONTH_ABBR[seg.startDt.getMonth()];
    seg.year = String(seg.startDt.getFullYear());
  });

  // ── 세그먼트 사이 공백 라벨 (압축된 월 범위) ──
  const BREAK_LABELS = [];
  for (let i = 0; i < SEGS.length - 1; i++) {
    const months = [];
    let m = new Date(SEGS[i].endDt.getFullYear(), SEGS[i].endDt.getMonth() + 1, 1);
    const endM = new Date(SEGS[i + 1].startDt.getFullYear(), SEGS[i + 1].startDt.getMonth(), 1);
    while (m < endM) { months.push(MONTH_ABBR[m.getMonth()]); m = new Date(m.getFullYear(), m.getMonth() + 1, 1); }
    BREAK_LABELS.push(months.length ? (months.length === 1 ? months[0] : months[0] + ' – ' + months[months.length - 1]) : '···');
  }

  // ── 세그먼트당 균등 폭 + 내부는 자기 기간 비례 배치 (:5000 방식 — 작은 구간도 안 찌부러짐) ──
  const containerW = container.clientWidth || 960;
  const availW = Math.max(SEGS.length * 120, containerW - LABEL_W - PAD_L - PAD_R - BREAK_W * (SEGS.length - 1));
  const segW = availW / SEGS.length;

  let xCur = LABEL_W + PAD_L;
  SEGS.forEach((seg, i) => {
    seg.xOff = xCur;
    seg.xEnd = xCur + segW;
    seg.spanMs = Math.max(1, seg.endDt - seg.startDt);
    xCur = seg.xEnd;
    if (i < SEGS.length - 1) xCur += BREAK_W;
  });
  const SVG_W = xCur + PAD_R;

  // 세그먼트 내 위치: 단일 날짜는 중앙, 여러 날짜는 자기 기간 비례
  function xInSeg(seg, dt) { return seg.endDt > seg.startDt ? seg.xOff + (dt - seg.startDt) / seg.spanMs * segW : seg.xOff + segW / 2; }
  function xOf(dateStr) {
    const dt = new Date(dateStr);
    for (const seg of SEGS) if (dt >= seg.startDt && dt <= seg.endDt) return xInSeg(seg, dt);
    return -1;
  }
  const ACTIVE_DATES = tl.dates.filter(d => xOf(d) >= 0);

  // 예전(:5000) 타임라인 스타일(config.timelineClassic): 막대 폭을 날짜 간격에 비례(촘촘하면 얇게),
  // 막대 높이 공식도 예전값, 하단 DNS/TLS 범례 생략 + 날짜범위 표기. cstnet 등에서 사용.
  const _classicTL = !!(CFG && CFG.timelineClassic);
  const _classicBarW = Math.max(3, Math.min(10, (segW / Math.max(1, _spanDays)) * 0.6));

  const TL_COLOR = {
    'VPN':'#f59e0b','nonVPN':'#38bdf8','Non-VPN':'#38bdf8','Tor':'#f59e0b','nonTor':'#38bdf8','non-Tor':'#38bdf8',
    '공격':'#ff5e8a','악성':'#ff5e8a','정상':'#00ffa3',   // 공격/정상 데이터셋: 공격=빨강·정상=초록
    'TCP':'#5b9bd5','UDP':'#7b72c8',
    'llmnr':'#c0524a','dns':'#c0524a','tls':'#4a8cc0','bt-dht':'#c0524a','http':'#4a8cc0',
    'ftp':'#4a8cc0','dtls':'#4a8cc0','sip':'#507898','irc':'#507898','xmpp':'#507898',
    'pop':'#4a7a90','rtmpt':'#4a7090','rtpproxy':'#4a7090','socks':'#456878','pptp':'#3d6e8a',
    'bittorrent':'#c0524a','bt-tracker':'#c0524a','lsd':'#c0524a',
    'nbns':'#3d6e8a','nbdgm':'#456880','mdns':'#507898','stun':'#3a6878','dhcpv6':'#4a7888',
    'gquic':'#538898','ssdp':'#4a7080','db-lsp':'#456878','db-lsp-disc':'#456878','srvloc':'#3f6070',
    'ssh':'#4a8098','dhcp':'#426878','ntp':'#4a7090',
  };
  function ha(hex, a) { const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16); return `rgba(${r},${g},${b},${+a.toFixed(3)})`; }

  const bySection = {};
  tl.rows.forEach(r => { (bySection[r.section] = bySection[r.section] || []).push(r); });
  const _withTotal = rows => rows.map(r => ({ ...r, _total: Object.values(r.data).reduce((s,v)=>s+v,0) })).sort((a,b) => b._total - a._total);
  const _topApps = (CFG && CFG.timelineTopApps) || 5;
  // 섹션별 전체 행(합계 내림차순) — 행 선택 팝오버·드릴다운에서 사용
  const bySectionAll = { '앱': _withTotal(bySection['앱'] || []), '서비스': _withTotal(bySection['서비스'] || []), 'L7': _withTotal(bySection['L7'] || []) };
  const TL_DEF_N = { '앱': _topApps, '서비스': 5, 'L7': 5 };
  // 표시 행: state.tlSel[sec]가 Set이면 그 선택(빈 Set=섹션 숨김), null/undefined면 기본 top-N
  function pickRows(sec) {
    const all = bySectionAll[sec];
    const sel = state.tlSel ? state.tlSel[sec] : null;
    if (sel != null) return all.filter(r => sel.has(r.label));
    return all.slice(0, TL_DEF_N[sec]);
  }
  bySection['앱']     = pickRows('앱');
  bySection['서비스'] = pickRows('서비스');
  bySection['L7']     = pickRows('L7');

  // 섹션 선택: 분류=그룹축 있을 때만, 서비스=의미있는 라벨(none/unknown 제외) 있을 때만
  const _svc = bySectionAll['서비스'] || [];
  const _svcMeaningful = _svc.some(r => !/^(none|unknown|)$/i.test((r.label || '').trim()));
  let TOP, BOT;
  if (CFG.timelineSections) {   // config에서 축 위/아래 섹션 배치 지정 (예: cipher = {top:['서비스'], bottom:['앱']})
    TOP = (CFG.timelineSections.top || []).slice();
    BOT = (CFG.timelineSections.bottom || []).slice();
  } else {
    TOP = [];
    if (CFG.group) TOP.push('분류');
    if (_svcMeaningful) TOP.push('서비스');
    TOP.push('앱');
    BOT = ['L7'];
  }
  // 행 선택 컨트롤(칩+팝오버) — 분류 제외, 전체 행이 있는 섹션만
  renderTlControls([...TOP, ...BOT].filter(s => s !== '분류' && (bySectionAll[s] || []).length), bySectionAll, TL_DEF_N);

  const TOP_PAD = 24;
  let totalH = TOP_PAD;
  [...TOP, ...BOT].forEach(s => { const rows = bySection[s] || []; if (rows.length) totalH += SEC_PAD + rows.length * ROW_H; });
  totalH += DIV_H + MID_AXIS_H + DIV_H + 16;

  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('width', SVG_W); svg.setAttribute('height', totalH);
  svg.style.cssText = 'display:block;overflow:visible;';
  function mk(tag, attrs, parent) { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k,v]) => e.setAttribute(k, String(v))); if (parent) parent.appendChild(e); return e; }

  function drawBreak(xStart, label) {
    mk('rect', { x:xStart, y:0, width:BREAK_W, height:totalH, fill:'#060f1c' }, svg);
    for (let yy = -BREAK_W; yy < totalH + BREAK_W; yy += 10) mk('line', { x1:xStart, y1:yy, x2:xStart+BREAK_W, y2:yy+BREAK_W, stroke:'#112236', 'stroke-width':1.5 }, svg);
    [xStart, xStart + BREAK_W].forEach(ex => mk('line', { x1:ex, y1:0, x2:ex, y2:totalH, stroke:'#1e3f5c', 'stroke-width':2 }, svg));
    const gg = document.createElementNS(NS, 'g');
    gg.setAttribute('transform', `translate(${xStart + BREAK_W / 2},${totalH / 2}) rotate(-90)`);
    svg.appendChild(gg);
    const lw = label.length * 6 + 12;
    mk('rect', { x:-lw/2, y:-9, width:lw, height:17, rx:3, fill:'#0c1f30', opacity:0.9 }, gg);
    mk('text', { x:0, y:4, fill:'#5a9fc0', 'font-size':10, 'font-family':"'JetBrains Mono',monospace", 'text-anchor':'middle', 'font-weight':'bold', 'letter-spacing':1.5 }, gg).textContent = label;
  }
  SEGS.slice(0, -1).forEach((seg, i) => drawBreak(seg.xEnd, BREAK_LABELS[i]));

  const _drawMonth = (x, lbl, yr) => {
    mk('line', { x1:x, y1:0, x2:x, y2:totalH, stroke:'#0d1e30', 'stroke-width':1 }, svg);
    mk('text', { x:x + 5, y:9, fill:'#4a7a9b', 'font-size':9, 'font-family':"'JetBrains Mono',monospace", 'font-weight':'bold', 'letter-spacing':1 }, svg).textContent = yr;
    mk('text', { x:x + 5, y:20, fill:'#6b8fa8', 'font-size':11, 'font-family':"'JetBrains Mono',monospace", 'font-weight':'bold', 'letter-spacing':2 }, svg).textContent = lbl;
  };
  SEGS.forEach(seg => {
    _drawMonth(seg.xOff, seg.monthLbl, seg.year);              // 세그먼트 시작 월
    let _mm = new Date(seg.startDt.getFullYear(), seg.startDt.getMonth() + 1, 1);
    while (_mm <= seg.endDt) {                                 // 세그먼트 내부 매 월초 (SEP 등 누락 방지)
      _drawMonth(xInSeg(seg, _mm), MONTH_ABBR[_mm.getMonth()], String(_mm.getFullYear()));
      _mm = new Date(_mm.getFullYear(), _mm.getMonth() + 1, 1);
    }
  });

  function drawDateAxis(baseY) {
    SEGS.forEach(seg => mk('line', { x1:seg.xOff, y1:baseY, x2:seg.xEnd, y2:baseY, stroke:'#2a4a6a', 'stroke-width':1.5 }, svg));
    if (_tlMode === 'continuous') {
      // 연속 모드: 축도 월 단위만 (개별 날짜 생략 — :5000 방식)
      SEGS.forEach(seg => {
        for (let _m = new Date(seg.startDt.getFullYear(), seg.startDt.getMonth(), 1); _m <= seg.endDt; _m = new Date(_m.getFullYear(), _m.getMonth() + 1, 1)) {
          const _x = xInSeg(seg, _m < seg.startDt ? seg.startDt : _m);
          mk('line', { x1:_x, y1:baseY - 24, x2:_x, y2:baseY, stroke:'#4d7fa8', 'stroke-width':2 }, svg);
          mk('text', { x:_x, y:baseY - 28, fill:'#c8e6ff', 'font-size':12, 'font-family':"'JetBrains Mono',monospace", 'text-anchor':'middle', 'font-weight':'600' }, svg).textContent = MONTH_ABBR[_m.getMonth()];
        }
      });
    } else {
      const sorted = [...ACTIVE_DATES].sort();
      // 시간단위 버킷(YYYY-MM-DD HH:00)이면 라벨이 넓어 겹치므로 간격을 넓히고 짧게 표기
      const _isHourly = sorted.some(d => d.length > 10);
      const MIN_GAP = _isHourly ? 58 : 36;
      const _segLabeled = new Set();
      let lastX = -Infinity;
      sorted.forEach(d => {
        const x = xOf(d); if (x < 0) return;
        mk('line', { x1:x, y1:baseY - 24, x2:x, y2:baseY, stroke:'#4d7fa8', 'stroke-width':2 }, svg);
        if (x - lastX >= MIN_GAP) {
          let lbl;
          if (_isHourly) {
            const hour = d.slice(11);                    // "11:00"
            const si = SEGS.findIndex(s => { const dt = new Date(d); return dt >= s.startDt && dt <= s.endDt; });
            if (!_segLabeled.has(si)) { lbl = d.slice(5, 10).replace('-', '/') + ' ' + hour; _segLabeled.add(si); }  // 하루당 첫 라벨엔 날짜
            else lbl = hour;                             // 이후엔 시각만
          } else {
            lbl = d.slice(5).replace('-', '/');
          }
          mk('text', { x, y:baseY - 28, fill:'#c8e6ff', 'font-size':12, 'font-family':"'JetBrains Mono',monospace", 'text-anchor':'middle', 'font-weight':'600' }, svg).textContent = lbl;
          lastX = x;
        }
      });
    }
  }

  let curY = TOP_PAD;
  let ttEl = container.parentElement && container.parentElement.querySelector('.tl-tt');
  if (!ttEl) {
    ttEl = document.createElement('div');
    ttEl.className = 'tl-tt';
    ttEl.style.cssText = "position:fixed;background:#0c1628;border:1px solid #1e3a5f;color:#94afc8;padding:5px 10px;font-size:11px;font-family:'Noto Sans KR',sans-serif;border-radius:4px;pointer-events:none;display:none;z-index:1000;white-space:nowrap;";
    document.body.appendChild(ttEl);
  }
  function positionTt(e) { const w = ttEl.offsetWidth || 220; const left = (e.clientX + 14 + w > window.innerWidth - 8) ? (e.clientX - 14 - w) : (e.clientX + 14); ttEl.style.left = left + 'px'; ttEl.style.top = (e.clientY - 32) + 'px'; }

  const APP_COLORS = ['#00ffa3','#00d4ff','#ffb454','#c792ea','#ff5e8a','#5eead4','#facc15','#fb7185','#a78bfa','#34d399','#f97316','#60a5fa','#e879f9','#4ade80','#fbbf24'];
  let _ci = 0; const _lc = new Map();
  function getColor(label) { if (TL_COLOR[label]) return TL_COLOR[label]; if (!_lc.has(label)) _lc.set(label, APP_COLORS[_ci++ % APP_COLORS.length]); return _lc.get(label); }

  function drawSection(secName) {
    const rows = bySection[secName] || [];
    if (!rows.length) return;
    curY += SEC_PAD;
    const _secLabel = (secName === '앱' && CFG.appTaskName) ? CFG.appTaskName : (secName === '서비스' && CFG.serviceTaskName) ? CFG.serviceTaskName : secName;
    mk('text', { x:LABEL_W - 4, y:curY - 4, fill:'#4a7a9b', 'font-size':9, 'font-family':"'JetBrains Mono',monospace", 'font-weight':'bold', 'text-anchor':'end', 'letter-spacing':1.5 }, svg).textContent = _secLabel.toUpperCase();
    mk('line', { x1:LABEL_W + PAD_L, y1:curY - 1, x2:SVG_W - PAD_R, y2:curY - 1, stroke:'#0c1a2a', 'stroke-width':1 }, svg);
    rows.forEach(row => {
      const cy = curY + ROW_H / 2;
      const color = getColor(row.label);
      const vals = ACTIVE_DATES.map(d => row.data[d] || 0);
      const rowMax = Math.max(...vals, 1);
      const rowTotal = vals.reduce((s,v) => s + v, 0);
      const active = ACTIVE_DATES.filter(d => row.data[d] > 0);
      if (active.length > 1) { const x1 = xOf(active[0]), x2 = xOf(active[active.length - 1]); mk('line', { x1, y1:cy, x2, y2:cy, stroke:ha(color, 0.35), 'stroke-width':2, 'stroke-linecap':'round' }, svg); }
      active.forEach(date => {
        const x = xOf(date); if (x < 0) return;
        const cnt = row.data[date];
        const inten = Math.sqrt(cnt / rowMax);
        const barH = _classicTL ? Math.round(4 + inten * (ROW_H - 8)) : Math.round(3 + inten * (ROW_H - 5));
        const barW = _classicTL ? _classicBarW : 7;
        const rect = mk('rect', { x:x - barW/2, y:cy - barH/2, width:barW, height:barH, rx:2, ry:2, fill:ha(color, 0.55 + inten * 0.45) }, svg);
        rect.style.cursor = 'pointer';
        rect.addEventListener('mouseenter', e => {
          const pct = rowTotal ? (cnt / rowTotal * 100).toFixed(1) : 0;
          ttEl.innerHTML = `<span style="color:${color}">${row.label}</span>&nbsp;·&nbsp;${date}&nbsp;·&nbsp;<b style="color:#f59e0b">${cnt.toLocaleString()}</b>세션&nbsp;(${pct}%)<span style="opacity:.5;">&nbsp;· 클릭 상세</span>`;
          ttEl.style.display = 'block'; positionTt(e); rect.setAttribute('fill', ha(color, 1));
        });
        rect.addEventListener('mousemove', e => positionTt(e));
        rect.addEventListener('mouseleave', () => { ttEl.style.display = 'none'; rect.setAttribute('fill', ha(color, 0.55 + inten * 0.45)); });
        rect.addEventListener('click', () => { ttEl.style.display = 'none'; openTlDrill(secName, row, date, color); });
      });
      mk('circle', { cx:8, cy, r:4, fill:color }, svg);
      mk('text', { x:16, y:cy + 4, fill:'#c8dded', 'font-size':11, 'font-family':"'Noto Sans KR',sans-serif", 'text-anchor':'start' }, svg).textContent = row.label;
      curY += ROW_H;
    });
  }

  TOP.forEach(drawSection);
  curY += DIV_H;
  drawDateAxis(curY + MID_AXIS_H);
  curY += MID_AXIS_H;
  BOT.forEach(drawSection);

  container.innerHTML = '';
  container.appendChild(svg);

  // ── 노트: 데이터셋별 자동 (세션수 · 수집일 · 활성 월 · 압축 구간) ──
  if (noteEl) {
    const sa = state.data.summary && state.data.summary.all;
    const totalSessions = sa ? sessTotal(sa) : null;
    let html;
    // 버킷이 시간단위(YYYY-MM-DD HH:00)여도 '수집일'은 달력상 날짜 수로 집계 (일단위면 동일)
    const _dayCount = new Set(sortedDates.map(d => d.slice(0, 10))).size;
    if (_classicTL) {
      // 예전(:5000) 방식: 세션 · 수집일 · 날짜범위 (DNS/TLS 범례 없음)
      html = (totalSessions ? totalSessions.toLocaleString() + ' 세션 &nbsp;·&nbsp; ' : '')
        + _dayCount + '개 수집일 &nbsp;·&nbsp; ' + sortedDates[0] + ' – ' + sortedDates[sortedDates.length - 1];
    } else {
      const segMonths = [...new Set(sortedDates.map(d => d.slice(0, 7).replace('-', '.')))];
      html = (totalSessions ? totalSessions.toLocaleString() + ' 세션 &nbsp;·&nbsp; ' : '')
        + _dayCount + '개 수집일 &nbsp;·&nbsp; ' + segMonths.join(' · ');
      if (BREAK_LABELS.length) html += '&emsp;<span style="opacity:.5;font-size:10px;">▒ ' + BREAK_LABELS.join(' · ') + ' 공백 압축</span>';
      html += '&emsp;<span style="color:#c0524a;font-weight:600;">●</span> DNS 계열 (dns · llmnr · bt-dht)'
           + '&ensp;<span style="color:#4a8cc0;font-weight:600;">●</span> TLS 계열 (tls · http)';
    }
    // 날짜축이 실제 날짜가 아닌 데이터셋(예: USTC 경과시간)용 캡션
    if (CFG.timelineCaption) html = `<span style="color:#e0a030;font-weight:600;">⚠ ${CFG.timelineCaption}</span><br>` + html;
    noteEl.innerHTML = html;
  }
}

// =========================================================
// 타임라인 행 선택(칩+팝오버) + 버킷 클릭 드릴다운
// =========================================================
const _tlEsc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// ── 행 선택 팝오버 ──
let _tlPopEl = null, _tlPopSec = null;
function _tlClosePop() { if (_tlPopEl) { _tlPopEl.remove(); _tlPopEl = null; _tlPopSec = null; } }
document.addEventListener('click', e => {
  if (_tlPopEl && !_tlPopEl.contains(e.target) && !(e.target.closest && e.target.closest('.tl-chip'))) _tlClosePop();
});
// 페이지/타임라인 스크롤 시 팝오버 닫기 — 단 팝오버 내부 리스트 스크롤은 유지
window.addEventListener('scroll', e => { if (_tlPopEl && !(e.target instanceof Node && _tlPopEl.contains(e.target))) _tlClosePop(); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { _tlClosePop(); _tlDrillClose(); } });

function renderTlControls(secs, bySectionAll, defN) {
  const body = document.getElementById('timeline-body');
  if (!body) return;
  let bar = document.getElementById('timeline-controls');
  if (!secs.length) { if (bar) bar.remove(); return; }
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'timeline-controls';
    bar.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:2px 0 8px;';
    body.parentElement.insertBefore(bar, body);
  }
  const secLabel = s => (s === '앱' && CFG.appTaskName) ? CFG.appTaskName : (s === '서비스' && CFG.serviceTaskName) ? CFG.serviceTaskName : s;
  bar.innerHTML = `<span style="font-size:10px;color:#4a7a9b;font-family:'JetBrains Mono',monospace;letter-spacing:1px;font-weight:bold;">표시 행</span>`;
  secs.forEach(sec => {
    const all = bySectionAll[sec] || [];
    const sel = state.tlSel ? state.tlSel[sec] : null;
    const effCnt = (sel != null) ? all.filter(r => sel.has(r.label)).length : Math.min(defN[sec] || 5, all.length);
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'tl-chip';
    chip.style.cssText = `background:#101d2e;border:1px solid ${sel != null ? '#2f6a9e' : '#24405e'};color:#9fc2dd;font-size:11px;padding:3px 10px;border-radius:12px;cursor:pointer;font-family:'Noto Sans KR',sans-serif;`;
    chip.innerHTML = `${_tlEsc(secLabel(sec))} <b style="color:#38bdf8;">${effCnt}</b><span style="opacity:.55;">/${all.length}</span> <span style="opacity:.6;">▾</span>`;
    chip.addEventListener('click', e => {
      e.stopPropagation();
      if (_tlPopSec === sec) _tlClosePop();
      else _tlOpenPop(chip, sec, all, defN[sec] || 5);
    });
    bar.appendChild(chip);
  });
}

function _tlOpenPop(anchor, sec, all, defN) {
  _tlClosePop();
  const pop = document.createElement('div');
  pop.style.cssText = 'position:fixed;z-index:1001;background:#0c1628;border:1px solid #1e3a5f;border-radius:8px;padding:8px;box-shadow:0 10px 28px rgba(0,0,0,.55);width:250px;';
  pop.addEventListener('click', e => e.stopPropagation());

  const head = document.createElement('div');
  head.style.cssText = 'display:flex;gap:6px;margin-bottom:7px;';
  const mkBtn = (txt) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = txt;
    b.style.cssText = 'flex:1;background:#13253a;border:1px solid #24405e;color:#9fc2dd;font-size:10px;padding:3px 0;border-radius:4px;cursor:pointer;';
    return b;
  };
  const bDef = mkBtn(`기본 상위${defN}`), bAll = mkBtn('전체');
  head.appendChild(bDef); head.appendChild(bAll);
  pop.appendChild(head);

  const list = document.createElement('div');
  list.style.cssText = 'max-height:250px;overflow-y:auto;display:flex;flex-direction:column;gap:1px;';
  pop.appendChild(list);

  const sel = state.tlSel ? state.tlSel[sec] : null;
  const eff = new Set((sel != null) ? [...sel] : all.slice(0, defN).map(r => r.label));
  const boxes = [];
  all.forEach(r => {
    const lab = document.createElement('label');
    lab.style.cssText = 'display:flex;align-items:center;gap:7px;font-size:11px;color:#c8dded;padding:3px 4px;border-radius:4px;cursor:pointer;';
    lab.addEventListener('mouseenter', () => lab.style.background = '#13253a');
    lab.addEventListener('mouseleave', () => lab.style.background = '');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = eff.has(r.label);
    cb.dataset.lbl = r.label;
    cb.style.cssText = 'accent-color:#38bdf8;margin:0;';
    const name = document.createElement('span');
    name.textContent = r.label;
    name.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    const cnt = document.createElement('span');
    cnt.textContent = r._total.toLocaleString();
    cnt.style.cssText = 'color:#4a7a9b;font-size:10px;font-family:\'JetBrains Mono\',monospace;';
    lab.appendChild(cb); lab.appendChild(name); lab.appendChild(cnt);
    list.appendChild(lab);
    boxes.push(cb);
    cb.addEventListener('change', () => {
      state.tlSel[sec] = new Set(boxes.filter(b => b.checked).map(b => b.dataset.lbl));
      renderTimeline();
    });
  });
  bDef.addEventListener('click', () => {
    state.tlSel[sec] = null;
    const defSet = new Set(all.slice(0, defN).map(r => r.label));
    boxes.forEach(b => b.checked = defSet.has(b.dataset.lbl));
    renderTimeline();
  });
  bAll.addEventListener('click', () => {
    state.tlSel[sec] = new Set(all.map(r => r.label));
    boxes.forEach(b => b.checked = true);
    renderTimeline();
  });

  document.body.appendChild(pop);
  const rc = anchor.getBoundingClientRect();
  const ph = pop.offsetHeight, pw = pop.offsetWidth;
  let top = rc.bottom + 6;
  if (top + ph > window.innerHeight - 8) top = Math.max(8, rc.top - ph - 6);
  let left = rc.left;
  if (left + pw > window.innerWidth - 8) left = window.innerWidth - 8 - pw;
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
  _tlPopEl = pop; _tlPopSec = sec;
}

// ── 버킷 클릭 드릴다운 모달 ──
let _tlDrillOv = null;
function _tlDrillClose() { if (_tlDrillOv) { _tlDrillOv.remove(); _tlDrillOv = null; } }

function openTlDrill(secName, row, dateKey, color) {
  _tlDrillClose();
  const tl = state.data && state.data.timeline;
  if (!tl) return;
  const hourlyDataset = tl.dates.some(d => d.length > 10);   // 버킷 키가 "YYYY-MM-DD HH:00"
  const day = dateKey.slice(0, 10);
  const clickedHour = dateKey.length > 10 ? parseInt(dateKey.slice(11, 13), 10) : -1;

  // 시간대별 시리즈: ① 시간 버킷 데이터셋이면 그 날의 24시간 조합, ② 일 버킷 + row.hourly 주입분, ③ 없음
  let hours = null;
  if (hourlyDataset) {
    hours = Array.from({ length: 24 }, (_, h) => row.data[`${day} ${String(h).padStart(2, '0')}:00`] || 0);
  } else if (row.hourly && Array.isArray(row.hourly[day])) {
    hours = row.hourly[day].slice(0, 24);
    while (hours.length < 24) hours.push(0);
  }
  const dayTotal = hours ? hours.reduce((s, v) => s + v, 0) : (row.data[dateKey] || 0);
  const rowTotal = Object.values(row.data).reduce((s, v) => s + v, 0);
  const dayPct = rowTotal ? (dayTotal / rowTotal * 100).toFixed(1) : '0';
  const peakH = (hours && dayTotal) ? hours.indexOf(Math.max(...hours)) : -1;

  // 같은 섹션 행들의 그 날짜 구성 (전체 행 기준 — 표시 선택과 무관)
  const dayVal = r => hourlyDataset
    ? Object.keys(r.data).reduce((s, k) => (k.slice(0, 10) === day ? s + r.data[k] : s), 0)
    : (r.data[day] || 0);
  const comp = tl.rows.filter(r => r.section === secName)
    .map(r => ({ label: r.label, v: dayVal(r) }))
    .filter(x => x.v > 0)
    .sort((a, b) => b.v - a.v);
  const compTotal = comp.reduce((s, x) => s + x.v, 0);

  const ov = document.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(2,8,16,.62);z-index:1002;display:flex;align-items:center;justify-content:center;padding:20px;';
  ov.addEventListener('click', e => { if (e.target === ov) _tlDrillClose(); });

  const kpi = (label, val, sub) => `
    <div style="flex:1;background:#0d1a2b;border:1px solid #1a2e45;border-radius:8px;padding:10px 12px;min-width:120px;">
      <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px;font-family:'JetBrains Mono',monospace;">${label}</div>
      <div style="font-size:18px;font-weight:700;color:#e6f2ff;margin-top:3px;">${val}</div>
      ${sub ? `<div style="font-size:10px;color:#4a7a9b;margin-top:2px;">${sub}</div>` : ''}
    </div>`;

  let hoursHtml;
  if (hours) {
    const hMax = Math.max(...hours, 1);
    hoursHtml = `
      <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px;font-family:'JetBrains Mono',monospace;margin:14px 0 6px;">시간대별 세션 (00–23시)</div>
      <div style="display:flex;align-items:flex-end;gap:2px;height:110px;background:#0a1524;border:1px solid #14273d;border-radius:8px;padding:8px 8px 4px;">
        ${hours.map((v, h) => {
          const hp = v ? Math.max(3, Math.round(v / hMax * 100)) : 0;
          const hl = h === clickedHour;
          return `<div title="${String(h).padStart(2, '0')}시 · ${v.toLocaleString()}세션" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;cursor:default;">
            <div style="height:${hp}%;min-height:${v ? 3 : 1}px;background:${v ? color : '#152538'};opacity:${v ? (hl ? 1 : 0.75) : 1};border-radius:2px 2px 0 0;${hl ? `outline:1.5px solid #ffffff88;outline-offset:1px;` : ''}"></div>
          </div>`;
        }).join('')}
      </div>
      <div style="display:flex;gap:2px;padding:2px 8px 0;">
        ${hours.map((_, h) => `<div style="flex:1;text-align:center;font-size:9px;color:#3d6484;font-family:'JetBrains Mono',monospace;">${h % 3 === 0 ? h : ''}</div>`).join('')}
      </div>`;
  } else {
    hoursHtml = `
      <div style="margin:14px 0 0;padding:12px;background:#0a1524;border:1px dashed #24405e;border-radius:8px;font-size:11px;color:#4a7a9b;">
        이 데이터셋에는 시간 단위 데이터가 없어 일 단위 정보만 표시합니다.
      </div>`;
  }

  const compHtml = comp.length ? `
    <div style="font-size:10px;color:#4a7a9b;letter-spacing:1px;font-family:'JetBrains Mono',monospace;margin:14px 0 6px;">${_tlEsc(day)} · ${_tlEsc(secName)} 구성 (상위 10)</div>
    <div style="display:flex;flex-direction:column;gap:4px;">
      ${comp.slice(0, 10).map((x, i) => {
        const w = compTotal ? Math.max(1.5, x.v / comp[0].v * 100) : 0;
        const pct = compTotal ? (x.v / compTotal * 100).toFixed(1) : '0';
        const me = x.label === row.label;
        return `<div style="display:flex;align-items:center;gap:8px;font-size:11px;">
          <span style="width:14px;text-align:right;color:#3d6484;font-family:'JetBrains Mono',monospace;">${i + 1}</span>
          <span style="width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:${me ? '#e6f2ff' : '#9fc2dd'};${me ? 'font-weight:700;' : ''}">${_tlEsc(x.label)}</span>
          <div style="flex:1;height:10px;background:#0a1524;border-radius:3px;overflow:hidden;"><div style="width:${w}%;height:100%;background:${me ? color : '#2f5f8a'};border-radius:3px;"></div></div>
          <span style="width:130px;text-align:right;color:#c8dded;font-family:'JetBrains Mono',monospace;font-size:10px;">${x.v.toLocaleString()} <span style="color:#4a7a9b;">(${pct}%)</span></span>
        </div>`;
      }).join('')}
      ${comp.length > 10 ? `<div style="font-size:10px;color:#4a7a9b;padding-left:22px;">외 ${comp.length - 10}개 행</div>` : ''}
    </div>` : '';

  ov.innerHTML = `
    <div style="width:min(680px,94vw);max-height:88vh;overflow-y:auto;background:#0f1923;border:1px solid #24405e;border-radius:12px;padding:16px 18px;box-shadow:0 18px 50px rgba(0,0,0,.6);">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:12px;">
        <span style="width:10px;height:10px;border-radius:50%;background:${color};flex-shrink:0;"></span>
        <span style="font-size:15px;font-weight:700;color:#e6f2ff;">${_tlEsc(row.label)}</span>
        <span style="font-size:10px;color:#4a7a9b;border:1px solid #24405e;border-radius:10px;padding:1px 8px;">${_tlEsc(secName)}</span>
        <span style="font-size:12px;color:#9fc2dd;font-family:'JetBrains Mono',monospace;">${_tlEsc(day)}${clickedHour >= 0 ? ` <span style="color:#f59e0b;">${String(clickedHour).padStart(2, '0')}:00</span>` : ''}</span>
        <button type="button" id="tl-drill-x" style="margin-left:auto;background:none;border:none;color:#4a7a9b;font-size:18px;cursor:pointer;line-height:1;">×</button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${kpi('해당일 세션', dayTotal.toLocaleString(), `행 전체의 ${dayPct}%`)}
        ${clickedHour >= 0 && hours ? kpi('클릭 시각', `${String(clickedHour).padStart(2, '0')}:00`, `${(hours[clickedHour] || 0).toLocaleString()}세션`) : ''}
        ${peakH >= 0 ? kpi('피크 시간대', `${String(peakH).padStart(2, '0')}:00`, `${hours[peakH].toLocaleString()}세션`) : ''}
        ${kpi('행 총 세션', rowTotal.toLocaleString(), '전체 수집 기간')}
      </div>
      ${hoursHtml}
      ${compHtml}
    </div>`;
  ov.querySelector('#tl-drill-x').addEventListener('click', _tlDrillClose);
  document.body.appendChild(ov);
  _tlDrillOv = ov;
}

// =========================================================
// 파일 테이블
// =========================================================
function renderTable() {
  const files = tableFiles();
  document.getElementById('table-count').textContent =
    `${files.length} / ${state.data.files.length} 폴더`;
  const tbody = document.getElementById('table-body');

  if (!files.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:32px; color:var(--fg-2);">조건에 맞는 폴더가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = files.map(f => {
    return `
      <tr data-folder="${encodeURIComponent(f.filename)}">
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--fg-0);">${f.filename}</td>
        <td${CFG.group ? '' : ' style="display:none"'}><span class="tag ${f.vpn ? TAG_ON : TAG_OFF}">${f.vpn ? GROUP_ON : GROUP_OFF}</span></td>
        <td>${f.app}</td>
        <td${state.serviceMeaningful === false ? ' style="display:none"' : ''}>${SERVICE_LABEL[f.service] || f.service}</td>
        <td class="num">${f.pcap_count || 1}</td>
        <td class="num">${fmtNum(f.stats.packet_count)}</td>
        <td class="num">${fmtBytes(f.stats.total_bytes)}</td>
        <td class="num">${fmtNum(sessTotal(f.stats))}</td>
      </tr>
    `;
  }).join('');

  // 행 클릭 → 모달
  tbody.querySelectorAll('tr[data-folder]').forEach(tr => {
    tr.addEventListener('click', () => {
      const folder = decodeURIComponent(tr.dataset.folder);
      const file = state.data.files.find(f => f.filename === folder);
      if (file) openModal(file);
    });
  });

  // 정렬 아이콘 갱신
  document.querySelectorAll('.data-table th.sortable').forEach(th => {
    const icon = th.querySelector('.sort-icon');
    if (th.dataset.sort === state.sortKey) {
      icon.textContent = state.sortDir === 'asc' ? '▲' : '▼';
      icon.classList.add('active');
    } else {
      icon.textContent = '';
      icon.classList.remove('active');
    }
  });
}

// =========================================================
// 서브필터
// =========================================================
function renderSubFilter() {
  const wrap  = document.getElementById('sub-filter');
  const label = document.getElementById('sub-label');
  const btns  = document.getElementById('sub-buttons');

  if (state.task !== 'Service' && state.task !== 'App') {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');

  const baseFiles = state.data.files.filter(f => state.cls === 'All' || f.class === state.cls);

  let items;
  if (state.task === 'Service') {
    label.textContent = '서비스 선택';
    items = [...new Set(baseFiles.map(f => f.service))].sort();
  } else {
    label.textContent = '앱 선택';
    items = [...new Set(baseFiles.map(f => f.app))].sort();
  }

  btns.innerHTML = items.map(item => `
    <button class="btn ${state.subSelection === item ? 'active' : ''}" data-sub="${item}">
      ${state.task === 'Service' ? (SERVICE_LABEL[item] || item) : item}
    </button>
  `).join('');

  btns.querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      state.subSelection = b.dataset.sub === state.subSelection ? null : b.dataset.sub;
      render();
    });
  });
}

// =========================================================
// 전체 렌더링
// =========================================================
function render() {
  renderSubFilter();
  renderTop();
  renderComparisonSection();
  renderCharts();
  renderTimeline();
  renderTable();
  renderMeta();
}

// =========================================================
// 모달 (폴더 상세)
// =========================================================
function openModal(file) {
  const s = file.stats;
  document.getElementById('modal-title').textContent = file.filename;

  // 태그
  const tag = CLASS_TAG[file.class] || 'unknown';
  const tagLabel = CLASS_NAME_KO[file.class] || '—';
  document.getElementById('modal-tags').innerHTML = `
    ${CFG.group ? `<span class="tag ${file.vpn ? TAG_ON : TAG_OFF}">${file.vpn ? GROUP_ON : GROUP_OFF}</span>` : ''}
    <span class="tag tag-${tag}">${tagLabel}</span>
    <span class="tag tag-nonvpn">앱: ${file.app}</span>
    <span class="tag tag-nonvpn">서비스: ${SERVICE_LABEL[file.service] || file.service}</span>
    ${file.type && file.type !== 'none' ? `<span class="tag tag-nonvpn">타입: ${file.type}</span>` : ''}
    <span class="tag tag-nonvpn">PCAP ${file.pcap_count || 1}개</span>
  `;

  // 본문
  const body = document.getElementById('modal-body');
  body.innerHTML = `
    <div class="modal-kpi-grid">
      <div class="modal-kpi"><div class="modal-kpi-label">총 패킷</div><div class="modal-kpi-value">${fmtNum(s.packet_count)}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">총 용량</div><div class="modal-kpi-value">${fmtBytes(s.total_bytes)}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">평균 패킷 크기</div><div class="modal-kpi-value">${fmtNum(s.avg_packet_size)} B</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">총 세션</div><div class="modal-kpi-value">${fmtNum(sessTotal(s))}</div></div>
    </div>

    <div class="modal-grid-2">
      <div class="modal-section">
        <h4>패킷 통계</h4>
        <div class="modal-list">
          <div class="modal-list-row"><span class="key">TCP 패킷</span><span class="val">${fmtNum(s.tcp_packets)}</span></div>
          <div class="modal-list-row"><span class="key">UDP 패킷</span><span class="val">${fmtNum(s.udp_packets)}</span></div>
          <div class="modal-list-row"><span class="key">기타 패킷</span><span class="val">${fmtNum(s.other_packets)}</span></div>
          <div class="modal-list-row"><span class="key">최소 크기</span><span class="val">${fmtNum(s.min_packet_size)} B</span></div>
          <div class="modal-list-row"><span class="key">최대 크기</span><span class="val">${fmtNum(s.max_packet_size)} B</span></div>
        </div>
      </div>

      <div class="modal-section">
        <h4>세션 통계</h4>
        <div class="modal-list">
          <div class="modal-list-row"><span class="key">TCP 세션</span><span class="val">${fmtNum(s.tcp_sessions)}</span></div>
          <div class="modal-list-row"><span class="key">UDP 세션</span><span class="val">${fmtNum(s.udp_sessions)}</span></div>
          ${s.other_sessions ? `<div class="modal-list-row"><span class="key">기타 세션 (GRE·ICMP 등)</span><span class="val">${fmtNum(s.other_sessions)}</span></div>` : ''}
          <div class="modal-list-row"><span class="key">TCP 세션당 평균 패킷</span><span class="val">${s.tcp_sessions ? Math.round(s.tcp_packets / s.tcp_sessions).toLocaleString() : '—'}</span></div>
          <div class="modal-list-row"><span class="key">UDP 세션당 평균 패킷</span><span class="val">${s.udp_sessions ? Math.round(s.udp_packets / s.udp_sessions).toLocaleString() : '—'}</span></div>
        </div>
      </div>
    </div>

    <div class="modal-grid-2">
      <div class="modal-section">
        <h4>프로토콜 분포</h4>
        <div class="modal-list">
          ${Object.entries(s.protocols).sort((a, b) => b[1] - a[1]).map(([k, v]) => `
            <div class="modal-list-row"><span class="key">${k}</span><span class="val">${fmtNum(v)} 패킷</span></div>
          `).join('')}
        </div>
      </div>

      <div class="modal-section">
        <h4>상위 목적지 포트</h4>
        <div class="modal-list">
          ${(s.top_dst_ports || []).slice(0, 10).map(([p, c]) => `
            <div class="modal-list-row"><span class="key">${p}</span><span class="val">${fmtNum(c)} 패킷</span></div>
          `).join('')}
        </div>
      </div>
    </div>

    <div class="modal-grid-2">
      <div class="modal-section">
        <h4>상위 로컬 IP</h4>
        <div class="modal-list">
          ${(s.top_local_ips || []).slice(0, 6).map(([ip, c]) => `
            <div class="modal-list-row"><span class="key">${ip}</span><span class="val">${fmtNum(c)}</span></div>
          `).join('') || '<div class="modal-list-row"><span class="key">없음</span></div>'}
        </div>
      </div>

      <div class="modal-section">
        <h4>상위 리모트 IP</h4>
        <div class="modal-list">
          ${(s.top_remote_ips || []).slice(0, 6).map(([ip, c]) => `
            <div class="modal-list-row"><span class="key">${ip}</span><span class="val">${fmtNum(c)}</span></div>
          `).join('') || '<div class="modal-list-row"><span class="key">없음</span></div>'}
        </div>
      </div>
    </div>
  `;

  document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

// =========================================================
// CSV 다운로드
// =========================================================
function downloadCSV() {
  const files = tableFiles();
  if (!files.length) {
    alert('다운로드할 데이터가 없습니다.');
    return;
  }

  const _hasGroup = !!CFG.group;
  const headers = ['폴더명', ...(_hasGroup ? [CFG.group.label || 'VPN'] : []), '앱', '서비스', '그룹', '미디어타입', 'PCAP수', '패킷', '용량(Bytes)', 'TCP패킷', 'UDP패킷', 'TCP세션', 'UDP세션', '기타세션', '평균패킷크기'];
  const rows = files.map(f => [
    f.filename,
    ...(_hasGroup ? [f.vpn ? GROUP_ON : GROUP_OFF] : []),
    f.app,
    f.service,
    f.class,
    f.type || '',
    f.pcap_count || 1,
    f.stats.packet_count,
    f.stats.total_bytes,
    f.stats.tcp_packets,
    f.stats.udp_packets,
    f.stats.tcp_sessions,
    f.stats.udp_sessions,
    f.stats.other_sessions || 0,
    f.stats.avg_packet_size,
  ]);

  // CSV 문자열 생성 (콤마/따옴표 이스케이프)
  const escape = (v) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [
    headers.map(escape).join(','),
    ...rows.map(r => r.map(escape).join(',')),
  ].join('\n');

  // UTF-8 BOM 포함 (엑셀 한글 깨짐 방지)
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  a.download = `iscx_folders_${ts}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// =========================================================
// 이벤트
// =========================================================
// 데이터셋 전체 통계 CSV 내보내기 (파일명 = 정식 데이터셋명, 예: USTC-TFC 2016 통계.csv)
function exportStatsCsv() {
  const d = state.data; if (!d) return;
  const g = CFG.group || {};
  const dsName = CFG.datasetName || CFG.name || (d.meta && d.meta.dataset) || 'dataset';
  const groupCol = CFG.group ? (g.label || 'group') : '유형';
  const svcCol = CFG.serviceTaskName || '서비스';
  const appCol = CFG.appTaskName || '앱';
  const header = [appCol, groupCol, svcCol, 'TCP세션', 'UDP세션', '기타세션', '총세션', '패킷수', '용량(bytes)', '평균패킷크기', 'frame_bytes', 'TCP패킷', 'UDP패킷'];
  const rows = [header];
  (d.files || []).forEach(f => {
    const s = f.stats || {};
    const ts = s.tcp_sessions || 0, us = s.udp_sessions || 0, others = s.other_sessions || 0;
    const grp = CFG.group ? (f.vpn ? (g.on || 'on') : (g.off || 'off')) : '';
    rows.push([f.app, grp, f.service || '', ts, us, others, ts + us + others, s.packet_count || 0, s.total_bytes || 0,
               s.avg_packet_size || 0, (s.frame_bytes != null ? s.frame_bytes : ''), s.tcp_packets || 0, s.udp_packets || 0]);
  });
  // 그룹별/전체 합계 (summary)
  const sm = d.summary || {};
  const sumRow = (label, s) => s ? [label, '', '', s.tcp_sessions || 0, s.udp_sessions || 0, s.other_sessions || 0,
      sessTotal(s), s.packet_count || 0, s.total_bytes || 0,
      s.avg_packet_size || 0, (s.frame_bytes != null ? s.frame_bytes : ''), s.tcp_packets || 0, s.udp_packets || 0] : null;
  if (CFG.group && sm.vpn)     rows.push(sumRow('[' + (g.on || 'on') + ' 합계]', sm.vpn));
  if (CFG.group && sm.non_vpn) rows.push(sumRow('[' + (g.off || 'off') + ' 합계]', sm.non_vpn));
  if (sm.all) rows.push(sumRow('[전체 합계]', sm.all));

  const csv = rows.map(r => r.map(c => {
    const v = String(c == null ? '' : c);
    return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }).join(',')).join('\r\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });   // BOM: 엑셀 한글
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = dsName + ' 통계.csv';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function bindButtons() {
  const _csvBtn = document.getElementById('csv-export-btn');
  if (_csvBtn) _csvBtn.addEventListener('click', exportStatsCsv);
  // Task
  document.querySelectorAll('#task-buttons .btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#task-buttons .btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.task = b.dataset.task;
      state.subSelection = null;
      // Task가 App이 아니면 앱 검색창도 정리
      if (state.task !== 'App') {
        const appInput = document.getElementById('app-search');
        if (appInput) {
          appInput.value = '';
          document.getElementById('app-search-box').classList.remove('active');
          document.getElementById('app-search-clear').classList.add('hidden');
        }
      }
      render();
    });
  });

  // Class (트래픽 그룹)
  document.querySelectorAll('#class-buttons .btn-col-item').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#class-buttons .btn-col-item').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.cls = b.dataset.class;
      state.subSelection = null;
      render();
    });
  });

  // VPN 빠른 토글
  document.querySelectorAll('#vpn-toggle .vpn-toggle-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#vpn-toggle .vpn-toggle-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.vpnMode = b.dataset.vpnMode;
      render();
    });
  });

  // 비교 차트 스케일 토글 (선형 / 로그 / 비율%)
  document.querySelectorAll('#scale-toggle .scale-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#scale-toggle .scale-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.chartScale = b.dataset.scale;
      renderComparisonSection();   // 비교 섹션만 다시 그림 (빠름)
    });
  });

  // 프로토콜 분포 계층 토글 (L2/L3/L4/L7/전체) (#6)
  document.querySelectorAll('#proto-layer-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.protoLayer === b.dataset.layer) return;
      document.querySelectorAll('#proto-layer-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.protoLayer = b.dataset.layer;
      renderCharts();
    });
  });

  // 프로토콜 분포 단위 토글 (세션수 / 패킷수)
  document.querySelectorAll('#proto-metric-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.protoMetric === b.dataset.metric) return;
      document.querySelectorAll('#proto-metric-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.protoMetric = b.dataset.metric;
      renderCharts();
    });
  });

  // 상위 앱 단위 토글 (세션수 / 패킷수)
  document.querySelectorAll('#app-metric-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.appMetric === b.dataset.metric) return;
      document.querySelectorAll('#app-metric-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.appMetric = b.dataset.metric;
      renderCharts();
    });
  });

  // 단위 토글 공통 (세션수 / 패킷수) — 상위 로컬/리모트 IP · 목적지 포트
  const metricToggles = [
    ['#local-metric-toggle', 'localIpMetric'],
    ['#remote-metric-toggle', 'remoteIpMetric'],
    ['#port-metric-toggle', 'portMetric'],
  ];
  for (const [sel, key] of metricToggles) {
    document.querySelectorAll(`${sel} .layer-btn`).forEach(b => {
      b.addEventListener('click', () => {
        if (state[key] === b.dataset.metric) return;
        document.querySelectorAll(`${sel} .layer-btn`).forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        state[key] = b.dataset.metric;
        renderCharts();
      });
    });
  }

  // 세션 길이 분포 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#sesslen-proto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.sessLenProto === b.dataset.proto) return;
      document.querySelectorAll('#sesslen-proto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.sessLenProto = b.dataset.proto;
      renderCharts();
    });
  });

  // 세션 지속시간 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#durproto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.durProto === b.dataset.proto) return;
      document.querySelectorAll('#durproto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.durProto = b.dataset.proto;
      renderCharts();
    });
  });

  // 세션당 바이트 분포 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#sbyte-proto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.sbyteProto === b.dataset.proto) return;
      document.querySelectorAll('#sbyte-proto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.sbyteProto = b.dataset.proto;
      renderCharts();
    });
  });

  // 세션 처리율 분포 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#thru-proto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (state.thruProto === b.dataset.proto) return;
      document.querySelectorAll('#thru-proto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.thruProto = b.dataset.proto;
      renderCharts();
    });
  });

  // 네트워크 식별자 VPN 토글 (전체 / VPN / Non-VPN)
  document.querySelectorAll('#fieldstat-vpn-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#fieldstat-vpn-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.fsVpn = b.dataset.fsvpn;
      renderFieldStats();
    });
  });

  // 네트워크 식별자 필드 토글 (dns_qry / tls_sni / http_uri / http_ua)
  document.querySelectorAll('#fieldstat-field-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#fieldstat-field-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.fsField = b.dataset.fsfield;
      renderFieldStats();
    });
  });

  // 세션 암호화 비율 KPI 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#enc-proto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if ((state.encKpiProto || 'all') === b.dataset.proto) return;
      document.querySelectorAll('#enc-proto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.encKpiProto = b.dataset.proto;
      renderTop();
    });
  });

  // 총 세션 KPI 프로토콜 토글 (전체 / TCP / UDP)
  document.querySelectorAll('#sessions-proto-toggle .layer-btn').forEach(b => {
    b.addEventListener('click', () => {
      if ((state.sessionProto || 'all') === b.dataset.proto) return;
      document.querySelectorAll('#sessions-proto-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.sessionProto = b.dataset.proto;
      renderSessionsCard();
    });
  });

  // 빠른 이동 — 해당 차트/섹션으로 스크롤
  document.querySelectorAll('#quick-nav .qnav-btn').forEach(b => {
    b.addEventListener('click', () => {
      const el = document.getElementById(b.dataset.target);
      if (!el) return;
      const target = el.closest('.chart-card') || el;
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  // 차트별 값/비율(%) 토글 (각 분석마다 독립)
  document.querySelectorAll('.pct-toggle').forEach(tog => {
    const key = tog.dataset.chart;
    tog.querySelectorAll('.scale-btn').forEach(b => {
      b.addEventListener('click', () => {
        const pct = b.dataset.pct === 'percent';
        if (!!state.chartPct[key] === pct) return;
        tog.querySelectorAll('.scale-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        state.chartPct[key] = pct;
        renderCharts();
      });
    });
  });

  // 검색
  const searchInput = document.getElementById('table-search');
  searchInput.addEventListener('input', (e) => {
    state.search = e.target.value;
    renderTable();   // 검색은 테이블만 다시 그림 (성능)
  });

  // 정렬 헤더 클릭
  document.querySelectorAll('.data-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortKey = key;
        state.sortDir = ['filename', 'app', 'service', 'class'].includes(key) ? 'asc' : 'desc';
      }
      renderTable();
    });
  });

  // CSV 다운로드
  document.getElementById('csv-download').addEventListener('click', downloadCSV);

  // (차트 헤더 클릭 접기 기능 제거됨 — 헤더 내 버튼 클릭과 충돌)

  // 서비스 앱 비교 버튼 토글
  document.getElementById('app-cmp-btn').addEventListener('click', () => {
    state.appCmpOpen = !state.appCmpOpen;
    document.getElementById('app-cmp-btn').classList.toggle('active', state.appCmpOpen);
    renderAppCmpTable();
  });

  // 앱 / 서비스 모드 전환
  document.querySelectorAll('#app-cmp-mode-toggle .layer-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (state.appCmpMode === btn.dataset.mode) return;
      document.querySelectorAll('#app-cmp-mode-toggle .layer-btn').forEach(x => x.classList.remove('active'));
      btn.classList.add('active');
      state.appCmpMode = btn.dataset.mode;
      renderAppCmpTable();
    });
  });

  // 모달 닫기
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target.id === 'modal-overlay') closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

// =========================================================
// IP 인덱스 빌드 (로컬 IP 검색용)
// =========================================================
function buildIpIndex() {
  ipIndex.clear();
  for (const f of state.data.files) {
    for (const [ip, count] of (f.stats.top_local_ips || [])) {
      if (!ipIndex.has(ip)) ipIndex.set(ip, []);
      ipIndex.get(ip).push({ folder: f.filename, count });
    }
  }
}

// =========================================================
// 자동완성 - 클래스(앱) 검색
// =========================================================
let appAcHighlight = -1;

function showAppAutocomplete(query) {
  const ac = document.getElementById('app-autocomplete');
  const apps = Object.keys(state.data.by_app);
  const q = query.toLowerCase().trim();

  let matches = apps;
  if (q) {
    matches = apps.filter(app => app.toLowerCase().includes(q));
  }

  // 정렬: query로 시작하는 것 우선, 그다음 패킷 수
  matches.sort((a, b) => {
    const aStart = a.toLowerCase().startsWith(q);
    const bStart = b.toLowerCase().startsWith(q);
    if (aStart !== bStart) return bStart - aStart;
    return state.data.by_app[b].packet_count - state.data.by_app[a].packet_count;
  });

  if (!matches.length) {
    ac.innerHTML = `<div class="ac-empty">일치하는 앱이 없습니다.</div>`;
  } else {
    ac.innerHTML = matches.slice(0, 12).map((app, i) => {
      const info = state.data.by_app[app];
      const services = (info.services || []).map(s => SERVICE_LABEL[s] || s).join(', ');
      return `
        <div class="ac-item" data-app="${app}" data-idx="${i}">
          <div class="ac-item-key">
            <span class="ac-item-name">${app}</span>
            <span class="ac-item-meta">${services}</span>
          </div>
          <span class="ac-item-meta">${fmtNum(info.packet_count)} 패킷</span>
        </div>
      `;
    }).join('');
  }
  ac.classList.remove('hidden');
  appAcHighlight = -1;

  ac.querySelectorAll('.ac-item').forEach(item => {
    item.addEventListener('mousedown', (e) => {  // mousedown: blur보다 먼저
      e.preventDefault();
      selectApp(item.dataset.app);
    });
  });
}

function hideAppAutocomplete() {
  document.getElementById('app-autocomplete').classList.add('hidden');
  appAcHighlight = -1;
}

function selectApp(app) {
  // Task=App + 해당 앱으로 필터링
  state.task = 'App';
  state.subSelection = app;

  // UI 동기화
  document.querySelectorAll('#task-buttons .btn').forEach(x => {
    x.classList.toggle('active', x.dataset.task === 'App');
  });

  // 검색 입력칸 갱신 (앱 이름 그대로 두기)
  const input = document.getElementById('app-search');
  input.value = app;
  document.getElementById('app-search-box').classList.add('active');
  document.getElementById('app-search-clear').classList.remove('hidden');

  hideAppAutocomplete();
  render();
}

function clearAppSearch() {
  const input = document.getElementById('app-search');
  input.value = '';
  document.getElementById('app-search-box').classList.remove('active');
  document.getElementById('app-search-clear').classList.add('hidden');
  if (state.task === 'App' && state.subSelection) {
    state.subSelection = null;
    render();
  }
  hideAppAutocomplete();
}

// =========================================================
// 자동완성 - 로컬 IP 검색
// =========================================================
let ipAcHighlight = -1;

function showIpAutocomplete(query) {
  const ac = document.getElementById('ip-autocomplete');
  const q = query.trim();

  // ipIndex의 모든 IP, 패킷 수 합 기준 정렬
  const allIps = [...ipIndex.entries()].map(([ip, list]) => {
    const total = list.reduce((a, b) => a + b.count, 0);
    return { ip, total, folderCount: list.length };
  });

  let matches = allIps;
  if (q) {
    matches = allIps.filter(item => item.ip.includes(q));
  }
  matches.sort((a, b) => {
    const aStart = a.ip.startsWith(q);
    const bStart = b.ip.startsWith(q);
    if (aStart !== bStart) return bStart - aStart;
    return b.total - a.total;
  });

  if (!matches.length) {
    ac.innerHTML = `<div class="ac-empty">일치하는 로컬 IP가 없습니다.</div>`;
  } else {
    ac.innerHTML = matches.slice(0, 12).map((item, i) => `
      <div class="ac-item" data-ip="${item.ip}" data-idx="${i}">
        <div class="ac-item-key">
          <span class="ac-item-name ac-item-mono">${item.ip}</span>
        </div>
        <span class="ac-item-meta">${item.folderCount}개 폴더 · ${fmtNum(item.total)} 패킷</span>
      </div>
    `).join('');
  }
  ac.classList.remove('hidden');
  ipAcHighlight = -1;

  ac.querySelectorAll('.ac-item').forEach(item => {
    item.addEventListener('mousedown', (e) => {
      e.preventDefault();
      selectIp(item.dataset.ip);
    });
  });
}

function hideIpAutocomplete() {
  document.getElementById('ip-autocomplete').classList.add('hidden');
  ipAcHighlight = -1;
}

function selectIp(ip) {
  state.ipFilter = ip;
  const input = document.getElementById('ip-search');
  input.value = ip;
  document.getElementById('ip-search-box').classList.add('active');
  document.getElementById('ip-search-clear').classList.remove('hidden');
  hideIpAutocomplete();
  render();
}

function clearIpSearch() {
  const input = document.getElementById('ip-search');
  input.value = '';
  document.getElementById('ip-search-box').classList.remove('active');
  document.getElementById('ip-search-clear').classList.add('hidden');
  state.ipFilter = null;
  hideIpAutocomplete();
  render();
}

// =========================================================
// 검색바 이벤트 바인딩
// =========================================================
function bindSearchBars() {
  // === 앱 검색 ===
  const appInput = document.getElementById('app-search');
  appInput.addEventListener('focus', () => showAppAutocomplete(appInput.value));
  appInput.addEventListener('input', (e) => {
    showAppAutocomplete(e.target.value);
    document.getElementById('app-search-clear').classList.toggle('hidden', !e.target.value);
  });
  appInput.addEventListener('blur', () => setTimeout(hideAppAutocomplete, 150));
  appInput.addEventListener('keydown', (e) => {
    const ac = document.getElementById('app-autocomplete');
    const items = ac.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      appAcHighlight = Math.min(appAcHighlight + 1, items.length - 1);
      updateHighlight(items, appAcHighlight);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      appAcHighlight = Math.max(appAcHighlight - 1, -1);
      updateHighlight(items, appAcHighlight);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (appAcHighlight >= 0 && items[appAcHighlight]) {
        selectApp(items[appAcHighlight].dataset.app);
      } else if (items.length > 0) {
        selectApp(items[0].dataset.app);
      }
    } else if (e.key === 'Escape') {
      appInput.blur();
    }
  });
  document.getElementById('app-search-clear').addEventListener('click', clearAppSearch);

  // === IP 검색 ===
  const ipInput = document.getElementById('ip-search');
  ipInput.addEventListener('focus', () => showIpAutocomplete(ipInput.value));
  ipInput.addEventListener('input', (e) => {
    showIpAutocomplete(e.target.value);
    document.getElementById('ip-search-clear').classList.toggle('hidden', !e.target.value);
  });
  ipInput.addEventListener('blur', () => setTimeout(hideIpAutocomplete, 150));
  ipInput.addEventListener('keydown', (e) => {
    const ac = document.getElementById('ip-autocomplete');
    const items = ac.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      ipAcHighlight = Math.min(ipAcHighlight + 1, items.length - 1);
      updateHighlight(items, ipAcHighlight);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      ipAcHighlight = Math.max(ipAcHighlight - 1, -1);
      updateHighlight(items, ipAcHighlight);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (ipAcHighlight >= 0 && items[ipAcHighlight]) {
        selectIp(items[ipAcHighlight].dataset.ip);
      } else if (items.length > 0) {
        selectIp(items[0].dataset.ip);
      }
    } else if (e.key === 'Escape') {
      ipInput.blur();
    }
  });
  document.getElementById('ip-search-clear').addEventListener('click', clearIpSearch);
}

function updateHighlight(items, idx) {
  items.forEach((item, i) => item.classList.toggle('highlighted', i === idx));
  if (idx >= 0 && items[idx]) {
    items[idx].scrollIntoView({ block: 'nearest' });
  }
}

// =========================================================
// 헤더/빠른검색 높이를 측정해 sticky 오프셋(CSS 변수)에 반영
function syncStickyOffsets() {
  const tb = document.querySelector('.topbar');
  const fr = document.querySelector('.filter-row');
  const root = document.documentElement;
  if (tb) root.style.setProperty('--header-h', tb.offsetHeight + 'px');
  if (fr) root.style.setProperty('--filter-h', fr.offsetHeight + 'px');
}
window.addEventListener('resize', syncStickyOffsets);

// 브랜딩 — config.js(CFG) 값으로 로고/푸터/제목/수집정보 덮어쓰기 (없으면 셸 기본=iscx 유지)
// =========================================================
function applyBranding() {
  if (CFG.name) document.title = CFG.name + ' · 트래픽 분석 대시보드';
  const setText = (id, txt) => { const el = document.getElementById(id); if (el && txt != null) el.textContent = txt; };
  setText('brand-logo-title', CFG.logoTitle);
  setText('brand-logo-sub', CFG.logoSub);
  setText('brand-footer', CFG.footer);
  setText('brand-dataset-name', CFG.datasetName || CFG.logoTitle);
  const g = CFG.group || {};
  setText('brand-task-group', g.label);
  setText('brand-group-cmp-label', g.label ? g.label + ' 빠른 비교' : null);
  setText('brand-group-on', g.on);
  setText('brand-group-off', g.off);
  setText('brand-fsvpn-on', g.on);
  setText('brand-fsvpn-off', g.off);
  setText('brand-th-vpn', g.label);
  // 공격 데이터셋은 '정상 vs 공격'(off vs on) 순서로, 그 외는 'on vs off'
  if (g.on && g.off) setText('brand-cmp-vpn-title', (g.attack ? (g.off + ' vs ' + g.on) : (g.on + ' vs ' + g.off)) + ' 종합 비교');
  if (g.label) setText('brand-cmp-sub', g.label + ' · 서비스 · 앱 한눈에 비교');
  if (CFG.collectionHtml != null) {
    const c = document.getElementById('collection-body');
    if (c) c.innerHTML = CFG.collectionHtml;
  }
  const _hide = el => { if (el) el.style.display = 'none'; };
  // 그룹축(VPN/Tor/공격 등)이 없는 데이터셋 → 관련 UI 숨김
  if (!CFG.group) {
    _hide(document.getElementById('brand-task-group'));
    const vt = document.getElementById('vpn-toggle'); if (vt) _hide(vt.closest('.tb-group'));
    _hide(document.getElementById('fieldstat-vpn-toggle'));
    const cs = document.getElementById('brand-cmp-sub'); if (cs) cs.textContent = '서비스 · 앱 한눈에 비교';
    _hide(document.querySelector('.data-table th[data-sort="vpn"]'));  // 폴더 목록의 그룹(VPN) 열 헤더 숨김
  }

  // 데이터셋 축 명칭 커스텀 (예: cipher = 서비스→'암호화 방식', 앱→'도메인')
  if (CFG.serviceTaskName || CFG.appTaskName) {
    const _setTxt = (sel, txt) => { const el = document.querySelector(sel); if (el && txt) el.textContent = txt; };
    const _setTh  = (sel, txt) => { const el = document.querySelector(sel); if (el && txt) el.innerHTML = txt + ' <span class="sort-icon"></span>'; };
    if (CFG.serviceTaskName) {
      _setTxt('#task-buttons [data-task="Service"]', CFG.serviceTaskName);          // 분석영역 탭
      _setTxt('#app-cmp-mode-toggle [data-mode="service"]', CFG.serviceTaskName);   // 비교 테이블 모드
      _setTh('.data-table th[data-sort="service"]', CFG.serviceTaskName);           // 폴더목록 헤더
    }
    if (CFG.appTaskName) {
      _setTxt('#task-buttons [data-task="App"]', CFG.appTaskName);
      _setTxt('#app-cmp-mode-toggle [data-mode="app"]', CFG.appTaskName);
      _setTh('.data-table th[data-sort="app"]', CFG.appTaskName);
    }
    // '서비스 앱 비교' 버튼 + '앱 비교' 라벨
    const _cmpBtn = document.getElementById('app-cmp-btn');
    if (_cmpBtn) _cmpBtn.textContent = CFG.serviceTaskName
      ? `${CFG.serviceTaskName} ${CFG.appTaskName || '앱'} 비교`   // 서비스 있음: '암호화 방식 도메인 비교'
      : `${CFG.appTaskName || '앱'} 비교`;                          // 서비스 없음: '웹사이트 비교'
    const _cmpLbl = [...document.querySelectorAll('.tb-label')].find(e => e.textContent.trim() === '앱 비교');
    if (_cmpLbl) _cmpLbl.textContent = `${CFG.appTaskName || '앱'} 비교`;
  }
}

// 부팅
// =========================================================
async function boot() {
  try {
    applyBranding();
    // 수집·추출 패널: 데이터셋별 collection.html 주입 (없으면 카드 숨김)
    try {
      const cr = await fetch('collection.html');
      const cb = document.getElementById('collection-body');
      if (cr.ok && cb) cb.innerHTML = await cr.text();
      else { const cc = document.getElementById('chart-collection-info'); if (cc) cc.style.display = 'none'; }
    } catch (_) { const cc = document.getElementById('chart-collection-info'); if (cc) cc.style.display = 'none'; }
    const res = await fetch('data.json', { cache: 'no-store' });   // 상대경로 = 현재 /<ds>/ 기준. no-store: 재생성 반영 위해 캐시 안 씀
    state.data = await res.json();
    console.log('[OK] data.json 로드 완료', state.data.meta);
    // 데이터셋 필드 정규화 (USTC 등: malicious→vpn, category→service, malware/benign→vpn/non_vpn)
    if (CFG.adapt) {
      const a = CFG.adapt, sm = state.data.summary || (state.data.summary = {});
      (state.data.files || []).forEach(f => {
        if (a.groupField) f.vpn = !!f[a.groupField];
        if (a.serviceField) f.service = f[a.serviceField];
        if (f.class == null) f.class = 'unknown';
      });
      if (a.serviceDim && state.data[a.serviceDim]) state.data.by_service = state.data[a.serviceDim];
      if (a.summaryOn && sm[a.summaryOn]) sm.vpn = sm[a.summaryOn];
      if (a.summaryOff && sm[a.summaryOff]) sm.non_vpn = sm[a.summaryOff];
      if (!state.data.by_class) state.data.by_class = {};
    }
    // 서비스 차원이 자명(none/unknown만)하면 서비스 관련 UI 숨김
    // (CFG.group 없을 때 그룹축 UI 자동숨김과 동일 원리 — cstnet 등 서비스 분류 없는 데이터셋용)
    const _svcKeys = Object.keys(state.data.by_service || {});
    const SERVICE_MEANINGFUL = _svcKeys.some(k => !/^(none|unknown|)$/i.test((k || '').trim()));
    state.serviceMeaningful = SERVICE_MEANINGFUL;
    if (!SERVICE_MEANINGFUL) {
      const _hideEl = el => { if (el) el.style.display = 'none'; };
      _hideEl(document.querySelector('#task-buttons [data-task="Service"]'));   // '서비스' 분석영역 탭
      _hideEl(document.querySelector('[data-mode="service"]'));                 // 앱/서비스 비교 테이블의 '서비스' 모드
      _hideEl(document.querySelector('.data-table th[data-sort="service"]'));   // 폴더 목록의 서비스 열 헤더
      const _svcCanvas = document.getElementById('cmp-service');                // '서비스별 트래픽 분포' 비교 차트
      if (_svcCanvas) { const c = _svcCanvas.closest('.chart-card'); if (c) _hideEl(c); }
    }
    state.appCmpSelected = new Set(Object.keys(state.data.by_app || {}));
    state.appCmpServiceSelected = new Set(Object.keys(state.data.by_service || {}));
    buildIpIndex();
    bindButtons();
    bindSearchBars();
    renderClassCounts();
    render();
    syncStickyOffsets();
  } catch (e) {
    console.error('data.json 로드 실패', e);
    document.body.innerHTML = `<div style="padding:40px; color:#ff5e8a; font-family:monospace;">❌ data.json 로드 실패<br><br>${e.message}<br><br>data.json 파일이 있는지 확인하세요.</div>`;
  }
}

boot();