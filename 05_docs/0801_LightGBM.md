# 📦 0801_LightGBM

> **한 줄**: 목표 = "**5-tuple(IP·포트·proto) 제거 + seq789 결합** 피처로 CSTNET·CipherSpectrum·LAB를 **동일 조건**(정직한 pcap-N 홀드아웃 + 랜덤 8:2)으로 비교". → 5-tuple을 빼도 **SNI(이름) + 패킷행동 시퀀스**만으로 정확도 유지되는지 검증. CSTNET **91.63%**·CipherSpectrum **83.11%** 확정, LAB(904k) 추출 진행 중. (0729_LightGBM 후속)

---

## 0. 방향 (사용자 의도)
- PPT 향후계획 실행분: **5-tuple 제거** + 0729에서 만든 **seq789** 피처를 세 데이터셋에 공통 적용.
- "이름(SNI) > 주소(IP/포트)" 가설을 세 데이터셋에서 재확인. 모델은 **LightGBM 유지**(배포정합성·gain 설명·CPU 자원).
- 스크립트: `feat_combined_no5t.py` (뷰 4종, OUT = `03_json/feat_combined_no5t_results.json`).

## 1. 사용 데이터셋

| 데이터셋 | 세션(행) | 클래스 | SNI 채움 | 비고 |
|---|---|---|---|---|
| CSTNET (TLS 1.3) | 46,372 | 120 | ~5% | CDN 공유 IP, SNI 거의 없음 → 어려운 타깃 |
| CipherSpectrum | 123,000 | 123 | 100% | cipher × domain, SNI 완비 |
| LAB (Week2, 앱) | ~904k (pcap 146만) | 91 (앱) | - | full 재추출 진행 중. 라벨=앱(폴더 parts[2]) |

각 데이터셋은 **독립 평가**(자기 클래스·자기 홀드아웃). 합치지 않음.

## 2. 사용 피처 & 개수 (뷰 4종)

| 뷰 | 피처 수 | 구성 |
|---|---|---|
| name(SNI) no5t | 7 | SNI 문자열·통계만 (5-tuple 제거) |
| seq+②④ | 789 | 패킷 행동 시퀀스 (원래부터 5-tuple 없음) |
| **combined no5t** (핵심) | **796** | SNI(7) + seq789 — 5-tuple 제거 |
| combined (full 5t) | 800 | 참고 기준선: + dst_ip·dst_net·dst_port·protocol(4) |

### seq789 내부 구성 (max 100패킷/flow)

| 그룹 | 개수 | 내용 |
|---|---|---|
| flow 집계 | 29 | 크기·IAT·TCP윈도우·payload의 평균/표준편차/min/max/합 + 재전송·패킷수·상하향 카운트 + burst_count·longest_burst·up_ratio·duration·mean_iat |
| channel (원시 시퀀스) | 500 | 앞 100패킷 × 5채널: 방향부호화 크기·log-IAT·log-윈도우·재전송·payload×방향 |
| cumulative | 200 | 방향·부호화크기 **누적합 트레이스**(위치 밀림에 강함) |
| burst | 10 | 방향 런 길이 top8 + 평균 + 표준편차 |
| histogram | 40 | 방향별(상/하) 크기 히스토그램 20빈 × 2 |
| quantile | 10 | IAT·크기 분위수 (10/25/50/75/90) |

합계 29+500+200+10+40+10 = **789**.

## 3. 피처가 무엇인가 (그룹별 의미)
- **5-tuple (제거 대상, 4개)**: `dst_ip`·`dst_net(/24)`·`dst_port`·`protocol` — 목적지 **주소** 정체성. 이번 실험은 이걸 뺀다.
- **SNI / 이름 (유지, 7개)**: `sni_c`(앞60자)·`sni_base`(도메인 base) 범주 + `sni_has/len/ndots/ndig/ent`(문자열 존재·길이·점수·숫자수·엔트로피) — 목적지 **이름** 정체성.
- **seq789 (패킷 행동, 789개)**: 앞 100패킷의 **크기·방향·타이밍 순서**와 그 구조 요약(누적합·버스트·히스토그램·분위수). 어느 데이터셋에서도 계산 가능한 **보편 신호**이자 도메인의 **행동 지문**.

## 4. 결과 — combined no5t (5-tuple 제거 + SNI + seq789)

| 데이터셋 | rows | 클래스 | LODO (pcap-N 홀드아웃) | 랜덤 8:2 |
|---|---|---|---|---|
| CSTNET | 46,372 | 120 | **91.63%** | 92.13% |
| CipherSpectrum | 123,000 | 123 | **83.11%** | 85.55% |
| LAB (앱) | ~904k | 91 | ⏳ 추출 진행 중 | ⏳ |

> 뷰별 상세(name-only / seq-only / combined / full-5t)는 `03_json/feat_combined_no5t_results.json`에 저장. LAB 완료 후 표 갱신 예정.

## 5. 결과 해석
1. **5-tuple을 빼도 정확도가 무너지지 않는다.** CSTNET은 SNI가 5%뿐인 어려운 타깃인데도 combined-no5t가 **91.63%** — 0729의 seq789(92%)와 정합. 즉 **주소(IP·포트)를 제거해도 패킷 행동 시퀀스가 목적지 정체성을 대체**한다.
2. **CipherSpectrum 83.11%**: 123개 세밀 클래스(cipher×domain), SNI 100%. LODO−랜덤 갭이 ~2.4%p로 작아 **홀드아웃 일반화가 안정적**.
3. **핵심 메시지**: 목적지 신호는 단일 5-tuple이 아니라 "**이름(SNI) + 행동(seq789)**"이 주도한다 → PPT의 "**이름 > 주소, 5-tuple 제거 가능**" 주장을 (현재 2/3 데이터셋) 재확인. LAB 904k 완료 시 앱 분류에서도 성립하는지 최종 확인.

## 6. 실행 / 환경
- 서버 **163.152.223.17** (12코어·62GB·RTX3060). ML = LightGBM **CPU**(n_jobs 8) — 병목은 tshark 추출이라 GPU 무의미.
- 데이터: Week2 pcap을 server28(W:)→server17 **robocopy**(146만 파일·22.7GB) 후, `extract_pcap_seq_sni_v2.py --label-depth 2`(앱 라벨)로 추출 → `feat_combined_no5t.py` 비교.
- 디렉터리 정리: `01_code / 02_dataset / 03_json / 04_logs / 05_docs` 재구성 완료(`STRUCTURE.md`).
- ⚠️ smoke/mini 검증이 "클래스 1개" 에러 → 정렬 앞 N개가 한 앱이라 생긴 표본 artifact. 전체 실행(limit=0)은 91클래스 전부 포함되어 정상.

---
*담당: Claude Code (Opus 4.8) · 서버17 `02_SGS/lab_dashboard_ver0.1/` — `01_code/feat_combined_no5t.py`·`run_lab904_extract_compare.sh`·`extract_pcap_seq_sni_v2.py(--label-depth)`. 관련: 0729·07_26 LightGBM.*
