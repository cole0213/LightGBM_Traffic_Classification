# 자동 라벨링 교차일 평가
- 학습: V:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0629\session_stat_lab0629.csv
- 평가: V:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0630\session_stat_lab0630.csv
- 실행: 2026-07-06 01:13:23  (--quick 모드)

학습 127,754세션 / 평가 134,960세션
평가 세션 중 학습에서 본 클래스: 99.96% (예측 상한)

[train] 세션 127,754 → 학습대상 127,685 (클래스 73개, 희소 제외 35개/69세션)
[train] --quick: 20,000 세션 서브샘플
[train] 1개 남은 클래스 4개 제외 → 19,996세션
[train] 완료 1s · best_iteration=2 · 클래스 65개
[predict] 134,960세션 0s

## 종합 결과
| 방법 | 정확도 |
|---|---|
| 다수결(chrome.exe) | 34.32% |
| 룩업 규칙(SNI→DNS→IP→포트) | 76.86% |
| **ML(LightGBM)** | **69.94%** |
| ML top-3 | 90.72% |
- macro-F1 = 0.1515 · weighted-F1 = 0.7156

## 문자열 피처 유무별 정확도
- SNI 있음: 67.07%  (n=58,113)
- DNS만: 74.09%  (n=67,396)
- 문자열 없음: 57.95%  (n=9,451)

## 신뢰도 임계값별 커버리지/정확도 (미분류 처리 설계용)
| 임계 τ | 커버리지 | 커버 세션 정확도 |
|---|---|---|
| 0.00 | 100.0% | 69.94% |
| 0.30 | 97.6% | 70.90% |
| 0.50 | 73.2% | 74.52% |
| 0.70 | 20.7% | 45.58% |
| 0.80 | 18.0% | 43.87% |
| 0.90 | 15.9% | 42.70% |
| 0.95 | 14.4% | 41.87% |

## 클래스별 성능 (평가셋 지원수 상위 30)
| 클래스 | n | recall | precision |
|---|---|---|---|
| chrome.exe | 46,321 | 80.1% | 78.0% |
| svchost.exe | 42,012 | 78.1% | 84.5% |
| Notion | 6,464 | 78.2% | 76.9% |
| Codex.exe | 5,604 | 34.9% | 64.1% |
| System | 5,145 | 43.2% | 61.7% |
| Visual_Studio | 4,524 | 67.5% | 68.8% |
| msedgewebview2.exe | 2,940 | 20.2% | 48.2% |
| NVIDIA_App | 2,553 | 56.3% | 63.7% |
| Claude | 2,426 | 65.0% | 61.7% |
| Parsec | 2,022 | 83.3% | 98.7% |
| RiotClient | 1,947 | 52.4% | 86.2% |
| msedge.exe | 1,892 | 47.5% | 61.5% |
| Discord | 1,414 | 64.6% | 66.5% |
| Genspark_Claw | 1,374 | 44.9% | 69.5% |
| NexonPlug | 1,369 | 51.6% | 67.1% |
| ChatGPT | 1,146 | 77.6% | 51.2% |
| Microsoft_OneDrive | 822 | 50.9% | 43.0% |
| MpDefenderCoreService.exe | 721 | 56.2% | 48.7% |
| FC_ONLINE | 696 | 43.7% | 22.0% |
| MoUsoCoreWorker.exe | 640 | 0.2% | 0.1% |
| Microsoft_Office | 617 | 36.6% | 18.9% |
| codex.exe | 455 | 16.0% | 37.4% |
| ASD_Framework | 167 | 71.3% | 30.5% |
| backgroundTaskHost.exe | 165 | 21.8% | 9.9% |
| League_of_Legends | 161 | 10.6% | 2.4% |
| Microsoft_Intune | 136 | 40.4% | 9.1% |
| Microsoft_Teams | 130 | 13.8% | 2.3% |
| Chrome_원격_데스크톱 | 128 | 43.8% | 15.1% |
| Microsoft_365_Copilot | 94 | 1.1% | 0.3% |
| WORKS.exe | 77 | 58.4% | 21.6% |

## 주요 혼동쌍 (true → pred, 상위 15)
- svchost.exe → chrome.exe: 3,513
- chrome.exe → svchost.exe: 2,139
- Codex.exe → chrome.exe: 1,817
- msedgewebview2.exe → chrome.exe: 1,112
- svchost.exe → Notion: 1,050
- svchost.exe → Visual_Studio: 797
- Codex.exe → svchost.exe: 790
- Visual_Studio → svchost.exe: 539
- svchost.exe → Codex.exe: 522
- NVIDIA_App → chrome.exe: 512
- Notion → svchost.exe: 490
- Genspark_Claw → chrome.exe: 417
- chrome.exe → FC_ONLINE: 412
- Visual_Studio → chrome.exe: 408
- chrome.exe → NVIDIA_App: 385
