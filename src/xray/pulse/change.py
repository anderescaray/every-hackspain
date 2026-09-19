"""Observed changes, separated from changes in evidence and methodology."""
from typing import Any

from xray.pulse.contracts import PulseScoreResult


def attribute_change(current: PulseScoreResult, previous: PulseScoreResult | dict | None) -> dict[str, Any]:
    if previous is None:
        return {"previous_health": None, "delta": None, "comparable_to_previous": False,
                "interpretation": "no_previous_result", "attribution": {"economic": {}, "evidence": {}, "methodology": {}}}
    before = previous.to_dict() if isinstance(previous, PulseScoreResult) else previous
    if before.get("company_id") != current.company_id or before.get("currency") != current.currency:
        raise ValueError("Previous result must refer to the same company and currency")
    after = current.to_dict()
    method = {}
    for key in ("score_version", "classification_version"):
        if before.get(key) != after[key]:
            method[key] = {"before": before.get(key), "after": after[key]}
    old_hash, new_hash = before.get("lineage", {}).get("config_hash"), current.lineage.get("config_hash")
    if old_hash != new_hash:
        method["config_hash"] = {"before": old_hash, "after": new_hash}
    old_class_hash = before.get("lineage", {}).get("classification_config_hash")
    new_class_hash = current.lineage.get("classification_config_hash")
    if old_class_hash != new_class_hash:
        method["classification_config_hash"] = {"before": old_class_hash, "after": new_class_hash}
    evidence = {}
    old_lineage = before.get("lineage", {})
    for key in ("data_vintage", "knowledge_cutoff"):
        old, new = old_lineage.get(key), current.lineage.get(key)
        if old != new:
            evidence[key] = {"before": old, "after": new,
                             "interpretation": "source_vintage_change_not_identified_economic_change"}
    # At an unchanged economic cutoff, revised consumed facts are a restatement,
    # even when their confidence aggregates happen to remain identical.
    if before.get("as_of") == after["as_of"]:
        old, new = old_lineage.get("input_hash"), current.lineage.get("input_hash")
        if old != new:
            evidence["input_restatement"] = {"before": old, "after": new,
                                               "interpretation": "same_cutoff_revised_source_snapshot"}
    old_evidence_hash = before.get("lineage", {}).get("classification_evidence_hash")
    new_evidence_hash = current.lineage.get("classification_evidence_hash")
    if old_evidence_hash != new_evidence_hash:
        evidence["classification_evidence_hash"] = {"before": old_evidence_hash, "after": new_evidence_hash}
    for key in ("history_coverage", "classification_coverage", "uncertain_amount_share", "perimeter_consistency", "currency_consistency", "debt_evidence"):
        old, new = before.get("confidence", {}).get(key), current.confidence.get(key)
        if old != new:
            evidence[key] = {"before": old, "after": new}
    old_products = before.get("evidence", {}).get("observed_product_ids")
    new_products = current.evidence.get("observed_product_ids")
    if old_products != new_products:
        evidence["account_perimeter"] = {"before": old_products, "after": new_products,
                                          "interpretation": "observed_account_set_change_not_proof_of_coverage"}
    old_missing = before.get("missing_components", [])
    if old_missing != current.missing_components:
        evidence["missing_components"] = {"before": old_missing, "after": current.missing_components}
    economic = {}
    for name in ("operating_inflows", "operating_outflows", "operating_net_cash", "debt_service_paid"):
        old, new = before.get("economic_facts", {}).get(name), current.economic_facts.get(name)
        economic[name] = {"before": old, "after": new,
                          "observed_fact_delta": new - old if old is not None and new is not None else None}
    # A changed evidence base can itself change classified cash; this is not identified economic attribution.
    comparable = not method and not evidence
    old_health = before.get("health")
    delta = current.health - old_health if old_health is not None and current.health is not None else None
    interpretation = "methodology_change" if method else "evidence_change" if evidence else "observed_economic_change"
    if comparable and delta is not None:
        interpretation = "economic_improvement" if delta > 0 else "economic_deterioration" if delta < 0 else "unchanged_health"
    return {"previous_health": old_health, "delta": delta, "comparable_to_previous": comparable,
            "economic_health_delta": delta if comparable else None, "interpretation": interpretation,
            "attribution": {"economic": {"facts": economic, "identified_as_economic": comparable},
                            "evidence": evidence, "methodology": method}}
