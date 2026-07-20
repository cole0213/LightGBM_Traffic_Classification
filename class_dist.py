import sys, csv, json, collections
sys.path.append('/nmlab/99_sgs/03_ML/lab_dashboard_demo')
import pipeline
csv.field_size_limit(10**7)

raw = collections.Counter()
for mmdd in ['0710', '0711', '0712', '0713', '0714']:
    f = f'/nmlab/99_sgs/01_datasets/2026.07.{mmdd[2:]}/session_stat_lab{mmdd}.csv'
    with open(f, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            t = str(row.get('task3') or '').strip()
            if t:
                raw[t] += 1
    print(f"  scanned {mmdd}", flush=True)

# 학습과 동일한 표시명 정규화 적용
dmap = pipeline.build_app_display_map(list(raw.keys()))
norm = collections.Counter()
for lab, c in raw.items():
    norm[dmap.get(lab, lab)] += c

total = sum(norm.values())
items = norm.most_common()
print(f"\n총 세션(라벨 보유): {total:,}", flush=True)
print(f"정규화 후 클래스 수: {len(items)}", flush=True)

# JSON으로 저장(리포트 주입용)
out = [{"app": k, "sessions": v, "pct": round(v / total * 100, 3)} for k, v in items]
with open('/nmlab/99_sgs/01_datasets/_class_dist.json', 'w', encoding='utf-8') as f:
    json.dump({"total": total, "n_classes": len(items), "classes": out}, f, ensure_ascii=False, indent=1)
print("SAVED /nmlab/99_sgs/01_datasets/_class_dist.json", flush=True)
# 상위 30 미리보기
for k, v in items[:30]:
    print(f"  {k:<30}{v:>10,}  {v/total*100:5.2f}%", flush=True)
print("DONE_CLASSDIST", flush=True)
