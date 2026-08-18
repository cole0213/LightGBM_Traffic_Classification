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


# 그룹 레지스트리. 새 후보 그룹은 여기 등록하되 DEFAULT_ORDER 엔 안 넣음(expand 때 명시적 사용).
GROUPS = {
    'flow': g_flow, 'chan': g_chan, 'cum': g_cum,
    'burst': g_burst, 'hist': g_hist, 'quant': g_quant,
}


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
