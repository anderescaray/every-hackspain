import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from xray.product.monitor import build_monitor, monitor_report
from xray.paths import PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Monitor de alertas del último cierre (D44).")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--month", type=str)
    args = parser.parse_args()
    features = pd.read_parquet(args.features_dir / "company_monthly_features.parquet",
                               columns=["company_id", "group_id", "month", "tx_inflow", "debt_principal_paid", "debt_interest_paid"])
    scores = pd.read_parquet(args.features_dir / "scores_v2" / "company_monthly_scores.parquet",
                             columns=["company_id", "month", "score", "trajectory", "episode", "delta_vs_prev"])
    alerts = build_monitor(features, scores, args.month)
    month = alerts.month.iloc[0] if len(alerts) else (args.month or features.month.max())
    report = monitor_report(alerts, month)
    out = args.out_dir or args.features_dir / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    alerts.to_parquet(out / "alerts.parquet", index=False)
    (out / "alerts.json").write_text(json.dumps({"report": report, "alerts": json.loads(alerts.to_json(orient="records", date_format="iso"))},
                                                indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if len(alerts):
        top = alerts.head(8)[["company_id", "alert", "severity", "streak_months", "score", "trajectory"]]
        print("\nPrimeras alertas por severidad:")
        print(top.to_string(index=False))
    print(f"\n-> {out / 'alerts.parquet'}")


if __name__ == "__main__":
    main()
