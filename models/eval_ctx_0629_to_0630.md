# 자동 라벨링 교차일 평가
- 학습: V:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0629\session_stat_lab0629.csv
- 평가: V:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0630\session_stat_lab0630.csv
- 실행: 2026-07-06 12:46:42

학습 127,754세션 / 평가 134,960세션
평가 세션 중 학습에서 본 클래스: 99.96% (예측 상한)

[train] 세션 127,754 → 학습대상 127,685 (클래스 73개, 희소 제외 35개/69세션)
[train] 완료 50s · best_iteration=303 · 클래스 73개
[predict] 134,960세션 20s

## 종합 결과
| 방법 | 정확도 |
|---|---|
| 다수결(chrome.exe) | 34.32% |
| 룩업 규칙(SNI→DNS→IP→포트) | 76.86% |
| **ML(LightGBM)** | **83.18%** |
| ML top-3 | 96.62% |
- macro-F1 = 0.3350 · weighted-F1 = 0.8270

## 문자열 피처 유무별 정확도
- SNI 있음: 84.71%  (n=58,113)
- DNS만: 81.50%  (n=67,396)
- 문자열 없음: 85.75%  (n=9,451)

## 신뢰도 임계값별 커버리지/정확도 (미분류 처리 설계용)
| 임계 τ | 커버리지 | 커버 세션 정확도 |
|---|---|---|
| 0.00 | 100.0% | 83.18% |
| 0.30 | 99.8% | 83.32% |
| 0.50 | 95.7% | 85.08% |
| 0.70 | 85.2% | 88.68% |
| 0.80 | 78.0% | 90.38% |
| 0.90 | 64.9% | 92.43% |
| 0.95 | 51.4% | 94.27% |

## 클래스별 성능 (평가셋 지원수 상위 30)
| 클래스 | n | recall | precision |
|---|---|---|---|
| chrome.exe | 46,321 | 91.6% | 85.4% |
| svchost.exe | 42,012 | 83.5% | 86.1% |
| Notion | 6,464 | 87.8% | 79.3% |
| Codex.exe | 5,604 | 56.4% | 73.5% |
| System | 5,145 | 81.2% | 76.8% |
| Visual_Studio | 4,524 | 77.5% | 71.7% |
| msedgewebview2.exe | 2,940 | 52.8% | 62.2% |
| NVIDIA_App | 2,553 | 79.0% | 80.7% |
| Claude | 2,426 | 77.1% | 74.9% |
| Parsec | 2,022 | 99.9% | 99.8% |
| RiotClient | 1,947 | 93.4% | 94.4% |
| msedge.exe | 1,892 | 79.3% | 77.2% |
| Discord | 1,414 | 70.7% | 67.9% |
| Genspark_Claw | 1,374 | 60.6% | 74.3% |
| NexonPlug | 1,369 | 83.7% | 94.4% |
| ChatGPT | 1,146 | 86.6% | 82.4% |
| Microsoft_OneDrive | 822 | 78.8% | 79.6% |
| MpDefenderCoreService.exe | 721 | 90.0% | 85.3% |
| FC_ONLINE | 696 | 59.3% | 83.1% |
| MoUsoCoreWorker.exe | 640 | 3.4% | 51.2% |
| Microsoft_Office | 617 | 48.8% | 67.2% |
| codex.exe | 455 | 91.6% | 94.3% |
| ASD_Framework | 167 | 97.0% | 99.4% |
| backgroundTaskHost.exe | 165 | 79.4% | 87.3% |
| League_of_Legends | 161 | 28.0% | 63.4% |
| Microsoft_Intune | 136 | 80.1% | 85.8% |
| Microsoft_Teams | 130 | 79.2% | 94.5% |
| Chrome_원격_데스크톱 | 128 | 60.2% | 85.6% |
| Microsoft_365_Copilot | 94 | 72.3% | 86.1% |
| WORKS.exe | 77 | 93.5% | 100.0% |

## 주요 혼동쌍 (true → pred, 상위 15)
- svchost.exe → chrome.exe: 3,137
- chrome.exe → svchost.exe: 2,058
- svchost.exe → Notion: 1,232
- Codex.exe → svchost.exe: 963
- Codex.exe → chrome.exe: 892
- svchost.exe → Visual_Studio: 842
- msedgewebview2.exe → chrome.exe: 653
- Visual_Studio → svchost.exe: 553
- svchost.exe → Codex.exe: 501
- Notion → svchost.exe: 482
- chrome.exe → msedgewebview2.exe: 426
- msedgewebview2.exe → svchost.exe: 416
- chrome.exe → Codex.exe: 400
- Genspark_Claw → chrome.exe: 372
- MoUsoCoreWorker.exe → chrome.exe: 337
