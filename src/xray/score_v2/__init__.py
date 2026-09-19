"""`financial_smoothed_v2`: score de salud financiera suavizado, con nivel de ventana,
momentum trimestre-contra-trimestre y separación explícita entre mes atípico y tendencia.

V1 (`xray.score`) se conserva intacto como control.
"""
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import METHOD, fit_reference_bundle, score_panel, validate_scores
from xray.score_v2.pipeline import run, validate_saved_scores

__all__ = ["METHOD", "ScoreV2Config", "fit_reference_bundle", "score_panel", "validate_scores", "run", "validate_saved_scores"]
