from dataclasses import dataclass

import pandas as pd

from xray.paths import EXTRACTION_DATE


@dataclass(frozen=True)
class FeatureConfig:
    start_month: str = "2024-09-01"
    end_month: str = "2026-08-01"
    extraction_date: str = str(EXTRACTION_DATE.date())
    min_history_months: int = 6
    thin_month_transactions: int = 5
    # D31: artefacto estático de categorías AI para filas `uncategorized`; None = desactivado.
    ai_categories_path: str | None = None
    ai_min_confidence: float = 0.7
    # FE10: cobertura. Cuenta dormida = ≤ N movimientos utilizables y < X unidades (moneda nominal) en el mes;
    # onboarding = primeros M meses desde la primera actividad real de la entidad-moneda.
    dormant_max_transactions: int = 3
    dormant_max_amount: float = 2000.0
    onboarding_months: int = 2
    account_change_min_share: float = 0.10

    def __post_init__(self):
        if self.dormant_max_transactions < 0 or self.dormant_max_amount <= 0 or self.onboarding_months < 0:
            raise ValueError("Los umbrales de cobertura deben ser no negativos y el importe positivo")
        if not 0 <= self.account_change_min_share <= 1:
            raise ValueError("account_change_min_share debe estar en [0, 1]")
        if not 0 <= self.ai_min_confidence <= 1:
            raise ValueError("ai_min_confidence debe estar en [0, 1]")
        start, end, extraction = map(pd.Timestamp, (self.start_month, self.end_month, self.extraction_date))
        if start != start.to_period("M").start_time or end != end.to_period("M").start_time:
            raise ValueError("start_month y end_month deben ser el primer día del mes")
        if end < start or end >= extraction.to_period("M").start_time:
            raise ValueError("El panel debe terminar en un mes completo anterior a extracción")
        if self.min_history_months < 1 or self.thin_month_transactions < 1:
            raise ValueError("Los mínimos de cobertura deben ser positivos")

    @property
    def months(self):
        return pd.date_range(self.start_month, self.end_month, freq="MS")

    @property
    def stop(self):
        return pd.Timestamp(self.end_month) + pd.offsets.MonthBegin(1)
