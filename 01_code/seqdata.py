# -*- coding: utf-8 -*-
"""seq789 데이터 로더 (모듈화).

목적: seq part(csv+npz) 로드 + 라벨 조인/노이즈제거/keep/≥10 필터를 한 곳에.
      bias_variance.py 와 feature harness(feat_harness.py)가 공유해 로직 중복·드리프트 방지.
      기존 bias_variance.load_seq789 의 로드+라벨 부분을 그대로 파라미터화한 것(피처 조립은 제외 —
      호출측이 features.build_features 로 원하는 그룹으로 조립).

핵심: load_labeled(...) -> (A dict, meta DataFrame, y ndarray[str])
      A = npz 배열(mask/packet_size/... 각 (N,P)), meta = flow meta, y = 문자열 라벨.
      서브샘플은 여기서 안 함(호출측 책임).
작성일 2026-08-18
"""
import os
from pathlib import Path
import numpy as np, pandas as pd


def _basename(s):
    return s.astype(str).str.split('/').str[-1].str.split('\\').str[-1]


def load_labeled(seqdir, is_lab, domain_only=False,
                 label_map=None, lab_noise_file=None,
                 keep=None, exclude=None, collapse=None,
                 noise_file=None, label_exclude=None, verbose=True):
    """seq 로드 + 라벨링. bias_variance.load_seq789(피처 조립 전) 과 동일 로직.

    seqdir        : seq part 디렉터리(Path/str)
    is_lab        : True=프로세스분류(canonical 라벨조인 경로), False=도메인(CSTNET/Cipher)
    domain_only   : True=Cipher none_<cipher>_<domain> → <domain>(cipher 합침)
    label_map     : (LAB) filename→task3 csv 경로. None이면 seqdir.parent/02_dataset/lab_canon_label.csv
    lab_noise_file: (LAB) 제거할 basename 목록 파일
    keep/exclude/collapse: (LAB) 소문자 라벨 set. keep=이것만 유지, exclude=제거, collapse=__background__로 묶기
    noise_file    : (비-LAB) 제거할 basename 목록 파일
    반환: (A, meta, y). y 는 meta 행과 정렬된 문자열 라벨 배열.
    """
    seqdir = Path(seqdir)
    keep = keep or set(); exclude = exclude or set(); collapse = collapse or set()
    metas, packs = [], []
    for cf in sorted(seqdir.glob('sequences_part_*.csv')):
        z = np.load(cf.with_suffix('.npz'))
        metas.append(pd.read_csv(cf)); packs.append({k: z[k] for k in z.files})
    if not metas:
        raise FileNotFoundError(f'seq part 없음: {seqdir}/sequences_part_*.csv')
    meta = pd.concat(metas, ignore_index=True)
    A = {k: np.concatenate([p[k] for p in packs], 0) for k in packs[0].keys()}
    N = len(meta)

    if is_lab:  # canonical: filename→task3 라벨 조인 + 중복제거 + 클래스≥10
        kmpath = label_map or str(seqdir.resolve().parent / '02_dataset' / 'lab_canon_label.csv')
        km = pd.read_csv(kmpath); fn2t = dict(zip(km['filename'].astype(str), km['task3'].astype(str)))
        bn = _basename(meta['pcap'])
        lab = bn.map(fn2t)
        tmp = pd.DataFrame({'bn': bn, 'lab': lab, 'i': np.arange(N)})[lab.notna().to_numpy()].drop_duplicates('bn', keep='first')
        labc = tmp['lab'].astype(str).str.lower().str.replace(r'\.exe$', '', regex=True)
        if collapse:
            nb = int(labc.isin(collapse).sum()); labc = labc.mask(labc.isin(collapse), '__background__')
            if verbose: print(f'[LAB] background 묶음 {len(collapse)}라벨 → {nb}행 = __background__', flush=True)
        nf = set()
        if lab_noise_file and os.path.exists(lab_noise_file):
            nf = {l.strip() for l in open(lab_noise_file, encoding='utf-8') if l.strip()}
        not_noise = ~tmp['bn'].isin(nf) if nf else pd.Series(True, index=tmp.index)
        # class≥10 은 노이즈/제외/keep 적용 '후' 잔존 개수로 계산(전 개수로 하면 노이즈 빼고 1개 남는 클래스가 stratify 크래시)
        surv = (~labc.isin(exclude)).to_numpy() & not_noise.to_numpy()
        if keep: surv = surv & labc.isin(keep).to_numpy()
        vc = labc[surv].value_counts(); keepmask = (surv & labc.isin(vc[vc >= 10].index).to_numpy())
        if verbose:
            if exclude: print(f'[LAB] 라벨노이즈 제외 {len(exclude)}라벨 → 제거 {int((labc.isin(exclude)).sum())}행', flush=True)
            if keep: print(f'[LAB] keep-list {len(keep)}라벨만 유지 → 잔존 {int(surv.sum())}행', flush=True)
            if nf: print(f'[LAB] 파이프라인노이즈 {len(nf)}basename → 매칭제거 {int(tmp["bn"].isin(nf).sum())}행', flush=True)
        idx = tmp['i'].to_numpy()[keepmask]
        meta = meta.iloc[idx].reset_index(drop=True); A = {k: v[idx] for k, v in A.items()}
        meta['label'] = labc.to_numpy()[keepmask]
    else:  # 비-LAB(CSTNET/Cipher): NOISE_FILE(basename) 파이프라인 노이즈 제거
        if noise_file and os.path.exists(noise_file):
            nfset = {l.strip() for l in open(noise_file, encoding='utf-8') if l.strip()}
            bn = _basename(meta['pcap'])
            km = ~bn.isin(nfset)
            if verbose: print(f'[비-LAB] 파이프라인노이즈 {len(nfset)}basename → 제거 {int((~km).sum())}행 / {len(meta)}', flush=True)
            meta = meta[km.to_numpy()].reset_index(drop=True); A = {k: v[km.to_numpy()] for k, v in A.items()}

    lab = meta['label'].astype(str)
    if domain_only:  # CipherSpectrum: none_<cipher>_<domain> → <domain>
        lab = lab.str.split('_', n=2).str[-1]
    # 최종 라벨 기준 제외(오염 라벨 제거용). 예: Cipher 'chacha20' = 도메인칸에 암호명이 잘못 박힌 가짜클래스.
    if label_exclude:
        le = {x.lower() for x in label_exclude}
        keepm = ~lab.str.lower().isin(le)
        n_drop = int((~keepm).sum())
        if n_drop:
            meta = meta[keepm.to_numpy()].reset_index(drop=True)
            A = {k: v[keepm.to_numpy()] for k, v in A.items()}
            lab = lab[keepm.to_numpy()]
            if verbose: print(f'[label_exclude] {sorted(le)} → 제거 {n_drop}행', flush=True)
    return A, meta, lab.to_numpy()
