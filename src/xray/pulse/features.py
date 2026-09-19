"""Six complete calendar months, deterministic facts and observable evidence only."""
import math
from dataclasses import dataclass
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from xray.pulse.config import PulseConfig, load_config
from xray.pulse.contracts import json_safe

MONEY = ("operating_inflows", "operating_outflows", "operating_net_cash", "debt_principal_paid",
         "debt_interest_paid", "verified_financing_fees", "debt_service_paid")


def complete_months(as_of: str | pd.Timestamp, window: int = 6) -> pd.DatetimeIndex:
    cutoff = pd.Timestamp(as_of)
    if pd.isna(cutoff) or cutoff.tzinfo is not None:
        raise ValueError("as_of must be a valid timezone-naive calendar date")
    current = cutoff.to_period("M")
    last = current if cutoff.normalize() == current.end_time.normalize() else current - 1
    return pd.date_range((last - window + 1).start_time, last.start_time, freq="MS")


def theil_sen(values: list[float]) -> float:
    return float(median((values[b] - values[a]) / (b - a)
                        for a in range(len(values)) for b in range(a + 1, len(values))))


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sum(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame or not all(_finite(v) for v in frame[column]):
        return None
    return math.fsum(float(v) for v in frame[column])


def _flags(frame: pd.DataFrame) -> list[str]:
    found: set[str] = set()
    if "flags" in frame:
        for value in frame["flags"]:
            if isinstance(value, (list, tuple, np.ndarray)):
                found.update(str(v) for v in value)
    return sorted(found)


@dataclass
class FeatureWindow:
    frame: pd.DataFrame
    features: dict[str, dict[str, Any]]
    sums: dict[str, float | None]
    diagnostics: dict[str, Any]
    confidence: dict[str, Any]
    flags: list[str]
    evidence: dict[str, Any]
    window: dict[str, Any]
    debt_status: str
    debt_reason: str

    def to_dict(self) -> dict[str, Any]:
        return json_safe({k: v for k, v in self.__dict__.items() if k != "frame"})


def extract_features(facts: pd.DataFrame, *, company_id: str, currency: str,
                     as_of: str | pd.Timestamp, config: PulseConfig | None = None) -> FeatureWindow:
    config = config or load_config()
    policy = config.to_dict()
    required = {"company_id", "currency", "month", "history_observed", *MONEY}
    if missing := required.difference(facts.columns):
        raise ValueError(f"Monthly facts contract missing: {sorted(missing)}")
    months = complete_months(as_of, policy["window_months"])
    frame = facts.loc[facts.company_id.eq(company_id) & facts.currency.eq(currency)].copy()
    frame["month"] = pd.to_datetime(frame.month)
    frame = frame.loc[frame.month.isin(months)]
    if frame.month.duplicated().any():
        raise ValueError("Monthly facts have duplicate company/currency/month keys")
    frame = frame.set_index("month").reindex(months).rename_axis("month").reset_index()
    observed = frame.history_observed.eq(True)
    complete = bool(observed.all())
    finite = bool(frame[list(MONEY[:3])].map(_finite).all().all())
    debt_finite = bool(frame[list(MONEY[3:])].map(_finite).all().all())
    for col in MONEY:
        if col != "operating_net_cash" and any(_finite(v) and float(v) < 0 for v in frame[col]):
            raise ValueError(f"{col} must be a nonnegative magnitude")
    for row in frame.itertuples():
        if all(_finite(getattr(row, col)) for col in MONEY[:3]):
            net = float(row.operating_inflows) - float(row.operating_outflows)
            # Reconciliation tolerates only floating summation representation, never fills denominators.
            representation_error = math.ulp(float(row.operating_inflows)) + math.ulp(float(row.operating_outflows))
            if abs(net - row.operating_net_cash) > representation_error:
                raise ValueError("operating_net does not reconcile with inflows minus outflows")
        if all(_finite(getattr(row, col)) for col in MONEY[3:]):
            row_service = math.fsum((float(row.debt_principal_paid), float(row.debt_interest_paid),
                                    float(row.verified_financing_fees)))
            if not math.isclose(row_service, row.debt_service_paid, rel_tol=1e-12, abs_tol=0.):
                raise ValueError("debt_service_paid does not reconcile; possible double counting")
    sums = {col: _sum(frame, col) for col in MONEY}
    window = {"months": [str(m.date()) for m in months], "start": str(months[0].date()),
              "end": str((months[-1] + pd.offsets.MonthEnd(0)).date()), "count": len(months),
              "observed_months": int(observed.sum())}
    flags = _flags(frame)
    base_reason = "insufficient_six_month_history" if not complete else "invalid_monthly_facts" if not finite else None
    i, o, n, service = (sums[k] for k in ("operating_inflows", "operating_outflows", "operating_net_cash", "debt_service_paid"))
    op_reason = base_reason or ("zero_operating_outflows" if o == 0 else None)
    nets = [float(v) for v in frame.operating_net_cash] if complete and finite else []
    beta = theil_sen(nets) if nets else None
    downside = math.fsum(max(-v, 0.) for v in nets) if nets else None
    uncertain_out = _sum(frame, "uncertain_outflows")
    excluded_out = _sum(frame, "excluded_outflows")
    unknown_currency = _sum(frame, "unknown_currency_count")
    ambiguous_currency = _sum(frame, "ambiguous_currency_count")
    currency_issue = bool((unknown_currency or 0) > 0 or (ambiguous_currency or 0) > 0)
    if base_reason or not debt_finite:
        debt_status, debt_reason = "partial" if service and service > 0 else "unknown", base_reason or "invalid_debt_facts"
    elif service == 0:
        debt_status, debt_reason = "unknown", "no_identified_service_is_not_verified_absence"
    elif uncertain_out is None or excluded_out is None:
        debt_status, debt_reason = "partial", "outflow_evidence_unavailable"
    elif uncertain_out > 0 or excluded_out > 0 or currency_issue:
        debt_status, debt_reason = "partial", "uncertain_or_excluded_outflows"
    else:
        debt_status, debt_reason = "verified", "six_month_identified_observed_service"
    debt_reason_missing = ("zero_operating_inflows" if i == 0 else None) if debt_status == "verified" else debt_reason

    g_raw = m_raw = d_raw = s_raw = None
    if not op_reason:
        assert n is not None and o is not None and o > 0 and beta is not None and downside is not None
        g_raw, m_raw, d_raw = n / o, 3 * beta / (o / 6), downside / o
    if not debt_reason_missing:
        assert service is not None and i is not None and i > 0
        s_raw = service / i

    def feature(name: str, raw: float | None, numerator: float | None, denominator: float | None,
                reason: str | None, **extra: Any) -> dict[str, Any]:
        return {"raw": raw if not reason else None, "numerator": numerator, "denominator": denominator,
                "window6m": window, "formula_id": policy["formulas"][name],
                "anchors": policy["anchors"][name], "missing_reason": reason, **extra}

    features = {
        "generation_ratio": feature("generation", g_raw, n, o, op_reason),
        "operating_net_trend": feature("momentum", m_raw,
                                        None if beta is None else 3 * beta, None if o is None else o / 6,
                                        op_reason, theil_sen_beta=beta, semantics="nowcast_not_forecast"),
        "operating_downside_ratio": feature("resilience", d_raw,
                                            downside, o, op_reason),
        "observed_debt_service_burden": feature("debt_obligations", s_raw,
                                                service, i, debt_reason_missing,
                                                breakdown={k: sums[k] for k in ("debt_principal_paid", "debt_interest_paid", "verified_financing_fees")}),
    }
    diagnostics = resilience_diagnostics(nets, o, policy["diagnostics"]["material_deficit_share"])
    abs_total = _sum(frame, "classified_amount")
    uncertain = _sum(frame, "uncertain_amount")
    denominator = abs_total + uncertain if abs_total is not None and uncertain is not None else None
    coverage = abs_total / denominator if abs_total is not None and denominator is not None and denominator > 0 else None
    products = [tuple(sorted(str(p) for p in v)) if isinstance(v, (list, tuple, np.ndarray)) else ()
                for v in frame.get("active_product_ids", pd.Series([None] * len(frame)))]
    active_sets = [set(v) for v in products if v]
    perimeter = "stable_observed" if len(active_sets) == 6 and all(s == active_sets[0] for s in active_sets) else "changed_or_unverified"
    confidence = {"history_coverage": float(observed.sum()) / 6,
                  "classification_coverage": coverage, "uncertain_amount_share": None if coverage is None else 1 - coverage,
                  "perimeter_consistency": perimeter,
                  "currency_consistency": {"status": "partial" if currency_issue else "unverified_source_coverage", "currency": currency,
                                           "method": "separate_currency_panel_no_conversion",
                                           "unknown_currency_count": unknown_currency, "ambiguous_currency_count": ambiguous_currency},
                  "debt_evidence": {"status": debt_status, "reason": debt_reason,
                                    "scope": "observed_cash_service_not_total_contractual_obligations"}}
    evidence = {"observed_product_ids": sorted(set().union(*active_sets)) if active_sets else [],
                "perimeter_method": "active_account_sets_not_verified_observability",
                "monthly_product_ids": products, "facts_months": window["months"], "debt_evidence_status": debt_status}
    if base_reason:
        flags.append(base_reason)
    if debt_status != "verified":
        flags.append(f"debt_evidence_{debt_status}")
    if perimeter != "stable_observed":
        flags.append("perimeter_not_verified_comparable")
    if currency_issue:
        flags.append("currency_evidence_incomplete")
    return FeatureWindow(frame, features, sums, diagnostics, confidence, sorted(set(flags)), evidence,
                         window, debt_status, debt_reason)


def resilience_diagnostics(nets: list[float], outflows: float | None, material_share: float) -> dict[str, Any]:
    if not nets:
        return dict.fromkeys(("negative_months", "material_negative_months", "open_negative_episode",
                              "episode_duration", "recovery_duration", "worst_month"))
    trailing = 0
    for value in reversed(nets):
        if value >= 0:
            break
        trailing += 1
    since_recovery = None
    if trailing == 0:
        negatives = [i for i, v in enumerate(nets) if v < 0]
        if negatives:
            since_recovery = len(nets) - 1 - negatives[-1]
    threshold = (outflows or 0) / 6 * material_share
    return {"negative_months": sum(v < 0 for v in nets),
            "material_negative_months": sum(v < -threshold for v in nets),
            "open_negative_episode": trailing > 0, "episode_duration": trailing,
            "recovery_duration": since_recovery, "worst_month": min(nets),
            "recovery_definition": "observed_months_since_last_negative_not_future_recovery"}
