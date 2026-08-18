# -*- coding: utf-8 -*-
"""seq789 피처 빌더 (모듈화).

목적: 앞 100패킷 raw 배열(npz) + flow meta 로부터 행동 피처를 그룹별로 조립.
      기존 bias_variance.py 안에 박혀있던 피처 조립 로직을 분리해, 그룹 on/off·새 피처 추가·
      feature importance/ablation 을 할 수 있게 함. 기본 그룹 전체 = 정확히 seq789 (동일 순서).

입력:
  A    : npz 배열 dict. 키 = mask, packet_size, direction, iat_ms, tcp_window, retrans, payload_size.
         각 (N, P) — N=flow수, P=패킷수(=100). mask 는 유효패킷 1/0.
  meta : flow meta DataFrame. 컬럼 = burst_count, longest_burst, up_ratio, duration_ms, mean_iat_ms.

출력: build_features(A, meta, groups) -> (X: (N, D) float32, names: [str] 길이 D)

주의: 컬럼 순서·값이 기존 seq789 와 100% 동일해야 함(회귀테스트로 검증). 새 그룹은 EXTRA 에 등록해
      기본(DEFAULT_ORDER)엔 안 넣음 — expand 단계에서 명시적으로 켜서 실험.
작성일 2026-08-18
"""
import numpy as np

# 기본 6그룹 순서 = 기존 seq789 조립 순서 (flow, chan, cum, burst, hist, quant)
DEFAULT_ORDER = ['flow', 'chan', 'cum', 'burst', 'hist', 'quant']


def prepare_raw(A, meta):
    """npz 배열에서 파생 배열 준비 (모든 그룹이 공유). 기존 bias_variance.py L81-83 과 동일."""
    m = A['mask'].astype(bool)
    size = A['packet_size'].astype('f4')
    dire = A['direction'].astype('f4')
    iat = A['iat_ms'].astype('f4')
    liat = np.log1p(iat)
    win = np.log1p(np.maximum(A['tcp_window'].astype('f4'), 0))
    ret = A['retrans'].astype('f4')
    pay = A['payload_size'].astype('f4')
    signed = size * dire
    N, P = m.shape
    return dict(m=m, size=size, dire=dire, iat=iat, liat=liat, win=win,
                ret=ret, pay=pay, signed=signed, N=N, P=P, meta=meta)


# ---------- 그룹 빌더: 각 (R, names) 반환. R=(N, d) float32 ----------

def _agg(a, m):
    """마스크된 채널의 [mean,std,min,max,sum] (기존 agg)."""
    x = np.where(m, a, np.nan)
    return np.column_stack([np.nanmean(x, 1), np.nanstd(x, 1), np.nanmin(x, 1),
                            np.nanmax(x, 1), np.nansum(x, 1)])


def g_flow(R):
    """flow 레벨 통계요약 (29): 채널별 5통계 + 카운트 4 + meta 5."""
    m, size, dire = R['m'], R['size'], R['dire']
    liat, win, pay, ret = R['liat'], R['win'], R['pay'], R['ret']
    meta = R['meta']
    block = np.column_stack([
        _agg(size, m), _agg(liat, m), _agg(win, m), _agg(pay, m),
        ret.sum(1), m.sum(1), (dire > 0).sum(1), (dire < 0).sum(1),
        meta[['burst_count', 'longest_burst', 'up_ratio', 'duration_ms', 'mean_iat_ms']].to_numpy('f4'),
    ]).astype('f4')
    stats = ['mean', 'std', 'min', 'max', 'sum']
    names = ([f'flow_size_{s}' for s in stats] + [f'flow_liat_{s}' for s in stats]
             + [f'flow_win_{s}' for s in stats] + [f'flow_pay_{s}' for s in stats]
             + ['flow_ret_sum', 'flow_npkt', 'flow_up_cnt', 'flow_dn_cnt',
                'flow_burst_count', 'flow_longest_burst', 'flow_up_ratio', 'flow_duration_ms', 'flow_mean_iat_ms'])
    return block, names


def g_chan(R):
    """패킷별 채널 5종 펼침 (5*P): signed size, liat, win, ret, payload*dir."""
    m, signed, liat, win, ret, pay, dire, P = (R['m'], R['signed'], R['liat'], R['win'],
                                               R['ret'], R['pay'], R['dire'], R['P'])
    block = np.column_stack([signed, liat, win, ret, pay * dire]).astype('f4')
    names = ([f'chan_signed_p{i:03d}' for i in range(P)] + [f'chan_liat_p{i:03d}' for i in range(P)]
             + [f'chan_win_p{i:03d}' for i in range(P)] + [f'chan_ret_p{i:03d}' for i in range(P)]
             + [f'chan_paydir_p{i:03d}' for i in range(P)])
    return block, names


def g_cum(R):
    """누적 시퀀스 2종 (2*P): 누적 방향, 누적 signed size."""
    m, dire, signed, P = R['m'], R['dire'], R['signed'], R['P']
    block = np.column_stack([np.cumsum(dire * m, 1), np.cumsum(signed * m, 1)]).astype('f4')
    names = [f'cum_dir_p{i:03d}' for i in range(P)] + [f'cum_signed_p{i:03d}' for i in range(P)]
    return block, names


def g_burst(R, K=8):
    """방향 run-length 버스트 (K+2): 앞 K개 run 길이 + run 평균/표준편차."""
    m, dire, N = R['m'], R['dire'], R['N']
    bl = np.zeros((N, K), 'f4'); bm = np.zeros(N, 'f4'); bs = np.zeros(N, 'f4')
    for i in range(N):
        dd = dire[i][m[i]]
        if len(dd):
            idx2 = np.flatnonzero(np.diff(dd) != 0) + 1
            runs = np.diff(np.concatenate(([0], idx2, [len(dd)])))
            bl[i, :min(K, len(runs))] = runs[:K]
            bm[i] = runs.mean(); bs[i] = runs.std()
    block = np.column_stack([bl, bm, bs]).astype('f4')
    names = [f'burst_run{i}' for i in range(K)] + ['burst_run_mean', 'burst_run_std']
    return block, names


def g_hist(R, nbin=20, binw=80):
    """크기 히스토그램 up/dn (2*nbin): |size|//binw 를 nbin 버킷으로, 방향별 카운트."""
    m, size, dire, N = R['m'], R['size'], R['dire'], R['N']
    bi = np.clip((np.abs(size) // binw).astype(int), 0, nbin - 1)
    up = (dire > 0) & m; dn = (dire < 0) & m
    hu = np.zeros((N, nbin), 'f4'); hd = np.zeros((N, nbin), 'f4')
    for b in range(nbin):
        hu[:, b] = ((bi == b) & up).sum(1)
        hd[:, b] = ((bi == b) & dn).sum(1)
    block = np.column_stack([hu, hd]).astype('f4')
    names = [f'hist_up_b{b:02d}' for b in range(nbin)] + [f'hist_dn_b{b:02d}' for b in range(nbin)]
    return block, names


def g_quant(R, pcts=(10, 25, 50, 75, 90)):
    """분위수 (2*len): IAT, |size| 의 백분위."""
    m, iat, size = R['m'], R['iat'], R['size']
    def q(a):
        x = np.where(m, a, np.nan)
        return np.nanpercentile(x, list(pcts), 1).T.astype('f4')
    block = np.column_stack([q(iat), q(np.abs(size))]).astype('f4')
    names = [f'quant_iat_p{p}' for p in pcts] + [f'quant_size_p{p}' for p in pcts]
    return block, names


# ================= EXTRA 후보 그룹 (expand 실험용, DEFAULT_ORDER 엔 없음) =================
# 현 789에 없는 행동 신호. 이미 있는 100패킷 배열에서만 계산(재추출 X). 정체성 무관.

def _masked_moments(a, m):
    """행별 마스크 skew, kurtosis (분포 모양). sd=0 이면 0."""
    x = np.where(m, a, np.nan)
    mu = np.nanmean(x, 1, keepdims=True); sd = np.nanstd(x, 1, keepdims=True)
    z = np.where(sd > 1e-9, (x - mu) / np.where(sd > 1e-9, sd, 1), 0.0)
    sk = np.nanmean(z ** 3, 1); ku = np.nanmean(z ** 4, 1) - 3.0
    return np.nan_to_num(sk).astype('f4'), np.nan_to_num(ku).astype('f4')


def g_dirtrans(R):
    """방향 전이 패턴 (6): up→up/up→dn/dn→up/dn→dn 확률, 전환율, 첫전환 위치. 요청-응답 리듬."""
    m, dire, N = R['m'], R['dire'], R['N']
    out = np.zeros((N, 6), 'f4')
    for i in range(N):
        d = dire[i][m[i]]
        n = len(d)
        if n >= 2:
            a, b = d[:-1], d[1:]
            tot = len(a)
            uu = np.sum((a > 0) & (b > 0)); ud = np.sum((a > 0) & (b < 0))
            du = np.sum((a < 0) & (b > 0)); dd = np.sum((a < 0) & (b < 0))
            sw = np.flatnonzero(a != b)
            out[i, 0] = uu / tot; out[i, 1] = ud / tot; out[i, 2] = du / tot; out[i, 3] = dd / tot
            out[i, 4] = len(sw) / tot                      # 전환율(turn-taking)
            out[i, 5] = (sw[0] + 1) / n if len(sw) else 1.0  # 첫 전환까지 위치(정규화)
    names = ['dt_uu', 'dt_ud', 'dt_du', 'dt_dd', 'dt_switch_rate', 'dt_first_switch']
    return out, names


def g_timing(R):
    """IAT 분포모양·주기성 (8): skew, kurt, 자기상관 lag1~3, FFT 상위2 파워비, idle비율."""
    m, iat = R['m'], R['iat']
    N = R['N']
    sk, ku = _masked_moments(iat, m)
    out = np.zeros((N, 6), 'f4')  # ac1,ac2,ac3,fft1,fft2,idle
    for i in range(N):
        v = iat[i][m[i]].astype('f8')
        n = len(v)
        if n >= 4:
            vc = v - v.mean(); denom = np.sum(vc * vc) + 1e-12
            for k in (1, 2, 3):
                out[i, k - 1] = np.sum(vc[:-k] * vc[k:]) / denom
            p = np.abs(np.fft.rfft(vc)) ** 2
            p = p[1:]  # DC 제외
            if p.size and p.sum() > 0:
                ps = np.sort(p)[::-1] / p.sum()
                out[i, 3] = ps[0]
                out[i, 4] = ps[1] if ps.size > 1 else 0.0
            med = np.median(v)
            out[i, 5] = np.mean(v > 3 * med) if med > 0 else 0.0  # idle(큰 gap) 비율
    block = np.column_stack([sk, ku, out]).astype('f4')
    names = ['tm_skew', 'tm_kurt', 'tm_ac1', 'tm_ac2', 'tm_ac3', 'tm_fft1', 'tm_fft2', 'tm_idle']
    return np.nan_to_num(block), names


def g_sizeshape(R, nbin=20, binw=80):
    """크기 분포 모양·다양성 (7): skew, kurt, 엔트로피, 고유버킷비, 최빈비, 소패킷비, 대패킷비."""
    m, size, N = R['m'], R['size'], R['N']
    asz = np.abs(size)
    sk, ku = _masked_moments(asz, m)
    bi = np.clip((asz // binw).astype(int), 0, nbin - 1)
    cnt = np.zeros((N, nbin), 'f8')
    for b in range(nbin):
        cnt[:, b] = ((bi == b) & m).sum(1)
    nv = cnt.sum(1, keepdims=True); p = cnt / np.where(nv > 0, nv, 1)
    ent = -np.sum(np.where(p > 0, p * np.log(p + 1e-12), 0.0), 1)      # 크기 엔트로피
    uniq = (cnt > 0).sum(1) / float(nbin)                              # 고유버킷 비율
    mode = cnt.max(1) / np.where(nv[:, 0] > 0, nv[:, 0], 1)            # 최빈버킷 비율
    small = ((asz < 100) & m).sum(1) / np.where(nv[:, 0] > 0, nv[:, 0], 1)   # ACK류 비율
    big = ((asz > 1400) & m).sum(1) / np.where(nv[:, 0] > 0, nv[:, 0], 1)    # MTU급 비율
    block = np.column_stack([sk, ku, ent, uniq, mode, small, big]).astype('f4')
    names = ['ss_skew', 'ss_kurt', 'ss_entropy', 'ss_uniq', 'ss_mode', 'ss_small', 'ss_big']
    return np.nan_to_num(block), names


def _cv(a, m):
    """행별 변동계수 std/mean (스케일 불변). mean~0 이면 0."""
    x = np.where(m, a, np.nan)
    mu = np.nanmean(x, 1); sd = np.nanstd(x, 1)
    return np.nan_to_num(np.where(np.abs(mu) > 1e-9, sd / np.where(np.abs(mu) > 1e-9, mu, 1), 0.0)).astype('f4')


def g_norm(R):
    """정규화(스케일 불변) 피처 (5): iat·size·pay·win 변동계수 + 전반부 시간비중. 환경/시점 드리프트 강건."""
    m, iat, size, pay, win, N = R['m'], R['iat'], R['size'], R['pay'], R['win'], R['N']
    asz = np.abs(size)
    cv_iat, cv_sz, cv_pay, cv_win = _cv(iat, m), _cv(asz, m), _cv(pay, m), _cv(win, m)
    # 전반 50% 패킷의 IAT 비중(타이밍 앞/뒤 쏠림)
    P = R['P']; half = P // 2
    im = np.where(m, iat, 0.0)
    early = im[:, :half].sum(1); tot = im.sum(1)
    early_frac = np.nan_to_num(np.where(tot > 0, early / np.where(tot > 0, tot, 1), 0.0)).astype('f4')
    block = np.column_stack([cv_iat, cv_sz, cv_pay, cv_win, early_frac]).astype('f4')
    names = ['nm_cv_iat', 'nm_cv_size', 'nm_cv_pay', 'nm_cv_win', 'nm_iat_early_frac']
    return np.nan_to_num(block), names


def g_winflow(R):
    """window 동역학 (4): window diff 평균/표준편차, zero-window 비율, window 감소횟수비."""
    m, N = R['m'], R['N']
    win = R['win']  # 이미 log1p(window)
    wm = np.where(m, win, np.nan)
    dwin = np.diff(wm, axis=1)
    dmean = np.nan_to_num(np.nanmean(dwin, 1)).astype('f4')
    dstd = np.nan_to_num(np.nanstd(dwin, 1)).astype('f4')
    zero = ((win <= 1e-6) & m).sum(1) / np.where(m.sum(1) > 0, m.sum(1), 1)  # log1p(0)=0
    dec = np.nan_to_num((dwin < 0).sum(1) / np.where(m.sum(1) > 1, m.sum(1) - 1, 1)).astype('f4')
    block = np.column_stack([dmean, dstd, zero.astype('f4'), dec]).astype('f4')
    names = ['wf_dmean', 'wf_dstd', 'wf_zero', 'wf_dec']
    return np.nan_to_num(block), names


def g_payload(R):
    """payload 구조 (4): 순수ACK(payload=0) 비율, payload/size 비율 평균/표준편차, payload>0 비율."""
    m, pay, size, N = R['m'], R['pay'], R['size'], R['N']
    asz = np.abs(size); nv = np.where(m.sum(1) > 0, m.sum(1), 1)
    ack = ((pay <= 0) & m).sum(1) / nv
    ratio = np.where((asz > 0) & m, pay / np.where(asz > 0, asz, 1), np.nan)
    rmean = np.nan_to_num(np.nanmean(ratio, 1)).astype('f4')
    rstd = np.nan_to_num(np.nanstd(ratio, 1)).astype('f4')
    haspay = ((pay > 0) & m).sum(1) / nv
    block = np.column_stack([ack.astype('f4'), rmean, rstd, haspay.astype('f4')]).astype('f4')
    names = ['pl_ack_ratio', 'pl_pratio_mean', 'pl_pratio_std', 'pl_haspay']
    return np.nan_to_num(block), names


# 그룹 레지스트리. 기본 6그룹(seq789) + EXTRA 후보 6그룹. DEFAULT_ORDER 엔 기본만.
GROUPS = {
    'flow': g_flow, 'chan': g_chan, 'cum': g_cum,
    'burst': g_burst, 'hist': g_hist, 'quant': g_quant,
    # EXTRA 후보(expand): 명시적으로 켜야 조립됨
    'dirtrans': g_dirtrans, 'timing': g_timing, 'sizeshape': g_sizeshape,
    'norm': g_norm, 'winflow': g_winflow, 'payload': g_payload,
}
EXTRA = ['dirtrans', 'timing', 'sizeshape', 'norm', 'winflow', 'payload']


def build_features(A, meta, groups=None):
    """선택 그룹으로 피처행렬 조립. groups=None → DEFAULT_ORDER(전체 6그룹=seq789).
    반환: (X float32 (N,D), names list[str]). NaN/inf 는 0 으로(기존 nan_to_num 동일)."""
    order = list(groups) if groups is not None else DEFAULT_ORDER
    R = prepare_raw(A, meta)
    blocks, names = [], []
    for g in order:
        if g not in GROUPS:
            raise KeyError(f'unknown feature group: {g} (있는 그룹: {list(GROUPS)})')
        blk, nm = GROUPS[g](R)
        blocks.append(blk); names.extend(nm)
    X = np.nan_to_num(np.column_stack(blocks).astype('f4'))
    return X, names
