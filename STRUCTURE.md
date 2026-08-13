# 디렉터리 구조 (2026-08-01 정리)

lab_dashboard_ver0.1 코드/데이터 재구성 결과. 루트의 흩어진 파일 200여 개를 용도별 폴더로 분리했다.

```
lab_dashboard_ver0.1/
├─ 01_code/        # 모든 .py / .sh / .ps1 / .bat  (104개)
├─ 02_dataset/     # 루트에 있던 결과 csv / txt 스냅샷
├─ 03_json/        # 모든 결과·설정 json (38개)
├─ 04_logs/        # 실행 로그 .log / .pid / .stdout (67개)
├─ 05_docs/        # 스터디·클래스 문서 .md
├─ _trash_20260801/# .bak 백업 5개 (삭제 보류, 확인 후 제거)
│
│   ── 아래는 "코드가 절대 서버경로(/nmlab/...)로 참조" + 용량 때문에 루트 유지 ──
├─ models/         # 학습 모델 .pkl (906MB)  ← app/autolabel/pipeline 이 참조
├─ static/         # Flask 대시보드 웹 자산 (app.js, dashboard.html ...)
├─ tools/          # ja4_official 등 외부 도구
├─ canonical_*/    # canonical seq789 실험 입출력 (진행 중이던 작업)
├─ cstnet_seq_*/   # CSTNET 시퀀스 추출 산출물
├─ lab_full45_seq_v2*/ # LAB seq789 평가 (가장 최근 작업)
├─ canonical_inputs/
└─ CANONICAL_EXPERIMENT_STATUS.md  # 실험 진행 상태 (루트 유지)
```

## 코드 이동에 따른 경로 패치

코드를 `01_code/`로 옮기면서, 데이터·모델·static 을 참조하는 핵심 3파일의 경로 기준을
프로젝트 루트로 재조정했다 (`Path(__file__).parent` → 루트).

- `01_code/app.py` : `CODE_DIR`(01_code) / `BASE_DIR`(루트) 분리. static·models 는 루트, pipeline.py 는 01_code.
- `01_code/autolabel.py`, `01_code/pipeline.py` : `BASE_DIR = ...parent.parent` (루트) → models·static 정상 참조.
- `01_code/backfill_sizes.py` : `sys.path` 를 자기 폴더(01_code)에 추가 → `import pipeline` 유지 (수정 불필요).

절대 서버경로(`/nmlab/99_sgs/03_ML/lab_dashboard_ver0.1/...`)를 쓰는 스크립트 14개와
CWD 기준으로 결과를 쓰는 스크립트들은 이동 영향 없음. 서로 간 `import autolabel/pipeline`
도 모두 `01_code/` 안 형제 파일이라 그대로 동작.

## 주의 (알려진 잔여 사항)

- `01_code/poll_*.sh`, `watchdog_*.sh` 는 종료된 실행의 로그를 옛 이름(`lab_seq.log` 등)으로
  tail 한다. 로그가 `04_logs/`로 이동해 그대로는 못 찾지만, 해당 실행은 이미 끝난 편의 스크립트라
  기능상 문제 없음. 재사용 시 `04_logs/` 경로로 고쳐 쓰면 된다.
- 결과 json 을 CWD 에 쓰는 스크립트는 재실행 시 실행 위치에 새 json 을 만든다. 과거 스냅샷은
  `03_json/`에 보관됨.
- 데이터 폴더(models/canonical_*/...)는 서버 실행 경로와 desync 를 피하려 **이동하지 않았다**.
