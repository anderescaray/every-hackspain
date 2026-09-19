"""Prototipo: categorizar movimientos bancarios sin categoría con TypeSafe Jev.

Experimento, no parte del pipeline. Lee data/_cache/transactions.parquet, deduplica por
plantilla de texto, envía las N plantillas más frecuentes a Jev y guarda respuestas crudas en
data/enriched/prototype/. Incluye un conjunto de control con plantillas YA categorizadas por
el banco para medir el acuerdo Jev <-> banco.

Uso:
    TYPESAFE_API_KEY=... python -X utf8 scripts/experimental/jev_categorize_prototype.py --top 1000 --control 300
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from xray.features.ai_categories import template  # noqa: E402  (misma plantilla que consume el pipeline)
CACHE = ROOT / "data" / "_cache" / "transactions.parquet"
OUT = ROOT / "data" / "enriched" / "prototype"
API = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

# Bloques alineados con FE03 (docs/decisiones.md). Opción `unknown` obligatoria para no forzar.
CATEGORY_CRITERIA = {
    "operating_inflow": "Money received from customers: invoice collections, remittances, card/POS settlements, receivables, sales proceeds",
    "supplier_payment": "Payment to a supplier or vendor for goods/services, rent, purchases, subscriptions, invoices paid",
    "utility": "Recurring utility or telecom bill: electricity, water, gas, phone, internet, insurance premium",
    "salary": "Payroll, wages, salary transfer to employees",
    "social_security": "Social security / pension / employer contributions to public bodies (TGSS, Sécurité sociale, Krankenkasse, etc.)",
    "tax": "Tax payment or tax refund to/from a tax authority (VAT, IVA, IRPF, corporate tax, withholding, customs)",
    "bank_fee": "Bank commission, service fee, card fee, maintenance fee, stamp duty on fees",
    "interest_or_debt": "Loan repayment, leasing installment, interest charge, credit line amortisation, financing costs",
    "internal_transfer": "Transfer between the company's own accounts, treasury sweep, investment placement/return, intra-group funding",
    "cash": "Cash withdrawal or cash deposit at branch/ATM",
    "bank_adjustment": "Technical bank entry: balance adjustment, correction, reversal, regularisation, period closing, no economic meaning",
    "unknown": "Text is too short, redacted or ambiguous to decide",
}

# Mapa de la categoría original del banco a los bloques anteriores, para el control.
BANK_TO_BLOCK = {
    "collection": "operating_inflow", "bulk_collection": "operating_inflow", "pos_settlement": "operating_inflow",
    "cash_settlement": "operating_inflow", "cash_settlements": "operating_inflow",
    "payment": "supplier_payment", "bulk_payment": "supplier_payment",
    "utility": "utility", "salary": "salary", "social_security": "social_security",
    "tax": "tax", "tax_refund": "tax", "fee": "bank_fee",
    "interest_charge": "interest_or_debt", "debt_repayment": "interest_or_debt",
    "transfer": "internal_transfer", "investment_deployment": "internal_transfer", "investment_return": "internal_transfer",
    "cash_withdrawal": "cash", "pos_withdrawal": "cash",
}

QUESTIONS = {
    "block": {
        "type": "choice",
        "instructions": "Classify this bank transaction into the economic block it belongs to. Use the narrative, the sign (positive = money in, negative = money out) and the amount. Placeholders like [COMPANY], [NUM], COUNTERPARTY_n are anonymised tokens.",
        "criteria": CATEGORY_CRITERIA,
    },
    "is_unpaid_return": {
        "type": "noul",
        "instructions": "This transaction is a returned/rejected direct debit, bounced bill or unpaid receivable caused by non-payment (not a refund, deposit return or transfer returned by error).",
    },
    "is_overdraft_or_seizure": {
        "type": "noul",
        "instructions": "This transaction is an overdraft charge/regularisation, a court or tax-authority seizure/garnishment (embargo, penhora, saisie), or a late-payment surcharge.",
    },
}


def build_samples(top: int, control: int, seed: int) -> pd.DataFrame:
    t = pd.read_parquet(CACHE, columns=["company_id", "amount", "category", "description", "exchange_rate", "status"])
    t = t[t.status == "booked"]
    t["tpl"] = template(t.description)
    t["sign"] = np.sign(t.amount).astype(int)
    t["uncat"] = t.category.isna() | (t.category == "-")
    t["absamt"] = t.amount.abs()

    def pick(df: pd.DataFrame, n: int, how: str) -> pd.DataFrame:
        df = df[df.tpl.str.len() > 0]
        keys = ["tpl", "sign"]
        agg = df.groupby(keys).agg(rows=("amount", "size"), amt=("absamt", "sum"),
                                   median_amt=("absamt", "median"), n_companies=("company_id", "nunique"))
        # Valor más frecuente por grupo, vectorizado: contar, ordenar, quedarse con el primero.
        def top_value(col: str) -> pd.Series:
            c = df.groupby(keys + [col], dropna=False).size().reset_index(name="n")
            c = c.sort_values("n", ascending=False).drop_duplicates(keys)
            return c.set_index(keys)[col]
        agg = agg.join(top_value("description").rename("example")).join(top_value("category").rename("bank_category")).reset_index()
        if how == "top":
            agg = agg.sort_values("rows", ascending=False).head(n)
        else:  # estratificado por categoría del banco
            agg = agg[agg.bank_category.isin(BANK_TO_BLOCK)]
            agg = agg.groupby("bank_category", group_keys=False).apply(
                lambda g: g.sample(min(len(g), max(1, n // agg.bank_category.nunique())), random_state=seed))
        return agg

    u = pick(t[t.uncat], top, "top").assign(set="uncategorized")
    c = pick(t[~t.uncat], control, "control").assign(set="control")
    out = pd.concat([u, c], ignore_index=True)
    out["key"] = [hashlib.sha1(f"{r.tpl}|{r.sign}".encode()).hexdigest()[:16] for r in out.itertuples()]
    return out


def call_jev(state: dict, api_key: str, retries: int = 6) -> dict:
    body = json.dumps({"state": state, "model": MODEL, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 529, 500, 502, 503) and attempt < retries - 1:
                time.sleep(min(30, 2 ** attempt) + np.random.rand())
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--control", type=int, default=300)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--dry-run", action="store_true", help="solo construye la muestra, no llama a la API")
    args = ap.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key and not args.dry_run:
        print("Falta TYPESAFE_API_KEY en el entorno", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    samples = build_samples(args.top, args.control, args.seed)
    samples.to_parquet(OUT / "samples.parquet", index=False)
    print(f"muestra: {len(samples)} plantillas ({(samples.set == 'uncategorized').sum()} sin categoría, "
          f"{(samples.set == 'control').sum()} control)")
    if args.dry_run:
        return 0

    raw_path = OUT / "responses.jsonl"
    done = set()
    if raw_path.exists():
        with raw_path.open() as f:
            done = {json.loads(l)["key"] for l in f}
    todo = samples[~samples.key.isin(done)]
    print(f"pendientes: {len(todo)} (ya en caché: {len(done)})")

    def work(row) -> dict:
        state = {
            "bank_narrative": row.example,
            "direction": "money_in" if row.sign > 0 else "money_out",
            "typical_amount": round(float(row.median_amt), 2),
        }
        resp = call_jev(state, api_key)
        return {"key": row.key, "state": state, "answers": resp["answers"], "usage": resp.get("usage")}

    t0 = time.time()
    n_err = 0
    with raw_path.open("a") as f, ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(work, r): r.key for r in todo.itertuples()}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
            except Exception as e:  # noqa: BLE001 - prototipo: registrar y seguir
                n_err += 1
                print(f"  error {futs[fut]}: {e}", file=sys.stderr)
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s")
    print(f"hecho en {time.time() - t0:.0f}s, errores: {n_err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
