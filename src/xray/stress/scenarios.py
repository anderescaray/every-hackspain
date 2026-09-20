"""Versioned, discrete stress assumptions for the existing frozen V2 scorer."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from xray.product.whatif import apply_scenario as apply_whatif

METHOD = "v2_observed_window_stress_v1"
SCHEMA_VERSION = "1.0"
ENGINE_VERSION = "stress-assumptions-v3"
HORIZONS = (1, 3, 6)
MIN_FX_STRESS_SHARE = 0.10
MIN_FX_STRESS_EUR = 1000.0
COST_CATEGORIES = ("payroll", "utilities", "payment_processing", "other_operating_payment")
COST_FACTORS = tuple(f"cost_{category}" for category in COST_CATEGORIES)
NAMED_FACTORS = ("operating_inflow", "operating_outflow", "observed_debt_service",
                 "customer_delay", "variable_rate", *COST_FACTORS)
FACTORS = NAMED_FACTORS
LABELS = {
    "operating_inflow": "Entradas operativas",
    "operating_outflow": "Salidas operativas",
    "observed_debt_service": "Servicio de deuda",
    "customer_delay": "Cliente principal",
    "variable_rate": "Tipos de interés",
    "cost_payroll": "Nómina",
    "cost_utilities": "Suministros",
    "cost_payment_processing": "Procesamiento de pagos",
    "cost_other_operating_payment": "Otros pagos operativos",
}
FACTOR_GROUP = {
    "operating_inflow": "comercial", "customer_delay": "comercial",
    "operating_outflow": "costes", "cost_payroll": "costes", "cost_utilities": "costes",
    "cost_payment_processing": "costes", "cost_other_operating_payment": "costes",
    "observed_debt_service": "financiacion", "variable_rate": "financiacion",
}
CUSTOM_GRID = {
    "operating_inflow": (-30, -20, -10, 10),
    "operating_outflow": (10, 20, 30),
    "observed_debt_service": (10, 20, 50),
    "customer_delay": (15, 30, 60),
    "variable_rate": (100, 200, 300),
}
REVERSE_GRID = {
    "operating_inflow": (-5, -10, -15, -20, -25, -30),
    "operating_outflow": (5, 10, 15, 20, 25, 30),
    "customer_delay": (10, 15, 20, 30, 45, 60),
    "observed_debt_service": (10, 20, 30, 40, 50),
}
BAND_BOUNDS = (40.0, 70.0)
UNITS = {"operating_inflow": "pct", "operating_outflow": "pct", "observed_debt_service": "pct",
         "customer_delay": "days", "variable_rate": "bp",
         **{factor: "pct" for factor in COST_FACTORS}}


def observed_horizon_months(quality_months, as_of, horizon):
    """Last `horizon` consecutive V2-quality months inside the level window.

    The block may end before `as_of` when the scored month is thin: V2 still
    publishes Health from earlier quality months, and stress must use those
    same months instead of requiring six perfect calendar months.
    """
    if horizon not in HORIZONS:
        raise ValueError("Stress horizon must be 1, 3 or 6 observed months")
    end = pd.Timestamp(as_of).to_period("M").to_timestamp()
    window = pd.date_range(end=end, periods=6, freq="MS")
    quality = {str(month) for month in (quality_months or [])}
    ok = [stamp.strftime("%Y-%m") in quality for stamp in window]
    last = next((index for index in range(len(ok) - 1, -1, -1) if ok[index]), None)
    if last is None:
        return None
    start = last
    while start > 0 and ok[start - 1]:
        start -= 1
    block = window[start:last + 1]
    if len(block) < horizon:
        return None
    return tuple(block[-horizon:])


def factor_unit(factor: str) -> str:
    return "pct" if factor.startswith("fx_") else UNITS[factor]


def health_band(value):
    if value is None:
        return None
    if value >= BAND_BOUNDS[1]:
        return "green"
    if value >= BAND_BOUNDS[0]:
        return "amber"
    return "red"


def material_cost_categories(gates: dict | None, limit=3):
    runnable = [(name, gate) for name, gate in (gates or {}).items()
                if name in COST_CATEGORIES and gate.get("score_runnable")]
    runnable.sort(key=lambda item: (-float(item[1].get("amount_6m") or 0), item[0]))
    return [name for name, _ in runnable[:limit]]


def _valid_pct(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -100 < value <= 100 and value != 0


@dataclass(frozen=True)
class Shock:
    factor: str
    relative_pct: int
    unit: str = "pct"

    def __post_init__(self):
        named = self.factor in NAMED_FACTORS
        fx = re.fullmatch(r"fx_[A-Z]{3}", self.factor) is not None
        expected = "pct" if fx else UNITS.get(self.factor)
        if (not named and not fx) or expected is None or self.unit != expected:
            raise ValueError(f"Shock de estrés inválido: {self.factor} {self.relative_pct} {self.unit}")
        if self.unit == "pct" and not _valid_pct(self.relative_pct):
            raise ValueError(f"Shock porcentual inválido: {self.factor} {self.relative_pct}")
        if self.unit == "days" and not (isinstance(self.relative_pct, int) and 0 < self.relative_pct <= 60):
            raise ValueError(f"Shock de días inválido: {self.relative_pct}")
        if self.unit == "bp" and not (isinstance(self.relative_pct, int) and 0 < self.relative_pct <= 300):
            raise ValueError(f"Shock de tipos inválido: {self.relative_pct}")

    def json(self):
        return {"factor": self.factor, "relative_pct": self.relative_pct, "unit": self.unit}


@dataclass(frozen=True)
class Scenario:
    id: str
    kind: str
    label: str
    shocks: tuple[Shock, ...]
    available: bool = True
    reason: str | None = None

    def __post_init__(self):
        factors = [shock.factor for shock in self.shocks]
        if len(factors) != len(set(factors)):
            raise ValueError("Factores duplicados en el escenario")
        if "operating_outflow" in factors and any(factor.startswith("cost_") for factor in factors):
            raise ValueError("No se combinan el shock total de costes y categorías específicas")
        if "observed_debt_service" in factors and "variable_rate" in factors:
            raise ValueError("No se combinan servicio de deuda y tipos")


def _shock(factor, value):
    return Shock(factor, value, factor_unit(factor))


def _label(factor, value):
    unit = factor_unit(factor)
    name = LABELS.get(factor, f"Valor EUR · {factor.removeprefix('fx_')}" if factor.startswith("fx_") else factor)
    if unit == "days":
        return f"{name} +{value} d"
    if unit == "bp":
        return f"{name} +{value} pb"
    sign = "+" if value > 0 else "−"
    return f"{name} {sign}{abs(value)} %"


def scenarios(has_observed_service: bool, cost_category_gates: dict | None = None,
              fx_currency: str | None = None, *, has_customer_delay: bool = False,
              has_variable_rate: bool = False):
    """Preset bundles plus one-factor custom grid; no dynamic TS combinations."""
    income = lambda pct: _shock("operating_inflow", pct)
    outflow = lambda pct: _shock("operating_outflow", pct)
    debt = lambda pct: _shock("observed_debt_service", pct)
    delay = lambda days: _shock("customer_delay", days)
    rate = lambda bp: _shock("variable_rate", bp)
    collections = (delay(30),) if has_customer_delay else (income(-10),)
    if has_variable_rate:
        financing, financing_ok, financing_reason = (rate(200),), True, None
    elif has_observed_service:
        financing, financing_ok, financing_reason = (debt(20),), True, None
    else:
        financing, financing_ok, financing_reason = (debt(20),), False, "no_observed_debt_service"
    adverse = [income(-15), outflow(10)]
    if has_customer_delay:
        adverse.append(delay(30))
    if has_variable_rate:
        adverse.append(rate(200))
    elif has_observed_service:
        adverse.append(debt(20))
    if fx_currency is not None:
        if re.fullmatch(r"[A-Z]{3}", fx_currency) is None or fx_currency == "EUR":
            raise ValueError("FX stress currency must be a non-EUR ISO3 source")
        adverse.append(_shock(f"fx_{fx_currency}", -10))
    presets = [
        Scenario("collections", "preset", "Cobros", collections),
        Scenario("margin", "preset", "Margen", (income(-10), outflow(10))),
        Scenario("financing", "preset", "Financiación", financing, financing_ok, financing_reason),
        Scenario("adverse", "preset", "Adverso", tuple(adverse)),
    ]
    if fx_currency is not None:
        presets.insert(3, Scenario("fx", "preset", "FX", (_shock(f"fx_{fx_currency}", -10),)))
    grid = []
    for factor, positions in CUSTOM_GRID.items():
        available = True
        reason = None
        if factor == "observed_debt_service":
            available, reason = has_observed_service, None if has_observed_service else "no_observed_debt_service"
        elif factor == "customer_delay":
            available, reason = has_customer_delay, None if has_customer_delay else "customer_delay_unavailable"
        elif factor == "variable_rate":
            available, reason = has_variable_rate, None if has_variable_rate else "variable_rate_unavailable"
        if not available:
            continue
        for value in positions:
            grid.append(Scenario(f"{factor}:{value:+d}", "single_factor", _label(factor, value),
                                 (_shock(factor, value),)))
    for category in material_cost_categories(cost_category_gates):
        factor = f"cost_{category}"
        for pct in (10, 20, 30):
            grid.append(Scenario(f"{factor}:{pct:+d}", "single_factor", _label(factor, pct),
                                 (_shock(factor, pct),)))
    if fx_currency is not None:
        factor = f"fx_{fx_currency}"
        for pct in (-20, -10, 10, 20):
            grid.append(Scenario(f"{factor}:{pct:+d}", "single_factor", _label(factor, pct),
                                 (_shock(factor, pct),)))
    return presets + grid


def custom_factor_contract(specs: list[Scenario], *, top1_share=None, fx_currency=None,
                           variable_outstanding=None):
    """UI catalogue of measurable custom levers, without disabled placeholders."""
    grouped = {}
    for spec in specs:
        if spec.kind != "single_factor" or not spec.available:
            continue
        shock = spec.shocks[0]
        grouped.setdefault(shock.factor, []).append(shock.relative_pct)
    rows = []
    for factor, positions in grouped.items():
        group = "mercado" if factor.startswith("fx_") else FACTOR_GROUP[factor]
        context = {}
        if factor == "customer_delay" and top1_share is not None:
            context["top1_share"] = top1_share
        if factor.startswith("fx_") and fx_currency:
            context["currency"] = fx_currency
        if factor == "variable_rate" and variable_outstanding is not None:
            context["outstanding_eur"] = variable_outstanding
        rows.append({"factor": factor, "group": group, "unit": factor_unit(factor),
                     "positions": sorted(set(positions)), "context": context or None})
    order = {"comercial": 0, "costes": 1, "financiacion": 2, "mercado": 3}
    rows.sort(key=lambda row: (order.get(row["group"], 9), row["factor"]))
    return rows


def apply_shocks(frame, shocks: tuple[Shock, ...], window_months, cost_monthly: dict | None = None,
                 context: dict | None = None):
    """Reuse current What-if inflow/outflow feature perturbation; add observed P+I only.

    V2 consumes debt principal and interest separately but scores their *sum*.
    Scaling both equally preserves the observed mix; fees are not in V2.
    Customer delay is applied to the V2 AR-delay median in proportion to top-1 share.
    """
    values = {shock.factor: shock.relative_pct for shock in shocks}
    if "operating_outflow" in values and any(factor.startswith("cost_") for factor in values):
        raise ValueError("No double-counting of total operating costs and category shocks")
    mapped = {"customer_term": values.get("operating_inflow", 0), "internal_support": values.get("operating_outflow", 0),
              "collection_delay": 0, "supplier_term": 0}
    changed = apply_whatif(frame, mapped, window_months)
    extra = context or {}
    delay_days = values.get("customer_delay", 0)
    if delay_days:
        share = extra.get("top1_share")
        if share is None or not 0 < float(share) <= 1:
            raise ValueError("Customer delay requires an identified top-1 share")
        mask = changed.month.isin(window_months)
        if "inv_ar_delay_median" not in changed:
            raise ValueError("Customer delay requires inv_ar_delay_median")
        changed.loc[mask, "inv_ar_delay_median"] = changed.loc[mask, "inv_ar_delay_median"] + delay_days * float(share)
    for factor in COST_FACTORS:
        pct = values.get(factor, 0)
        if not pct:
            continue
        if cost_monthly is None:
            raise ValueError("Category stress requires reconciled monthly canonical amounts")
        category = factor.removeprefix("cost_")
        for month in window_months:
            month_key = pd.Timestamp(month).strftime("%Y-%m")
            pieces = cost_monthly.get(month_key)
            if pieces is None or pieces.get(category) is None:
                raise ValueError(f"Missing category amount for {factor} {month_key}")
            mask_month = changed.month.eq(month)
            changed.loc[mask_month, "tx_outflow"] = changed.loc[mask_month, "tx_outflow"] + pieces[category] * pct / 100
        mask = changed.month.isin(window_months)
        total = changed.loc[mask, "tx_inflow"] + changed.loc[mask, "tx_outflow"]
        changed.loc[mask, "tx_operating_margin"] = ((changed.loc[mask, "tx_inflow"] - changed.loc[mask, "tx_outflow"])
                                                      / total.where(total > 0)).where(total.notna())
    debt_pct = values.get("observed_debt_service", 0)
    if debt_pct:
        mask = changed.month.isin(window_months)
        for column in ("debt_principal_paid", "debt_interest_paid"):
            changed.loc[mask, column] = changed.loc[mask, column] * (1 + debt_pct / 100)
    bp = values.get("variable_rate", 0)
    if bp:
        outstanding = extra.get("variable_outstanding_eur")
        if outstanding is None or float(outstanding) <= 0:
            raise ValueError("Variable-rate stress requires identified outstanding")
        monthly = float(outstanding) * (bp / 10000.0) / 12.0
        mask = changed.month.isin(window_months)
        changed.loc[mask, "debt_interest_paid"] = changed.loc[mask, "debt_interest_paid"] + monthly
    return changed
