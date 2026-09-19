"""Observed changes, separated from changes in evidence and methodology."""
from typing import Any

from xray.pulse.contracts import PulseScoreResult


def _debt_evidence_structure(value: dict[str, Any]) -> dict[str, Any]:
    """Amounts and score ranges are economic observations, not new source evidence."""
    identified = value.get("identified_service", {})
    return {**{key: value.get(key) for key in ("status", "reason", "scope", "service_absence_verified")},
            "history": {key: identified.get(key) for key in ("observed_months", "required_months", "history_complete")},
            "uncertainty_version": value.get("uncertainty", {}).get("version")}


def attribute_change(current: PulseScoreResult, previous: PulseScoreResult | dict | None) -> dict[str, Any]:
    if previous is None:
        result: dict[str, Any] = {"previous_health": None, "delta": None, "comparable_to_previous": False,
                  "interpretation": "no_previous_result", "attribution": {"economic": {}, "evidence": {}, "methodology": {}}}
        if current.composition_version is not None:
            result.update(previous_operating_health=None, operating_health_delta=None,
                          previous_extended_health=None, extended_health_delta=None,
                          health_level_transition=None)
        return result
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
        old_comparison, new_comparison = old, new
        if (key == "debt_evidence" and before.get("score_version") == current.score_version
                and current.score_version in ("PulseFourPillars-v1.0.1", "PulseFourPillars-v1.1", "PulseFourPillars-v1.2")
                and isinstance(old, dict) and isinstance(new, dict)):
            old_comparison, new_comparison = _debt_evidence_structure(old), _debt_evidence_structure(new)
        if old_comparison != new_comparison:
            evidence[key] = {"before": old, "after": new}
    old_products = before.get("evidence", {}).get("observed_product_ids")
    new_products = current.evidence.get("observed_product_ids")
    if old_products != new_products:
        evidence["account_perimeter"] = {"before": old_products, "after": new_products,
                                          "interpretation": "observed_account_set_change_not_proof_of_coverage"}
    old_missing = before.get("missing_components", [])
    if old_missing != current.missing_components:
        evidence["missing_components"] = {"before": old_missing, "after": current.missing_components}
    if current.composition_version is not None and before.get("health_level") != current.health_level:
        evidence["health_level"] = {"before": before.get("health_level"), "after": current.health_level,
                                    "interpretation": "identification_level_change_not_economic_performance"}
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
    result = {"previous_health": old_health, "delta": delta, "comparable_to_previous": comparable,
            "economic_health_delta": delta if comparable else None, "interpretation": interpretation,
            "attribution": {"economic": {"facts": economic, "identified_as_economic": comparable},
                            "evidence": evidence, "methodology": method}}
    if current.composition_version is not None:
        old_operating: float | None = before.get("operating_health")
        old_extended: float | None = before.get("extended_health")
        result.update(previous_operating_health=old_operating,
                      operating_health_delta=(current.operating_health - old_operating
                                              if old_operating is not None and current.operating_health is not None else None),
                      previous_extended_health=old_extended,
                      extended_health_delta=(current.extended_health - old_extended
                                             if old_extended is not None and current.extended_health is not None else None),
                      health_level_transition=({"before": before.get("health_level"), "after": current.health_level}
                                               if before.get("health_level") != current.health_level else None))
    return result
