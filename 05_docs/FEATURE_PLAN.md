# 피처 정립 & 이후 계획 (seq-core)

> 최종 갱신 2026-08-19. 정체성(SNI·IP·포트) 없이 **패킷 행동**만으로 통하는 보편 트래픽 분류기 —
> 그 토대인 피처 표현을 근거 기반으로 확정하고, 이후 논지 확장으로 가는 전체 로드맵.

---

## 0. 최종 목표

**환경·라벨공간·수집시점이 달라도 '같은 방법'으로 통하는 보편 트래픽 분류기.**

- **환경**: TLS1.3(Cipher)·앱(CSTNET)·실환경 프로세스(LAB)·VPN/Tor(예정) — 수집 조건이 달라도.
- **라벨공간**: 도메인(42→41)·앱(120)·프로세스(81) — 맞히는 대상 종류·개수가 달라도.
- **수집시점**: week2 vs week3 — 시간 지나 분포가 드리프트해도.
- **같은 방법** = 단일 파이프라인(seq 행동피처 + 트리앙상블 + 노이즈 정제)이 세 축 다 일관.

지도학습: 라벨은 수집 때 정답 출처(LAB=OS 소켓 실측, 도메인=통제 수집 SNI)에서 얻고,
**모델 입력은 행동피처뿐**(SNI·IP·포트는 라벨링·노이즈필터에만, 피처 아님).
→ 배포 시 정체성 숨겨져도 행동만으로 분류.

---

## 1. 피처 정립 여정 (완료된 결정 + 근거)

파이프라인: **789 → 299(앞30패킷, 정본) → 100/60(compact core)**

| 단계 | 결정 | 근거 | 채택 |
|---|---|---|---|
| **0. 인프라·정제** | 피처조립 모듈화(features.py), 로드·라벨 분리(seqdata.py), 측정자(feat_harness.py) | 그룹 on/off·재현 실험 위해. 회귀테스트로 789 bit-exact 확인 후 교체 | 모듈화 + 라벨오염 제거 |
| **0. 라벨 오염** | Cipher `chacha20`(암호명이 도메인칸 오염, 1000행) 제외 → **41도메인**. LAB `unknown`(라벨 못붙인 7989행) 제외 → **81클래스**. CSTNET 정상 | 가짜 클래스가 성능·중요도 왜곡 | 41 / 120 / 81 |
| **1. 진단(importance)** | 6그룹 LightGBM 중요도 3데이터셋 전량 측정 | burst≈0(죽음), chan+cum 지배, 상위피처 **앞20패킷 집중**(중앙값 3번째) | 자르기·burst 가설 |
| **2. 자르기(789→299)** | 앞 K=100~5 패킷 sweep → 무릎점 | **K30이 무릎점**. 손실 0, CSTNET·LAB은 오히려 오름(뒤 70패킷=노이즈). K15부터 붕괴 | **앞 30패킷(K30)** |
| **3. 그룹 검증** | leave-one-out으로 뺄 그룹 확인 | flow·cum·hist 다 필요(빼면 −1~2.6). **burst만 애매하나 빼면 2/3 나빠짐**(Cipher −0.03·CSTNET −0.21·LAB +0.05) | **6그룹 전부 유지 = 299** |
| **4. 새피처 추가** | 789에 없던 6그룹(방향전이·타이밍주기성·엔트로피·정규화·window·payload, 34피처) 테스트 | **전부 개선 없음**(0~음수). chan/cum이 raw 담아 중복 | **미채택** — "core가 놓친 신호 없다"는 충족성 증거 |
| **5. 압축(299→N)** | 중요도 3데이터셋 평균 통합랭킹 → top-N 공통 core | N40도 full과 거의 동일. 단 **희소클래스는 N100이 최고**(중요도는 큰 클래스가 지배→상위N은 흔한 클래스 위주) | **N100(희소 보존) + N60(최경량)** |
| **6. 잠금** | 실행 시 env로 골라 씀(모델 자동선택 아님) | 피처는 상류 → 확정해야 하류(튜닝·BV·전이) 안 흔들림 | **299 정본 + N100/N60** |

### seq-core 299 구성 (앞 30패킷 × 6그룹)
| 그룹 | 개수 | 내용 |
|---|---|---|
| flow | 29 | 채널별 통계(mean/std/min/max/sum)+카운트+duration (패킷수 무관 고정) |
| chan | 150 | 앞30패킷 × 5채널(signed size·log IAT·window·retrans·payload×방향) |
| cum | 60 | 앞30패킷 × 누적 2종(방향·signed size) |
| hist | 40 | 크기 히스토그램 up/dn 20버킷 (고정) |
| quant | 10 | IAT·크기 분위수 (고정) |
| burst | 10 | 방향 run-length(연속 덩어리) 앞8+평균·std — importance 최하위지만 유지 |
| **합** | **299** | |

### 성능 (스크리닝: 전량 클린·단일split·가벼운 자, macro-F1)
| 피처셋 | dim | Cipher | CSTNET | LAB(F1) | 성격 |
|---|---|---|---|---|---|
| 원본 789 | 789 | 99.34 | 89.91 | 68.15 | 노이즈 포함 |
| **seq-core 299** | 299 | 99.31 | 90.06 | 68.80 | **정본·안정 최고급** |
| compact N100 | 100 | 99.20 | 89.91 | **69.64** | 희소 최고·경량 |
| compact N60 | 60 | 99.13 | 90.06 | 68.70 | 최경량 |

- **789가 최고 아님** — 잉여·노이즈 피처 탓에 실환경(CSTNET·LAB)서 오히려 낮음.
- **LAB 68은 macro-F1**(Acc는 ~89%). 불균형+시스템프로세스 행동중첩 탓. 실앱은 잘 맞힘.
- **압축은 정확도용 아님** — 다 동률. 스토리(60개로 충분)·배포효율·전이강건성 때문(전이는 검증 예정).

---

## 2. 확정된 방침

- **정본 = seq-core 299** (K30 6그룹, burst 유지).
- **compact = N100(주력) + N60(경량)**, 중요도 상위 공통 core.
- **튜닝 = 299만 재튜닝, N100/N60은 그 값 재사용**(방식 A). 이유: compact가 전용튜닝 없이도 맞으면 "충분" 주장이 더 강함(conservative). 재사용값으로 확 떨어지면 그때만 전용튜닝.
- **노이즈 정본 = seqmeta**(LAB 64→실제 전량 81클래스), 옛 pipeline(65)은 폐기.
- **전량 클린, 서브샘플 없음.**

---

## 3. 남은 계획 (진행 순)

1. **[진행중] coredump** — 299 base 3데이터셋 통합 importance → `core100_features.txt`·`core60_features.txt`·`core_ranking.txt` 저장.
2. **재튜닝(299만)** — Optuna, `FEAT_TRUNC=30` 기준 부스팅 재튜닝(기존 789 튜닝값 대체).
3. **full BV(6모델·B=15·튜닝)** — 3설정(299 자기값 / N100·N60 재사용) → 최종 공식 성능표 + per-class F1.
   → **여기까지 = 피처 정립 완료.**
4. **[보류] LAB 희소클래스 진단** — confusion matrix로 ①데이터부족/②불균형/③행동중첩 가르기. 실앱전용 서브셋+open-set. (memory: lab-rare-class-diagnosis)
5. **논지 확장** (우선순위):
   - **A. VPN/Tor 터널 통과** — 데이터 있음(ISCX-VPN 30.7만·Tor 4.4만). 정체성 완전은닉서 행동만으로 되나 = 궁극 증명.
   - **B. open-set/미지 클래스 거부** — 학습 안 한 새 앱 "모름" 처리. 배포 필수.
   - **C. 조기분류 곡선** — 앞 K패킷 만에 분류(실시간). trunc 결과가 씨앗.
   - **D. 교차전이(week2→week3)** — 공통클래스로 train A→test B, 시점 넘는 전이 직접 증명. (week_common_labels.txt 준비됨)
   - **E. 5-fold ±std** — 엄밀성.

---

## 4. 코드 인프라 (핵심 파일 + env)

- `01_code/features.py` — 피처 빌더. 그룹 레지스트리(기본6 + EXTRA6). `build_features(A,meta,groups,select)`. 기본=seq789 bit-exact.
- `01_code/seqdata.py` — seq 로드+라벨링(bias_variance·harness 공유). `load_labeled(...)`. `label_exclude`(chacha20/unknown).
- `01_code/feat_harness.py` — 측정자. 모드: importance/ablation/expand/trunc/select/coredump/eval. env: `HARNESS_LIGHT`(가벼운자), `HARNESS_TRUNC`(공통 K), `HARNESS_LAB_SUB`.
- `01_code/bias_variance.py` — BV. env: `FEAT_TRUNC`(앞K패킷=K30), `FEAT_GROUPS`, `FEAT_SELECT`(compact 이름리스트), `TUNED_PARAMS`, `LAB_NOISE_FILE`, `LAB_LABEL_MAP`, `LAB_KEEP_FILE`, `DOMAIN_EXCLUDE`, `ONLY`, `BV_SUB`, `BV_B`.

### 세 설정 실행법 (BV/학습)
```
299 정본 : FEAT_TRUNC=30
N100     : FEAT_TRUNC=30 FEAT_SELECT=02_dataset/core100_features.txt
N60      : FEAT_TRUNC=30 FEAT_SELECT=02_dataset/core60_features.txt
```
(+ LAB은 LAB_LABEL_MAP·LAB_NOISE_FILE·DOMAIN_EXCLUDE=unknown, Cipher는 DOMAIN_ONLY=1·DOMAIN_EXCLUDE=chacha20)

### 산출 결과 (03_json)
- `feat_importance.json`(그룹 중요도), `feat_trunc.json`(K sweep), `feat_ablation.json`, `feat_expand.json`, `feat_select.json`(core sweep).

---

## 5. 데이터셋 (클린)

| | 환경 | 대상 | 클래스 | rows(클린 전량) | 노이즈 정제 |
|---|---|---|---|---|---|
| CipherSpectrum | TLS1.3 | 도메인 | 41 | 122,000 | ≈0 (chacha20 제외) |
| CSTNET | TLS1.3 | 앱 | 120 | 46,372 | ≈0 |
| LAB week2 | 실환경 | 프로세스 | 81 | 603,556 | seqmeta 30% + unknown 제외 |

시각 요약: `claude.ai/code/artifact/1f58da13-f87a-444a-92d7-90082fd95f08`

---

## 6. [예정] 폴더 정리 (전체 계획 끝난 뒤)

루트 문서는 `05_docs/`로 이동 완료(HANDOFF·STRUCTURE·FEATURE_PLAN·CANONICAL_EXPERIMENT_STATUS). 루트엔 넘버폴더 + git/dotfiles만.

**01_code 하위 폴더 그룹핑** (방안 A — 폴더에만 숫자, .py는 import 안전 위해 이름 유지):
```
01_code/
  01_core/     features.py seqdata.py bias_variance.py feat_harness.py tune_boosting.py
  02_extract/  extract_pcap_seq_sni_v2.py autolabel.py pipeline.py(용도 확인 후)
  03_analysis/ probe_lgbm_it.py
  04_app/      app.py
  05_runners/  run_*.sh (10개)
```

- **주의**: `.py`에 숫자접두사·공백·버전점 금지(파이썬 import 규칙 — 모듈명은 숫자시작·공백·점 불가). 버전은 git으로.
- **이동 시 고칠 것**: ① 러너 `.sh`의 `$CODE`/python 호출 경로, ② import 그룹(core)은 같은 폴더 유지라 안 깨짐(bias_variance/feat_harness가 `sys.path.insert(dirname)` 함), ③ 이동 후 각 러너 1회 스모크.
- **선행**: `pipeline.py`(61KB) 용도 파악 후 배치.
- **실행 시점**: coredump→재튜닝→full BV 완료 후(무거운 job 없을 때).

### 02_dataset 정리 (메타 텍스트 + seq 데이터 폴더 혼재)
```
02_dataset/
  01_labels/   lab_canon_label.csv week3_label.csv lab_background_labels.txt lab_drop_labels.txt lab_noise_labels.txt
  02_noise/    *_pipeline_noise_basenames.txt *_seqmeta_noise_basenames.txt
  03_core/     week_common_labels.txt core60_features.txt core100_features.txt core_ranking.txt
  04_fingerprint/ ja3_ja4_keyed_nodoh.csv ja3_ja4_missing_filenames.txt
```
- **seq 데이터 폴더는 06_data로 이동**(일관): cipherspectrum·cipherspectrum_seq_100_v1·cipherspectrum_smoke_v2·iscx_tor_2016·iscx_vpn_2016·tor2016_seq_100·vpn2016_seq_100.
- **주의**: VPN/Tor seq(tor2016_seq_100·vpn2016_seq_100)는 논지확장 A에서 씀 → 이동 시 그 실험 경로 반영. bias_variance.py 기본 라벨맵 경로도 확인.

### 03_json 정리 (67개 — 활성 15 + 레거시 50+)
```
03_json/
  (활성, 루트 유지)  bias_variance_tuned_results.json bias_variance_tuned_dirty.json boosting_best_params.json
                      feat_*.json _tc_*.json (현 피처정립·튜닝)
  optuna_db/         optuna_*.db (8개)
  archive/           레거시 — sttabnet/etbert(feat45_* deep_compare model_compare) doh_exp ablation_v2
                      lodo sixway peh_* cstnet_lgbm_sequence_* 및 일회성 *_results.json
```
- **선행**: 어떤 json이 현 파이프라인에서 실제 참조되는지 확인 후 archive 이동(오이동 방지).

### 04_logs 정리 (107개 — 대부분 옛 로그)
```
04_logs/
  (최근 유지)  현 세션 로그(feat_*.out coredump.out bv_tuned*.out 등)
  archive/     옛 실험 로그 전부
```
- 로그는 재현 불필요분 많음 → 과감히 archive. 필요시 99_trash로.

### 정리 원칙
- **활성/레거시 구분이 핵심** — 지금 파이프라인이 참조하는 것만 루트, 나머지 archive/06_data.
- 이동 전 `grep`으로 경로 참조 확인, 이동 후 러너 스모크.
- 애매하면 삭제 말고 archive(안전).
