# Auto-label Threshold Sweep

- CSV: `/nmlab/99_sgs/lab_dashboard/static/datasets/lab0701_auto/session_stat_lab0701_auto.csv`
- Ground truth: `task3_folder`
- Model: `/nmlab/99_sgs/lab_dashboard/models/autolabel_model_candidate_0630_0704_full_serverpy38.pkl`
- Classes: 90

| threshold | exact | normalized | normalized excl. unknown | unknown | coverage |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 79.38% | 80.4% | 80.4% | 0.0% | 100.0% |
| 0.10 | 79.38% | 80.4% | 80.4% | 0.0% | 100.0% |
| 0.20 | 79.38% | 80.4% | 80.43% | 0.03% | 99.97% |
| 0.30 | 79.33% | 80.34% | 80.6% | 0.32% | 99.68% |
| 0.40 | 78.88% | 79.83% | 81.44% | 1.98% | 98.02% |
| 0.50 | 77.25% | 78.02% | 83.1% | 6.11% | 93.89% |
| 0.60 | 74.03% | 74.56% | 85.73% | 13.03% | 86.97% |
| 0.70 | 70.15% | 70.5% | 88.22% | 20.08% | 79.92% |
| 0.80 | 64.34% | 64.57% | 90.68% | 28.8% | 71.2% |
| 0.90 | 53.0% | 53.12% | 93.67% | 43.29% | 56.71% |
| 0.95 | 42.47% | 42.53% | 95.56% | 55.5% | 44.5% |
