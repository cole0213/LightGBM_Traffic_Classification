# Auto-label Threshold Sweep

- CSV: `/nmlab/99_sgs/lab_dashboard/static/datasets/lab0701_auto/session_stat_lab0701_auto.csv`
- Ground truth: `task3_folder`
- Model: `/nmlab/99_sgs/lab_dashboard/models/autolabel_model_candidate_0630_0701folder_0704_serverpy38.pkl`
- Classes: 101

| threshold | exact | normalized | normalized excl. unknown | unknown | coverage |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 93.19% | 93.3% | 93.3% | 0.0% | 100.0% |
| 0.10 | 93.19% | 93.3% | 93.3% | 0.0% | 100.0% |
| 0.20 | 93.19% | 93.3% | 93.31% | 0.01% | 99.99% |
| 0.30 | 93.16% | 93.26% | 93.37% | 0.11% | 99.89% |
| 0.40 | 92.73% | 92.81% | 93.82% | 1.08% | 98.92% |
| 0.50 | 91.17% | 91.21% | 94.97% | 3.96% | 96.04% |
| 0.60 | 88.16% | 88.18% | 96.42% | 8.54% | 91.46% |
| 0.70 | 83.8% | 83.81% | 97.5% | 14.04% | 85.96% |
| 0.80 | 77.11% | 77.12% | 98.42% | 21.64% | 78.36% |
| 0.90 | 62.96% | 62.96% | 99.46% | 36.7% | 63.3% |
| 0.95 | 49.29% | 49.29% | 99.82% | 50.62% | 49.38% |
