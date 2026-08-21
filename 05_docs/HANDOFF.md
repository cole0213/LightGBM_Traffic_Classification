# HANDOFF — lab_dashboard / 01_MachineLearning (2026-08-20 갱신)

다음 에이전트가 이 파일만 읽고 이어서 작업할 수 있도록 정리한 인수인계 문서.
(이전 2026-08-13 버전 대체. 그 이후 "피처 정립" 세션 전부 반영.)

---

## ★ 최신 갱신 (2026-08-20) — 피처 정립 세션

- **피처 정립 완료**: seq789 → **정본 seq-core 299**(앞30패킷·6그룹) + **compact core N100/N60**. 근거 기반 압축(truncation·ablation·expand·select). 상세 = `05_docs/FEATURE_PLAN.md`, 시각요약 = artifact `claude.ai/code/artifact/1f58da13-f87a-444a-92d7-90082fd95f08`.
- **인프라 모듈화**: 피처조립 `features.py`, 로드/라벨 `seqdata.py`, 측정 harness `feat_harness.py`. bias_variance/tune_boosting도 이 모듈 쓰게 리팩터(회귀테스트 통과, bit-exact).
- **라벨 오염 정제**: Cipher `chacha20`(암호명이 도메인칸 오염, 1000행) 제외 → **42→41 도메인**. LAB `unknown`(라벨 없음 7989행) 제외. CSTNET 정상.
- **정본 299 재튜닝 완료**: `03_json/boosting_best_params_core.json` (Cipher LGB 99.47/XGB 99.34, CSTNET 90.62/89.53, LAB 72.09/73.02, val macro-F1).
- **[진행 중] 최종 full BV**: `run_bv_core.sh` — 3설정(299/N100/N60)×3데이터셋×5모델×B=15. 결과 `bias_variance_core_{299,N100,N60}.json`. → **이게 끝나면 피처정립 최종 성능표 완성.**
- **문서·산출물**: PPT `심규상_260820_피처정립_실험결과.pptx`(OneDrive, 원본 260813 템플릿 위에 빌드=로고·양식 상속), 정제기준 규칙별 breakdown, 연구실 공용 시트(구글) 행 작성.

---

## 0. 환경 · 절대 규칙 (반드시 준수)

- **로컬 PC(Windows)에서 학습/heavy 추출 금지.** ML은 서버. (로컬 `C:\Python313\python.exe`는 PPT·가벼운 라벨집계·피처 회귀테스트 소량만. node+pptxgenjs는 scratchpad에 설치됨. soffice/pdftoppm 없음 → PPT 시각 QA 불가, python-pptx 구조검증만.)
- **주 서버 = 17** `163.152.223.17` (root). 12코어·62GB·**RTX 3060 (VRAM 8GB)**. 사용자가 Xshell로 접속·실행.
  - **에이전트 SSH 직접실행 차단** → 명령을 만들어 주고 **사용자가 붙여넣어 실행**. 결과를 사용자가 붙여주면 확인.
  - `U:` 마운트로 서버 파일 읽기/쓰기(코드 수정·파일 생성 가능).
  - **⚠️ `U:` 로그·파일 읽기는 SMB 캐시로 지연**(옛 내용 보임). "멈췄다" 판단 전 **서버 `pgrep`/`ps`/`tail`로 크로스체크**(이번 세션에도 로그가 9시간 옛것 보여줘 오진할 뻔).
- **무거운 CPU 작업 2개 동시 = 서로 굶김.** 순차 원칙. 병렬은 CPU작업 ∥ GPU작업(자원 다를 때)만 — 재튜닝은 LightGBM(CPU) ∥ XGBoost(GPU)로 동시 OK.
- 드라이브: `U:`=서버17(프로젝트), `X:`=서버99(공개데이터셋 + 노이즈파이프라인 00_codes), `W:`=서버28(원본 pcap).
- **git**: `github.com/cole0213/LightGBM_Traffic_Classification` (origin/master). 코드 후 `/commit`. SMB라 `git config --global --add safe.directory` 필요했음.

## 1. 프로젝트 목표

**정체성(SNI·IP·포트) 은닉(TLS1.3·DoH·CDN·VPN/Tor) 환경에서도 정체성 피처 없이 패킷 행동(seq)만으로 되는 보편 트래픽 분류기.** 환경·라벨공간·수집시점이 달라도 같은 방법으로 통함을 증명.

- 지도학습: **라벨 = 수집 때 정답출처**(LAB=OS 소켓 실측 프로세스, 도메인=통제수집 SNI). **모델 입력 = 행동 피처(seq)뿐** — SNI·IP·포트는 라벨링/노이즈필터에만, 피처 아님.
- 주력 = **트리앙상블(LightGBM) on seq-core + 노이즈 정제 + 주차/데이터셋 일반화**. CatBoost 전면 제외(8GB GPU 다중클래스 OOM + 최하위).
- 분류 유형: **Cipher=도메인, CSTNET=앱, PRISM(LAB)=프로세스**.

## 2. 피처 정립 — 완료 (이번 세션 핵심)

파이프라인: **789 → 299(앞30패킷 정본) → 100/60(compact core)**. 전부 전량 클린·단일split·가벼운 자(uniform LightGBM) 스크리닝. macro-F1.

| 단계 | 결정 | 근거 |
|---|---|---|
| 진단 importance | — | burst≈0(죽음), chan+cum 지배, 상위피처 앞20패킷 집중(중앙값 3번째) |
| truncation | 앞 30패킷(K30, 789→299) | 무릎점. 손실 0, CSTNET/LAB은 오히려 상승(뒤 70패킷=노이즈). K15부터 붕괴 |
| ablation | 6그룹 전부 유지(burst 포함) | burst 빼면 2/3 데이터셋 나빠짐(Cipher −0.03·CSTNET −0.21·LAB +0.05), 10피처뿐 → 유지 |
| expand | 새 후보 6그룹(34피처) **미채택** | 전부 개선 0 이하 → chan/cum이 raw 담아 중복 = core 충족성 증거 |
| select | compact = **N100**(희소보존) + N60(경량) | N40도 full과 거의 동일. LAB 희소클래스는 피처 많을수록 유리(중요도는 큰 클래스 지배) → N100 최고 |

- **seq-core 299 구성**: flow(29 통계요약) + chan(150=앞30패킷×5채널) + cum(60) + hist(40) + quant(10) + burst(10). 앞100→30패킷만.
- **compact core 선택**: 299 importance 3데이터셋 평균 통합랭킹 상위 N. 리스트 = `02_dataset/core100_features.txt`·`core60_features.txt`·`core_ranking.txt`.
- **스크리닝 성능(가벼운 자)**: 789/299/N100/N60 전부 ±0.3 이내 동률. 789가 최고 아님(노이즈 포함). 압축 가치 = 스토리·배포효율·전이강건성(정확도 아님, 전이는 미검증).

## 3. 완료된 실험 (성공)

1. **부스팅 튜닝 완결**(789기준) → `boosting_best_params.json`. Cipher LGB 98.49·CSTNET 91.21·LAB 71.32(val).
2. **튜닝반영 BV 클린**(789, B=15) → `bias_variance_tuned_results.json`. Cipher(42) LGB F1 98.59/Acc 99.06, CSTNET(120) 90.32/92.41, LAB(64,20만서브) LGB 69.08·XGB 70.04.
3. **튜닝반영 BV 더티**(노이즈 미제거) → `bias_variance_tuned_dirty.json`. LAB 클린이 더티보다 F1 +2.6~3.4 → 노이즈 정제 가치 재확인.
4. **노이즈 정본 = seqmeta 확정** (prism04 조인과 30.3% 일치 검증). 옛 pipeline(prism04, LAB 65클래스) 폐기(`_notes`·`02_dataset`에 [DEPRECATED] 마킹).
5. **피처 정립 인프라 + 5개 분석**(importance/trunc/ablation/expand/select/coredump) → `03_json/feat_*.json`.
6. **정본 299 재튜닝** → `boosting_best_params_core.json`.
7. **정제 기준 규칙별 breakdown**(scratchpad/noise_breakdown.py): LAB week2 Cc-DNS(port53) 32.5% 압도적, week3 24.8%. SMB·broadcast·DoH·De 소수.
8. **PPT·시트**: 실험결과 PPT(원본 템플릿 상속), 구글 공용시트용 4행(Cipher/CSTNET/PRISM w2·w3).

### 클래스 수 참고 (전량 vs 20만 서브샘플)
| PRISM | 전량(≥10) | 20만 서브(≥15) |
|---|---|---|
| week2 | **81** (603,556행) | **64** |
| week3 | **120** (1,574,410행) | **79** |
- Cipher 41(전량), CSTNET 120(전량). PRISM만 서브샘플 사용(전량은 B=15 BV엔 너무 큼).
- 피처정립 스크리닝은 LAB **전량 81** 사용(단일split). B=15 BV는 **20만 서브 64/79**.

## 4. 진행 중

**최종 full BV** — `01_code/run_bv_core.sh`
```
cd /root/02_SGS/01_MachineLearning && unset XGB_GPU CAT_GPU && BASE=$(pwd) N_JOBS=11 BV_B=15 nohup bash 01_code/run_bv_core.sh > 04_logs/bv_core.out 2>&1 & disown
```
- 3설정(299=FEAT_TRUNC30 / N100=FEAT_SELECT core100 / N60=core60) × 3데이터셋 × 5모델 × B=15. core 튜닝값 사용.
- **3설정 동일 데이터**(같은 서브샘플 seed·클래스≥15·split·부트스트랩) → 피처만 다름 = 통제비교.
- 출력 `bias_variance_core_{299,N100,N60}.json`. ETA ~1.5~2일. 확인: `tail -f 04_logs/bv_core.out`, `설정 299 완료` 후 N100→N60.

## 5. 다음 단계 (우선순위)

1. **full BV 완주 대기** → PPT S8~10·S19를 **정본 299 실측 B=15 표**로 갱신 + compact(N100/N60) 표 추가. 구글시트 행도 299값으로 갱신. per-class F1도 확보.
2. **[보류] LAB 희소클래스 진단** — confusion matrix로 ①데이터부족 ②불균형 ③행동중첩 구분. 실앱전용 서브셋 + open-set. (memory: `lab-rare-class-diagnosis`. 사용자가 "피처정립 끝나면"으로 보류시킴.)
3. **논지 확장**: (A) **VPN/Tor 터널 통과**(데이터 보유: vpn2016_seq_100 30.7만·tor2016_seq_100 4.4만) — 정체성 완전은닉서 행동만으로=궁극 증명. (B) **open-set** 미지클래스 거부. (C) **교차전이 week2→week3**(공통클래스 `week_common_labels.txt` 준비됨). (D) 조기분류·5-fold±std.
4. **저장소 정리**(FEATURE_PLAN §6): 01_code 하위폴더(01_core/02_extract/03_analysis/04_app/05_runners), 03_json 활성/archive, 02_dataset labels/noise/core, 로그 archive. **.py에 숫자접두사·공백·버전점 금지(import 깨짐).** run_bv_core 등 도는 job 끝난 뒤.
5. (선택) week3 튜닝반영 BV(현재 통일params), 김지민 프로세스108/응용89와 조건 맞춰 대조.

## 6. 핵심 파일 · env

- `01_code/features.py` — 피처빌더. `build_features(A,meta,groups,select)`. 그룹 레지스트리(기본6=seq789 + EXTRA6 미채택). 기본=bit-exact seq789.
- `01_code/seqdata.py` — 로드+라벨링(bias_variance·tune·harness 공유). `load_labeled(seqdir,is_lab,domain_only,label_map,lab_noise_file,keep,exclude,collapse,noise_file,label_exclude)`.
- `01_code/feat_harness.py` — 측정자. 모드 importance/ablation/expand/trunc/select/coredump/eval. env `HARNESS_LIGHT`(uniform 자)·`HARNESS_TRUNC`(공통K)·`HARNESS_LAB_SUB`.
- `01_code/bias_variance.py` — BV. env `FEAT_TRUNC`(앞K=정본30)·`FEAT_GROUPS`·`FEAT_SELECT`(compact 이름리스트)·`TUNED_PARAMS`·`LAB_NOISE_FILE`·`LAB_LABEL_MAP`·`DOMAIN_EXCLUDE`(chacha20/unknown)·`ONLY`·`BV_SUB`·`BV_B`.
- `01_code/tune_boosting.py` — Optuna. seqdata+build_features 씀. env `TUNE_TAG`(db 분리)·`XGB_GPU`·`FEAT_TRUNC` 등.
- 러너: `run_tune_core.sh`(299 재튜닝), `run_bv_core.sh`(최종 BV 3설정), `run_bv_tuned.sh`(789 튜닝BV, 옛), `run_tune_clean.sh`(789 튜닝, 옛).
- **세 피처설정 실행법**: 299=`FEAT_TRUNC=30` / N100=`FEAT_TRUNC=30 FEAT_SELECT=02_dataset/core100_features.txt` / N60=`...core60...`. (+ Cipher `DOMAIN_ONLY=1 DOMAIN_EXCLUDE=chacha20`, LAB `LAB_LABEL_MAP·LAB_NOISE_FILE·DOMAIN_EXCLUDE=unknown·BV_SUB=200000`.)
- 노이즈/라벨: `02_dataset/lab_seqmeta_noise_basenames.txt`(week2 정본)·`week3_seqmeta_noise_basenames.txt`·`lab_canon_label.csv`(week2 라벨)·`week3_label.csv`. **옛 `lab_pipeline_noise_basenames.txt`(prism04, 폐기)**.
- scratchpad(로컬, 커밋X): `noise_breakdown.py`(규칙별집계)·`class_count.py`·`gen_ppt2.py`(PPT생성)·`common_class.py`(주차공통라벨)·회귀테스트.

## 7. 실패·교훈 (반복 금지)

1. **인라인 `BASE=$(pwd) python $BASE/...`** — 같은 줄 prefix 할당은 그 줄 인자 전개엔 미반영(빈값) → SEQDIR 깨짐. 상대경로나 `export BASE && ...`로.
2. **LAB_LABEL_MAP 기본경로** — bias_variance 기본이 `SEQDIR.parent/02_dataset`인데 폴더 재편(06_data/) 후 깨짐(`06_data/02_dataset` 오참조 FileNotFoundError). 러너에서 명시 필요.
3. **tune_boosting가 789 피처 자체복제** — 정본 299 재튜닝 위해 seqdata+build_features 쓰게 리팩터해야 했음.
4. **optuna db 태그** — 피처셋 다르면 study 섞임 → `TUNE_TAG=_core`로 db 분리.
5. **U: SMB 캐시** — 재튜닝 로그가 9시간 옛것 보여줘 "멈췄나" 오진. 서버 pgrep/ps로 확인하니 정상 진행 중이었음.
6. **CatBoost GPU OOM**(8GB, 다중클래스) → 전면 제외. **LightGBM predict 느림**(다중클래스, XGBoost의 3~9배) — 추론=per-flow µs로 보고(저번 PPT 방식).
7. **라벨 오염** — Cipher chacha20(암호명), LAB unknown. 새 데이터셋은 라벨 distinct 먼저 훑을 것.
8. **STTabNet 폐기**(2026-08-11, 이전 세션) — 다중분류 붕괴. 트리앙상블이 tabular 우위.

## 8. 데이터셋 상태 (클린)

| 데이터셋 | seq 경로(06_data) | 분류 | 클래스 | 노이즈정제 |
|---|---|---|---|---|
| CipherSpectrum | canonical_cipherspec_seq_v2 | 도메인 | 41 | ≈0(De=정답, chacha20 제외) |
| CSTNET | canonical_cstnet_seq | 앱 | 120 | ≈0 |
| PRISM week2 | lab_full45_seq_v2_904k | 프로세스 | 81(전량)/64(20만) | seqmeta 30%+unknown |
| PRISM week3 | lab_week3_seq_100 | 프로세스 | 120(전량)/79(20만) | seqmeta 30% |
| VPN/Tor | vpn2016_seq_100·tor2016_seq_100 | (논지확장용) | — | 미사용, 보유 |

- 전부 seq789(앞100패킷·789피처) 추출본. 정본 피처 = 이 위에서 앞30패킷·299.
- 노이즈 규칙(seqmeta): De(CDN/SNI)·Cc(DNS·SMB·NTP·broadcast)·Cd(torrent·telemetry)·DoH. 도메인분류는 De 유지(SNI=정답)→노이즈≈0, 프로세스분류는 De 포함→30%.
