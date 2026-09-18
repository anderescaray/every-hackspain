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

    def __post_init__(self):
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
