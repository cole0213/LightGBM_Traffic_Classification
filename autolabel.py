# -*- coding: utf-8 -*-
"""
autolabel.py — 세션 통계 기반 앱 자동 라벨링 (진짜 추론: 폴더 라벨에 의존하지 않음)

원리:
  KJM 수집 데이터의 프로세스 수준 ground truth(폴더 라벨)로 LightGBM 분류기를 학습해두고,
  라벨이 없는 세션 pcap의 통계(플로우 수치 + SNI/DNS/호스트/포트 범주형)만으로 앱(task3)을 예측한다.
  - snaplen 절단 데이터에서도 SNI/DNS는 상당수 생존하지만 94%가 다중앱 공유 SNI이므로
    문자열 룩업 규칙만으로는 부족 → 플로우 통계와 결합한 ML이 필요 (profile_labels.py 분석 근거).

사용:
  # 교차일 평가 (0629 학습 → 0630 예측; 정직한 성능 측정)
  python autolabel.py eval --train-csv <lab0629.csv> --test-csv <lab0630.csv> [--quick]

  # 배포 모델 학습 (여러 날짜 합산)
  python autolabel.py train --csv <lab0629.csv> --csv <lab0630.csv> --out models/autolabel_model.pkl

  # 단독 추론 (CSV에 예측 컬럼 추가)
  python autolabel.py predict --model models/autolabel_model.pkl --csv <in.csv> --out-csv <out.csv>

pipeline.py 통합용 API:
  bundle = load_bundle(path)
  pred = predict_df(bundle, df)   # -> DataFrame[pred_label, pred_conf, pred_2nd, pred_2nd_conf]
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"

MODEL_VERSION = "1.0"
MIN_CLASS_N_DEFAULT = 5          # 학습에 포함할 클래스 최소 세션 수
UNKNOWN_LABEL = "미분류(자동)"    # 신뢰도 임계 미달 시 라벨

STR_COLS = ["tls_sni", "dns_qry", "http_ua", "http_uri"]

# 2단계 공공 도메인 흉내 (co.kr 등) — 완벽할 필요 없음, 범주 병합용
_SLD = {"co", "or", "ne", "go", "ac", "re", "pe", "com", "net", "org", "gov", "edu", "mil"}


def base_domain(d: str) -> str:
    d = d.strip().strip(".").lower()
    if not d or d.count(".") == 0:
        return d
    p = d.split(".")
    if len(p) >= 3 and p[-2] in _SLD:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def net_prefix(ip: str) -> str:
    """IPv4 → /24 프리픽스, IPv6 → 앞 2그룹."""
    if not ip:
        return ""
    if ":" in ip:
        g = ip.split(":")
        return ":".join(g[:2]).lower()
    return ".".join(ip.split(".")[:3])


NUM_COLS = [
    "pkt_count", "payload_size", "fwd_pkt", "fwd_byte", "bwd_pkt", "bwd_byte",
    "frame_bytes", "duration", "avg_frame", "avg_payload",
    "fwd_pkt_ratio", "fwd_byte_ratio", "pkt_rate", "byte_rate",
    "src_port_n", "dst_port_n", "hour_kst",
    "has_SYN", "has_SYN_ACK", "has_FIN_cli", "has_FIN_serv",
    "has_TLS_CHLO", "has_TLS_SHLO", "has_sni", "has_dns", "has_ua",
    # 문맥(버스트) 피처 — 크로미움/일렉트론 계열 구분용 (260706 v1.1)
    "ctx_gap_prev", "ctx_gap_next", "ctx_pdelta_prev", "ctx_pdelta_next",
    "ctx_burst_5s", "ctx_burst_60s", "ctx_anchor_gap",
]
CAT_COLS = [
    "L4", "L7", "host", "dst_ip_c", "dst_net", "dport_c",
    "sni_c", "sni_base", "dns_c", "dns_base", "ua_c",
    "ctx_anchor_sni",   # 같은 호스트 ±30s 내 가장 가까운 SNI/DNS 세션의 기반 도메인
]
FEATURE_COLS = NUM_COLS + CAT_COLS

CTX_ANCHOR_WINDOW = 30.0   # 앵커 탐색 창(초)
CTX_PDELTA_GAP = 30.0      # 포트 델타를 계산할 이웃 시간 창(초)


def _context_features(df: pd.DataFrame) -> pd.DataFrame:
    """같은 호스트(task2)의 시간 축 문맥 — 세션 하나만으론 동일해 보이는
    크로미움/일렉트론 계열을 '주변에 무엇이 있었나'로 구분하기 위한 피처.
    입력 df는 하루치 전체(또는 학습 시 여러 날 concat)여야 의미가 있다."""
    n = len(df)
    ts = pd.to_numeric(df["ts_first"], errors="coerce").to_numpy(dtype=float)
    sp = pd.to_numeric(df["src_port"], errors="coerce").to_numpy(dtype=float)
    host = df["task2"].astype(str).to_numpy()
    sni = df["tls_sni"].astype(str).str.strip().str.lower().to_numpy()
    dns = df["dns_qry"].astype(str).str.strip().str.lower().to_numpy()

    out = {k: np.full(n, np.nan) for k in
           ("ctx_gap_prev", "ctx_gap_next", "ctx_pdelta_prev", "ctx_pdelta_next",
            "ctx_burst_5s", "ctx_burst_60s", "ctx_anchor_gap")}
    anchor_sni = np.full(n, "", dtype=object)

    order = np.lexsort((np.where(np.isnan(ts), np.inf, ts), host))
    host_s = host[order]
    boundaries = np.flatnonzero(np.r_[True, host_s[1:] != host_s[:-1], True])
    for b in range(len(boundaries) - 1):
        seg = order[boundaries[b]:boundaries[b + 1]]
        t = ts[seg]
        valid = ~np.isnan(t)
        seg = seg[valid]
        t = t[valid]
        if len(seg) == 0:
            continue
        p = sp[seg]
        gap_prev = np.r_[np.nan, np.diff(t)]
        gap_next = np.r_[np.diff(t), np.nan]
        pd_prev = np.r_[np.nan, np.abs(np.diff(p))]
        pd_next = np.r_[np.abs(np.diff(p)), np.nan]
        pd_prev[~(gap_prev <= CTX_PDELTA_GAP)] = np.nan
        pd_next[~(gap_next <= CTX_PDELTA_GAP)] = np.nan
        out["ctx_gap_prev"][seg] = gap_prev
        out["ctx_gap_next"][seg] = gap_next
        out["ctx_pdelta_prev"][seg] = pd_prev
        out["ctx_pdelta_next"][seg] = pd_next
        out["ctx_burst_5s"][seg] = (np.searchsorted(t, t + 5, "right")
                                    - np.searchsorted(t, t - 5, "left"))
        out["ctx_burst_60s"][seg] = (np.searchsorted(t, t + 60, "right")
                                     - np.searchsorted(t, t - 60, "left"))
        # 앵커: 같은 호스트에서 SNI(우선) 또는 DNS 쿼리를 가진 가장 가까운 세션
        dom = np.where(sni[seg] != "", sni[seg], dns[seg])
        a_idx = np.flatnonzero(dom != "")
        if len(a_idx):
            a_t = t[a_idx]
            pos = np.searchsorted(a_t, t)
            left = np.clip(pos - 1, 0, len(a_idx) - 1)
            right = np.clip(pos, 0, len(a_idx) - 1)
            dl = np.abs(t - a_t[left])
            dr = np.abs(a_t[right] - t)
            pick = np.where(dr < dl, right, left)
            dist = np.minimum(dl, dr)
            ok = dist <= CTX_ANCHOR_WINDOW
            out["ctx_anchor_gap"][seg[ok]] = dist[ok]
            picked = a_idx[pick[ok]]
            anchor_sni[seg[ok]] = [base_domain(d) for d in dom[picked]]

    ctx = pd.DataFrame(out, index=df.index)
    ctx["ctx_anchor_sni"] = pd.Series(anchor_sni, index=df.index).astype(str)
    return ctx


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """CSV 로드본이든 pipeline row dict 유래든 동일 형태로 정규화."""
    df = df.copy()
    for c in STR_COLS + ["L4", "L7", "task2", "dst_ip", "src_ip"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str)
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """정규화된 세션 DF → 피처 DF (라벨/파일명 등 누출 컬럼 미사용)."""
    n = len(df)
    X = pd.DataFrame(index=df.index)

    def num(col):
        return pd.to_numeric(df[col], errors="coerce") if col in df.columns \
            else pd.Series(np.nan, index=df.index)

    pkt = num("pkt_count").fillna(0)
    pay = num("payload_size").fillna(0)
    fwd_p, fwd_b = num("fwd_pkt").fillna(0), num("fwd_byte").fillna(0)
    bwd_p, bwd_b = num("bwd_pkt").fillna(0), num("bwd_byte").fillna(0)
    frm = num("frame_bytes").fillna(0)
    ts0, ts1 = num("ts_first"), num("ts_last")
    dur = (ts1 - ts0).clip(lower=0)

    X["pkt_count"] = pkt
    X["payload_size"] = pay
    X["fwd_pkt"], X["fwd_byte"] = fwd_p, fwd_b
    X["bwd_pkt"], X["bwd_byte"] = bwd_p, bwd_b
    X["frame_bytes"] = frm
    X["duration"] = dur
    X["avg_frame"] = np.where(pkt > 0, frm / pkt.replace(0, np.nan), np.nan)
    X["avg_payload"] = np.where(pkt > 0, pay / pkt.replace(0, np.nan), np.nan)
    X["fwd_pkt_ratio"] = np.where(pkt > 0, fwd_p / pkt.replace(0, np.nan), np.nan)
    X["fwd_byte_ratio"] = np.where(pay > 0, fwd_b / pay.replace(0, np.nan), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        X["pkt_rate"] = np.where(dur > 0, pkt / dur, np.nan)
        X["byte_rate"] = np.where(dur > 0, pay / dur, np.nan)
    X["src_port_n"] = num("src_port").fillna(-1)
    X["dst_port_n"] = num("dst_port").fillna(-1)
    X["hour_kst"] = np.floor(((ts0 + 9 * 3600) % 86400) / 3600)

    for c in ("has_SYN", "has_SYN_ACK", "has_FIN_cli", "has_FIN_serv",
              "has_TLS_CHLO", "has_TLS_SHLO"):
        X[c] = num(c).fillna(0).astype("int8")

    sni = df["tls_sni"].str.strip().str.lower()
    dns = df["dns_qry"].str.strip().str.lower()
    ua = df["http_ua"].str.strip()
    X["has_sni"] = (sni != "").astype("int8")
    X["has_dns"] = (dns != "").astype("int8")
    X["has_ua"] = (ua != "").astype("int8")

    X["L4"] = df["L4"]
    X["L7"] = df["L7"]
    X["host"] = df["task2"]
    X["dst_ip_c"] = df["dst_ip"]
    X["dst_net"] = df["dst_ip"].map(net_prefix)
    X["dport_c"] = num("dst_port").fillna(-1).astype("int64").astype(str)
    X["sni_c"] = sni
    X["sni_base"] = sni.map(base_domain)
    X["dns_c"] = dns
    X["dns_base"] = dns.map(base_domain)
    X["ua_c"] = ua.str.slice(0, 48)

    ctx = _context_features(df)
    for c in ctx.columns:
        X[c] = ctx[c]

    assert len(X) == n
    return X[FEATURE_COLS]


def encode_cats_fit(X: pd.DataFrame):
    """학습: 범주형 → category dtype, 레벨 저장. (X에 존재하는 범주형만 — A/B drop 지원)"""
    levels = {}
    for c in [c for c in CAT_COLS if c in X.columns]:
        X[c] = X[c].astype("category")
        levels[c] = list(X[c].cat.categories)
    return X, levels


def encode_cats_apply(X: pd.DataFrame, levels: dict):
    """추론: 학습 레벨로 고정(미지 범주 → 결측). 번들에 저장된 범주형만 처리."""
    for c in levels:
        dt = pd.CategoricalDtype(categories=levels[c])
        s = X[c]
        # 미지 범주는 먼저 결측으로 — pandas 4에서 범주 밖 값의 Categorical 생성은 에러가 됨
        X[c] = s.where(s.isin(levels[c])).astype(dt)
    return X


def apply_denoise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "task3" not in df.columns:
        return df
    
    # Check tls_sni and dns_qry
    sni = df["tls_sni"].fillna("").astype(str).str.strip().str.lower()
    dns = df["dns_qry"].fillna("").astype(str).str.strip().str.lower()
    
    telemetry_patterns = [
        "windowsupdate.com",
        "update.microsoft.com",
        "delivery.mp.microsoft.com",
        "telemetry.microsoft.com",
        "self.events.data.microsoft.com",
        "settings-win.data.microsoft.com",
        "v10.events.data.microsoft.com",
        "watson.telemetry.microsoft.com",
        "g.doubleclick.net",
        "google-analytics.com",
        "googletagmanager.com",
        "ahnlab.com",
        "v3.co.kr",
        "alyac",
    ]
    
    mask = pd.Series(False, index=df.index)
    for p in telemetry_patterns:
        mask = mask | sni.str.contains(p, regex=False) | dns.str.contains(p, regex=False)
        
    df.loc[mask, "task3"] = "svchost.exe"
    return df


def apply_grouping(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "task3" not in df.columns:
        return df
        
    def canonicalize(l: str) -> str:
        if not isinstance(l, str) or not l.strip():
            return "unknown"
        l_lower = l.lower().strip()
        if l_lower in ["codex.exe", "codex"]:
            return "Codex"
        if l_lower in ["chrome.exe", "msedge.exe", "msedgewebview2.exe", "whale.exe", "whale", "iexplore.exe", "chrome__ũ"]:
            return "Web_Browser"
        if l_lower in ["svchost.exe", "system", "mpdefendercoreservice.exe", "mousocoreworker.exe", "backgroundtaskhost.exe", "asd_framework", "microsoft_intune", "runtimebroker.exe", "explorer.exe", "searchhost.exe"]:
            return "System_Background"
        if l_lower in ["visual_studio", "visual_studio_code", "code.exe", "devenv.exe", "pycharm64.exe", "git.exe"]:
            return "IDE_Developer"
        if l_lower in ["microsoft_office", "microsoft_365_copilot", "excel.exe", "powerpnt.exe", "winword.exe", "outlook.exe", "officeclicktorun.exe", "works.exe"]:
            return "Office_Productivity"
        return l.strip()
        
    df["task3"] = df["task3"].map(canonicalize)
    return df


def load_csv(path, denoise=False, group=False):
    df = pd.read_csv(path, low_memory=False)
    df = normalize_df(df)
    if denoise:
        df = apply_denoise(df)
    if group:
        df = apply_grouping(df)
    return df


# ─────────────────────────── 학습 ───────────────────────────

def train_model(df: pd.DataFrame, min_class_n=MIN_CLASS_N_DEFAULT,
                quick=False, holdout_frac=0.1, log=print, drop_cols=(),
                denoise=False, group=False, smooth=False, rules=False,
                **lgbm_overrides):
    """반환: bundle. drop_cols = 피처 제외 목록(A/B 실험용).
    lgbm_overrides: LGBMClassifier 파라미터 오버라이드(예: n_jobs=6로 코어 제한). 미지정 시 기본값."""
    import lightgbm as lgb

    vc = df["task3"].value_counts()
    keep = vc[vc >= min_class_n].index
    dropped = vc[vc < min_class_n]
    tr = df[df["task3"].isin(keep)].copy()
    log(f"[train] 세션 {len(df):,} → 학습대상 {len(tr):,} "
        f"(클래스 {len(keep)}개, 희소 제외 {len(dropped)}개/{int(dropped.sum())}세션)")

    if quick and len(tr) > 20000:
        tr = tr.sample(n=20000, random_state=42).copy()
        log(f"[train] --quick: 20,000 세션 서브샘플")

    # 층화 분할 요건: 모든 클래스 최소 2개 (서브샘플 후 깨질 수 있음)
    vc2 = tr["task3"].value_counts()
    if (vc2 < 2).any():
        tr = tr[tr["task3"].isin(vc2[vc2 >= 2].index)].copy()
        log(f"[train] 1개 남은 클래스 {int((vc2 < 2).sum())}개 제외 → {len(tr):,}세션")

    X = build_features(tr)
    if drop_cols:
        X = X.drop(columns=[c for c in drop_cols if c in X.columns])
    y = tr["task3"].to_numpy()
    X, levels = encode_cats_fit(X)

    # 층화 랜덤 홀드아웃(조기 종료 전용) — 모든 클래스가 학습 파트에 남도록 보장.
    # 성능 수치는 여기가 아니라 교차일(train→test) 평가에서 측정한다.
    from sklearn.model_selection import train_test_split
    idx_tr, idx_va = train_test_split(
        np.arange(len(X)), test_size=holdout_frac, random_state=42, stratify=y)
    X_tr, y_tr = X.iloc[idx_tr], y[idx_tr]
    X_va, y_va = X.iloc[idx_va], y[idx_va]

    # ⚠️ reg_lambda·min_sum_hessian_in_leaf는 발산 방지 필수 (260706 실측):
    #   기본값(0, 1e-3)이면 잘 적합된 리프에서 헤시안≈0 → 리프값 -G/(H+λ) 폭주로
    #   검증 정확도가 4반복 후 붕괴(0.27→0.81). 지표도 multi_error로 고정
    #   (multi_logloss는 외운 범주값이 다음날 다르게 행동할 때 폭발해 조기종료를 오작동시킴).
    params = dict(
        objective="multiclass",
        metric="multi_error",
        n_estimators=60 if quick else 500,
        learning_rate=0.15 if quick else 0.05,
        num_leaves=63,
        min_child_samples=50,
        colsample_bytree=0.8,
        reg_lambda=15,
        min_sum_hessian_in_leaf=10,
        cat_smooth=100,          # 고카디널리티 범주형(dst_ip/SNI) 과적합 완화
        cat_l2=50,
        max_cat_threshold=32,
        # n_jobs를 12로 제한하여 서버 과부하 및 cgroup loky 데드락을 원천 차단
        n_jobs=12,
        verbosity=-1,
        random_state=42,
    )
    params.update(lgbm_overrides)   # 호출부에서 n_jobs 등 오버라이드 가능(하위호환)
    model = lgb.LGBMClassifier(**params)
    t0 = time.time()
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_va, y_va)],
        eval_metric="multi_error",
        callbacks=[lgb.early_stopping(60, verbose=False), lgb.log_evaluation(50)],
    )
    best_it = getattr(model, "best_iteration_", None) or params["n_estimators"]
    log(f"[train] 완료 {time.time()-t0:.0f}s · best_iteration={best_it} · 클래스 {len(model.classes_)}개")

    bundle = {
        "version": MODEL_VERSION,
        "model": model,
        "cat_levels": levels,
        "num_cols": [c for c in NUM_COLS if c in X.columns],
        "cat_cols": [c for c in CAT_COLS if c in X.columns],
        "classes": list(model.classes_),
        "min_class_n": min_class_n,
        "meta": {
            "trained_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n_sessions": int(len(tr)),
            "n_classes": int(len(model.classes_)),
            "dropped_classes": {str(k): int(v) for k, v in dropped.items()},
            "best_iteration": int(best_it),
            "params": {k: v for k, v in params.items() if k != "n_jobs"},
            "denoise": denoise,
            "group": group,
            "smooth": smooth,
            "rules": rules,
        },
    }
    return bundle


def save_bundle(bundle, path):
    import joblib
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path, compress=3)
    return path


def load_bundle(path):
    import joblib
    bundle = joblib.load(path)
    # 과거 저장본이 n_jobs=-1이어도 cpu_count() 경로(V: cwd에서 loky 크래시)를 타지 않도록 고정
    try:
        bundle["model"].set_params(n_jobs=(os.cpu_count() or 4))
    except Exception:
        pass
    return bundle


# ─────────────────────────── 추론 ───────────────────────────

import collections

def apply_rules(df: pd.DataFrame, group=False) -> pd.Series:
    """1단계: 명확한 도메인 매핑 규칙 적용. 매핑된 경우 정답 라벨 리턴, 아니면 NaN."""
    sni = df["tls_sni"].fillna("").astype(str).str.strip().str.lower()
    dns = df["dns_qry"].fillna("").astype(str).str.strip().str.lower()
    
    pred = pd.Series(np.nan, index=df.index, dtype=object)
    
    # 룰 정의: (패턴 목록, 클래스명)
    rules = [
        (["notion.so", "notion.com"], "Notion"),
        (["slack.com", "slack-edge.com"], "Slack"),
        (["discord.gg", "discord.com", "discordapp.com", "discordapp.net"], "Discord"),
        (["chatgpt.com", "openai.com"], "ChatGPT"),
        (["claude.ai", "anthropic.com"], "Claude"),
        (["github.com", "githubusercontent.com"], "IDE_Developer" if group else "Visual_Studio"),
        
        # System Background
        (["windowsupdate.com", "update.microsoft.com", "delivery.mp.microsoft.com", 
          "telemetry.microsoft.com", "settings-win.data.microsoft.com", "v10.events.data.microsoft.com", 
          "watson.telemetry.microsoft.com"], "System_Background" if group else "svchost.exe"),
        (["ahnlab.com", "v3.co.kr", "alyac"], "System_Background" if group else "svchost.exe"),
        
        # Game clients
        (["riotgames.com", "leagueoflegends.com", "pvp.net"], "League_of_Legends"),
        (["nexon.com", "nexonplug.nexon.com"], "NexonPlug"),
    ]
    
    for patterns, cls in rules:
        mask = pd.Series(False, index=df.index)
        for p in patterns:
            mask = mask | sni.str.contains(p, regex=False) | dns.str.contains(p, regex=False)
        # 매핑 적용
        pred[mask & pred.isna()] = cls
        
    return pred


def smooth_predictions(df: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    """호스트(task2)별로 짧은 시간 간격(예: 30초) 내의 세션들을 묶어 다수결 투표로 저신뢰도 예측 보정."""
    pred = pred.copy()
    if "ts_first" not in df.columns or "task2" not in df.columns:
        return pred
        
    ts = pd.to_numeric(df["ts_first"], errors="coerce").to_numpy(dtype=float)
    host = df["task2"].astype(str).to_numpy()
    
    order = np.lexsort((np.where(np.isnan(ts), np.inf, ts), host))
    inv_order = np.zeros_like(order)
    inv_order[order] = np.arange(len(order))
    
    ts_sorted = ts[order]
    host_sorted = host[order]
    labels = pred["pred_label"].to_numpy()[order]
    confs = pred["pred_conf"].to_numpy()[order]
    
    smoothed_labels = labels.copy()
    smoothed_confs = confs.copy()
    
    boundaries = np.flatnonzero(np.r_[True, host_sorted[1:] != host_sorted[:-1], True])
    for b in range(len(boundaries) - 1):
        seg = np.arange(boundaries[b], boundaries[b + 1])
        t_seg = ts_sorted[seg]
        valid = ~np.isnan(t_seg)
        seg = seg[valid]
        t_seg = t_seg[valid]
        if len(seg) == 0:
            continue
            
        l_seg = labels[seg]
        c_seg = confs[seg]
        
        for idx in range(len(seg)):
            t_curr = t_seg[idx]
            left = np.searchsorted(t_seg, t_curr - 15.0, "left")
            right = np.searchsorted(t_seg, t_curr + 15.0, "right")
            
            w_labels = l_seg[left:right]
            w_confs = c_seg[left:right]
            
            weights = collections.defaultdict(float)
            for wl, wc in zip(w_labels, w_confs):
                weights[wl] += wc
                
            best_lbl = max(weights, key=weights.get)
            best_weight = weights[best_lbl]
            
            if c_seg[idx] < 0.65 and best_lbl != l_seg[idx] and len(w_labels) >= 2:
                smoothed_labels[seg[idx]] = best_lbl
                smoothed_confs[seg[idx]] = max(c_seg[idx], best_weight / len(w_labels))
                
    pred["pred_label"] = smoothed_labels[inv_order]
    pred["pred_conf"] = smoothed_confs[inv_order]
    return pred


def predict_df(bundle, df: pd.DataFrame, batch=200_000) -> pd.DataFrame:
    """세션 DF → 예측. 반환 DF: pred_label, pred_conf, pred_2nd, pred_2nd_conf (index 유지).
    문맥 피처는 전체 df 기준으로 먼저 계산(배치 경계에서 문맥이 끊기지 않게)."""
    df = normalize_df(df)
    model = bundle["model"]
    classes = np.asarray(bundle["classes"])
    X = build_features(df)
    cols = list(bundle.get("num_cols", NUM_COLS)) + list(bundle.get("cat_cols", CAT_COLS))
    X = X[cols]     # 구버전 번들(문맥 피처 없음)과도 호환
    X = encode_cats_apply(X, bundle["cat_levels"])
    
    # Scikit-learn 모델용 호환성 변환
    is_sklearn = bundle.get("meta", {}).get("is_sklearn", False)
    if is_sklearn:
        for c in bundle.get("cat_cols", CAT_COLS):
            if c in X.columns:
                X[c] = X[c].cat.codes + 1
        num_cols = list(bundle.get("num_cols", NUM_COLS))
        X[num_cols] = X[num_cols].fillna(-999).replace([np.inf, -np.inf], -999)

    outs = []
    for s in range(0, len(X), batch):
        part = X.iloc[s:s + batch]
        proba = model.predict_proba(part)
        top2 = np.argsort(-proba, axis=1)[:, :2]
        rows = np.arange(len(part))
        outs.append(pd.DataFrame({
            "pred_label": classes[top2[:, 0]],
            "pred_conf": proba[rows, top2[:, 0]],
            "pred_2nd": classes[top2[:, 1]],
            "pred_2nd_conf": proba[rows, top2[:, 1]],
        }, index=part.index))
        
    res = pd.concat(outs) if outs else pd.DataFrame(
        columns=["pred_label", "pred_conf", "pred_2nd", "pred_2nd_conf"])
        
    meta = bundle.get("meta", {})
    group = meta.get("group", False)
    
    # 1. Apply Temporal Smoothing (if enabled in bundle)
    if meta.get("smooth", False):
        res = smooth_predictions(df, res)
        
    # 2. Apply Rule-Based Mapping Override (if enabled in bundle)
    if meta.get("rules", False):
        rules_lbl = apply_rules(df, group=group)
        mask = rules_lbl.notna()
        res.loc[mask, "pred_label"] = rules_lbl[mask]
        res.loc[mask, "pred_conf"] = 1.0
        
    # 3. Post-process override for denoise
    if meta.get("denoise", False):
        sni = df["tls_sni"].fillna("").astype(str).str.strip().str.lower()
        dns = df["dns_qry"].fillna("").astype(str).str.strip().str.lower()
        telemetry_patterns = [
            "windowsupdate.com",
            "update.microsoft.com",
            "delivery.mp.microsoft.com",
            "telemetry.microsoft.com",
            "self.events.data.microsoft.com",
            "settings-win.data.microsoft.com",
            "v10.events.data.microsoft.com",
            "watson.telemetry.microsoft.com",
            "g.doubleclick.net",
            "google-analytics.com",
            "googletagmanager.com",
            "ahnlab.com",
            "v3.co.kr",
            "alyac",
        ]
        mask = pd.Series(False, index=df.index)
        for p in telemetry_patterns:
            mask = mask | sni.str.contains(p, regex=False) | dns.str.contains(p, regex=False)
            
        bg_label = "System_Background" if group else "svchost.exe"
        res.loc[mask, "pred_label"] = bg_label
        res.loc[mask, "pred_conf"] = 1.0
        
    return res


def apply_threshold(pred: pd.DataFrame, threshold: float) -> pd.Series:
    """신뢰도 임계 미달 → UNKNOWN_LABEL."""
    return pred["pred_label"].where(pred["pred_conf"] >= threshold, UNKNOWN_LABEL)


# ─────────────────────────── 베이스라인 (평가용) ───────────────────────────

def fit_lookup_baseline(train: pd.DataFrame):
    """단순 룩업 규칙: SNI→최빈앱, DNS→최빈앱, dst_ip→최빈앱, dst_port→최빈앱, 최후엔 다수결."""
    maps = {}
    for col in ("tls_sni", "dns_qry", "dst_ip", "dst_port"):
        sub = train[train[col].astype(str) != ""]
        g = sub.groupby([col, "task3"], observed=True).size().reset_index(name="n")
        g = g.sort_values("n", ascending=False).drop_duplicates(col)
        maps[col] = dict(zip(g[col].astype(str), g["task3"]))
    majority = train["task3"].value_counts().idxmax()
    return maps, majority


def predict_lookup(maps, majority, test: pd.DataFrame) -> np.ndarray:
    pred = pd.Series(np.nan, index=test.index, dtype=object)
    for col in ("tls_sni", "dns_qry", "dst_ip", "dst_port"):
        vals = test[col].astype(str)
        mapped = vals.map(maps[col])
        mask = pred.isna() & (vals != "") & mapped.notna()
        pred[mask] = mapped[mask]
    return pred.fillna(majority).astype(str).to_numpy()


# ─────────────────────────── 평가 ───────────────────────────

def evaluate(train_csv, test_csv, min_class_n=MIN_CLASS_N_DEFAULT,
             quick=False, report_out=None, save_model=None,
             denoise=False, group=False, smooth=False, rules=False):
    from sklearn.metrics import f1_score

    log_lines = []

    def log(msg=""):
        print(msg, flush=True)
        log_lines.append(str(msg))

    log(f"# 자동 라벨링 교차일 평가")
    log(f"- 학습: {train_csv}")
    log(f"- 평가: {test_csv}")
    log(f"- 전처리/Denoise: {denoise}")
    log(f"- 대분류/Grouping: {group}")
    log(f"- 시계열 보정/Smoothing: {smooth}")
    log(f"- 룰 기반 매핑/Rules: {rules}")
    log(f"- 실행: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        + ("  (--quick 모드)" if quick else ""))
    log()

    tr_df = load_csv(train_csv, denoise=denoise, group=group)
    te_df = load_csv(test_csv, denoise=denoise, group=group)
    y_true = te_df["task3"].astype(str).to_numpy()
    log(f"학습 {len(tr_df):,}세션 / 평가 {len(te_df):,}세션")

    # 상한: 평가 세션 중 학습에 존재하는 클래스 비율
    seen = set(tr_df["task3"].unique())
    seen_mask = np.isin(y_true, list(seen))
    log(f"평가 세션 중 학습에서 본 클래스: {seen_mask.mean()*100:.2f}% (예측 상한)")
    log()

    # 베이스라인 1: 다수결
    majority = tr_df["task3"].value_counts().idxmax()
    acc_maj = float((y_true == majority).mean())

    # 베이스라인 2: 룩업 규칙
    maps, mj = fit_lookup_baseline(tr_df)
    pred_lk = predict_lookup(maps, mj, te_df)
    acc_lk = float((pred_lk == y_true).mean())

    # ML 모델 — 규칙/보정 매개변수를 넘겨서 번들 생성
    bundle = train_model(tr_df, min_class_n=min_class_n, quick=quick, log=log,
                         denoise=denoise, group=group, smooth=smooth, rules=rules)
    t0 = time.time()
    # predict_df로 규칙 및 보정이 적용된 최종 예측 획득
    pred_res = predict_df(bundle, te_df)
    log(f"[predict] {len(te_df):,}세션 {time.time()-t0:.0f}s")
    y_pred = pred_res["pred_label"].to_numpy()
    conf = pred_res["pred_conf"].to_numpy()
    
    # top-3 평가는 원래의 모델 분류 확률 기반으로 도출 (metrics 참고용)
    X_all = build_features(te_df)[list(bundle["num_cols"]) + list(bundle["cat_cols"])]
    X_all = encode_cats_apply(X_all, bundle["cat_levels"])
    proba = bundle["model"].predict_proba(X_all)
    classes = np.asarray(bundle["classes"])
    top3_idx = np.argsort(-proba, axis=1)[:, :3]

    acc = float((y_pred == y_true).mean())
    # macro-F1: 학습 클래스 ∪ 실제 클래스 기준
    labels_eval = sorted(set(bundle["classes"]) | set(np.unique(y_true)))
    f1m = float(f1_score(y_true, y_pred, labels=labels_eval, average="macro", zero_division=0))
    f1w = float(f1_score(y_true, y_pred, labels=labels_eval, average="weighted", zero_division=0))
    top3_hit = np.any(classes[top3_idx] == y_true[:, None], axis=1)
    acc_top3 = float(top3_hit.mean())

    log()
    log("## 종합 결과")
    log(f"| 방법 | 정확도 |")
    log(f"|---|---|")
    log(f"| 다수결({majority}) | {acc_maj*100:.2f}% |")
    log(f"| 룩업 규칙(SNI→DNS→IP→포트) | {acc_lk*100:.2f}% |")
    log(f"| **ML(LightGBM)** | **{acc*100:.2f}%** |")
    log(f"| ML top-3 | {acc_top3*100:.2f}% |")
    log(f"- macro-F1 = {f1m:.4f} · weighted-F1 = {f1w:.4f}")
    log()

    # 문자열 피처 유무별
    has_sni = (te_df["tls_sni"].str.strip() != "").to_numpy()
    has_dns = (te_df["dns_qry"].str.strip() != "").to_numpy()
    grp = np.where(has_sni, "SNI 있음", np.where(has_dns, "DNS만", "문자열 없음"))
    log("## 문자열 피처 유무별 정확도")
    for g in ("SNI 있음", "DNS만", "문자열 없음"):
        m = grp == g
        if m.sum():
            log(f"- {g}: {(y_pred[m]==y_true[m]).mean()*100:.2f}%  (n={m.sum():,})")
    log()

    # 신뢰도-커버리지
    log("## 신뢰도 임계값별 커버리지/정확도 (미분류 처리 설계용)")
    log("| 임계 τ | 커버리지 | 커버 세션 정확도 |")
    log("|---|---|---|")
    for tau in (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95):
        m = conf >= tau
        cov = m.mean()
        a = (y_pred[m] == y_true[m]).mean() if m.sum() else float("nan")
        log(f"| {tau:.2f} | {cov*100:.1f}% | {a*100:.2f}% |")
    log()

    # 클래스별 (지원수 상위 30)
    log("## 클래스별 성능 (평가셋 지원수 상위 30)")
    log("| 클래스 | n | recall | precision |")
    log("|---|---|---|---|")
    vc = pd.Series(y_true).value_counts()
    for cls in vc.head(30).index:
        tm = y_true == cls
        pm = y_pred == cls
        rec = (y_pred[tm] == cls).mean()
        prec = (y_true[pm] == cls).mean() if pm.sum() else float("nan")
        log(f"| {cls} | {tm.sum():,} | {rec*100:.1f}% | {prec*100:.1f}% |")
    log()

    # 주요 혼동쌍
    err = y_pred != y_true
    ce = pd.DataFrame({"true": y_true[err], "pred": y_pred[err]})
    top_conf = ce.value_counts().head(15)
    log("## 주요 혼동쌍 (true → pred, 상위 15)")
    for (t, p), n in top_conf.items():
        log(f"- {t} → {p}: {n:,}")
    log()

    metrics = {
        "train_csv": str(train_csv), "test_csv": str(test_csv),
        "n_train": int(len(tr_df)), "n_test": int(len(te_df)),
        "acc_majority": acc_maj, "acc_lookup": acc_lk,
        "acc_ml": acc, "acc_ml_top3": acc_top3,
        "macro_f1": f1m, "weighted_f1": f1w,
        "seen_class_ceiling": float(seen_mask.mean()),
        "quick": quick,
    }
    if report_out:
        p = Path(report_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(log_lines), encoding="utf-8")
        p.with_suffix(".json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"[리포트] {p}")
    if save_model:
        bundle["meta"]["eval_metrics"] = metrics
        save_bundle(bundle, save_model)
        log(f"[모델 저장] {save_model}")
    return metrics


# ─────────────────────────── CLI ───────────────────────────

def main():
    ap = argparse.ArgumentParser(description="앱 자동 라벨링 학습/평가/추론")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("eval", help="교차일 평가 (train→test)")
    e.add_argument("--train-csv", required=True)
    e.add_argument("--test-csv", required=True)
    e.add_argument("--min-class-n", type=int, default=MIN_CLASS_N_DEFAULT)
    e.add_argument("--quick", action="store_true", help="빠른 검증(서브샘플+얕은 모델)")
    e.add_argument("--report-out", default=str(MODELS_DIR / "eval_report.md"))
    e.add_argument("--save-model", default=None, help="평가에 쓴 모델을 저장할 경로(선택)")
    e.add_argument("--denoise", action="store_true", help="학습/평가 전 노이즈 필터링 적용")
    e.add_argument("--group", action="store_true", help="학습/평가 전 클래스 대분류 그룹화 적용")
    e.add_argument("--smooth", action="store_true", help="시계열 보정(Temporal Smoothing) 적용")
    e.add_argument("--rules", action="store_true", help="룰 기반 도메인 매핑 적용")

    t = sub.add_parser("train", help="배포 모델 학습")
    t.add_argument("--csv", action="append", required=True, help="학습 CSV (반복 지정 가능)")
    t.add_argument("--min-class-n", type=int, default=MIN_CLASS_N_DEFAULT)
    t.add_argument("--quick", action="store_true")
    t.add_argument("--out", default=str(MODELS_DIR / "autolabel_model.pkl"))
    t.add_argument("--metrics-json", default=None,
                   help="교차일 eval이 남긴 metrics json을 모델 메타에 첨부 (대시보드 표기용)")
    t.add_argument("--denoise", action="store_true", help="학습 전 노이즈 필터링 적용")
    t.add_argument("--group", action="store_true", help="학습 전 클래스 대분류 그룹화 적용")
    t.add_argument("--smooth", action="store_true", help="시계열 보정(Temporal Smoothing) 적용")
    t.add_argument("--rules", action="store_true", help="룰 기반 도메인 매핑 적용")

    p = sub.add_parser("predict", help="CSV 단독 추론")
    p.add_argument("--model", default=str(MODELS_DIR / "autolabel_model.pkl"))
    p.add_argument("--csv", required=True)
    p.add_argument("--out-csv", required=True)
    p.add_argument("--threshold", type=float, default=0.0)

    args = ap.parse_args()

    if args.cmd == "eval":
        evaluate(args.train_csv, args.test_csv, min_class_n=args.min_class_n,
                 quick=args.quick, report_out=args.report_out, save_model=args.save_model,
                 denoise=args.denoise, group=args.group, smooth=args.smooth, rules=args.rules)

    elif args.cmd == "train":
        dfs = [load_csv(c, denoise=args.denoise, group=args.group) for c in args.csv]
        df = pd.concat(dfs, ignore_index=True)
        bundle = train_model(df, min_class_n=args.min_class_n, quick=args.quick,
                             denoise=args.denoise, group=args.group, smooth=args.smooth, rules=args.rules)
        bundle["meta"]["train_csvs"] = [str(c) for c in args.csv]
        if args.metrics_json:
            bundle["meta"]["eval_metrics"] = json.loads(
                Path(args.metrics_json).read_text(encoding="utf-8"))
        save_bundle(bundle, args.out)
        print(f"[모델 저장] {args.out}")

    elif args.cmd == "predict":
        bundle = load_bundle(args.model)
        df = pd.read_csv(args.csv, low_memory=False)
        pred = predict_df(bundle, df)
        df["task3_pred"] = apply_threshold(pred, args.threshold) if args.threshold > 0 \
            else pred["pred_label"]
        df["task3_pred_conf"] = pred["pred_conf"].round(4)
        df["task3_pred_2nd"] = pred["pred_2nd"]
        df.to_csv(args.out_csv, index=False, encoding="utf-8-sig")
        print(f"[저장] {args.out_csv} ({len(df):,}행)")


if __name__ == "__main__":
    main()
