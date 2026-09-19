from dataclasses import dataclass
import math


PANELS = {
    "company": ("company_id", "company_monthly_features.parquet"),
    "company_currency": ("company_id", "company_currency_monthly_features.parquet"),
    "group_currency": ("group_id", "group_currency_monthly_features.parquet"),
}


@dataclass(frozen=True)
class ScoreConfig:
    panel: str = "company"
    reference_months: int = 12
    holdout_fraction: float = 0.2
    split_seed: int = 20260918
    min_transactions: int = 5
    min_usable_share: float = 0.8
    min_operating_share: float = 0.1
    min_level_coverage: float = 0.4
    momentum_weight: float = 0.2

    def __post_init__(self):
        if self.panel not in PANELS:
            raise ValueError(f"Panel desconocido: {self.panel}")
        if self.reference_months < 1 or self.min_transactions < 1:
            raise ValueError("Las ventanas y mínimos deben ser positivos")
        for name in ("holdout_fraction", "min_usable_share", "min_operating_share", "min_level_coverage", "momentum_weight"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} debe estar entre 0 y 1")
        if self.holdout_fraction >= 1:
            raise ValueError("Debe quedar algún grupo de referencia")

    @property
    def unit(self):
        return PANELS[self.panel][0]

    @property
    def feature_file(self):
        return PANELS[self.panel][1]
