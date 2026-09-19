"""One deterministic economic interpretation of each cleaned transaction.

Categories are evidence, not unquestionable truth. Unpaired transfers, generic
fees and ambiguous directions remain uncertain. Quality-excluded rows are kept
in the ledger, but never contribute financial amounts. No snapshot debt balance
or machine-learning/reference score is used here.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from xray.ledger.contracts import CLASSIFICATION_VERSION
from xray.ledger.enrichment import apply_ai_categories, load_template_categories

INFLOW = frozenset({"collection", "bulk_collection", "pos_settlement", "cash_settlement",
                    "cash_settlements", "payment_refund", "tax_refund"})
OUTFLOW = frozenset({"payment", "bulk_payment", "utility", "salary", "social_security",
                     "tax", "collection_refund"})
FIXED = frozenset({"salary", "social_security", "tax", "utility"})
QUALITY_FLAGS = ("is_extreme_amount", "is_relative_outlier", "is_sync_duplicate",
                 "is_unknown_product", "has_invalid_exchange_rate")
UNPAIRED = frozenset({"transfer", "cash_withdrawal", "pos_withdrawal"})


def _bool(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame[name].fillna(False).astype(bool) if name in frame else pd.Series(False, index=frame.index)


def classification_metadata(ai_categories_path: str | Path | None = None,
                            ai_min_confidence: float = 0.7) -> dict[str, Any]:
    """Explicit method/evidence identities, including for an empty ledger."""
    if not 0 <= ai_min_confidence <= 1:
        raise ValueError("ai_min_confidence must be in [0, 1]")
    classification_config = {"classification_version": CLASSIFICATION_VERSION,
        "enrichment_version": "jev-static-v1", "enrichment_enabled": ai_categories_path is not None,
        "ai_min_confidence": ai_min_confidence if ai_categories_path is not None else None}
    config_hash = hashlib.sha256(json.dumps(classification_config, sort_keys=True).encode()).hexdigest()
    evidence_hash = hashlib.sha256(Path(ai_categories_path).read_bytes()).hexdigest() if ai_categories_path is not None else None
    method_version = CLASSIFICATION_VERSION + ("+jev-" + config_hash[:12] if ai_categories_path is not None else "")
    return {"classification_version": method_version, "config_hash": config_hash,
            "evidence_hash": evidence_hash, "config": classification_config}


def classify_transactions(transactions: pd.DataFrame, *, as_of: Any = None,
                          ai_categories_path: str | Path | None = None,
                          ai_min_confidence: float = 0.7) -> pd.DataFrame:
    """Cleaned transactions → full ledger. ``as_of`` is an inclusive date cutoff.

    Negative debt principal/interest have priority over own-mirror flags: the
    positive settlement counterleg stays circulation, preventing either erased
    service or double counting. A group candidate remains group/uncertain support,
    not assumed commercial or contractual external debt.
    """
    metadata = classification_metadata(ai_categories_path, ai_min_confidence)
    config_hash, evidence_hash = metadata["config_hash"], metadata["evidence_hash"]
    method_version = metadata["classification_version"]
    required = {"transaction_id", "company_id", "product_id", "date", "amount", "status", "exchange_rate"}
    missing = required - set(transactions)
    if missing:
        raise ValueError(f"Ledger input missing columns: {sorted(missing)}")
    t = transactions.copy()
    t["date"] = pd.to_datetime(t.date, errors="raise")
    if t.date.isna().any():
        raise ValueError("Ledger dates must be known")
    if as_of is not None:
        stop = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)
        t = t.loc[t.date.lt(stop)].copy()
    if t.transaction_id.isna().any() or t.transaction_id.duplicated().any():
        raise ValueError("Ledger transaction_id must be non-null and unique")
    t["amount"] = pd.to_numeric(t.amount, errors="raise").astype(float)
    if not np.isfinite(t.amount).all():
        raise ValueError("Ledger amounts must be finite")
    if "currency" not in t:
        t["currency"] = t.get("product_currency", pd.Series(pd.NA, index=t.index, dtype="string"))
    t["currency"] = t.currency.astype("string")
    invalid_currency = ~t.currency.str.fullmatch(r"[A-Z]{3}").fillna(False)
    t["source_currency"] = t.currency
    t.loc[invalid_currency, "currency"] = pd.NA
    t["category"] = t.get("category", pd.Series("uncategorized", index=t.index)).fillna("uncategorized").astype(str).str.lower()
    t["description"] = t.get("description", pd.Series("", index=t.index)).fillna("").astype(str)
    if ai_categories_path is not None:
        t = apply_ai_categories(t, load_template_categories(ai_categories_path), ai_min_confidence)
    else:
        t["category_bank"] = t.category
        t["category_source"] = np.where(t.category.eq("uncategorized"), "none", "bank")
        t["category_ai_confidence"] = np.nan
    t["month"] = t.date.dt.to_period("M").dt.to_timestamp()
    t["classification_version"] = method_version
    t["classification_config_hash"] = config_hash
    t["classification_evidence_hash"] = evidence_hash
    t["is_internal_candidate"] = _bool(t, "is_internal_transfer")
    t["is_group_candidate"] = _bool(t, "is_intragroup")
    quality = pd.DataFrame({name: _bool(t, name) for name in QUALITY_FLAGS}, index=t.index)
    fx_ok = pd.to_numeric(t.exchange_rate, errors="coerce").eq(1)
    t["eligible"] = (t.status.eq("booked") & fx_ok & t.currency.notna()
                     & t.currency.str.fullmatch(r"[A-Z]{3}").fillna(False) & ~quality.any(axis=1))
    t["economic_class"] = "uncertain"
    t["economic_subclass"] = "unidentified"
    t["classification_rule"] = "CT99-insufficient-evidence"
    t["classification_confidence"] = "low"
    available = t.eligible.copy()

    def assign(mask: pd.Series, cls: str, sub: str, rule: str, confidence: str = "high") -> None:
        nonlocal available
        chosen = mask.fillna(False) & available
        t.loc[chosen, ["economic_class", "economic_subclass", "classification_rule", "classification_confidence"]] = [cls, sub, rule, confidence]
        available &= ~chosen

    pos, neg = t.amount.gt(0), t.amount.lt(0)
    cat = t.category
    # Anonymized names do not suffice for economic inference. These exact semantic
    # templates override known mislabelled categories, not arbitrary NLP guesses.
    text = t.description.str.normalize("NFKD").str.replace("[\u0300-\u036f]", "", regex=True).str.upper()
    gateway_cost = _bool(t, "is_gateway_cost") | text.str.contains(r"^\[[^\]]*\]\s*(?:STRIPE_FEE|NETWORK_COST)\s*$", regex=True)
    gateway = t.get("gateway_kind", pd.Series(pd.NA, index=t.index, dtype="string"))
    assign(t.is_group_candidate, "group_or_internal", "group_transfer_candidate", "CT01-group-mirror", "medium")
    assign(gateway_cost & neg, "operating", "payment_processing_fee", "CT02-verified-gateway-cost")
    assign(cat.eq("debt_repayment") & neg, "debt_service", "debt_principal", "CT03-principal-paid")
    assign(cat.eq("interest_charge") & neg & gateway.isna(), "debt_service", "debt_interest", "CT04-financial-interest")
    fee_verified = _bool(t, "is_verified_financing_fee") | text.str.contains(
        r"(?:COMISION(?:ES)?\s+(?:DE\s+)?(?:APERTURA|AMORTIZACION|CANCELACION)\s+(?:DE\s+)?(?:PRESTAMO|CREDITO)|LOAN\s+(?:ORIGINATION|FINANCING)\s+FEE)", regex=True)
    assign(cat.eq("fee") & fee_verified & neg, "debt_service", "financial_fee", "CT05-verified-financing-fee")
    assign(t.is_internal_candidate, "own_account_circulation", "own_transfer", "CT06-own-mirror", "medium")
    drawdown = cat.isin({"loan_drawdown", "loan_disbursement", "financing_received", "loan_received"}) | text.str.contains(
        r"(?:LOAN\s+(?:DRAWDOWN|DISBURSEMENT|RECEIVED)|PRESTAMO\s+RECIBIDO|ABONO\s+(?:DE\s+)?PRESTAMO|DISPOSICION\s+(?:DE\s+)?(?:PRESTAMO|CREDITO))", regex=True)
    assign(drawdown & pos, "external_financing", "loan_drawdown", "CT07-loan-drawdown")
    scf = _bool(t, "is_scf_adjustment") | text.str.startswith("SCF-AJUS.SALDO")
    assign(scf, "external_financing", "scf_adjustment", "CT08-scf-adjustment", "medium")
    repo = _bool(t, "is_repo_pair") | text.str.contains(r"^(?:PR|VT)\.A\b", regex=True)
    assign(repo | cat.isin({"investment_deployment", "investment_return"}), "investment", "investment_movement", "CT09-investment")
    # Both refund labels changed meaning in the raw source around Jan 2025.
    refunds = cat.isin({"payment_refund", "collection_refund", "tax_refund"})
    assign(refunds & pos, "operating", "operating_refund_received", "CT10-refund-sign")
    assign(refunds & neg, "operating", "operating_refund_paid", "CT10-refund-sign")
    assign(cat.isin(INFLOW) & pos, "operating", "operating_collection", "CT11-operating-collection")
    for category in sorted(FIXED):
        assign(cat.eq(category) & neg, "operating", category, f"CT12-{category}")
    assign(cat.isin(OUTFLOW) & neg, "operating", "operating_payment", "CT13-operating-payment")
    assign(cat.isin(UNPAIRED) | _bool(t, "is_cash_disposal"), "uncertain", "unpaired_transfer", "CT90-unpaired-transfer", "low")
    assign(cat.eq("fee"), "uncertain", "unverified_fee", "CT91-unverified-fee", "low")
    t.loc[~t.eligible, ["economic_class", "economic_subclass", "classification_rule", "classification_confidence"]] = [
        "uncertain", "quality_excluded", "CT00-not-eligible", "none"]
    # Cache confidence is evidence, not verified bank/financial provenance.
    ai = t.category_source.eq("ai")
    t.loc[ai & ~t.economic_class.eq("uncertain"), "classification_confidence"] = "medium"
    t.loc[ai, "classification_rule"] = t.loc[ai, "classification_rule"] + "+JEV-static"
    t["is_uncertain"] = t.economic_class.eq("uncertain")
    t["included_in_operating_inflows"] = t.eligible & t.economic_class.eq("operating") & pos
    t["included_in_operating_outflows"] = t.eligible & t.economic_class.eq("operating") & neg
    t["included_in_debt_service"] = t.eligible & t.economic_class.eq("debt_service") & neg
    flag_arrays = {name: series.to_numpy() for name, series in quality.items()}
    flag_arrays.update({"not_booked": ~t.status.eq("booked").to_numpy(),
                        "ambiguous_currency_or_fx": (~fx_ok | t.currency.isna()).to_numpy(),
                        "uncertain_classification": t.is_uncertain.to_numpy(),
                        "internal_mirror_candidate": t.is_internal_candidate.to_numpy(),
                        "group_mirror_candidate": t.is_group_candidate.to_numpy(),
                        "static_ai_category_evidence": ai.to_numpy()})
    t["flags"] = [[name for name, values in flag_arrays.items() if values[i]] for i in range(len(t))]
    prior = t.get("source_lineage", pd.Series([None] * len(t), index=t.index, dtype=object))
    source_rows = t.get("_source_row_number", pd.Series([None] * len(t), index=t.index, dtype=object))
    lineages = []
    for lineage, txid, source_row, category_source in zip(prior, t.transaction_id, source_rows, t.category_source):
        value = dict(lineage) if isinstance(lineage, dict) else {}
        value.update(table="transactions", source_table="transactions.csv", transaction_id=str(txid))
        if source_row is not None and pd.notna(source_row):
            value["source_row_number"] = int(source_row)
        if evidence_hash is not None:
            value["classification_evidence_hash"] = evidence_hash
            value["classification_config_hash"] = config_hash
            value["category_source"] = str(category_source)
        lineages.append(value)
    t["source_lineage"] = lineages
    result = t.sort_values(["company_id", "currency", "date", "transaction_id"], na_position="last").reset_index(drop=True)
    result.attrs["classification_metadata"] = metadata
    return result
