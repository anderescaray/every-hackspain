import numpy as np
import pandas as pd


LEVEL_FEATURES = [
    "tx_operating_margin", "tx_inflow_outflow_ratio", "tx_fixed_cost_coverage",
    "debt_service_to_inflow_ratio", "debt_interest_to_inflow_ratio", "tx_fee_to_inflow_ratio",
    "tx_lfl_inflow_growth", "inv_dso_median", "inv_dpo_median",
    "inv_ar_delay_median", "inv_ap_delay_median", "inv_ar_late_paid_ratio", "inv_ap_late_paid_ratio",
    "inv_ar_due_30_to_issued_ratio", "inv_ap_due_30_to_received_ratio",
]
DYNAMIC_BASES = [
    "tx_inflow", "tx_outflow", "tx_net_cashflow", "tx_operating_margin",
    "debt_service_to_inflow_ratio", "debt_interest_to_inflow_ratio", "inv_issued_amount",
    "inv_received_amount", "inv_dso_median", "inv_dpo_median", "inv_ar_overdue_ratio", "inv_ap_overdue_ratio",
]
AMOUNT_BASES = {"tx_inflow", "tx_outflow", "tx_net_cashflow", "inv_issued_amount", "inv_received_amount"}


def divide(numerator, denominator):
    return (numerator / denominator.where(denominator > 0)).replace([np.inf, -np.inf], np.nan)


def add_ratios(panel):
    p = panel.copy()
    p["tx_net_cashflow"] = p.tx_inflow - p.tx_outflow
    p["tx_operating_margin"] = divide(p.tx_net_cashflow, p.tx_inflow + p.tx_outflow)
    p["tx_inflow_outflow_ratio"] = divide(p.tx_inflow, p.tx_outflow)
    p["tx_fixed_cost_coverage"] = divide(p.tx_inflow, p.tx_fixed_cost)
    p["debt_service_to_inflow_ratio"] = divide(p.debt_principal_paid + p.debt_interest_paid, p.tx_inflow)
    p["debt_interest_to_inflow_ratio"] = divide(p.debt_interest_paid, p.tx_inflow)
    p["tx_fee_to_inflow_ratio"] = divide(p.tx_fees_paid, p.tx_inflow)
    p["inv_ar_due_30_to_issued_ratio"] = divide(p.inv_ar_due_30_amount, p.inv_issued_amount)
    p["inv_ap_due_30_to_received_ratio"] = divide(p.inv_ap_due_30_amount, p.inv_received_amount)
    return p


def add_temporal(panel, unit, config):
    p = panel.sort_values([unit, "currency", "month"]).reset_index(drop=True)
    group_keys = [p[unit], p.currency]
    additions = {}
    for col in DYNAMIC_BASES:
        grouped = p[col].groupby(group_keys, sort=False)
        for window in (3, 6):
            rolling = grouped.rolling(window, min_periods=window)
            for suffix, values in (("ma", rolling.mean()), ("std", rolling.std(ddof=0))):
                additions[f"{col}_{suffix}{window}"] = values.droplevel([0, 1]).reindex(p.index)
            slope = pd.Series(0., index=p.index)
            center = (window - 1) / 2
            for lag in range(window):
                slope += (center - lag) * grouped.shift(lag)
            additions[f"{col}_slope{window}"] = slope / sum((i - center) ** 2 for i in range(window))
        for lag in (1, 3, 6):
            delta = p[col] - grouped.shift(lag)
            additions[f"{col}_delta{lag}"] = delta
            if col in AMOUNT_BASES:
                additions[f"{col}_change{lag}_scaled"] = divide(delta, grouped.shift(lag).abs())
        previous = grouped.shift(1)
        prior = previous.groupby(group_keys, sort=False).rolling(6, min_periods=3)
        mean = prior.mean().droplevel([0, 1]).reindex(p.index)
        std = prior.std(ddof=0).droplevel([0, 1]).reindex(p.index)
        additions[f"{col}_zscore_prior6"] = divide(p[col] - mean, std)
        additions[f"{col}_yoy_change"] = divide(p[col] - grouped.shift(12), grouped.shift(12).abs())
        if col in AMOUNT_BASES:
            for window in (3, 6):
                scale = additions[f"{col}_ma{window}"].abs()
                additions[f"{col}_slope{window}_scaled"] = divide(additions[f"{col}_slope{window}"], scale)
    p = pd.concat([p, pd.DataFrame(additions)], axis=1)
    p["tx_volatility_ratio"] = divide(p.tx_net_cashflow_std3, p.tx_net_cashflow_std6)
    negative = p.tx_net_cashflow.lt(0).astype(float).where(p.tx_net_cashflow.notna())
    p["tx_negative_months_6"] = negative.groupby(group_keys).rolling(6, min_periods=6).sum().droplevel([0, 1]).reindex(p.index)
    valid = p.tx_usable_count.gt(0).astype(int)
    p["history_observed_months"] = valid.groupby(group_keys).cumsum()
    month_number = p.month.dt.year * 12 + p.month.dt.month
    previous_seen = month_number.where(p.tx_count.gt(0)).groupby(group_keys).ffill()
    p["months_since_last_transaction"] = (month_number - previous_seen).astype(float)
    recent = valid.groupby(group_keys).rolling(config.min_history_months, min_periods=config.min_history_months).sum()
    p["has_sufficient_history"] = recent.droplevel([0, 1]).reindex(p.index).eq(config.min_history_months)
    p["is_thin_month"] = p.tx_count.between(1, config.thin_month_transactions - 1)
    p["is_missing_after_onboarding"] = p.history_observed_months.gt(0) & p.tx_count.eq(0)
    p["is_training_eligible"] = (p.has_sufficient_history & p.tx_usable_count.ge(config.thin_month_transactions)
                                 & p.tx_company_coverage.eq(1))
    p["month_of_year"] = p.month.dt.month
    return p


def model_columns(columns):
    allowed = list(LEVEL_FEATURES) + ["tx_volatility_ratio", "tx_negative_months_6", "month_of_year"]
    for col in DYNAMIC_BASES:
        allowed += [f"{col}_zscore_prior6", f"{col}_yoy_change"]
        if col in AMOUNT_BASES:
            allowed += [f"{col}_change{lag}_scaled" for lag in (1, 3, 6)]
            allowed += [f"{col}_slope{window}_scaled" for window in (3, 6)]
        else:
            suffixes = ("std", "slope") if "overdue_ratio" in col else ("ma", "std", "slope")
            allowed += [f"{col}_{suffix}{window}" for suffix in suffixes for window in (3, 6)]
            allowed += [f"{col}_delta{lag}" for lag in (1, 3, 6)]
    return [col for col in allowed if col in columns]
