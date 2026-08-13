# 디렉터리 구조 (2026-08-13 재정리)

연구 방향이 트리앙상블(LightGBM) + 노이즈 정제 + 일반화로 확정되면서, 흩어진 데이터·미사용 코드를 대거 정리했다. (이전 2026-08-01 정리를 대체.)

```
lab_dashboard_ver0.1/            # ← 예정: 01_MachineLearning 으로 이름 변경 (LAB 튜닝 job 완주 후)
├─ 01_code/        # 현재 쓰는 코드만 17개 (연구핵심 4 + 러너 10 + 대시보드 3)
├─ 02_dataset/     # 라벨맵·노이즈 basename 목록·클래스 리스트 (txt/csv)
├─ 03_json/        # 결과·튜닝 json + optuna sqlite(*.db, git 제외)
├─ 04_logs/        # 실행 로그 (*.out/*.log, git 제외)
├─ 05_docs/        # 스터디·실험 문서 .md
├─ 06_data/        # 연구 데이터 (seq789 · canonical) — 대용량, git 제외
│   ├─ canonical_cipherspec_seq_v2/   # CipherSpectrum (도메인 42)
│   ├─ canonical_cstnet_seq/          # CSTNET (앱 120)
│   ├─ canonical_inputs/
│   ├─ lab_full45_seq_v2_904k/        # LAB week2 seq789
│   └─ lab_week3_seq_100/             # LAB week3 seq789
├─ 07_app/         # 대시보드 런타임 — git 제외
│   ├─ models/     # 학습 모델 .pkl
│   ├─ static/     # Flask 웹 자산
│   └─ tools/      # ja4_official 등 외부 도구
└─ 99_trash_20260813/  # 미사용 아카이브 (되돌리기 가능, 하드삭제 보류)
    ├─ 01_code_dead/   # 미사용 스크립트 111개 (STTabNet 폐기분·ablation·smoke·구버전)
    └─ (구버전 데이터·smoke·tmp·STTabNet 산출물 폴더들)
```

## 01_code 유지 목록 (17)

- 연구핵심: `bias_variance.py` `tune_boosting.py` `extract_pcap_seq_sni_v2.py` `probe_lgbm_it.py`
- 러너: `run_tune_clean.sh`(현 튜닝 job) `run_bias_variance.sh` `run_bv_tuned.sh` `run_noise_bv.sh` `run_week3_bv.sh` `run_week_bv.sh` `run_catboost_bv.sh` `run_lab_noise.sh` `run_tune_boosting.sh` `run_tune_xgbgpu.sh`
- 대시보드: `app.py` `autolabel.py` `pipeline.py`

## 폴더 이동에 따른 경로 패치 (2026-08-13)

데이터를 `06_data/`, 대시보드 런타임을 `07_app/`로 옮기며 유지 코드의 참조를 일괄 갱신했다.

- 러너 10개(.sh): `$BASE/<datadir>` → `$BASE/06_data/<datadir>` (canonical_*, lab_full45_seq_v2_904k, lab_week3_seq_100).
- `app.py` `autolabel.py` `pipeline.py`: `BASE_DIR / "models"|"static"` → `BASE_DIR / "07_app" / ...`.
- `bias_variance.py` `tune_boosting.py`는 seq 경로를 인자로 받으므로(러너가 전달) 자체 수정 불필요.
- 유지 코드는 전부 상대 기준(`BASE=$(pwd)`, `BASE_DIR=Path(__file__).parent.parent`)만 쓴다. 절대 서버경로(`/nmlab/...`, `/root/02_SGS/lab_dashboard_ver0.1`)를 박아둔 스크립트는 전부 미사용이라 `99_trash_20260813/01_code_dead/`로 이동됨.

## 이름 변경 예정 (lab_dashboard_ver0.1 → 01_MachineLearning)

- 유지 코드가 전부 상대경로라 **폴더명 변경 시 코드 수정은 필요 없다** (새 위치에서 실행하면 `pwd`/`__file__`이 자동 반영).
- 이름이 박힌 곳은 문서·주석뿐: 이 파일, `HANDOFF.md`, `05_docs/*`, `app.py`/`pipeline.py` 주석, `.agents/AGENTS.md` — 리네임 시 함께 갱신.
- **실행 중인 LAB 튜닝 job의 작업 디렉터리라, job 완주 후 이름 변경** (optuna sqlite 경로 재열림·SMB open-file 충돌 위험 회피). optuna 스터디는 resume 가능(`load_if_exists`)이라 최악의 경우도 재실행으로 복구.

## git 버전 관리 (2026-08-13 시작)

- 저장소: `github.com/cole0213/LightGBM_Traffic_Classification` (origin/master).
- `.gitignore`: 대용량·런타임 제외 — `06_data/` `07_app/` `04_logs/` `99_trash_20260813/` `*.db` `*.out` `*.pkl` `*.csv` `*basenames*.txt` 등. 코드·문서·결과 json만 버전관리.
- `.gitattributes`: `* text=auto eol=lf` — 서버(Linux) 실행 스크립트의 CRLF 오염 방지.
- 커밋·push는 `/commit` 커맨드(수동 트리거)로.
