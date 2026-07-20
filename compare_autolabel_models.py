import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


UNKNOWN_ALIASES = {"미분류(자동)", "誘몃텇瑜??먮룞)"}


def canonical_label(value):
    s = "" if pd.isna(value) else str(value)
    s = s.strip()
    if s in UNKNOWN_ALIASES:
        return "__unknown__"
    s = s.lower()
    for suffix in (".exe",):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s.replace(" ", "_").replace("-", "_")


def summarize_model(autolabel, model_path, df, true_col, threshold):
    t0 = time.time()
    bundle = autolabel.load_bundle(model_path)
    pred = autolabel.predict_df(bundle, df)
    final = autolabel.apply_threshold(pred, threshold)
    elapsed = time.time() - t0

    y_true = df[true_col].astype(str)
    exact = final.astype(str).eq(y_true)
    y_can = y_true.map(canonical_label)
    p_can = final.map(canonical_label)
    norm = p_can.eq(y_can)
    not_unknown = p_can.ne("__unknown__")

    mismatches = Counter()
    for t, p in zip(y_true[~norm], final[~norm]):
        mismatches[(str(t), str(p))] += 1

    conf = pd.to_numeric(pred["pred_conf"], errors="coerce")
    return {
        "model_path": str(model_path),
        "classes": int(len(bundle.get("classes", []))),
        "meta": bundle.get("meta", {}),
        "threshold": threshold,
        "elapsed_sec": round(elapsed, 2),
        "total": int(len(df)),
        "exact_agree": int(exact.sum()),
        "exact_agree_pct": round(float(exact.mean() * 100), 2),
        "normalized_agree": int(norm.sum()),
        "normalized_agree_pct": round(float(norm.mean() * 100), 2),
        "normalized_agree_excluding_unknown_pct": round(float(norm[not_unknown].mean() * 100), 2)
        if int(not_unknown.sum())
        else None,
        "unknown": int((p_can == "__unknown__").sum()),
        "unknown_pct": round(float((p_can == "__unknown__").mean() * 100), 2),
        "mean_conf": round(float(conf.mean()), 4),
        "median_conf": round(float(conf.median()), 4),
        "p10_conf": round(float(conf.quantile(0.1)), 4),
        "p90_conf": round(float(conf.quantile(0.9)), 4),
        "top_mismatches": [
            {"true": t, "pred": p, "n": int(n)}
            for (t, p), n in mismatches.most_common(20)
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--true-col", default=None)
    ap.add_argument("--old-model", required=True)
    ap.add_argument("--new-model", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    project = Path(args.project)
    sys.path.insert(0, str(project))
    import autolabel

    df = pd.read_csv(args.csv, low_memory=False)
    true_col = args.true_col
    if not true_col:
        true_col = "task3_folder" if "task3_folder" in df.columns else "task3"
    if true_col not in df.columns:
        raise SystemExit(f"missing true column: {true_col}")

    result = {
        "csv": args.csv,
        "true_col": true_col,
        "threshold": args.threshold,
        "old": summarize_model(autolabel, args.old_model, df, true_col, args.threshold),
        "candidate": summarize_model(autolabel, args.new_model, df, true_col, args.threshold),
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Auto-label Model Comparison",
        "",
        f"- CSV: `{args.csv}`",
        f"- Ground truth column: `{true_col}`",
        f"- Threshold: `{args.threshold}`",
        "",
        "| model | classes | exact | normalized | normalized excl. unknown | unknown | mean conf | elapsed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("old", "current"), ("candidate", "candidate")):
        r = result[key]
        lines.append(
            f"| {label} | {r['classes']} | {r['exact_agree_pct']}% | "
            f"{r['normalized_agree_pct']}% | {r['normalized_agree_excluding_unknown_pct']}% | "
            f"{r['unknown_pct']}% | {r['mean_conf']} | {r['elapsed_sec']}s |"
        )
    lines += ["", "## Top Candidate Mismatches", ""]
    for item in result["candidate"]["top_mismatches"][:15]:
        lines.append(f"- `{item['true']}` -> `{item['pred']}`: {item['n']:,}")
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "old_normalized": result["old"]["normalized_agree_pct"],
        "candidate_normalized": result["candidate"]["normalized_agree_pct"],
        "out_json": args.out_json,
        "out_md": args.out_md,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
