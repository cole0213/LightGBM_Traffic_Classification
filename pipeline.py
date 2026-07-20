# -*- coding: utf-8 -*-
"""
pipeline.py — 랩 수집 pcap 폴더 → 세션 CSV → data.json → 대시보드 데이터셋 등록 (원커맨드)

입력 폴더 구조 (KJM auto_match_out_div 출력):
    <src>/<호스트IP>/<앱·프로세스>/*.pcap     (src = 날짜 폴더)
    <src>/<앱·프로세스>/*.pcap                (src = 호스트 폴더도 허용)
  - pcap 1개 = 세션 1개 (KJM이 소켓-프로세스 매칭으로 앱별 분류를 이미 완료)
  - 라벨: task1='-'(그룹 없음) / task2=호스트IP / task3=앱(폴더명 그대로)
  - match_evidence*.csv는 무시. _dropped_sessions.csv(수집기가 pcap으로 저장하지 않은
    흐름 목록)는 집계해 매칭 커버리지로 노출 (260706)

앱 표시명 정규화 (260706):
    data.json 생성 단계에서만 task3를 표시명으로 정규화 — 트레일링 .exe 제거,
    '_'→공백, 표기 변형 병합(League_of_Legends ≡ 'League of Legends.exe' 등).
    CSV의 task3는 원본(폴더명/모델 예측) 그대로 유지 → ML 학습 호환.
    실제 적용된 매핑은 _app_display.json에 기록.

산출물 (static/datasets/<key>/):
    session_stat_<key>.csv  — 기존 33컬럼 스키마 + frame_bytes (UTF-8 BOM)
    _app_display.json       — 표시명 정규화 매핑 (원본→표시명, 변경분만)
    data.json               — 공통 대시보드 엔진 스키마 (cic 생성기 템플릿 이식)
    config.js               — 엔진 설정 (그룹 없음, 서비스축=호스트)
    collection.html         — 수집·추출 안내 (자동 생성)
    info.json               — 랜딩 카드용 메타 (app.py가 스캔)
    _job.json               — 진행률/상태 (app.py가 폴링)

실행:
    python pipeline.py --src "Z:\\data\\99_KJM\\auto_match_out_div\\2026.06.29" --key lab0629 --name "연구실 수집 2026-06-29"
    옵션: --workers N(기본 12) --limit N(스모크 테스트용 pcap 상한) --tz-offset 9(타임라인 시간대, 기본 KST)

자동 라벨링 모드 (--auto-label):
    폴더 구조의 라벨을 쓰지 않고, 학습된 ML 모델(autolabel.py, models/autolabel_model.pkl)이
    세션 통계만으로 앱(task3)을 추론한다. 폴더 라벨이 존재하면 task3_folder 컬럼에 보존해 대조 가능.
    신뢰도 임계(--conf-threshold, 기본 0.3) 미달 세션은 '미분류(자동)' 처리.
    앱 폴더 구조가 없는(pcap이 흩어진) 폴더도 입력 가능.
"""
import argparse
import collections
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR / "static" / "datasets"

TSHARK_CANDIDATES = [
    r"C:\Program Files\Wireshark\tshark.exe",
    r"C:\Program Files (x86)\Wireshark\tshark.exe",
    "tshark",
]

IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# ── tshark 추출 필드 (00_codes/03_session_stat.py와 동일 + frame.len) ──
FIELDS = [
    "frame.number",                              # 0
    "frame.protocols",                           # 1
    "tcp.stream",                                # 2
    "udp.stream",                                # 3
    "ip.src",                                    # 4
    "ipv6.src",                                  # 5
    "ip.dst",                                    # 6
    "ipv6.dst",                                  # 7
    "tcp.srcport",                               # 8
    "udp.srcport",                               # 9
    "tcp.dstport",                               # 10
    "udp.dstport",                               # 11
    "tcp.len",                                   # 12
    "udp.length",                                # 13
    "tcp.flags.syn",                             # 14
    "tcp.flags.ack",                             # 15
    "tcp.flags.fin",                             # 16
    "tls.handshake.type",                        # 17
    "tls.handshake.extensions_server_name",      # 18
    "http.request.uri",                          # 19
    "dns.qry.name",                              # 20
    "http.user_agent",                           # 21
    "_ws.col.info",                              # 22
    "frame.time_epoch",                          # 23
    "frame.len",                                 # 24 (신규: 프레임 실측 크기)
]

OUT_COLUMNS = [
    "filename", "session_id", "task1", "task2", "task3", "noise_label",
    "L2", "L3", "L4", "L7", "src_ip", "src_port", "dst_ip", "dst_port",
    "pkt_count", "payload_size",
    "fwd_pkt", "fwd_byte", "bwd_pkt", "bwd_byte",
    "ts_first", "ts_last", "ws_col_info",
    "has_SYN", "has_SYN_ACK", "has_FIN_cli", "has_FIN_serv",
    "has_TLS_CHLO", "has_TLS_SHLO", "tls_sni", "http_uri", "dns_qry", "http_ua",
    "frame_bytes",   # 확장 컬럼 (기존 33 + 1)
]

# frame.protocols 토큰 분류 (03_session_stat.py와 동일)
_L2 = {"eth", "ethernet", "sll", "sll2", "linux_sll", "raw", "null",
       "loop", "ppp", "nflog", "ipnet", "ieee802", "wlan"}
_L3 = {"ip", "ipv6", "arp", "rarp"}
_L4 = {"tcp", "udp", "icmp", "icmpv6", "igmp", "sctp", "gre"}
_SKIP = {"ethertype", "data", "frame", "vlan", "llc", "fc",
         "_ws.malformed", "tcp.segments", "tls.segments"}
_SMB_WRAP = {"nbss"}
_SMB_INNER = {"smb", "smb2"}

WARN_SUBSTRS = (
    "tcp dup ack", "previous segment not captured",
    "packet size limited during capture", "malformed", "truncated",
    "retransmission", "zerowindow", "zero window",
    "out-of-order", "out of order", "acked unseen segment",
    "spurious", "reassembly error",
)
INFO_CAP = 1000

# 패킷(프레임) 크기 bin — 기존 대시보드 packet_size_bins와 동일 경계
PSIZE_LABELS = ["0-19", "20-39", "40-79", "80-159", "160-319", "320-639",
                "640-1279", "1280-2559", "2560-5119", "5120+"]
PSIZE_EDGES = [20, 40, 80, 160, 320, 640, 1280, 2560, 5120]

def psize_bin(n):
    for i, e in enumerate(PSIZE_EDGES):
        if n < e:
            return i
    return len(PSIZE_EDGES)

# 정밀 크기 히스토그램(엔진 size_fine_hist 규격: step=8, max=2560, counts 321칸(오버플로 포함))
FINE_STEP, FINE_MAX = 8, 2560
FINE_NBINS = FINE_MAX // FINE_STEP + 1

def median_from_counter(c):
    """{크기: 개수}에서 정확 중앙값 (짝수면 두 중앙값 평균 반올림)"""
    total = sum(c.values())
    if not total:
        return 0
    lo_i = (total - 1) // 2
    hi_i = total // 2
    lo = hi = None
    cum = 0
    for size in sorted(c):
        cum += c[size]
        if lo is None and cum > lo_i:
            lo = size
        if cum > hi_i:
            hi = size
            break
    return round((lo + hi) / 2)

def fine_hist_from_counter(c):
    counts = [0] * FINE_NBINS
    for size, n in c.items():
        counts[min(size // FINE_STEP, FINE_NBINS - 1)] += n
    return {"step": FINE_STEP, "max": FINE_MAX, "counts": counts}

# ── data.json 생성용 (extract_cic2017_sessionstat.py와 동일 규약) ──
PROTO_MAP = {
    "http": "HTTP", "tls": "TLS/HTTPS", "dtls": "TLS/HTTPS", "gquic": "QUIC", "quic": "QUIC",
    "dns": "DNS", "mdns": "MDNS", "llmnr": "LLMNR", "nbns": "NBNS",
    "ssh": "SSH", "ftp": "FTP", "ftp-data": "FTP", "kerberos": "KERBEROS",
    "ldap": "LDAP", "cldap": "LDAP", "nbss": "NBSS", "nbdgm": "NBDGM",
    "smb": "SMB", "smb2": "SMB", "dcerpc": "DCERPC", "rpc": "RPC",
    "ntp": "NTP", "stun": "STUN", "ssdp": "SSDP", "bjnp": "BJNP",
    "dhcpv6": "DHCPv6", "dhcp": "DHCP", "elasticsearch": "Elasticsearch",
}
ENC_PROTOS = {"TLS/HTTPS", "QUIC"}
UNKNOWN_PROTOS = {"기타 TCP", "기타 UDP", "ICMP"}

DUR_LABELS = ["<0.1s", "0.1-1s", "1-10s", "10-60s", "60s+"]
def dur_bin(d):
    if d < 0.1: return 0
    if d < 1: return 1
    if d < 10: return 2
    if d < 60: return 3
    return 4

TPUT_LABELS = ["<1KB/s", "1–10KB/s", "10–100KB/s", "100KB–1MB/s", "1MB/s+"]
def tput_bin(bps):
    if bps < 1000: return 0
    if bps < 10000: return 1
    if bps < 100000: return 2
    if bps < 1000000: return 3
    return 4

SLEN_LABELS = ["1", "2", "3-5", "6-10", "11-50", "51-100", "101-500", "500+"]
def slen_bin(n):
    if n <= 1: return 0
    if n == 2: return 1
    if n <= 5: return 2
    if n <= 10: return 3
    if n <= 50: return 4
    if n <= 100: return 5
    if n <= 500: return 6
    return 7

SBYTES_LABELS = ["0", "<100", "100-500", "500-1.5K", "1.5K-10K", "10K-100K", "100K-1M", ">1M"]
def sbytes_bin(b):
    if b <= 0: return 0
    if b < 100: return 1
    if b < 500: return 2
    if b < 1500: return 3
    if b < 10000: return 4
    if b < 100000: return 5
    if b < 1000000: return 6
    return 7

def is_local_v4(ip):
    if ip.startswith("192.168.") or ip.startswith("10."):
        return True
    if ip.startswith("163.152."):     # 랩 공인대역도 '내부' 취급
        return True
    if ip.startswith("172."):
        try:
            o2 = int(ip.split(".")[1])
            return 16 <= o2 <= 31
        except Exception:
            return False
    return False

def is_local(ip):
    if not ip:
        return False
    if ":" in ip:
        low = ip.lower()
        return low.startswith("fe80") or low.startswith("fc") or low.startswith("fd") or low == "::1"
    return is_local_v4(ip)

def dst_cast(ip):
    if not ip:
        return "unicast"
    if ":" in ip:
        return "multicast" if ip.lower().startswith("ff") else "unicast"
    if ip == "255.255.255.255":
        return "broadcast"
    parts = ip.split(".")
    try:
        o1 = int(parts[0]); o4 = int(parts[3])
    except Exception:
        return "unicast"
    if 224 <= o1 <= 239:
        return "multicast"
    if o4 == 255:
        return "broadcast"
    return "unicast"


def classify_layers(protocols):
    toks = [t for t in protocols.split(":") if t]
    l2 = l3 = l4 = "-"
    for t in toks:
        if l2 == "-" and t in _L2:
            l2 = t
        if l3 == "-" and t in _L3:
            l3 = t
        if l4 == "-" and t in _L4:
            l4 = t
    l7 = "-"
    for t in toks:
        if t in _L2 or t in _L3 or t in _L4 or t in _SKIP:
            continue
        if t in _SMB_WRAP:
            inner = next((x for x in toks if x in _SMB_INNER), None)
            l7 = inner if inner else t
        else:
            l7 = t
        break
    return l2, l3, l4, l7


def _flag_set(v):
    for t in v.split(","):
        if t.strip().lower() in ("1", "true"):
            return True
    return False


class SessionAcc:
    """00_codes/03_session_stat.py의 SessionAcc 이식 + frame.len(크기 bin/합계) 추가."""
    __slots__ = (
        "pkt_count", "payload_size", "proto_best", "info_set",
        "client", "server", "first_src", "first_dst", "sid",
        "a_pkt", "a_byte", "b_pkt", "b_byte", "fin_a", "fin_b",
        "ts_first", "ts_last",
        "has_SYN", "has_SYN_ACK",
        "has_CHLO", "has_SHLO", "sni", "uri", "qry", "ua",
        "frame_bytes", "fmin", "fmax", "size_bins", "sizes",
    )

    def __init__(self):
        self.pkt_count = 0
        self.payload_size = 0
        self.proto_best = ""
        self.info_set = []
        self.client = None
        self.server = None
        self.first_src = None
        self.first_dst = None
        self.sid = None
        self.a_pkt = self.a_byte = 0
        self.b_pkt = self.b_byte = 0
        self.fin_a = self.fin_b = 0
        self.ts_first = None
        self.ts_last = None
        self.has_SYN = self.has_SYN_ACK = 0
        self.has_CHLO = self.has_SHLO = 0
        self.sni = self.uri = self.qry = self.ua = ""
        self.frame_bytes = 0
        self.fmin = None
        self.fmax = 0
        self.size_bins = [0] * len(PSIZE_LABELS)
        self.sizes = {}          # {frame.len: count} — median·정밀 히스토그램용

    def add(self, f):
        self.pkt_count += 1
        proto = f[1]
        if proto.count(":") > self.proto_best.count(":"):
            self.proto_best = proto
        if self.sid is None:
            if f[2]:
                self.sid = f"tcp_{f[2].split(',')[0]}"
            elif f[3]:
                self.sid = f"udp_{f[3].split(',')[0]}"
        src = f[4] or f[5]
        dst = f[6] or f[7]
        sport = f[8] or f[9]
        dport = f[10] or f[11]
        ep_s = (src, sport)
        ep_d = (dst, dport)
        if self.first_src is None:
            self.first_src, self.first_dst = ep_s, ep_d
        plen = 0
        if f[12]:
            try:
                plen = int(f[12].split(",")[0])
            except ValueError:
                plen = 0
        elif f[13]:
            try:
                plen = max(0, int(f[13].split(",")[0]) - 8)
            except ValueError:
                plen = 0
        self.payload_size += plen
        if ep_s == self.first_src:
            self.a_pkt += 1; self.a_byte += plen
        else:
            self.b_pkt += 1; self.b_byte += plen
        if f[23]:
            try:
                te = float(f[23].split(",")[0])
                if self.ts_first is None or te < self.ts_first:
                    self.ts_first = te
                if self.ts_last is None or te > self.ts_last:
                    self.ts_last = te
            except ValueError:
                pass
        syn = _flag_set(f[14]); ack = _flag_set(f[15]); fin = _flag_set(f[16])
        if syn and not ack:
            self.has_SYN = 1
            if self.client is None:
                self.client, self.server = ep_s, ep_d
        if syn and ack:
            self.has_SYN_ACK = 1
            if self.server is None:
                self.server, self.client = ep_s, ep_d
        if fin:
            if ep_s == self.first_src:
                self.fin_a = 1
            else:
                self.fin_b = 1
        tt = f[17].split(",")
        if "1" in tt:
            self.has_CHLO = 1
        if "2" in tt:
            self.has_SHLO = 1
        if not self.sni and f[18]:
            self.sni = f[18].split(",")[0]
        if not self.uri and f[19]:
            self.uri = f[19].split(",")[0]
        if not self.qry and f[20]:
            self.qry = f[20].split(",")[0]
        if not self.ua and f[21]:
            self.ua = f[21].split(",")[0]
        info = f[22].strip()
        if info:
            low = info.lower()
            if any(kw in low for kw in WARN_SUBSTRS) and info not in self.info_set:
                if sum(len(x) for x in self.info_set) < INFO_CAP:
                    self.info_set.append(info)
        # frame.len (프레임 실측)
        if len(f) > 24 and f[24]:
            try:
                fl = int(f[24].split(",")[0])
                self.frame_bytes += fl
                if self.fmin is None or fl < self.fmin:
                    self.fmin = fl
                if fl > self.fmax:
                    self.fmax = fl
                self.size_bins[psize_bin(fl)] += 1
                self.sizes[fl] = self.sizes.get(fl, 0) + 1
            except ValueError:
                pass

    def finalize(self):
        client = self.client or self.first_src or ("", "")
        server = self.server or self.first_dst or ("", "")
        if self.first_src is not None and client == self.first_src:
            fwd_pkt, fwd_byte = self.a_pkt, self.a_byte
            bwd_pkt, bwd_byte = self.b_pkt, self.b_byte
            fin_cli, fin_serv = self.fin_a, self.fin_b
        else:
            fwd_pkt, fwd_byte = self.b_pkt, self.b_byte
            bwd_pkt, bwd_byte = self.a_pkt, self.a_byte
            fin_cli, fin_serv = self.fin_b, self.fin_a
        l2, l3, l4, l7 = classify_layers(self.proto_best)
        return {
            "L2": l2, "L3": l3, "L4": l4, "L7": l7,
            "src_ip": client[0], "src_port": client[1],
            "dst_ip": server[0], "dst_port": server[1],
            "pkt_count": self.pkt_count,
            "payload_size": self.payload_size,
            "fwd_pkt": fwd_pkt, "fwd_byte": fwd_byte,
            "bwd_pkt": bwd_pkt, "bwd_byte": bwd_byte,
            "ts_first": f"{self.ts_first:.6f}" if self.ts_first is not None else "-",
            "ts_last": f"{self.ts_last:.6f}" if self.ts_last is not None else "-",
            "ws_col_info": " || ".join(self.info_set) if self.info_set else "-",
            "has_SYN": self.has_SYN, "has_SYN_ACK": self.has_SYN_ACK,
            "has_FIN_cli": fin_cli, "has_FIN_serv": fin_serv,
            "has_TLS_CHLO": self.has_CHLO, "has_TLS_SHLO": self.has_SHLO,
            "tls_sni": self.sni, "http_uri": self.uri,
            "dns_qry": self.qry, "http_ua": self.ua,
            "frame_bytes": self.frame_bytes,
            "_fmin": self.fmin if self.fmin is not None else 0,
            "_fmax": self.fmax,
            "_size_bins": self.size_bins,
            "_sizes": self.sizes,
        }


def process_pcap(args):
    """pcap 1개(=세션 1개) → row dict 또는 ('ERR', reason). nfstream 기반 초고속 추출."""
    pcap_path, host, app = args
    try:
        from nfstream import NFStreamer
        # n_meters=1: pcap 1개(세션 1개)만 읽으므로 nfstream 내부 멀티프로세스 억제.
        # (미지정 시 스트리머마다 코어 수만큼 meter 프로세스를 fork → 외부 워커와 곱해져 프로세스 폭증/부하 급등)
        streamer = NFStreamer(source=pcap_path, statistical_analysis=True, n_meters=1)
        flow = None
        for f in streamer:
            flow = f
            break
        if flow is None:
            return ("ERR", f"0packets\t{pcap_path}")
            
        has_syn = 1 if (flow.src2dst_syn_packets > 0 or flow.dst2src_syn_packets > 0) else 0
        has_syn_ack = 1 if (flow.dst2src_syn_packets > 0 and flow.dst2src_ack_packets > 0) else 0
        
        # L2, L3, L4 매핑
        l2 = "eth"
        l3 = "ipv6" if flow.ip_version == 6 else "ipv4"
        l4 = "tcp" if flow.protocol == 6 else ("udp" if flow.protocol == 17 else str(flow.protocol))
        l7 = flow.application_name or "-"
        
        # ts_first, ts_last
        ts_first = flow.bidirectional_first_seen_ms / 1000.0
        ts_last = flow.bidirectional_last_seen_ms / 1000.0
        
        # frame.len bins 및 sizes 모사
        size_bins = [0] * len(PSIZE_LABELS)
        sizes = {}
        # nfstream은 개별 패킷 크기 히스토그램을 주지 않으므로 평균 크기로 모사
        avg_ps = int(flow.bidirectional_mean_ps) if flow.bidirectional_mean_ps else 0
        if avg_ps > 0:
            size_bins[psize_bin(avg_ps)] = flow.bidirectional_packets
            sizes[avg_ps] = flow.bidirectional_packets
            
        row = {
            "L2": l2, "L3": l3, "L4": l4, "L7": l7,
            "src_ip": flow.src_ip, "src_port": flow.src_port,
            "dst_ip": flow.dst_ip, "dst_port": flow.dst_port,
            "pkt_count": flow.bidirectional_packets,
            "payload_size": flow.bidirectional_bytes,
            "fwd_pkt": flow.src2dst_packets, "fwd_byte": flow.src2dst_bytes,
            "bwd_pkt": flow.dst2src_packets, "bwd_byte": flow.dst2src_bytes,
            "ts_first": f"{ts_first:.6f}",
            "ts_last": f"{ts_last:.6f}",
            "ws_col_info": "-",
            "has_SYN": has_syn, "has_SYN_ACK": has_syn_ack,
            "has_FIN_cli": 1 if flow.src2dst_fin_packets > 0 else 0,
            "has_FIN_serv": 1 if flow.dst2src_fin_packets > 0 else 0,
            "has_TLS_CHLO": 1 if (flow.src2dst_syn_packets > 0 and flow.requested_server_name) else 0,
            "has_TLS_SHLO": 0,
            "tls_sni": flow.requested_server_name or "",
            "http_uri": "",
            "dns_qry": flow.requested_server_name if flow.application_name == "DNS" else "",
            "http_ua": flow.user_agent or "",
            "frame_bytes": flow.bidirectional_bytes,
            "_fmin": flow.bidirectional_min_ps or 0,
            "_fmax": flow.bidirectional_max_ps or 0,
            "_size_bins": size_bins,
            "_sizes": sizes,
        }
        row["filename"] = os.path.basename(pcap_path)
        row["session_id"] = "-"
        row["task1"] = "-"
        row["task2"] = host
        row["task3"] = app
        row["noise_label"] = ""
        return ("OK", row)
    except Exception as e:
        return ("ERR", f"nfstream:{e}\t{pcap_path}")


# ── 앱 표시명 정규화 (data.json 단계 전용 — CSV의 task3는 원본 유지) ──
# canonical key(소문자·영숫자·한글만) → 표시명. 규칙 결과가 어색한 것만 명시.
APP_DISPLAY_OVERRIDES = {
    "chrome": "Chrome",
    "msedge": "Microsoft Edge",
    "microsoftedge": "Microsoft Edge",
    "msedgewebview2": "Edge WebView2",
    "riotclient": "Riot Client",
    "leagueoflegends": "League of Legends",
}


def canon_key(label: str) -> str:
    """표기 변형 병합용 정규화 키: 소문자화, 트레일링 .exe 제거, 영숫자·한글만."""
    s = label.strip().lower()
    if s.endswith(".exe"):
        s = s[:-4]
    return "".join(ch for ch in s if ch.isalnum())


def prettify_label(raw: str) -> str:
    """표시용 정리: 트레일링 .exe 제거, '_'→공백. 원본 대소문자는 유지."""
    s = raw.strip()
    if s.lower().endswith(".exe"):
        s = s[:-4]
    return " ".join(s.replace("_", " ").split()) or raw


def build_app_display_map(labels):
    """관측 라벨 전체 → {원본: 표시명}. canonical key가 같은 라벨은 하나로 병합.
    표시명 = 명시 매핑 우선, 없으면 최다 빈도 변형의 prettify (동률은 사전순)."""
    cnt = collections.Counter(labels)
    groups = collections.defaultdict(list)
    for lbl, n in cnt.items():
        groups[canon_key(lbl)].append((n, lbl))
    out = {}
    for ck, members in groups.items():
        disp = APP_DISPLAY_OVERRIDES.get(ck)
        if not disp:
            members.sort(key=lambda t: (-t[0], t[1]))
            disp = prettify_label(members[0][1]) or members[0][1] or "unknown"
        for _, lbl in members:
            out[lbl] = disp
    return out


# ── 매칭 커버리지 (_dropped_sessions.csv 집계) ──
def collect_dropped_stats(dropped_files):
    """수집기가 pcap으로 저장하지 않은 흐름(_dropped_sessions.csv) 집계.
    반환: {files, flows, packets, reasons(사유별 건수, 빈도순)}."""
    flows = 0
    packets = 0
    reasons = collections.Counter()
    n_files = 0
    for fp in dropped_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                rd = csv.DictReader(f)
                for row in rd:
                    flows += 1
                    try:
                        packets += int(row.get("pkt_count") or 0)
                    except ValueError:
                        pass
                    reason = re.sub(r"\(.*\)$", "", (row.get("reason") or "").strip()) or "unknown"
                    reasons[reason] += 1
            n_files += 1
        except OSError:
            continue
    return {"files": n_files, "flows": flows, "packets": packets,
            "reasons": dict(reasons.most_common())}


# ── 입력 스캔 ──
def scan_src(src: Path, auto=False):
    """(pcap_path, host, app) 목록 + 호스트 집합 + _dropped_sessions.csv 경로 목록.
    KJM 구조: <날짜>/<호스트IP>/<앱그룹>[/<프로세스.exe>...]/*.pcap
      - 호스트 = src 자신 또는 src 아래 경로에서 IP 형태인 첫 폴더
      - 앱     = 호스트 바로 아래 1단계 폴더(앱 그룹; ChatGPT/ChatGPT.exe → 'ChatGPT')
    auto=True(자동 라벨링 모드): 앱 폴더 구조가 없어도 됨 — src 바로 아래 pcap도 수용,
      폴더 앱명은 있으면 대조용으로만 기록(없으면 ""), 실제 라벨은 이후 모델 추론이 부여.
    """
    tasks = []
    hosts = set()
    dropped_files = []
    src_is_host = bool(IP_RE.match(src.name))
    for dirpath, dirnames, filenames in os.walk(src):
        if "_dropped_sessions.csv" in filenames:
            dropped_files.append(str(Path(dirpath) / "_dropped_sessions.csv"))
        pcaps = [f for f in filenames if f.lower().endswith((".pcap", ".pcapng"))]
        if not pcaps:
            continue
        d = Path(dirpath)
        if d == src and not auto:
            continue                      # src 바로 아래 pcap은 라벨 불명 → 무시 (auto는 수용)
        parts = d.relative_to(src).parts if d != src else ()
        if src_is_host:
            host = src.name
            app_parts = parts
        else:
            # 첫 IP형 폴더를 깊이 무관하게 탐색 — 날짜 폴더의 상위(루트)를 선택해도
            # '2026.06.29' 같은 날짜명이 앱 라벨로 오염되지 않게 (여러 날짜 일괄 처리 지원)
            ip_idx = next((i for i, p in enumerate(parts) if IP_RE.match(p)), None)
            if ip_idx is not None:
                host = parts[ip_idx]
                app_parts = parts[ip_idx + 1:]
            else:
                host = "-"
                app_parts = parts
        app = app_parts[0] if app_parts else ("" if auto else "unknown")
        hosts.add(host)
        for f in pcaps:
            tasks.append((str(d / f), host, app))
    return tasks, hosts, dropped_files


# ── 진행률 기록 ──
def write_job(job_path, **kw):
    kw["updated"] = time.time()
    tmp = job_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kw, f, ensure_ascii=False)
    os.replace(tmp, job_path)


# ── ML 자동 라벨링 (auto 모드 전용) ──
def infer_autolabel(rows, bundle, conf_threshold, jstate, key, out_dir):
    """추출 완료된 rows의 task3를 모델 예측으로 부여.
    폴더 유래 라벨은 task3_folder에 보존(있으면 일치율 계산), 신뢰도 미달은 미분류 처리."""
    import autolabel
    import pandas as pd
    jstate(state="running", stage="infer", done=len(rows), total=len(rows))
    t0 = time.time()
    cols = ["L4", "L7", "task2", "dst_ip", "dst_port", "src_port",
            "pkt_count", "payload_size", "fwd_pkt", "fwd_byte", "bwd_pkt", "bwd_byte",
            "ts_first", "ts_last", "frame_bytes",
            "has_SYN", "has_SYN_ACK", "has_FIN_cli", "has_FIN_serv",
            "has_TLS_CHLO", "has_TLS_SHLO", "tls_sni", "dns_qry", "http_ua", "http_uri"]
    df = pd.DataFrame({c: [r.get(c, "") for r in rows] for c in cols})
    pred = autolabel.predict_df(bundle, df)
    labels = pred["pred_label"].to_numpy()
    confs = pred["pred_conf"].to_numpy()
    n_unknown = 0
    agree = n_folder = 0
    for r, lbl, cf_ in zip(rows, labels, confs):
        folder = r["task3"]
        r["task3_folder"] = folder
        if folder and folder != "unknown":
            n_folder += 1
            if folder == str(lbl):
                agree += 1
        if float(cf_) >= conf_threshold:
            r["task3"] = str(lbl)
        else:
            r["task3"] = autolabel.UNKNOWN_LABEL
            n_unknown += 1
        r["task3_pred_conf"] = round(float(cf_), 4)
    rep = {
        "model_trained_at": bundle["meta"].get("trained_at"),
        "model_train_csvs": bundle["meta"].get("train_csvs"),
        "model_classes": len(bundle["classes"]),
        "eval_metrics": bundle["meta"].get("eval_metrics"),
        "threshold": conf_threshold,
        "sessions": len(rows),
        "unknown": n_unknown,
        "mean_conf": round(float(confs.mean()), 4) if len(confs) else 0,
        "folder_labeled": n_folder,
        "agreement_with_folder": round(agree / n_folder, 4) if n_folder else None,
        "infer_sec": round(time.time() - t0, 1),
    }
    with open(out_dir / "_autolabel.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(f"[{key}] infer: {len(rows):,} sessions, unknown={n_unknown:,}"
          f" ({n_unknown/max(1,len(rows))*100:.1f}%), folder-agree="
          f"{(agree/n_folder*100 if n_folder else 0):.1f}% ({rep['infer_sec']}s)")
    return rep


# ── data.json 생성 (cic 생성기 템플릿 이식: 그룹 없음 / 서비스축=호스트) ──
def build_datajson(rows, key, name, src, tz_offset):
    tz = datetime.timezone(datetime.timedelta(hours=tz_offset))
    APP_META = {}                      # (host, app) -> True
    aggs = collections.defaultdict(new_agg)
    tl_dates = set()
    tl_sec = {
        "서비스": collections.defaultdict(collections.Counter),
        "앱": collections.defaultdict(collections.Counter),
        "L4": collections.defaultdict(collections.Counter),
        "L7": collections.defaultdict(collections.Counter),
    }
    day_cache = {}

    for row in rows:
        host, app = row["task2"], row["task3"]
        fkey = (host, app)
        APP_META[fkey] = True
        a = aggs[fkey]
        pkt = row["pkt_count"]
        byt = row["payload_size"]
        l3, l4, l7 = row["L3"], row["L4"], row["L7"]
        src_ip, dst_ip = row["src_ip"], row["dst_ip"]

        a["pkt"] += pkt; a["bytes"] += byt
        a["frame_bytes"] += row["frame_bytes"]
        fmin = row["_fmin"]
        if fmin and (a["fmin"] is None or fmin < a["fmin"]):
            a["fmin"] = fmin
        if row["_fmax"] > a["fmax"]:
            a["fmax"] = row["_fmax"]
        for i, c in enumerate(row["_size_bins"]):
            a["psize"][i] += c
        a["sizes"].update(row["_sizes"])

        if l4 == "tcp":
            a["tcp_pkt"] += pkt; a["tcp_sess"] += 1; l4d = "TCP"
        elif l4 == "udp":
            a["udp_pkt"] += pkt; a["udp_sess"] += 1; l4d = "UDP"
        else:
            a["icmp_pkt"] += pkt; a["icmp_sess"] += 1; l4d = "ICMP"
        a["l4_pkt"][l4d] += pkt; a["l4_sess"][l4d] += 1
        l3d = "IPv6" if l3 == "ipv6" else "IPv4"
        a["l3_pkt"][l3d] += pkt; a["l3_sess"][l3d] += 1

        proto = PROTO_MAP.get(l7)
        if proto is None:
            proto = {"TCP": "기타 TCP", "UDP": "기타 UDP", "ICMP": "ICMP"}[l4d]
        a["proto_pkt"][proto] += pkt
        a["proto_sess"][proto] += 1
        if proto in ENC_PROTOS:
            ei = 0
        elif proto in UNKNOWN_PROTOS:
            ei = 2
        else:
            ei = 1
        a["enc"][ei] += 1
        if l4d == "TCP":
            a["enc_tcp"][ei] += 1
        elif l4d == "UDP":
            a["enc_udp"][ei] += 1

        s_local = is_local(src_ip); d_local = is_local(dst_ip)
        if s_local:
            a["lip_pkt"][src_ip] += pkt; a["lip_sess"][src_ip] += 1; a["local_sess"] += 1
        else:
            a["rip_pkt"][src_ip] += pkt; a["rip_sess"][src_ip] += 1; a["remote_sess"] += 1
        if d_local:
            a["lip_pkt"][dst_ip] += pkt; a["lip_sess"][dst_ip] += 1; a["local_sess"] += 1
        else:
            a["rip_pkt"][dst_ip] += pkt; a["rip_sess"][dst_ip] += 1; a["remote_sess"] += 1

        try:
            spn = int(row["src_port"])
        except (ValueError, TypeError):
            spn = -1
        try:
            dpn = int(row["dst_port"])
        except (ValueError, TypeError):
            dpn = -1
        if spn >= 0:
            a["sport_pkt"][spn] += pkt
        if dpn >= 0:
            a["dport_pkt"][dpn] += pkt; a["dport_sess"][dpn] += 1

        a[dst_cast(dst_ip)] += 1

        v = (row.get("tls_sni") or "").strip()
        if v:
            a["fs_sni"][v] += 1
        v = (row.get("http_uri") or "").strip()
        if v and v != "/":
            a["fs_uri"][v] += 1
        v = (row.get("dns_qry") or "").strip()
        if v:
            a["fs_dns"][v] += 1
        v = (row.get("http_ua") or "").strip()
        if v:
            a["fs_ua"][v] += 1

        try:
            ts = float(row["ts_first"])
            hi = int(ts // 3600)
            date = day_cache.get(hi)
            if date is None:
                date = datetime.datetime.fromtimestamp(hi * 3600, tz).strftime("%Y-%m-%d %H:00")
                day_cache[hi] = date
            tl_dates.add(date)
            tl_sec["서비스"][host][date] += 1
            tl_sec["앱"][app][date] += 1
            tl_sec["L4"][l4d][date] += 1
            tl_sec["L7"][(l7 if (l7 and l7 != "-") else "other")][date] += 1
        except (ValueError, KeyError, OSError):
            pass

        a["slen"][slen_bin(pkt)] += 1
        if l4d == "TCP":
            a["slen_tcp"][slen_bin(pkt)] += 1
        elif l4d == "UDP":
            a["slen_udp"][slen_bin(pkt)] += 1
        a["sbytes"][sbytes_bin(byt)] += 1
        try:
            dur = float(row["ts_last"]) - float(row["ts_first"])
            dbi = dur_bin(dur if dur > 0 else 0)
            a["fdur"][dbi] += 1
            if l4d == "TCP":
                a["fdur_tcp"][dbi] += 1
            elif l4d == "UDP":
                a["fdur_udp"][dbi] += 1
            if dur > 0:
                tbi = tput_bin(byt / dur)
                a["tput"][tbi] += 1
                if l4d == "TCP":
                    a["tput_tcp"][tbi] += 1
                elif l4d == "UDP":
                    a["tput_udp"][tbi] += 1
        except (ValueError, KeyError):
            pass

    def top(counter, n=10):
        return [[k, v] for k, v in counter.most_common(n)]

    files = []
    for (host, app) in sorted(APP_META.keys(), key=lambda k: (k[0], -aggs[k]["pkt"])):
        a = aggs[(host, app)]
        tcp_s = a["tcp_sess"]
        udp_s = a["udp_sess"] + a["icmp_sess"]
        total_sess = tcp_s + udp_s
        pkt = a["pkt"]
        avg = round(a["frame_bytes"] / pkt, 2) if pkt else 0
        proto = dict(a["proto_pkt"])
        stats = {
            "packet_count": pkt,
            "total_bytes": a["bytes"],
            "avg_packet_size": avg,
            "min_packet_size": a["fmin"] or 0,
            "max_packet_size": a["fmax"],
            "median_packet_size": median_from_counter(a["sizes"]),
            "size_fine_hist": fine_hist_from_counter(a["sizes"]),
            "frame_bytes": a["frame_bytes"],
            "tcp_packets": a["tcp_pkt"],
            "udp_packets": a["udp_pkt"] + a["icmp_pkt"],
            "other_packets": 0,
            "tcp_sessions": tcp_s,
            "udp_sessions": udp_s,
            "protocols": proto,
            "protocol_layers": {
                "L2": {"Ethernet": pkt},
                "L3": dict(a["l3_pkt"]),
                "L4": dict(a["l4_pkt"]),
                "L7": proto,
            },
            "sessions_by_layer": {
                "L2": {"Ethernet": total_sess},
                "L3": dict(a["l3_sess"]),
                "L4": dict(a["l4_sess"]),
                "L7": dict(a["proto_sess"]),
            },
            "sessions_by_l7": dict(a["proto_sess"]),
            "top_local_ips": top(a["lip_pkt"]),
            "top_remote_ips": top(a["rip_pkt"]),
            "top_local_ips_sessions": top(a["lip_sess"]),
            "top_remote_ips_sessions": top(a["rip_sess"]),
            "top_src_ports": top(a["sport_pkt"]),
            "top_dst_ports": top(a["dport_pkt"]),
            "top_dst_ports_sessions": top(a["dport_sess"]),
            "packet_size_histogram": {"edges": [], "counts": []},
            "packet_size_bins": {"labels": PSIZE_LABELS, "counts": a["psize"]},
            "session_length_histogram": {"labels": SLEN_LABELS, "counts": a["slen"]},
            "session_length_histogram_tcp": {"labels": SLEN_LABELS, "counts": a["slen_tcp"]},
            "session_length_histogram_udp": {"labels": SLEN_LABELS, "counts": a["slen_udp"]},
            "session_bytes_hist": {"labels": SBYTES_LABELS, "counts": a["sbytes"]},
            "flow_duration_hist": {"labels": DUR_LABELS, "counts": a["fdur"]},
            "flow_duration_hist_tcp": {"labels": DUR_LABELS, "counts": a["fdur_tcp"]},
            "flow_duration_hist_udp": {"labels": DUR_LABELS, "counts": a["fdur_udp"]},
            "throughput_hist": {"labels": TPUT_LABELS, "counts": a["tput"]},
            "throughput_hist_tcp": {"labels": TPUT_LABELS, "counts": a["tput_tcp"]},
            "throughput_hist_udp": {"labels": TPUT_LABELS, "counts": a["tput_udp"]},
            "unicast_sessions": a["unicast"],
            "multicast_sessions": a["multicast"],
            "broadcast_sessions": a["broadcast"],
            "local_sessions": a["local_sess"],
            "remote_sessions": a["remote_sess"],
            "encryption_sessions": {"labels": ["암호화", "평문", "미상"], "counts": a["enc"]},
            "encryption_sessions_tcp": {"labels": ["암호화", "평문", "미상"], "counts": a["enc_tcp"]},
            "encryption_sessions_udp": {"labels": ["암호화", "평문", "미상"], "counts": a["enc_udp"]},
        }
        files.append({
            "filename": f"{host}_{app}",
            "vpn": False, "app": app, "service": host,
            "class": "unknown", "type": "none",
            "pcap_count": total_sess,
            "stats": stats,
        })

    by_app = {}
    for fe in files:
        app = fe["app"]
        e = by_app.setdefault(app, {"packet_count": 0, "services": []})
        e["packet_count"] += fe["stats"]["packet_count"]
        if fe["service"] not in e["services"]:
            e["services"].append(fe["service"])

    def blank():
        return {"packet_count": 0, "total_bytes": 0, "tcp_packets": 0, "udp_packets": 0,
                "other_packets": 0, "tcp_sessions": 0, "udp_sessions": 0,
                "avg_packet_size": 0, "min_packet_size": 0, "max_packet_size": 0,
                "frame_bytes": 0}

    summary = {"all": blank(), "vpn": blank(), "non_vpn": blank()}
    for fe in files:
        s = fe["stats"]
        for tgt in (summary["all"], summary["non_vpn"]):
            tgt["packet_count"] += s["packet_count"]
            tgt["total_bytes"] += s["total_bytes"]
            tgt["tcp_packets"] += s["tcp_packets"]
            tgt["udp_packets"] += s["udp_packets"]
            tgt["other_packets"] += s["other_packets"]
            tgt["tcp_sessions"] += s["tcp_sessions"]
            tgt["udp_sessions"] += s["udp_sessions"]
            tgt["frame_bytes"] += s["frame_bytes"]
    for k in summary:
        pc = summary[k]["packet_count"]
        summary[k]["avg_packet_size"] = round(summary[k]["frame_bytes"] / pc, 2) if pc else 0

    total_sessions = summary["all"]["tcp_sessions"] + summary["all"]["udp_sessions"]

    def fs_top(counter, n=20):
        return [[k, c] for k, c in counter.most_common(n)]

    # field_stats: by_app은 앱 단위(호스트 합산)
    app_counters = collections.defaultdict(lambda: {
        "fs_sni": collections.Counter(), "fs_uri": collections.Counter(),
        "fs_dns": collections.Counter(), "fs_ua": collections.Counter()})
    total_counters = {"fs_sni": collections.Counter(), "fs_uri": collections.Counter(),
                      "fs_dns": collections.Counter(), "fs_ua": collections.Counter()}
    svc_counters = collections.defaultdict(lambda: {
        "fs_sni": collections.Counter(), "fs_uri": collections.Counter(),
        "fs_dns": collections.Counter(), "fs_ua": collections.Counter()})
    for (host, app), a in aggs.items():
        for k in total_counters:
            total_counters[k].update(a[k])
            app_counters[app][k].update(a[k])
            svc_counters[host][k].update(a[k])

    def fields_of(c):
        return {"tls_sni": fs_top(c["fs_sni"]), "http_uri": fs_top(c["fs_uri"]),
                "dns_qry": fs_top(c["fs_dns"]), "http_ua": fs_top(c["fs_ua"])}

    EMPTY_FIELDS = {"tls_sni": [], "http_uri": [], "dns_qry": [], "http_ua": []}
    field_stats = {
        "summary": {
            "overall": fields_of(total_counters),
            "vpn": dict(EMPTY_FIELDS),
            "non_vpn": fields_of(total_counters),
        },
        "by_app": {
            app: {"overall": fields_of(c), "vpn": dict(EMPTY_FIELDS), "non_vpn": fields_of(c)}
            for app, c in app_counters.items()
        },
        "by_service": {
            host: {"overall": fields_of(c), "vpn": dict(EMPTY_FIELDS), "non_vpn": fields_of(c)}
            for host, c in svc_counters.items()
        },
    }

    timeline = {"dates": sorted(tl_dates), "rows": []}
    for sec in ["서비스", "앱", "L4", "L7"]:
        for label, datemap in tl_sec[sec].items():
            timeline["rows"].append({"section": sec, "label": label, "data": dict(datemap)})

    meta = {
        "dataset": name,
        "source": str(src),
        "total_folders": len(files),
        "total_pcaps": total_sessions,
        "generated_at": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
        "tz_offset": tz_offset,
    }
    return {"meta": meta, "summary": summary,
            "by_app": by_app, "by_service": {}, "by_class": {}, "comparison": {},
            "field_stats": field_stats, "timeline": timeline, "files": files}


def new_agg():
    return {
        "pkt": 0, "bytes": 0,
        "tcp_pkt": 0, "udp_pkt": 0, "icmp_pkt": 0,
        "tcp_sess": 0, "udp_sess": 0, "icmp_sess": 0,
        "proto_pkt": collections.Counter(), "proto_sess": collections.Counter(),
        "l3_pkt": collections.Counter(), "l3_sess": collections.Counter(),
        "l4_pkt": collections.Counter(), "l4_sess": collections.Counter(),
        "lip_pkt": collections.Counter(), "rip_pkt": collections.Counter(),
        "lip_sess": collections.Counter(), "rip_sess": collections.Counter(),
        "sport_pkt": collections.Counter(), "dport_pkt": collections.Counter(),
        "dport_sess": collections.Counter(),
        "slen": [0]*8, "slen_tcp": [0]*8, "slen_udp": [0]*8,
        "sbytes": [0]*8,
        "fdur": [0]*5, "fdur_tcp": [0]*5, "fdur_udp": [0]*5,
        "tput": [0]*5, "tput_tcp": [0]*5, "tput_udp": [0]*5,
        "unicast": 0, "multicast": 0, "broadcast": 0,
        "local_sess": 0, "remote_sess": 0,
        "enc": [0, 0, 0], "enc_tcp": [0, 0, 0], "enc_udp": [0, 0, 0],
        "fs_sni": collections.Counter(), "fs_uri": collections.Counter(),
        "fs_dns": collections.Counter(), "fs_ua": collections.Counter(),
        "frame_bytes": 0, "fmin": None, "fmax": 0, "psize": [0]*len(PSIZE_LABELS),
        "sizes": collections.Counter(),
    }


CONFIG_TMPL = """// {name} — dataset config (lab_dashboard 자동 생성)
window.DASHBOARD_CONFIG = {{
  key: "{key}",
  name: "{name}",
  datasetName: "{name}",
  logoTitle: "{name}",
  logoSub: "연구실 수집 트래픽 대시보드",
  footer: "{name} · {label_note}",
  serviceTaskName: "호스트",
  timelineMode: "segmented",
  timelineGapDays: 0.25,
}};
"""

COVERAGE_LI_TMPL = """<li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#38bdf8;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#c8e6ff;">매칭 커버리지</b>&nbsp;&nbsp;수집기가 관측한 흐름 {total_flows:,}건 중 세션 pcap으로 저장 {sessions:,}건(<b style="color:#c8e6ff;">{cov_pct:.1f}%</b>) · 미저장 {dropped:,}건 — 사유: {reasons}<br><span style="color:var(--fg-2,#4a7a9b);font-size:11px;">근거: 원본 폴더 _dropped_sessions.csv (pcap 미저장 흐름 목록 — 대시보드에 미포함)</span></span>
                </li>
"""

AUTO_COLLECTION_TMPL = """<!-- COLLECTION (자동 생성 · ML 자동 라벨링) -->
            <div style="background:var(--bg-2,#0f1923);border:1px solid var(--border,#1a2840);border-radius:8px;padding:14px 16px;">
              <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--fg-2,#4a7a9b);margin-bottom:10px;font-family:'JetBrains Mono',monospace;">COLLECTION · AUTO-LABEL</div>
              <ul style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px;">
                <li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#ffb454;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#ffd9a0;">라벨 = ML 자동 추론</b>&nbsp;&nbsp;이 데이터셋의 앱 라벨은 수집기 매칭이 아니라 <b>LightGBM 분류기</b>가 세션 통계(플로우 수치·SNI·DNS·호스트·포트)만으로 추론한 결과입니다. 학습 {n_train:,}세션·{n_classes}클래스({trained_at}), 교차일 검증 정확도 <b style="color:#ffd9a0;">{acc}</b>.</span>
                </li>
                <li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#ffb454;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#ffd9a0;">신뢰도 처리</b>&nbsp;&nbsp;예측 신뢰도 τ&lt;{threshold} 세션은 '미분류(자동)' 처리 — 이번 데이터 {unknown:,}세션({unknown_pct:.1f}%). 원본 폴더 라벨 보유 세션과의 일치율: <b style="color:#ffd9a0;">{agree}</b> (CSV의 task3_folder 컬럼으로 대조 가능).</span>
                </li>
                <li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#38bdf8;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#c8e6ff;">원본</b>&nbsp;&nbsp;<code style="background:#1a2840;padding:1px 5px;border-radius:3px;font-size:10px;font-family:'JetBrains Mono',monospace;">{src}</code><br><span style="color:var(--fg-2,#4a7a9b);font-size:11px;">호스트 {hosts}대 · 세션 pcap {sessions:,}개 · 처리일 {generated}</span></span>
                </li>
                {coverage_li}</ul>
            </div>
            <div style="background:var(--bg-2,#0f1923);border:1px solid var(--border,#1a2840);border-radius:8px;padding:14px 16px;">
              <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--fg-2,#4a7a9b);margin-bottom:10px;font-family:'JetBrains Mono',monospace;">PIPELINE</div>
              <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">세션 pcap (라벨 없음)</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">nfstream 세션 통계 (33컬럼+frame.len)</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #6a4a2a;padding:3px 8px;border-radius:4px;color:#ffb454;">LightGBM 앱 추론 (신뢰도)</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">data.json</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#00ffa3;">대시보드</span>
              </div>
            </div>
"""

COLLECTION_TMPL = """<!-- COLLECTION (자동 생성) -->
            <div style="background:var(--bg-2,#0f1923);border:1px solid var(--border,#1a2840);border-radius:8px;padding:14px 16px;">
              <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--fg-2,#4a7a9b);margin-bottom:10px;font-family:'JetBrains Mono',monospace;">COLLECTION</div>
              <ul style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px;">
                <li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#38bdf8;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#c8e6ff;">수집 방식</b>&nbsp;&nbsp;연구실 호스트에서 소켓-프로세스 매칭 기반 자동 수집(KJM auto-match) — 세션별 pcap이 소유 프로세스(앱) 폴더로 자동 분류되어 저장됨. 라벨 = 프로세스 수준 실측(추정 아님).</span>
                </li>
                <li style="display:flex;gap:10px;align-items:flex-start;">
                  <span style="min-width:6px;height:6px;margin-top:5px;border-radius:50%;background:#38bdf8;display:inline-block;flex-shrink:0;"></span>
                  <span style="font-size:12px;color:var(--fg-1,#c0d8f0);line-height:1.55;"><b style="color:#c8e6ff;">원본</b>&nbsp;&nbsp;<code style="background:#1a2840;padding:1px 5px;border-radius:3px;font-size:10px;font-family:'JetBrains Mono',monospace;">{src}</code><br><span style="color:var(--fg-2,#4a7a9b);font-size:11px;">호스트 {hosts}대 · 세션 pcap {sessions:,}개 · 처리일 {generated}</span></span>
                </li>
                {coverage_li}</ul>
            </div>
            <div style="background:var(--bg-2,#0f1923);border:1px solid var(--border,#1a2840);border-radius:8px;padding:14px 16px;">
              <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--fg-2,#4a7a9b);margin-bottom:10px;font-family:'JetBrains Mono',monospace;">PIPELINE</div>
              <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">세션 pcap (앱 폴더 = 라벨)</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">nfstream 세션 통계 (33컬럼 CSV + frame.len 실측)</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#7fb8d8;">data.json</span>
                <span style="color:#2a4a6a;font-size:13px;">→</span>
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;background:#1a2840;border:1px solid #2a3d56;padding:3px 8px;border-radius:4px;color:#00ffa3;">대시보드</span>
              </div>
            </div>
"""


def run(src, key, name, workers, limit, tz_offset,
        auto_label=False, model_path=None, conf_threshold=0.3):
    out_dir = DATASETS_DIR / key
    out_dir.mkdir(parents=True, exist_ok=True)
    job_path = out_dir / "_job.json"

    def jstate(**kw):
        write_job(job_path, key=key, name=name, src=str(src), **kw)

    # auto 모드: 추출 50분을 헛돌리지 않도록 모델을 먼저 로드(실패 시 즉시 종료)
    bundle = None
    if auto_label:
        mp = model_path or str(BASE_DIR / "models" / "autolabel_model.pkl")
        try:
            import autolabel
            bundle = autolabel.load_bundle(mp)
        except Exception as e:
            jstate(state="error", stage="init",
                   error=f"자동 라벨링 모델 로드 실패({mp}): {e} — autolabel.py train으로 먼저 학습 필요")
            sys.exit(1)
        print(f"[{key}] autolabel model: {mp} (classes={len(bundle['classes'])}, "
               f"trained={bundle['meta'].get('trained_at')})")

    jstate(state="running", stage="scan", done=0, total=0)
    src = Path(src)
    tasks, hosts, dropped_files = scan_src(src, auto=auto_label)
    if limit:
        tasks = tasks[:limit]
    total = len(tasks)
    if not total:
        jstate(state="error", stage="scan", error="pcap을 찾지 못함 — 폴더 구조 확인 필요")
        sys.exit(1)
    dropped_stats = collect_dropped_stats(dropped_files)
    print(f"[{key}] scan: {total:,} pcaps, hosts={sorted(hosts)}, "
          f"dropped_flows={dropped_stats['flows']:,} ({dropped_stats['files']} files)")
    jstate(state="running", stage="extract", done=0, total=total)

    csv_path = out_dir / f"session_stat_{key}.csv"
    fieldnames = OUT_COLUMNS + (["task3_folder", "task3_pred_conf"] if auto_label else [])
    rows = []
    errors = []
    autolabel_rep = None
    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as cf:
        w = csv.DictWriter(cf, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # imap_unordered 모사를 위해 map 사용
            futures = [executor.submit(process_pcap, t) for t in tasks]
            for i, future in enumerate(futures, 1):
                status, payload = future.result()
                if status == "OK":
                    rows.append(payload)
                    if not auto_label:
                        w.writerow(payload)      # auto 모드는 추론 후 일괄 기록
                else:
                    errors.append(payload)
                if i % 200 == 0 or i == total:
                    rate = i / max(1e-9, time.time() - t0)
                    eta = int((total - i) / max(rate, 1e-9))
                    jstate(state="running", stage="extract", done=i, total=total,
                           errors=len(errors), eta_sec=eta)
        if auto_label and rows:
            try:
                autolabel_rep = infer_autolabel(rows, bundle, conf_threshold, jstate, key, out_dir)
            except Exception as e:
                # 추론이 죽어도 수십 분짜리 추출 결과는 보존 (라벨=폴더값 그대로)
                for r in rows:
                    r.setdefault("task3_folder", r["task3"])
                    w.writerow(r)
                jstate(state="error", stage="infer", done=total, total=total,
                       errors=len(errors), error=f"추론 실패: {e} — 추출 CSV는 보존됨")
                print(f"[{key}] INFER FAILED: {e} — 추출 CSV 보존, 라벨=폴더값")
                sys.exit(1)
            for r in rows:
                w.writerow(r)
    print(f"[{key}] extract: ok={len(rows):,} err={len(errors)} ({time.time()-t0:.0f}s)")
    if errors:
        with open(out_dir / "_errors.txt", "w", encoding="utf-8") as ef:
            ef.write("\n".join(errors))
    if not rows:
        jstate(state="error", stage="extract", error="추출된 세션이 없음", errors=len(errors))
        sys.exit(1)

    jstate(state="running", stage="generate", done=total, total=total, errors=len(errors))

    # 앱 표시명 정규화 — CSV 기록이 끝난 뒤에만 적용 (CSV task3 = 원본 유지)
    display_map = build_app_display_map(r["task3"] for r in rows)
    renamed = {k: v for k, v in display_map.items() if k != v}
    with open(out_dir / "_app_display.json", "w", encoding="utf-8") as f:
        json.dump(renamed, f, ensure_ascii=False, indent=1, sort_keys=True)
    if renamed:
        for r in rows:
            r["task3"] = display_map[r["task3"]]
        print(f"[{key}] display-map: {len(renamed)}개 라벨 정규화 "
              f"(고유 앱 {len(set(display_map))}→{len(set(display_map.values()))})")

    # 매칭 커버리지 (표시용)
    coverage = None
    if dropped_stats["files"]:
        denom = len(rows) + dropped_stats["flows"]
        coverage = len(rows) / denom if denom else None

    data = build_datajson(rows, key, name, src, tz_offset)
    data["meta"]["dropped_flows"] = dropped_stats["flows"]
    data["meta"]["dropped_packets"] = dropped_stats["packets"]
    data["meta"]["match_coverage"] = round(coverage, 4) if coverage is not None else None
    tmp = out_dir / "data.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(", ", ": "))
    os.replace(tmp, out_dir / "data.json")   # 서빙 중 부분 파일 노출 방지

    label_note = "라벨=ML 자동 추론(LightGBM)" if auto_label else "NMLab 자동 수집(소켓-프로세스 매칭)"
    with open(out_dir / "config.js", "w", encoding="utf-8") as f:
        f.write(CONFIG_TMPL.format(key=key, name=name, label_note=label_note))

    n_sessions = data["summary"]["all"]["tcp_sessions"] + data["summary"]["all"]["udp_sessions"]
    n_hosts = len([h for h in hosts if h != "-"]) or 1
    cov_li = ""
    if coverage is not None:
        top_r = " · ".join(f"{k} {v:,}건" for k, v in
                           list(dropped_stats["reasons"].items())[:3]) or "-"
        cov_li = COVERAGE_LI_TMPL.format(
            total_flows=len(rows) + dropped_stats["flows"], sessions=len(rows),
            cov_pct=coverage * 100, dropped=dropped_stats["flows"], reasons=top_r)
    with open(out_dir / "collection.html", "w", encoding="utf-8") as f:
        if auto_label:
            em = (bundle["meta"].get("eval_metrics") or {})
            rep = autolabel_rep or {}
            agree = rep.get("agreement_with_folder")
            f.write(AUTO_COLLECTION_TMPL.format(
                src=str(src), hosts=n_hosts, sessions=n_sessions,
                generated=data["meta"]["generated_at"][:10],
                n_train=bundle["meta"].get("n_sessions", 0),
                n_classes=len(bundle["classes"]),
                trained_at=(bundle["meta"].get("trained_at") or "미상")[:10],
                acc=(f"{em['acc_ml']*100:.1f}%" if em.get("acc_ml") else "미측정"),
                threshold=conf_threshold,
                unknown=rep.get("unknown", 0),
                unknown_pct=rep.get("unknown", 0) / max(1, rep.get("sessions", 1)) * 100,
                agree=(f"{agree*100:.1f}%" if agree is not None else "해당 없음"),
                coverage_li=cov_li))
        else:
            f.write(COLLECTION_TMPL.format(
                src=str(src),
                hosts=n_hosts,
                sessions=n_sessions,
                generated=data["meta"]["generated_at"][:10],
                coverage_li=cov_li))

    info = {
        "key": key, "name": name,
        "desc": ("[ML 자동라벨] " if auto_label else "")
                + f"세션 {n_sessions:,} · 앱 {len(data['by_app'])}종 · 호스트 {n_hosts}대"
                + (f" · 커버리지 {coverage*100:.1f}%" if coverage is not None else ""),
        "src": str(src), "created": data["meta"]["generated_at"],
        "sessions": n_sessions, "apps": len(data["by_app"]),
        "auto_label": bool(auto_label),
        "dropped_flows": dropped_stats["flows"],
        "dropped_packets": dropped_stats["packets"],
        "coverage": round(coverage, 4) if coverage is not None else None,
    }
    with open(out_dir / "info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)

    jstate(state="done", stage="done", done=total, total=total, errors=len(errors),
           sessions=n_sessions, apps=len(data["by_app"]))
    print(f"[{key}] DONE — sessions={n_sessions:,} apps={len(data['by_app'])} "
          f"packets={data['summary']['all']['packet_count']:,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="랩 수집 pcap 폴더 → 대시보드 데이터셋")
    ap.add_argument("--src", required=True, help="입력 폴더 (날짜 폴더 또는 호스트 폴더)")
    ap.add_argument("--key", required=True, help="데이터셋 키 (예: lab0629, [a-z0-9_])")
    ap.add_argument("--name", required=True, help="표시 이름")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="pcap 개수 상한 (스모크 테스트)")
    ap.add_argument("--tz-offset", type=int, default=9, help="타임라인 시간대 오프셋 (기본 KST=+9)")
    ap.add_argument("--auto-label", action="store_true",
                    help="폴더 라벨 대신 ML 모델(autolabel)로 앱(task3) 자동 추론")
    ap.add_argument("--model", default=None,
                    help="autolabel 모델 경로 (기본 models/autolabel_model.pkl)")
    ap.add_argument("--conf-threshold", type=float, default=0.3,
                    help="이 신뢰도 미만 예측은 '미분류(자동)' 처리 (기본 0.5)")
    args = ap.parse_args()
    if not re.match(r"^[a-z0-9_]{2,32}$", args.key):
        sys.exit("[ERROR] key는 소문자/숫자/_ 2~32자")
    run(args.src, args.key, args.name, args.workers, args.limit, args.tz_offset,
        auto_label=args.auto_label, model_path=args.model,
        conf_threshold=args.conf_threshold)
