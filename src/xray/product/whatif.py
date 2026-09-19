"""Escenarios what-if precalculados sobre `financial_smoothed_v2` con la referencia congelada.

Cada escenario modifica las features de los últimos `window` meses de una empresa (un cambio
sostenido, no un mes aislado) y vuelve a puntuar con `score_v2.score_panel` y el JSON de
referencia ya ajustado: misma función, misma referencia, sin recalibrar. El resultado es
una rejilla "una palanca cada vez" por empresa que el frontend selecciona por coincidencia
exacta (no interpola). Escenario, no predicción.

Palancas (claves fijadas por el contrato del frontend; la semántica la define esta capa):
    customer_term     variación % de las entradas operativas identificadas (tx_inflow)
    collection_delay  días añadidos al retraso de cobro AR (pago − vencimiento)
    supplier_term     días añadidos al retraso de pago AP
    internal_support  variación % de las salidas operativas identificadas (tx_outflow); baseline 100 = sin cambio
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from xray.paths import PROCESSED_DIR
from xray.score.pipeline import read_panel
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import score_panel

LEVERS = {
    "customer_term": {"label": "Entradas operativas", "unit": "%", "baseline": 100, "min": -30, "max": 30, "step": 10,
                      "steps": [-30, -20, -10, 10, 20, 30],
                      "explanation": "Variación sostenida (seis meses) de las entradas operativas identificadas; 100 = nivel actual. El margen y el crecimiento se recalculan."},
    "collection_delay": {"label": "Retraso de cobro a clientes", "unit": "days", "baseline": 0, "min": 0, "max": 60, "step": 15,
                         "steps": [15, 30, 45, 60],
                         "explanation": "Días añadidos al retraso realizado de cobro (pago − vencimiento) en los últimos seis meses."},
    "supplier_term": {"label": "Retraso de pago a proveedores", "unit": "days", "baseline": 0, "min": 0, "max": 60, "step": 15,
                      "steps": [15, 30, 45, 60],
                      "explanation": "Días añadidos al retraso realizado de pago a proveedores; el score no premia pagar más tarde."},
    "internal_support": {"label": "Salidas operativas", "unit": "%", "baseline": 100, "min": -30, "max": 30, "step": 10,
                         "steps": [-30, -20, -10, 10, 20, 30],
                         "explanation": "Variación sostenida (seis meses) de las salidas operativas identificadas; 100 = nivel actual."},
}
METHODOLOGY = ("Cada escenario aplica un cambio sostenido durante los últimos seis meses a una sola palanca y vuelve a calcular "
               "el Health Score con la misma fórmula y la misma referencia congelada de financial_smoothed_v2. No es una predicción: "
               "muestra la sensibilidad del score a ese cambio, sin combinar palancas ni interpolar.")
ZERO = {"customer_term": 0, "collection_delay": 0, "supplier_term": 0, "internal_support": 0}


def scenario_grid():
    scenarios = [("base", dict(ZERO))]
    for key, spec in LEVERS.items():
        for value in spec["steps"]:
            scenarios.append((f"{key}:{value:+d}", {**ZERO, key: value}))
    return scenarios


def apply_scenario(frame, inputs, window_months):
    """Devuelve una copia del calendario de una empresa con la palanca aplicada en los meses de la ventana."""
    f = frame.copy()
    mask = f.month.isin(window_months)
    inflow_scale = 1 + inputs["customer_term"] / 100.0
    outflow_scale = 1 + inputs["internal_support"] / 100.0
    if inflow_scale != 1:
        first = f.loc[mask, "month"].min()
        growth = f.loc[mask & f.month.eq(first), "tx_lfl_inflow_growth"]
        f.loc[growth.index, "tx_lfl_inflow_growth"] = (1 + growth) * inflow_scale - 1
        f.loc[mask, "tx_inflow"] = f.loc[mask, "tx_inflow"] * inflow_scale
    if outflow_scale != 1:
        f.loc[mask, "tx_outflow"] = f.loc[mask, "tx_outflow"] * outflow_scale
    if inflow_scale != 1 or outflow_scale != 1:
        total = f.loc[mask, "tx_inflow"] + f.loc[mask, "tx_outflow"]
        f.loc[mask, "tx_operating_margin"] = ((f.loc[mask, "tx_inflow"] - f.loc[mask, "tx_outflow"]) / total.where(total > 0)).where(total.notna())
    for key, column in (("collection_delay", "inv_ar_delay_median"), ("supplier_term", "inv_ap_delay_median")):
        if inputs[key] and column in f:
            f.loc[mask, column] = f.loc[mask, column] + inputs[key]
    return f


def build_whatif(panel, reference, company_ids, month, window=6, chunk=40, verbose=True):
    """Puntúa la rejilla de escenarios para `company_ids` en `month`. Devuelve una fila por empresa y escenario."""
    config = ScoreV2Config(**reference["config"])
    unit = config.unit
    month = pd.Timestamp(month)
    window_months = pd.date_range(end=month, periods=window, freq="MS")
    grid = scenario_grid()
    keep = [unit, "group_id", "currency", "month", "score"]
    results = []
    ids = list(company_ids)
    for start in range(0, len(ids), chunk):
        pieces = []
        for cid in ids[start:start + chunk]:
            base = panel.loc[panel[unit].eq(cid) & panel.month.le(month)]
            if base.empty:
                continue
            for sid, inputs in grid:
                copy = apply_scenario(base, inputs, window_months)
                copy[unit] = f"{cid}|{sid}"
                pieces.append(copy)
        if not pieces:
            continue
        scored, _ = score_panel(pd.concat(pieces, ignore_index=True), reference)
        latest = scored.loc[scored.month.eq(month), keep].copy()
        split = latest[unit].str.split("|", n=1, expand=True)
        latest["company_id"], latest["scenario_id"] = split[0], split[1]
        results.append(latest.drop(columns=[unit]) if unit != "company_id" else latest)
        if verbose:
            print(f"  what-if {min(start + chunk, len(ids))}/{len(ids)} empresas")
    if not results:
        return pd.DataFrame(columns=["company_id", "scenario_id", "score", "delta", *ZERO])
    out = pd.concat(results, ignore_index=True)
    inputs = pd.DataFrame([{"scenario_id": sid, **values} for sid, values in grid])
    out = out.merge(inputs, on="scenario_id", how="left")
    base = out.loc[out.scenario_id.eq("base"), ["company_id", "score"]].rename(columns={"score": "base_score"})
    out = out.merge(base, on="company_id", how="left")
    out["delta"] = out.score - out.base_score
    return out[["company_id", "currency", "month", "scenario_id", *ZERO, "score", "base_score", "delta"]]


def run(features_dir=PROCESSED_DIR, scores_dir=None, out_dir=None, month=None, verbose=True):
    features_dir = Path(features_dir)
    scores_dir = Path(scores_dir or features_dir / "scores_v2")
    out_dir = Path(out_dir or features_dir / "product")
    reference = json.loads((scores_dir / "_company_score_reference.json").read_text(encoding="utf-8"))
    config = ScoreV2Config(**reference["config"])
    panel, _ = read_panel(features_dir, config)
    panel["month"] = pd.to_datetime(panel.month)
    scores = pd.read_parquet(scores_dir / "company_monthly_scores.parquet", columns=["company_id", "month", "score"])
    month = pd.Timestamp(month) if month else scores.month.max()
    ids = scores.loc[scores.month.eq(month) & scores.score.notna(), "company_id"].unique()
    result = build_whatif(panel, reference, ids, month, window=config.level_window, verbose=verbose)
    mismatch = (result.loc[result.scenario_id.eq("base")].merge(scores.loc[scores.month.eq(month)], on=["company_id", "month"], suffixes=("", "_published")))
    mismatch = mismatch.loc[(mismatch.score - mismatch.score_published).abs().gt(1e-6), "company_id"]
    if len(mismatch):
        result = result.loc[~result.company_id.isin(mismatch)]
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_dir / "whatif_scenarios.parquet", index=False)
    summary = {"month": str(month.date()), "companies": int(result.company_id.nunique()), "scenarios_per_company": len(scenario_grid()),
               "dropped_base_mismatch": int(len(mismatch)), "levers": {k: {kk: vv for kk, vv in v.items() if kk != "steps"} for k, v in LEVERS.items()},
               "methodology": METHODOLOGY}
    (out_dir / "_whatif_manifest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        print(f"  escenarios: {len(result):,} filas · {summary['companies']} empresas · base descartada en {summary['dropped_base_mismatch']} -> {out_dir}")
    return result, summary
