import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def load_with_truth(autolabel, csv_path, truth_col):
    df = autolabel.load_csv(csv_path)
    if truth_col:
        if truth_col not in df.columns:
            raise SystemExit(f"{csv_path}: missing truth column {truth_col}")
        df["task3"] = df[truth_col].astype(str)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--meta-json", required=True)
    ap.add_argument("--min-class-n", type=int, default=5)
    ap.add_argument(
        "--csv",
        action="append",
        required=True,
        help="CSV spec: path or path::truth_col. If truth_col is provided, it replaces task3.",
    )
    args = ap.parse_args()

    sys.path.insert(0, args.project)
    import autolabel

    dfs = []
    specs = []
    for spec in args.csv:
        if "::" in spec:
            path, truth_col = spec.split("::", 1)
        else:
            path, truth_col = spec, ""
        df = load_with_truth(autolabel, path, truth_col)
        dfs.append(df)
        specs.append({
            "path": path,
            "truth_col": truth_col or "task3",
            "sessions": int(len(df)),
            "classes": int(df["task3"].nunique()),
        })

    train_df = pd.concat(dfs, ignore_index=True)
    bundle = autolabel.train_model(train_df, min_class_n=args.min_class_n, quick=False)
    bundle["meta"]["train_csvs"] = [s["path"] for s in specs]
    bundle["meta"]["truth_specs"] = specs
    bundle["meta"]["source_sessions"] = int(len(train_df))
    bundle["meta"]["source_classes"] = int(train_df["task3"].nunique())
    autolabel.save_bundle(bundle, args.out)
    Path(args.meta_json).write_text(json.dumps(bundle["meta"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "out": args.out,
        "sessions": bundle["meta"]["source_sessions"],
        "classes": bundle["meta"]["source_classes"],
        "model_classes": bundle["meta"]["n_classes"],
        "best_iteration": bundle["meta"]["best_iteration"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
