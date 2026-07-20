# Auto-label Model Comparison

- CSV: `/nmlab/99_sgs/lab_dashboard/static/datasets/lab0701_auto/session_stat_lab0701_auto.csv`
- Ground truth column: `task3_folder`
- Threshold: `0.5`

| model | classes | exact | normalized | normalized excl. unknown | unknown | mean conf | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 90 | 77.25% | 78.02% | 83.1% | 6.11% | 0.8514 | 41.03s |
| candidate | 90 | 77.25% | 78.02% | 83.1% | 6.11% | 0.8514 | 37.6s |

## Top Candidate Mismatches

- `svchost.exe` -> `chrome.exe`: 2,072
- `Visual_Studio` -> `Visual_Studio_Code`: 1,265
- `chrome.exe` -> `svchost.exe`: 1,248
- `svchost.exe` -> `미분류(자동)`: 1,132
- `chrome.exe` -> `미분류(자동)`: 1,119
- `Codex.exe` -> `미분류(자동)`: 986
- `svchost.exe` -> `Notion`: 888
- `Visual_Studio` -> `svchost.exe`: 878
- `Notion` -> `svchost.exe`: 783
- `Codex.exe` -> `svchost.exe`: 707
- `Visual_Studio` -> `미분류(자동)`: 658
- `NVIDIA_App` -> `미분류(자동)`: 557
- `svchost.exe` -> `Visual_Studio`: 480
- `msedgewebview2.exe` -> `미분류(자동)`: 439
- `NVIDIA_App` -> `svchost.exe`: 412
