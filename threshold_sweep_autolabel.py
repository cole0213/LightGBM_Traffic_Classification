import argparse
import json
import sys
from pathlib import Path

import pandas as pd


UNKNOWN_ALIASES = {"미분류(자동)", "誘몃텇瑜??먮룞)"}


def canonical_label(value):
    s = "" if pd.isna(value) else str(value)
    s = s.strip()
    if s in UNKNOWN_ALIASES:
        return "__unknown__"
    s = s.lower()
    if s.endswith(".exe"):
        s = s[:-4]
    return s.replace(" ", "_").replace("-", "_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--true-col", default="task3")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args()

    sys.path.insert(0, args.project)
    import autolabel

    df = pd.read_csv(args.csv, low_memory=False)
    true = df[args.true_col].astype(str)
    true_can = true.map(canonical_label)
    bundle = autolabel.load_bundle(args.model)
    pred = autolabel.predict_df(bundle, df)

    rows = []
    for tau in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
        final = autolabel.apply_threshold(pred, tau) if tau > 0 else pred["pred_label"]
        pred_can = final.map(canonical_label)
        exact = final.astype(str).eq(true)
        norm = pred_can.eq(true_can)
        not_unknown = pred_can.ne("__unknown__")
        rows.append({
            "threshold": tau,
            "exact_pct": round(float(exact.mean() * 100), 2),
            "normalized_pct": round(float(norm.mean() * 100), 2),
            "normalized_excluding_unknown_pct": round(float(norm[not_unknown].mean() * 100), 2)
            if int(not_unknown.sum())
            else None,
            "unknown_pct": round(float(pred_can.eq("__unknown__").mean() * 100), 2),
            "coverage_pct": round(float(not_unknown.mean() * 100), 2),
        })

    out = {
        "csv": args.csv,
        "true_col": args.true_col,
        "model": args.model,
        "classes": len(bundle.get("classes", [])),
        "rows": rows,
    }
    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Auto-label Threshold Sweep",
        "",
        f"- CSV: `{args.csv}`",
        f"- Ground truth: `{args.true_col}`",
        f"- Model: `{args.model}`",
        f"- Classes: {out['classes']}",
        "",
        "| threshold | exact | normalized | normalized excl. unknown | unknown | coverage |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['threshold']:.2f} | {r['exact_pct']}% | {r['normalized_pct']}% | "
            f"{r['normalized_excluding_unknown_pct']}% | {r['unknown_pct']}% | {r['coverage_pct']}% |"
        )
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
