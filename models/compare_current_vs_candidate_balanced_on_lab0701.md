# Auto-label Model Comparison

- CSV: `Z:\nmlab\99_sgs\lab_dashboard\static\datasets\lab0701_auto\session_stat_lab0701_auto.csv`
- Ground truth column: `task3_folder`
- Threshold: `0.5`

| model | classes | exact | normalized | normalized excl. unknown | unknown | mean conf | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 83 | 82.67% | 82.7% | 86.14% | 3.99% | 0.8756 | 50.28s |
| candidate | 90 | 35.52% | 36.36% | 50.35% | 27.79% | 0.6792 | 31.94s |

## Top Candidate Mismatches

- `chrome.exe` -> `미분류(자동)`: 16,697
- `svchost.exe` -> `미분류(자동)`: 9,827
- `svchost.exe` -> `msedgewebview2.exe`: 5,861
- `svchost.exe` -> `NVIDIA_App`: 4,959
- `chrome.exe` -> `msedgewebview2.exe`: 3,121
- `chrome.exe` -> `unknown`: 1,967
- `svchost.exe` -> `Visual_Studio`: 1,639
- `svchost.exe` -> `codex.exe`: 1,589
- `Codex.exe` -> `미분류(자동)`: 1,318
- `Visual_Studio` -> `Visual_Studio_Code`: 1,283
- `chrome.exe` -> `msedge.exe`: 1,263
- `svchost.exe` -> `Notion`: 1,198
- `svchost.exe` -> `ChatGPT`: 1,012
- `Visual_Studio` -> `미분류(자동)`: 899
- `svchost.exe` -> `Genspark_Claw`: 851
