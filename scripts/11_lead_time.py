import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from xray.evaluation.lead_time import lead_time_report, render_markdown
from xray.io import read_cleaned
from xray.paths import PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Anticipación medida de V2 frente a eventos de estrés propio (D41).")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--horizon", type=int, default=6)
    args = parser.parse_args()
    features = pd.read_parquet(args.features_dir / "company_monthly_features.parquet", columns=["company_id", "month", "tx_count"])
    scores = pd.read_parquet(args.features_dir / "scores_v2" / "company_monthly_scores.parquet")
    tx = read_cleaned("transactions")[["company_id", "date", "status", "event_type", "is_sync_duplicate"]]
    report, leads = lead_time_report(tx, features, scores, horizon=args.horizon)
    out = args.out_dir or args.features_dir / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "lead_time.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    leads.to_parquet(out / "lead_time_events.parquet", index=False)
    md = render_markdown(report)
    (out / "lead_time.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"JSON: {out / 'lead_time.json'}")


if __name__ == "__main__":
    main()
