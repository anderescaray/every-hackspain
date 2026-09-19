from dataclasses import dataclass
import math

from xray.score.config import PANELS


@dataclass(frozen=True)
class ScoreV2Config:
    """Parámetros de `financial_smoothed_v2`.

    Nivel: ratios de flujos agregados en una ventana de `level_window` meses (mínimo
    `level_min_months` meses con calidad). Momentum: trimestre reciente frente al
    trimestre anterior (`momentum_window` meses cada uno, mínimo `momentum_min_months`).
    Los umbrales de calidad mensual son los mismos que en V1; a diferencia de V1, un mes
    actual fino no impide puntuar si la ventana tiene soporte, pero deja el score como
    `provisional` con motivo explícito.
    """

    panel: str = "company"
    level_window: int = 6
    level_min_months: int = 3
    momentum_window: int = 3
    momentum_min_months: int = 2
    min_delay_count: int = 5
    growth_log_clip: float = 1.5
    reference_months: int = 24
    holdout_fraction: float = 0.2
    split_seed: int = 20260918
    min_transactions: int = 5
    min_usable_share: float = 0.8
    min_operating_share: float = 0.1
    min_level_coverage: float = 0.4
    momentum_weight: float = 0.2
    min_momentum_coverage: float = 0.5
    volatility_window: int = 12
    volatility_min_months: int = 4
    sigma_floor_margin: float = 0.05
    sigma_floor_debt: float = 0.02
    sigma_floor_delay: float = 3.0
    sigma_floor_growth: float = 0.05
    z_clip: float = 4.0
    z_scale: float = 2.0
    direction_z: float = 1.5
    hysteresis: float = 0.5
    atypical_z: float = 2.0
    # Estacionalidad del crecimiento de entradas (hallazgos-datos.md §3): factores por mes del año estimados
    # con la referencia y restados de inflow_growth_q / inflow_growth_m1. Mínimo de filas por mes del año.
    seasonal_adjustment: bool = True
    seasonal_min_rows: int = 50

    def __post_init__(self):
        if self.seasonal_min_rows < 1:
            raise ValueError("seasonal_min_rows debe ser positivo")
        if self.panel not in PANELS:
            raise ValueError(f"Panel desconocido: {self.panel}")
        for name in ("level_window", "level_min_months", "momentum_window", "momentum_min_months",
                     "min_delay_count", "reference_months", "min_transactions"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} debe ser positivo")
        if self.level_min_months > self.level_window or self.momentum_min_months > self.momentum_window:
            raise ValueError("El mínimo de meses no puede superar la ventana")
        if 2 * self.momentum_window > self.level_window:
            raise ValueError("Dos trimestres de momentum deben caber en la ventana de nivel")
        for name in ("holdout_fraction", "min_usable_share", "min_operating_share", "min_level_coverage",
                     "momentum_weight", "min_momentum_coverage"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} debe estar entre 0 y 1")
        if self.holdout_fraction >= 1:
            raise ValueError("Debe quedar algún grupo de referencia")
        for name in ("growth_log_clip", "sigma_floor_margin", "sigma_floor_debt", "sigma_floor_delay",
                     "sigma_floor_growth", "z_clip", "z_scale", "direction_z", "atypical_z"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} debe ser positivo")
        if self.direction_z >= self.z_clip:
            raise ValueError("direction_z debe ser alcanzable dentro del recorte z_clip")
        if not math.isfinite(self.hysteresis) or not 0 < self.hysteresis <= 1:
            raise ValueError("hysteresis debe estar en (0, 1]: fracción de direction_z que mantiene una dirección confirmada")
        if self.volatility_window < 2 or self.volatility_min_months < 2 or self.volatility_min_months > self.volatility_window:
            raise ValueError("La ventana de volatilidad necesita al menos dos meses y un mínimo coherente")

    @property
    def direction_threshold(self):
        """Puntos de momentum respecto a 50 que equivalen a |z agregado| = direction_z."""
        return 50 * math.tanh(self.direction_z / self.z_scale)

    @property
    def unit(self):
        return PANELS[self.panel][0]

    @property
    def feature_file(self):
        return PANELS[self.panel][1]
