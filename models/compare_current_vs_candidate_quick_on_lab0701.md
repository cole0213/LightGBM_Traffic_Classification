# Auto-label Model Comparison

- CSV: `Z:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0701_auto\session_stat_lab0701_auto.csv`
- Ground truth column: `task3_folder`
- Threshold: `0.5`

| model | classes | exact | normalized | normalized excl. unknown | unknown | mean conf | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 83 | 82.67% | 82.7% | 86.14% | 3.99% | 0.8756 | 130.31s |
| candidate | 60 | 65.21% | 66.11% | 83.48% | 20.81% | 0.7297 | 2.12s |

## Top Candidate Mismatches

- `svchost.exe` -> `미분류(자동)`: 4,975
- `chrome.exe` -> `미분류(자동)`: 3,738
- `Codex.exe` -> `미분류(자동)`: 2,979
- `svchost.exe` -> `chrome.exe`: 2,590
- `Visual_Studio` -> `미분류(자동)`: 2,304
- `NVIDIA_App` -> `미분류(자동)`: 1,477
- `System` -> `미분류(자동)`: 1,222
- `msedgewebview2.exe` -> `미분류(자동)`: 1,215
- `Claude` -> `미분류(자동)`: 1,154
- `svchost.exe` -> `Notion`: 990
- `Visual_Studio` -> `Visual_Studio_Code`: 836
- `svchost.exe` -> `codex.exe`: 832
- `Notion` -> `미분류(자동)`: 804
- `msedge.exe` -> `미분류(자동)`: 692
- `Visual_Studio` -> `svchost.exe`: 571
