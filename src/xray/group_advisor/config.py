"""Parámetros de `treasury_advisor_v1` (spec `docs/group-optimization.md` §11).

`horizon_months` debe coincidir con `level_window` de la referencia V2; esa comprobación
necesita la referencia y la hace `state.load_inputs`, no el constructor. La tabla FX es
opcional (`None` → solo acciones en la misma moneda) y solo se usa para importes.
"""
import math
from dataclasses import dataclass, field

import pandas as pd


GROUP_LEVERS = ("D1", "P")
SENSITIVITY_LEVERS = ("cut_outflow", "raise_inflow", "debt_service_cut", "ap_on_time", "ar_faster")
WEIGHTINGS = ("equal", "size")
TRAMO_LABELS = ("red", "amber", "green")


def _default_r_max():
    return {"cut_outflow": 0.5, "raise_inflow": 1.0, "debt_service_cut": 1.0, "ap_on_time": 1.0, "ar_faster": 1.0}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _increasing_fractions(values, name):
    if not values or any(not _finite(v) or not 0 < v <= 1 for v in values):
        raise ValueError(f"{name} debe contener fracciones en (0, 1]")
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(f"{name} debe ser estrictamente creciente")


@dataclass(frozen=True)
class AdvisorConfig:
    month: str | None = None
    levers: tuple = GROUP_LEVERS
    fractions: tuple = (0.25, 0.5, 0.75, 1.0)
    donor_buffer_months: float = 2.0
    donor_level_floor_drop: float = 5.0
    horizon_months: int = 6
    report_k: tuple = (1, 6)
    utility_knots: tuple = ((0, 3.0), (40, 2.0), (70, 1.0))
    tramo_bounds: tuple = (40.0, 70.0)
    subsidiary_weighting: str = "equal"
    min_gain_utility: float = 0.25
    max_steps: int = 10
    exhaustive_max_subsidiaries: int = 6
    liquidity_constrained_runway: float = 1.0
    rejected_alternatives_kept: int = 5
    sensitivity_grid: tuple = (0.01, 0.05, 0.10, 0.25)
    sensitivity_r_max: dict = field(default_factory=_default_r_max)
    finite_difference_eps: float = 1e-4
    bisection_tol: float = 1e-4
    reporting_currency: str = "EUR"
    fx_rates_to_eur: dict | None = None
    fx_source: str | None = None
    fx_asof: str | None = None

    def __post_init__(self):
        if self.month is not None:
            stamp = pd.Timestamp(self.month)
            if pd.isna(stamp) or stamp != stamp.to_period("M").to_timestamp():
                raise ValueError("month debe ser el primer día de un mes (YYYY-MM-01)")
        if not self.levers or any(lever not in GROUP_LEVERS for lever in self.levers) or len(set(self.levers)) != len(self.levers):
            raise ValueError(f"levers debe ser un subconjunto no vacío y sin repetidos de {GROUP_LEVERS}")
        _increasing_fractions(self.fractions, "fractions")
        _increasing_fractions(self.sensitivity_grid, "sensitivity_grid")
        for name in ("donor_buffer_months", "donor_level_floor_drop", "min_gain_utility", "liquidity_constrained_runway"):
            if not _finite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} debe ser un número finito no negativo")
        for name in ("horizon_months", "max_steps"):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise ValueError(f"{name} debe ser un entero positivo")
        for name in ("exhaustive_max_subsidiaries", "rejected_alternatives_kept"):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 0:
                raise ValueError(f"{name} debe ser un entero no negativo")
        if (not self.report_k or any(not isinstance(k, int) or not 1 <= k <= self.horizon_months for k in self.report_k)
                or any(b <= a for a, b in zip(self.report_k, self.report_k[1:]))):
            raise ValueError("report_k debe ser una tupla creciente de enteros en 1..horizon_months")
        self._check_utility()
        if self.subsidiary_weighting not in WEIGHTINGS:
            raise ValueError(f"subsidiary_weighting debe ser uno de {WEIGHTINGS}")
        if set(self.sensitivity_r_max) != set(SENSITIVITY_LEVERS) or any(not _finite(v) or v <= 0 for v in self.sensitivity_r_max.values()):
            raise ValueError(f"sensitivity_r_max debe tener exactamente las palancas {SENSITIVITY_LEVERS} con r_max > 0")
        for name in ("finite_difference_eps", "bisection_tol"):
            if not _finite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} debe ser positivo")
        self._check_fx()

    def _check_utility(self):
        knots = self.utility_knots
        if len(knots) < 1 or any(len(k) != 2 for k in knots):
            raise ValueError("utility_knots debe ser una tupla de pares (inicio_tramo, pendiente)")
        starts, slopes = [k[0] for k in knots], [k[1] for k in knots]
        if starts[0] != 0 or any(not _finite(s) for s in starts) or any(b <= a for a, b in zip(starts, starts[1:])):
            raise ValueError("utility_knots debe empezar en 0 con inicios de tramo estrictamente crecientes")
        if any(not _finite(s) or s <= 0 for s in slopes):
            raise ValueError("Las pendientes de utilidad deben ser positivas")
        if any(b > a for a, b in zip(slopes, slopes[1:])):
            raise ValueError("Las pendientes de utilidad deben ser no crecientes (utilidad cóncava)")
        bounds = self.tramo_bounds
        if len(bounds) != len(TRAMO_LABELS) - 1:
            raise ValueError(f"tramo_bounds debe tener {len(TRAMO_LABELS) - 1} cortes: tramos {TRAMO_LABELS}")
        if any(not _finite(b) or not 0 < b < 100 for b in bounds) or any(b <= a for a, b in zip(bounds, bounds[1:])):
            raise ValueError("tramo_bounds debe ser creciente y estar en (0, 100)")
        if tuple(float(b) for b in bounds) != tuple(float(s) for s in starts[1:]):
            raise ValueError("tramo_bounds debe coincidir con los inicios de tramo de utility_knots (salvo el 0)")

    def _check_fx(self):
        if not isinstance(self.reporting_currency, str) or not self.reporting_currency:
            raise ValueError("reporting_currency debe ser un código de moneda")
        table = self.fx_rates_to_eur
        if table is None:
            return
        if not isinstance(table, dict) or table.get("EUR") != 1.0:
            raise ValueError("fx_rates_to_eur debe ser un dict con EUR: 1.0 (unidades de moneda por 1 EUR)")
        for currency, rate in table.items():
            if not isinstance(currency, str) or not _finite(rate) or rate <= 0:
                raise ValueError(f"Tipo FX inválido para {currency!r}: debe ser un número finito positivo")
        if self.reporting_currency not in table:
            raise ValueError(f"reporting_currency {self.reporting_currency!r} no está en fx_rates_to_eur")
