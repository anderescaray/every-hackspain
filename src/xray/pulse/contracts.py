"""Backend-independent, finite JSON contracts for PulseFourPillars."""
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

PILLARS = ("generation", "momentum", "resilience", "debt_obligations")


def json_safe(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


@dataclass
class PulseScoreResult:
    company_id: str
    currency: str
    as_of: str
    score_version: str
    classification_version: str
    run_id: str
    status: str
    health: float | None
    pillars: dict[str, dict[str, Any]]
    known_weight: float
    health_min: float
    health_max: float
    missing_components: list[str]
    confidence: dict[str, Any]
    lineage: dict[str, Any]
    schema_version: str = "1.0"
    config_version: str = "pulse-config-v1"
    facts_version: str = "monthly-facts-v1"
    cleaning_version: str = "cleaning-v1"
    bounds_kind: str = "identification_bounds_not_confidence_interval"
    direction: str = "unknown"
    raw_features: dict[str, Any] = field(default_factory=dict)
    normalized_features: dict[str, Any] = field(default_factory=dict)
    contributions: dict[str, float | None] = field(default_factory=dict)
    economic_facts: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    critical_movements: list[dict[str, Any]] = field(default_factory=list)
    change: dict[str, Any] = field(default_factory=dict)
    robustness: dict[str, Any] = field(default_factory=dict)
    health_evidence: str | None = None
    identified_range: dict[str, Any] | None = None
    composition_version: str | None = None
    operating_health: float | None = None
    extended_health: float | None = None
    health_level: str | None = None
    insights_available: list[str] = field(default_factory=list)
    missing_modules: list[str] = field(default_factory=list)
    operating_weights: dict[str, float] = field(default_factory=dict)
    operating_contributions: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = json_safe(asdict(self))
        if self.health_evidence is None:
            result.pop("health_evidence")
            result.pop("identified_range")
        if self.composition_version is None:
            for key in ("composition_version", "operating_health", "extended_health", "health_level",
                        "insights_available", "missing_modules", "operating_weights", "operating_contributions"):
                result.pop(key)
        json.dumps(result, allow_nan=False)
        return result
