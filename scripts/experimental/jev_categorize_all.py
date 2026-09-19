"""Pasada ÚNICA de categorización con TypeSafe Jev sobre plantillas de texto bancario.

Produce un artefacto estático que el pipeline puede consumir sin llamar a la API:
    data/enriched/jev_categories/responses.jsonl          respuestas crudas (reanudable)
    data/enriched/jev_categories/template_categories.parquet  plantilla+signo -> bloque, confianza, nouls
    data/enriched/jev_categories/_manifest.json           parámetros, preguntas, hashes, conteos

Universo: transacciones booked con |amount| <= 1e8 (D01). Todas las plantillas sin categoría
más las N plantillas más frecuentes con categoría del banco (control / posibles overrides).

Uso:
    set -a; . ./.env; set +a
    python -X utf8 scripts/experimental/jev_categorize_all.py --workers 16
    python -X utf8 scripts/experimental/jev_categorize_all.py --finalize   # solo consolida
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev_categorize_prototype import BANK_TO_BLOCK, MODEL, QUESTIONS, call_jev, template  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "_cache" / "transactions.parquet"
OUT = ROOT / "data" / "enriched" / "jev_categories"
PROTO = ROOT / "data" / "enriched" / "prototype" / "responses.jsonl"

COARSE = {
    "operating_inflow": "op_in", "supplier_payment": "op_out", "utility": "op_out", "salary": "op_out",
    "social_security": "op_out", "tax": "op_out", "interest_or_debt": "debt", "bank_fee": "fee",
    "internal_transfer": "nonop", "cash": "nonop", "bank_adjustment": "nonop", "unknown": "unknown",
}


def key_of(tpl: str, sign: int) -> str:
    return hashlib.sha1(f"{tpl}|{sign}".encode()).hexdigest()[:16]


def build_universe(top_categorized: int) -> pd.DataFrame:
    t = pd.read_parquet(CACHE, columns=["company_id", "amount", "category", "description", "status"])
    t = t[(t.status == "booked") & (t.amount.abs() <= 1e8)].copy()
    t["tpl"] = template(t.description)
    t = t[t.tpl.str.len() > 0]
    t["sign"] = np.sign(t.amount).astype(int)
    t["uncat"] = t.category.isna() | (t.category == "-")
    t["absamt"] = t.amount.abs()
    keys = ["tpl", "sign"]

    def agg(df: pd.DataFrame) -> pd.DataFrame:
        a = df.groupby(keys).agg(rows=("amount", "size"), amt=("absamt", "sum"),
                                 median_amt=("absamt", "median"), n_companies=("company_id", "nunique"))

        def top_value(col: str) -> pd.Series:
            c = df.groupby(keys + [col], dropna=False).size().reset_index(name="n")
            return c.sort_values("n", ascending=False).drop_duplicates(keys).set_index(keys)[col]

        return a.join(top_value("description").rename("example")).join(top_value("category").rename("bank_category")).reset_index()

    u = agg(t[t.uncat]).assign(set="uncategorized")
    c = agg(t[~t.uncat]).sort_values("rows", ascending=False).head(top_categorized).assign(set="categorized")
    out = pd.concat([u, c], ignore_index=True)
    out["key"] = [key_of(r.tpl, r.sign) for r in out.itertuples()]
    return out


def load_done(path: Path) -> dict[str, dict]:
    done = {}
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    x = json.loads(line)
                    done[x["key"]] = x
                except json.JSONDecodeError:
                    continue  # línea truncada por interrupción; se reintenta
    return done


def finalize(universe: pd.DataFrame, responses: dict[str, dict], args) -> None:
    rec = []
    for k, x in responses.items():
        b = x["answers"]["block"]
        rec.append({"key": k, "jev_block": b["choice"], "jev_confidence": b["confidence"],
                    "jev_p_top": max(b["probabilities"].values()),
                    "noul_unpaid_return": x["answers"]["is_unpaid_return"]["noul"],
                    "noul_overdraft_or_seizure": x["answers"]["is_overdraft_or_seizure"]["noul"]})
    r = pd.DataFrame(rec)
    d = universe.merge(r, on="key", how="left")
    d["jev_coarse"] = d.jev_block.map(COARSE)
    # Veto: bloque operativo incoherente con el signo -> unknown.
    bad = ((d.jev_coarse == "op_in") & (d.sign < 0)) | ((d.jev_coarse == "op_out") & (d.sign > 0))
    d["sign_conflict"] = bad
    d.loc[bad, ["jev_block", "jev_coarse"]] = ["unknown", "unknown"]
    d["bank_block"] = d.bank_category.map(BANK_TO_BLOCK)
    d["bank_coarse"] = d.bank_block.map(COARSE)
    cols = ["key", "set", "tpl", "sign", "rows", "amt", "median_amt", "n_companies", "example", "bank_category", "bank_block",
            "bank_coarse", "jev_block", "jev_coarse", "jev_confidence", "jev_p_top", "sign_conflict",
            "noul_unpaid_return", "noul_overdraft_or_seizure"]
    d = d[cols]
    out_path = OUT / "template_categories.parquet"
    d.to_parquet(out_path, index=False)

    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    answered = d.jev_block.notna()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL, "questions": QUESTIONS, "coarse_map": COARSE, "bank_to_block": BANK_TO_BLOCK,
        "universe": {"filter": "status==booked & |amount|<=1e8 & template non-empty",
                     "top_categorized": args.top_categorized, "templates": int(len(d)),
                     "uncategorized": int((d.set == "uncategorized").sum()), "categorized": int((d.set == "categorized").sum())},
        "answered": int(answered.sum()), "unanswered": int((~answered).sum()),
        "sign_conflicts_vetoed": int(d.sign_conflict.sum()),
        "template_fn": "upper; COUNTERPARTY_n->CP; [TOKEN]->T; digits->#; non-letters->space; collapse spaces",
        "state_fields": ["bank_narrative", "direction", "typical_amount"],
        "files": {"template_categories.parquet": sha(out_path), "responses.jsonl": sha(OUT / "responses.jsonl") if (OUT / "responses.jsonl").exists() else None,
                  "transactions.parquet(input)": sha(CACHE)},
        "code_sha256": {p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name("jev_categorize_prototype.py")]},
    }
    (OUT / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    u = d[(d.set == "uncategorized") & answered]
    print(f"artefacto: {out_path}  plantillas {len(d)}  respondidas {answered.sum()}  vetos signo {d.sign_conflict.sum()}")
    print("sin categoría, bloque grueso ponderado por filas (conf>=0.7):")
    m = u[u.jev_confidence >= 0.7]
    print((m.groupby("jev_coarse").rows.sum() / u.rows.sum()).sort_values(ascending=False).round(3).to_string())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-categorized", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None, help="máximo de llamadas en esta ejecución")
    ap.add_argument("--finalize", action="store_true", help="no llamar a la API; consolidar lo que haya")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    uni_path = OUT / "universe.parquet"
    if uni_path.exists():
        universe = pd.read_parquet(uni_path)
    else:
        universe = build_universe(args.top_categorized)
        universe.to_parquet(uni_path, index=False)
    print(f"universo: {len(universe)} plantillas ({(universe.set == 'uncategorized').sum()} sin categoría, "
          f"{(universe.set == 'categorized').sum()} con categoría)")

    raw_path = OUT / "responses.jsonl"
    done = load_done(raw_path)
    # Reutilizar respuestas del prototipo (misma clave y mismas preguntas).
    if PROTO.exists():
        new = 0
        with raw_path.open("a") as f:
            for k, x in load_done(PROTO).items():
                if k not in done and k in set(universe.key):
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
                    done[k] = x
                    new += 1
        if new:
            print(f"reutilizadas {new} respuestas del prototipo")

    if not args.finalize:
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            print("Falta TYPESAFE_API_KEY", file=sys.stderr)
            return 2
        todo = universe[~universe.key.isin(done)]
        if args.limit:
            todo = todo.head(args.limit)
        print(f"pendientes: {len(todo)} (en caché: {len(done)})")

        def work(row) -> dict:
            state = {"bank_narrative": row.example, "direction": "money_in" if row.sign > 0 else "money_out",
                     "typical_amount": round(float(row.median_amt), 2)}
            resp = call_jev(state, api_key)
            return {"key": row.key, "state": state, "answers": resp["answers"], "usage": resp.get("usage")}

        t0, n_err, n_ok = time.time(), 0, 0
        with raw_path.open("a") as f, ThreadPoolExecutor(args.workers) as ex:
            futs = {ex.submit(work, r): r.key for r in todo.itertuples()}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    x = fut.result()
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
                    done[x["key"]] = x
                    n_ok += 1
                except Exception as e:  # noqa: BLE001
                    n_err += 1
                    if n_err <= 20:
                        print(f"  error {futs[fut]}: {e}", file=sys.stderr)
                if i % 1000 == 0:
                    el = time.time() - t0
                    f.flush()
                    print(f"  {i}/{len(todo)}  {el/60:.1f} min  {i/el:.1f} req/s  errores {n_err}  ETA {(len(todo)-i)/(i/el)/60:.0f} min", flush=True)
        print(f"llamadas ok {n_ok}, errores {n_err}, {(time.time()-t0)/60:.1f} min")

    finalize(universe, done, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
