"""Additive Debt evidence; never changes the canonical economic classification.

The current source can suggest a financing fee but cannot certify that an
unidentified payment is financially impossible debt service. In particular a
withdrawal or transfer is a channel, not proof of the eventual use of cash.
"""
from typing import Literal

import pandas as pd

DEBT_UNCERTAINTY_VERSION = "debt-uncertainty-v1"
DebtUncertaintyStatus = Literal[
    "not_applicable", "debt_possible", "debt_impossible", "debt_unresolved",
]
DEBT_UNCERTAINTY_STATUSES = (
    "not_applicable", "debt_possible", "debt_impossible", "debt_unresolved",
)
DEBT_UNCERTAINTY_COLUMNS = (
    "debt_possible_uncertain_outflows", "debt_impossible_uncertain_outflows",
    "debt_unresolved_uncertain_outflows", "potentially_financial_uncertain_outflows",
)


def assess_debt_uncertainty(ledger: pd.DataFrame, *, copy: bool = True) -> pd.DataFrame:
    """Attach a conservative, reproducible assessment to each canonical row.

    References name fields on the same ledger row; ``source_lineage`` anchors
    them to the original transaction ID and raw source row. No caller-supplied
    assessment is trusted: recomputing also prevents stale tags in hypotheses.
    No rule in this version emits ``debt_impossible``. That state is reserved
    for a future explicitly versioned rule with affirmative financial evidence.
    """
    result = ledger.copy() if copy else ledger
    relevant = result.eligible & result.is_uncertain & result.amount.lt(0)
    bank_category = result.get("category_bank", pd.Series(None, index=result.index, dtype=object))
    category_source = result.get("category_source", pd.Series(None, index=result.index, dtype=object))
    possible_fee = (relevant & bank_category.eq("fee") & category_source.eq("bank")
                    & result.economic_subclass.eq("unverified_fee"))
    result["debt_uncertainty_status"] = "not_applicable"
    result["debt_uncertainty_rule"] = "DU00-outside-eligible-uncertain-outflows"
    result.loc[relevant, "debt_uncertainty_status"] = "debt_unresolved"
    result.loc[relevant, "debt_uncertainty_rule"] = "DU99-insufficient-financial-evidence"
    result.loc[possible_fee, "debt_uncertainty_status"] = "debt_possible"
    result.loc[possible_fee, "debt_uncertainty_rule"] = "DU01-bank-generic-fee-may-include-financing"
    result["debt_uncertainty_version"] = DEBT_UNCERTAINTY_VERSION
    references = ("source_lineage.transaction_id", "classification_rule", "economic_subclass",
                  "category_bank", "category_source")
    # Immutable shared tuples avoid millions of identical lists during batch runs.
    result["debt_uncertainty_evidence_refs"] = [references if value else () for value in relevant]
    return result
