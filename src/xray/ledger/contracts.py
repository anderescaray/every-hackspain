"""Typed contracts for observed cash; independent of product and score engines."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd

from xray.ledger.debt_uncertainty import (
    DEBT_UNCERTAINTY_STATUSES,
    DEBT_UNCERTAINTY_VERSION,
    DebtUncertaintyStatus,
)

SCHEMA_VERSION = "1.0"
CLEANING_VERSION = "cleaning-v2"
CLASSIFICATION_VERSION = "cash-truth-v2"
FACTS_VERSION = "monthly-facts-v2"
ECONOMIC_CLASSES = (
    "operating", "own_account_circulation", "group_or_internal", "external_financing",
    "debt_service", "investment", "uncertain",
)
DebtEvidenceStatus = Literal["verified", "partial", "unknown"]


def json_safe(value: Any) -> Any:
    """JSON primitives only: unavailable numbers become null, never NaN/Infinity."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


@dataclass(frozen=True)
class LedgerTransaction:
    transaction_id: str
    company_id: str
    product_id: str
    date: str
    currency: str | None
    amount: float
    economic_class: str
    economic_subclass: str
    classification_rule: str
    classification_version: str
    classification_confidence: str
    included_in_operating_inflows: bool
    included_in_operating_outflows: bool
    included_in_debt_service: bool
    is_internal_candidate: bool
    is_group_candidate: bool
    is_uncertain: bool
    flags: list[str] = field(default_factory=list)
    source_lineage: dict[str, Any] = field(default_factory=dict)
    debt_uncertainty_status: DebtUncertaintyStatus = "not_applicable"
    debt_uncertainty_rule: str = "DU00-outside-eligible-uncertain-outflows"
    debt_uncertainty_evidence_refs: list[str] = field(default_factory=list)
    debt_uncertainty_version: str = DEBT_UNCERTAINTY_VERSION

    def __post_init__(self) -> None:
        if self.economic_class not in ECONOMIC_CLASSES:
            raise ValueError("Unknown economic class")
        if not np.isfinite(self.amount):
            raise ValueError("Ledger amount must be finite")
        if self.debt_uncertainty_status not in DEBT_UNCERTAINTY_STATUSES:
            raise ValueError("Unknown Debt uncertainty assessment")
        if self.debt_uncertainty_status != "not_applicable" and (not self.is_uncertain or self.amount >= 0):
            raise ValueError("Debt uncertainty requires an uncertain outflow")
        if self.debt_uncertainty_status == "debt_impossible" and not self.debt_uncertainty_evidence_refs:
            raise ValueError("Financial impossibility requires affirmative evidence")
        if sum((self.included_in_operating_inflows, self.included_in_operating_outflows,
                self.included_in_debt_service)) > 1:
            raise ValueError("A transaction cannot contribute to two financial flows")

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class MonthlyFacts:
    company_id: str
    currency: str
    month: str
    operating_inflows: float | None
    operating_outflows: float | None
    operating_net_cash: float | None
    debt_principal_paid: float | None
    debt_interest_paid: float | None
    verified_financing_fees: float | None
    debt_service_paid: float | None
    external_financing_inflows: float | None
    external_financing_outflows: float | None
    eligible_net_cash: float | None
    internal_or_group_flows: float | None
    investment_flows: float | None
    uncertain_inflows: float | None
    uncertain_outflows: float | None
    transaction_count: int
    classified_amount: float | None
    uncertain_amount: float | None
    classification_coverage: float | None
    history_observed: bool
    debt_evidence_status: DebtEvidenceStatus
    debt_evidence_reason: str
    debt_possible_uncertain_outflows: float | None = None
    debt_impossible_uncertain_outflows: float | None = None
    debt_unresolved_uncertain_outflows: float | None = None
    potentially_financial_uncertain_outflows: float | None = None
    debt_uncertainty_version: str = DEBT_UNCERTAINTY_VERSION
    active_product_ids: list[str] = field(default_factory=list)
    facts_version: str = FACTS_VERSION
    classification_version: str = CLASSIFICATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class CashTruthResult:
    company_id: str
    currency: str
    as_of: str
    summary: dict[str, float | None]
    coverage: dict[str, Any]
    classes: list[dict[str, Any]]
    evidence: dict[str, Any]
    critical_movements: list[dict[str, Any]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    classification_version: str = CLASSIFICATION_VERSION
    facts_version: str = FACTS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))
