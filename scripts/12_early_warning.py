import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from xray.evaluation.early_warning import compare_alarms, render_markdown
from xray.io import read_cleaned
from xray.paths import PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Compara alertas tempranas (score, caja y combinaciones) con el protocolo de D41.")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--horizon", type=int, default=6)
    args = parser.parse_args()
    features = pd.read_parquet(args.features_dir / "company_monthly_features.parquet", columns=["company_id", "group_id", "month", "tx_count", "tx_inflow", "debt_principal_paid", "debt_interest_paid"])
    scores = pd.read_parquet(args.features_dir / "scores_v2" / "company_monthly_scores.parquet",
                             columns=["company_id", "month", "momentum_z"])
    liquidity = pd.read_parquet(args.features_dir / "company_currency_liquidity_context.parquet",
                                columns=["company_id", "month", "reconstructed_cash", "cash_runway_months_retrospective"])
    tx = read_cleaned("transactions")[["company_id", "date", "status", "event_type", "is_sync_duplicate"]]
    report = compare_alarms(tx, features, scores, liquidity, horizon=args.horizon)
    out = args.out_dir or args.features_dir / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "early_warning.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = render_markdown(report)
    (out / "early_warning.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"JSON: {out / 'early_warning.json'}")


if __name__ == "__main__":
    main()
