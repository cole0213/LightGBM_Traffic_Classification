# Canonical full45 + seq789 실행 상태

## 고정 목표

- CSTNET: 120 클래스, full45 / seq789 / full45+seq789, pcap-N holdout 및 랜덤 8:2
- CipherSpectrum: 123 클래스(cipher × domain), 같은 평가
- LAB: 904,807 고유 세션 → 모델 평가 903,970행·88 클래스, 3-fold 날짜 LODO 및 랜덤 8:2

## 현재 상태

- CSTNET 원본 PCAP 시퀀스 추출: 완료 (46,372 flow, 오류 0)
- CSTNET 시퀀스 평가: 실행 체인에서 진행/검증 중
- 다음: CipherSpectrum 원본 추출 → 공통 평가 → LAB canonical manifest/추출/평가

## 영속 로그

- 체인: `04_logs/canonical_chain.log`, `04_logs/canonical_chain_runner.log`  (2026-08-01 로그를 04_logs/ 로 이동)
- CSTNET 추출: `canonical_cstnet_seq/extract.log`
- CSTNET 평가: `canonical_cstnet_seq/eval.log`

## 운영 규칙

- CSV 결측 필드는 임의 보정하지 않고 원본 PCAP에서 재추출한다.
- 체인이 다음 단계를 즉시 실행하고, 1분 자동 작업은 자원 감시·저부하 복구만 수행한다.
- 최종 표와 Markdown 완료 뒤에만 `/mnt/prism28`을 언마운트한다.
