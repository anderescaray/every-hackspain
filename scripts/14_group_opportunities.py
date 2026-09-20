import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from xray.fx import to_eur
from xray.io import read_cleaned
from xray.paths import PROCESSED_DIR
from xray.product.group_opportunities import (netting_opportunities, opportunities_report, overdraft_coincidence,
                                              pooling_opportunities, render_markdown, unused_credit_opportunities)


def main():
    parser = argparse.ArgumentParser(description="Oportunidades de tesorería intragrupo medidas sobre datos reales (D47).")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    companies = read_cleaned("companies")[["company_id", "group_id"]]
    tx = read_cleaned("transactions")
    tx["amount_eur"] = to_eur(tx.amount.astype(float), tx.product_currency)
    liquidity = pd.read_parquet(args.features_dir / "company_currency_liquidity_context.parquet",
                                columns=["company_id", "month", "reconstructed_cash", "reconstruction_coverage"])
    debt = pd.read_parquet(args.features_dir / "debt_snapshot_context.parquet")
    pooling = pooling_opportunities(liquidity, companies, tx)
    netting = netting_opportunities(tx, companies)
    credit = unused_credit_opportunities(debt, liquidity, companies)
    overdrafts = overdraft_coincidence(tx, liquidity, companies)
    cost = -tx.loc[tx.event_type.eq("descubierto") & tx.amount_eur.lt(0), "amount_eur"].sum()
    report = opportunities_report(pooling, netting, credit, overdrafts, cost)
    out = args.out_dir or args.features_dir / "group_opportunities"
    out.mkdir(parents=True, exist_ok=True)
    pooling.to_parquet(out / "cash_pooling.parquet", index=False)
    netting.to_parquet(out / "netting.parquet", index=False)
    credit.to_parquet(out / "unused_credit.parquet", index=False)
    overdrafts.to_parquet(out / "overdrafts.parquet", index=False)
    (out / "group_opportunities.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = render_markdown(report)
    (out / "group_opportunities.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
