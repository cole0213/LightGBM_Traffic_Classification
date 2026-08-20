# HANDOFF — lab_dashboard_ver0.1 (2026-08-12 갱신)

다음 에이전트가 이 파일만 읽고 이어서 작업할 수 있도록 정리한 인수인계 문서.
(이전 260805 버전을 대체. 그 이후 진행분 전부 반영)

---

## ★ 최신 갱신 (2026-08-13)

- **저장소 대청소 + 폴더 재편**: 루트 40 → 8 (`01_code 02_dataset 03_json 04_logs 05_docs 06_data 07_app 99_trash_20260813`).
  - 연구 데이터(seq789·canonical) → **`06_data/`**, 대시보드 런타임(models/static/tools) → **`07_app/`**.
  - `01_code` 121 → **17개**(연구핵심·러너·대시보드만). 미사용 코드/데이터 → `99_trash_20260813/`(되돌리기 가능, 하드삭제 보류).
  - 이동에 맞춰 유지 코드 경로 참조 일괄 갱신(러너 `$BASE/06_data/...`, app 3파일 `BASE_DIR/07_app/...`). 상세 = `STRUCTURE.md`.
- **git 버전관리 시작**: `github.com/cole0213/LightGBM_Traffic_Classification` (origin/master, push 완료). `.gitignore`(대용량·런타임 제외)·`.gitattributes`(LF 강제). 코드 작업 후 `/commit`으로 커밋+push.
- **PPT 재작업**: `심규상_260813_연구계획.pptx`(OneDrive) — STTabNet 제거, 클린 데이터셋만, BV 표에 전체지표(F1/Acc/bias/var/err/학습s/추론s/mem).
- **⚠️ 예정 — 폴더 이름 변경**: `lab_dashboard_ver0.1` → **`01_MachineLearning`**. 유지 코드가 전부 상대경로라 **코드 수정 불필요**(문서·주석 이름만 갱신). **실행 중 LAB 튜닝 job의 작업 디렉터리라 job 완주 후 진행**(optuna sqlite 경로 재열림·SMB open-file 충돌 회피). optuna resume 가능이라 최악도 재실행 복구.

---

## 0. 환경 · 절대 규칙 (반드시 준수)

- **로컬 PC(Windows)에서 학습/추출/heavy 연산 금지.** ML·pcap추출은 서버에서. (PPT용 python-pptx, 가벼운 데이터 조인/집계는 로컬 `C:\Python313\python.exe` 승인됨. soffice/pdftoppm은 로컬에 없음 → PPT 시각 QA 불가.)
- **주 서버 = 17** `163.152.223.17` (root). 12코어·62GB·**RTX 3060 (VRAM 8GB)**. 사용자가 Xshell로 접속·실행.
  - **에이전트 SSH 직접실행 차단** → 명령을 만들어 주고 **사용자가 Xshell에 붙여넣어 실행**.
  - 에이전트는 `U:` 마운트로 서버 파일을 읽어 진행 확인(쓰기도 가능 — 코드 수정·파일 생성 함).
  - **⚠️ `U:` 로그 읽기는 SMB 캐시로 지연될 수 있음**(옛 내용 보임). 진행상황은 서버 `tail`/`ps`가 정확. "멈춘 것 같다" 판단 전 서버에서 크로스체크.
- **드라이브 매핑**: `U:`=서버17(프로젝트), `W:`=서버28(원본 pcap, `//163.152.223.28/RAID1`, nasuser/tpwhd.Wkd), `X:`=서버99(`//163.152.234.99/root`, root/tpwhd.Wkd, **공개데이터셋 data-8t + 노이즈 파이프라인 00_codes**), `Z:`=서버16(옵시디언 볼트), `Y:`=서버188.
- 서버 프로젝트 경로: `/root/02_SGS/lab_dashboard_ver0.1`.
- **무거운 CPU 작업 2개 동시 = 서로 굶김**(실제로 추출+LightGBM BV 동시 돌려 6시간 정지 사고). **순차 실행 원칙.** 병렬은 CPU작업 ∥ GPU작업처럼 자원이 다를 때만.

## 1. 프로젝트 목표

**"암호화·정체성 은닉(TLS1.3·DoH·CDN·VPN·Tor) 환경에서도 정체성 피처(SNI·IP·5-tuple) 없이 패킷 행동(seq789)만으로 되는 보편 트래픽 분류기."** 최종 산출 = 논문/졸업작품, 보편성 증명.

- **★ STTabNet(딥 시퀀스모델) 폐기 (2026-08-11)**: 다중분류 붕괴 + ET-BERT 등 선행연구 존재 + tabular에선 트리가 딥 이김(Grinsztajn 2022). 코드/데이터는 남겨두되 진행 안 함.
- **현재 주력 = 트리앙상블(LightGBM) on seq789 + 노이즈 정제 + 주차/데이터셋 일반화.**
- seq789 = 순수 행동피처(크기·방향·IAT·window·retrans·payload + 통계·버스트·히스토그램·분위수). **SNI·IP·포트는 피처 아님, 라벨매칭·노이즈필터링에만 사용.**

## 2. 완료된 것 (성공)

1. **bias-variance 6모델×3 (통일 params, B=15)** → `03_json/bias_variance_results.json`. macro-F1: **LightGBM 최고**(Cipher 98.03 / CSTNET 88.89 / LAB 65.35). 단일→Bagging var 급감, Boosting bias·var 최저. CatBoost 최하(통일params 불리). 6모델=DT/RF/ET/LightGBM/XGBoost/CatBoost.
2. **CatBoost 튜닝 회복**: Optuna로 Cipher 93.5→97.4 → "열세=params 탓" 검증. → `03_json/boosting_best_params.json`(현재 Cipher만).
3. **추론속도 probe**: LightGBM predict가 XGBoost의 10배(leaf-wise 깊이 36% + predict 구현). depth6 캡하면 정확도 손해없이 1.5배↑. (`01_code/probe_lgbm_it.py`)
4. **노이즈 정의 확립 ⭐**: X:\data-8t\00_codes\noise_rule 규칙(De=CDN/SNI, Cc=제어, Cd=배경, DoH)을 seq meta에서 직접 재현(`scratchpad/seqmeta_noise.py`). **prism04 04파일과 교차검증: LAB 30.3% 일치.** **데이터셋 성격별**: 도메인분류(Cipher/CSTNET)=De 제외(SNI=정답)→노이즈≈0(원본=클린), 프로세스분류(LAB)=De 포함→30%.
5. **LAB week2 클린 BV** → `03_json/bias_variance_lab_pipeclean.json`. 노이즈(DNS/CDN 30%) 제거로 **macro-F1 +2.7~4.3, Acc +2.6~4.4, bias −3~5** 일관 상승. (5모델, CatBoost 제외)
6. **week3 데이터(2026.07.20~24) 추출+클린 BV**: 서버28 Week3 pcap 2.43M flow 추출(에러1)→dedup 2.27M·123클래스. 클린 BV → `03_json/bias_variance_week3_pipeclean.json`(79클래스). **week2 vs week3: 모델 순위·"LightGBM 최고" 재현됨**(LightGBM 주차차 −0.76로 가장 안정). 절대값 차이는 대부분 클래스수(65 vs 79) 차이.
7. **ISCX-VPN/Tor 추출**(에러0): `02_dataset/vpn2016_seq_100`(30.7만), `tor2016_seq_100`(4.4만). STTabNet용이었으나 폐기 — 데이터만 남음.
8. **산출물**: Notion `0811_ML`(업무관리 DB), 옵시디언 볼트 이식(`.claude/commands/기록.md`·`정리.md` + `CLAUDE.md` + `_notes/`), 분석 아티팩트(bias-variance 상세).

## 3. 실패 · 교훈 (반복 금지)

1. **STTabNet 다중분류 붕괴** — ISCX-VPN application macro-F1 11%(이진 encap만 65~94). 원인=pcap 수 부족(클래스당 1~4개)+pcap그룹분할이 클래스 굶김+극단불균형. → 폐기 결정.
2. **CatBoost GPU OOM** — 8GB VRAM에서 다중클래스(CSTNET 120·LAB) OOM(border32·Plain으로도). Cipher(42)만 GPU 성공. → CatBoost 튜닝은 Cipher만, CSTNET/LAB은 CPU 초저속이라 사실상 스킵.
3. **무거운 CPU 2개 동시 → 6시간 정지**. 순차 원칙.
4. **class≥10 필터를 노이즈 제거 "전" 개수로 계산 → stratify 크래시**("least populated class has 1 member"). 노이즈 빼면 1개 남는 클래스 생김. **고침**: 제거 후 개수로 계산(`bias_variance.py`·`tune_boosting.py` 둘 다).
5. **LAB seq ↔ prism04 filename 안 맞음** — 이름 체계 다름. → `(proto, 정렬 endpoints, ts_first)` **5-tuple+시각 조인 91% 매칭**으로 해결(`scratchpad/lab_join_noise.py`).
6. **De 규칙을 도메인 데이터셋에 쓰면 정답 삭제** — Cipher에 De(google SNI) 적용시 google.com 클래스 통째로 사라짐(42→36). 도메인분류는 De 제외해야 함.
7. **U: 로그 SMB 캐시 지연** — "멈췄다" 오진 2회. 서버 tail/ps로 확인.

## 4. 진행 중 (2026-08-12 시작)

**클린 데이터 부스팅 튜닝** — `01_code/run_tune_clean.sh`
```
cd /root/02_SGS/lab_dashboard_ver0.1 && BASE=$(pwd) N_JOBS=11 TRIALS=60 nohup bash 01_code/run_tune_clean.sh > 04_logs/tune_clean.out 2>&1 & disown
```
- 대상: **CSTNET(clean=원본, resume) + LAB week2 클린**(노이즈 제거, `LAB_NOISE_FILE=02_dataset/lab_seqmeta_noise_basenames.txt`, BV_SUB=200000).
- LightGBM(CPU) ∥ XGBoost(GPU device=cuda). **CatBoost 제외**(GPU OOM). Cipher는 이미 완료.
- 결과 `03_json/boosting_best_params.json` 병합. Optuna sqlite(`03_json/optuna_*.db`) resume.
- 확인: `tail -f 04_logs/tune_clean.out`, 초반 `[LAB] 노이즈 ...제거 ...행`·`tune rows=... trials=60` 뜨면 정상.

## 5. 다음 단계 (우선순위)

1. **클린 튜닝 완주** 대기 → **튜닝반영 BV 재실행**: `TUNED_PARAMS=03_json/boosting_best_params.json` 로 `bias_variance.py` 재실행(클린 데이터) → **"통일 params" vs "튜닝" 두 표** 비교. (`run_bv_tuned.sh` 참고, 노이즈·클린 반영 필요)
2. **주차간 공통클래스 통제비교** — week2·week3 공통 앱만 골라 같은 클래스셋으로 → 재현성 순수 측정(현재 65 vs 79로 통제 안 됨). 가벼움.
3. **교차 데이터셋 일반화** — 학습A→테스트B. 보편성 핵심 증거.
4. **5-fold 평균±std** — 엄밀성. 클래스셋 고정.
5. (선택) week3 튜닝, LAB 실앱전용(시스템프로세스 제외), 추론속도/메모리 배포 관점.

## 6. 핵심 파일 (기능·주요 env)

- `01_code/bias_variance.py` — BV 분해. env: `ONLY`(모델 필터), `TUNED_PARAMS`(튜닝값 반영), `BV_SUB`(서브샘플), `BV_B`(부트스트랩), `XGB_GPU=1`(XGBoost GPU), `LAB_LABEL_MAP`(라벨맵, week3용), `LAB_NOISE_FILE`(LAB basename 노이즈제거), `NOISE_FILE`(비-LAB), `LAB_EXCLUDE_FILE`/`LAB_COLLAPSE_FILE`(라벨 제외/background 묶기). **class≥10은 노이즈 제거 후 개수 기준(버그 수정됨).**
- `01_code/tune_boosting.py` — Optuna 튜닝. env: `XGB_GPU`, `CAT_GPU`, `ONLY`... `--models lightgbm,xgboost,catboost`, `--trials`. 노이즈필터 반영됨.
- `01_code/extract_pcap_seq_sni_v2.py` — pcap→seq789. `--label-depth`, `--timeout`(대용량), `--cap-packets`(-c, 초대용량), truncated pcap 파싱분 유지, errors.log.
- 러너: `run_tune_clean.sh`(클린튜닝), `run_week3_bv.sh`(week3 클린BV), `run_noise_bv.sh`(3데이터셋 노이즈BV), `run_bias_variance.sh`(원본BV).
- 노이즈 목록: `02_dataset/lab_seqmeta_noise_basenames.txt`(week2), `week3_seqmeta_noise_basenames.txt`, `lab_pipeline_noise_basenames.txt`(prism04조인, week2와 동등). `week3_label.csv`(week3 라벨맵). `lab_canon_label.csv`(week2 라벨맵).
- scratchpad(로컬): `seqmeta_noise.py`(노이즈목록 생성), `lab_join_noise.py`(prism04 5tuple조인), `noise_breakdown.py`(규칙별 집계), `0811_ML.md`, `bv_analysis.html`.

## 7. 데이터셋 상태

| 데이터셋 | seq 경로 | flow | 클래스 | 노이즈(파이프라인) |
|---|---|---|---|---|
| CipherSpectrum | `06_data/canonical_cipherspec_seq_v2` | 123,000 | 42(도메인) | ~0% (De=정답이라 제외) |
| CSTNET(tls) | `06_data/canonical_cstnet_seq` | 46,372 | 120(도메인) | ~0% |
| LAB week2 | `06_data/lab_full45_seq_v2_904k` | 146만→canon 87.9만 | 62~65(프로세스) | 30.3% (DNS/CDN/배경) |
| LAB week3 | `06_data/lab_week3_seq_100` | 243만→dedup 227만 | 123→클린79 | 30.7% |

- 노이즈 규칙별(LAB): **Cc_2 DNS(port53)가 압도적**(week2 28%·week3 23%), De google 2~3%, SMB, 브로드캐스트, DoH 0.3%.
- 원본 pcap: week2/3 LAB=서버28 `//RAID1/00_DATASET/23_PRISM_week/2026.07/Week2·Week3`. VPN/Tor·CSTNET·Cipher=서버99 `X:\data-8t`.

## 8. Notion / 옵시디언

- Notion `업무관리` DB(data_source `36d53f02-dc31-8003-b735-000bec9d01a1`) 날짜별 페이지. `0811_ML` 생성됨(유형=연구실, 상태=진행중).
- 옵시디언 볼트 = `_notes/`(서버17). `/기록`·`/정리` 명령 이식됨(`.claude/commands/`, `CLAUDE.md`). 허브=`_notes/02_SGS.md`. 07-29~08-11 기록 완료.
