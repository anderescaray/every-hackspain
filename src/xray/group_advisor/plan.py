"""Ensamblado del JSON `group_plans/{group_id}.json` (spec `docs/group-optimization.md` §8.1).

`build_plan` ejecuta el greedy (`optimizer.optimize_group`) y el certificado, y devuelve un `dict`
con exactamente la estructura de `tests/fixtures/advisor_plan_example.json`: solo tipos nativos
(sin `numpy.float64`/`bool_`), floats redondeados a 6 decimales, `None` donde no hay dato.
`status`: `single_subsidiary` si el grupo tiene una sola filial, `no_feasible_levers` sin pasos,
`plan` con al menos uno. Las filiales sin nivel se listan con su `score_reason`, no se omiten.
"""
import dataclasses
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from xray.group_advisor import fx
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.counterfactual import COMPONENTS
from xray.group_advisor.objective import group_utility, levels_by_tramo, subsidiary_weights
from xray.group_advisor.optimizer import (LEVER_COMPONENT, REASON_RECIPIENT_CASH, REASON_RECIPIENT_NOT_CONSTRAINED, ap_delay_unexplained,
                                          ap_need, certificate, donor_buffer, donor_capacity, donor_reason, optimize_group,
                                          recipient_need, recipient_reason, reliable_cash)

SCHEMA_VERSION = 1
METHOD = "group_treasury_advisor_v1"
STATUS_PLAN = "plan"
STATUS_NO_LEVERS = "no_feasible_levers"
STATUS_SINGLE = "single_subsidiary"
STOP_SINGLE = "single_subsidiary"
ASSUMPTIONS = ("estacionariedad de flujos y servicio en la ventana",
               "el credito intragrupo no se liquida por banco en el horizonte",
               "no se modelan fiscalidad, legal, covenants ni precio intragrupo")
LIMITATIONS = ("caja reconstruida retrospectivamente; no saldo observado",
               "momentum no simulado",
               "el consolidado grupo-moneda no cambia con D1 y no se recalcula con P")
STRUCTURAL_NOTE = "margen 6m {margin}: no es palanca de tesoreria"
STRUCTURAL_BLOCKER = "margen 6m {margin}: problema estructural de negocio"
UNEXPLAINED_NOTE = "retraso AP no explicado por liquidez (politica de pago o higiene ERP)"
DONOR_EVIDENCE = ("reconstructed_cash", "runway_months")
RECIPIENT_EVIDENCE = {"D1": ("window_debt_service_sum", "level_inflow_sum"),
                      "P": ("inv_ap_overdue_amount", "inv_ap_due_30_amount", "reconstructed_cash", "runway_months"),
                      "O": ("window_outflow_sum", "level_inflow_sum")}
RECIPIENT_CANDIDATE_REASONS = frozenset({None, REASON_RECIPIENT_NOT_CONSTRAINED, REASON_RECIPIENT_CASH})
DECIMALS = 6


# ---------------------------------------------------------------- utilidades


def _num(value):
    if value is None:
        return math.nan
    try:
        value = float(value)
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def _text(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value)
    return None if text in ("", "None", "nan", "<NA>") else text


def _margin_text(margin):
    """`-0,30`: dos decimales con coma, como el fixture de WP4."""
    return "n/d" if math.isnan(margin) else f"{margin:.2f}".replace(".", ",")


def _jsonable(value):
    """Tipos nativos JSON: tuplas → listas, numpy → Python, NaN/inf → None, floats redondeados a 6 decimales."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return None
        rounded = round(number, DECIMALS)
        return 0.0 if rounded == 0 else rounded
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _subsidiary_rows(state):
    frame = state.subsidiaries
    return {str(cid): dict(zip(frame.columns, values)) for cid, values in zip(frame.index, frame.to_numpy(dtype=object))}


def _k(k):
    return f"k{int(k)}"


# ---------------------------------------------------------------- bloques


def _coverage(subs, optimizable):
    return {"subsidiaries": len(subs), "optimizable": len(optimizable), "not_scored": len(subs) - len(optimizable),
            "with_reliable_cash": sum(1 for row in subs.values() if bool(row["cash_reliable"])),
            "with_debt_component": sum(1 for row in subs.values() if not math.isnan(_num(row["level_debt"]))),
            "with_ap_component": sum(1 for row in subs.values() if not math.isnan(_num(row["level_payments"]))),
            "currencies": sorted({str(row["currency"]) for row in subs.values()})}


def _subsidiary_entry(cid, row, config):
    cash, buffer = reliable_cash(row), donor_buffer(row, 0.0, config)
    excess = max(0.0, cash - buffer) if not (math.isnan(cash) or math.isnan(buffer)) else math.nan
    gap = recipient_need(row, "P", config) if not math.isnan(ap_need(row)) else math.nan
    return {
        "company_id": cid, "currency": str(row["currency"]), "level": _num(row["level"]), "score": _num(row["score"]),
        "momentum_adjustment": _num(row["momentum_adjustment"]), "tramo": str(row["tramo"]),
        "score_status": _text(row["score_status"]), "score_reason": _text(row["score_reason"]),
        "components": {component: _num(row[f"level_{component}"]) for component in COMPONENTS},
        "signals": {key: _num(row[key]) for key in ("op_margin_w", "debt_service_w", "ar_delay_w", "ap_delay_w",
                                                   "level_inflow_sum", "window_outflow_sum", "monthly_debt_service")},
        "liquidity": {"reconstructed_cash": cash, "reliable": bool(row["cash_reliable"]), "runway_months": _num(row["runway_months"]),
                      "buffer": buffer, "excess_cash": excess},
        "ap": {"overdue_amount": _num(row["inv_ap_overdue_amount"]), "due_30": _num(row["inv_ap_due_30_amount"]),
               "due_60": _num(row["inv_ap_due_60_amount"]), "gap": gap},
    }


def _baseline(state, subs, optimizable, config):
    weights = subsidiary_weights(state, config)
    levels = [_num(subs[cid]["level"]) for cid in optimizable]
    finite = [level for level in levels if not math.isnan(level)]
    return {
        "group_utility_0_100": group_utility(levels, [weights[cid] for cid in optimizable], config) if optimizable else math.nan,
        "min_level": min(finite) if finite else math.nan,
        "mean_level": sum(finite) / len(finite) if finite else math.nan,
        "levels_by_tramo": levels_by_tramo(levels, config),
        "consolidated_group_currency_score": {str(ccy): (None if value is None else _num(value))
                                              for ccy, value in sorted(state.consolidated_scores.items())},
        "subsidiaries": [_subsidiary_entry(cid, subs[cid], config) for cid in subs],
    }


def _diagnosis(subs, optimizable, config):
    bound = float(config.tramo_bounds[0])
    bottleneck = {"company_id": None, "level": None, "weakest_components": []}
    if optimizable:
        cid = min(optimizable, key=lambda c: (_num(subs[c]["level"]), c))
        row = subs[cid]
        weak = [(component, _num(row[f"level_{component}"])) for component in COMPONENTS]
        weak = [component for component, score in sorted(weak, key=lambda item: (item[1], item[0])) if not math.isnan(score) and score < bound]
        bottleneck = {"company_id": cid, "level": _num(row["level"]), "weakest_components": weak}
    structural = [{"company_id": cid, "component": "operations", "note": STRUCTURAL_NOTE.format(margin=_margin_text(_num(subs[cid]["op_margin_w"])))}
                  for cid in optimizable if _num(subs[cid]["level_operations"]) < bound]
    unexplained = [{"company_id": cid, "ap_delay_w": _num(subs[cid]["ap_delay_w"]), "reconstructed_cash": reliable_cash(subs[cid]),
                    "ap_need": ap_need(subs[cid]), "note": UNEXPLAINED_NOTE}
                   for cid in optimizable if ap_delay_unexplained(subs[cid], config)]
    donors, recipients = [], []
    if len(optimizable) >= 2:
        for cid in optimizable:
            row = subs[cid]
            cash = reliable_cash(row)
            if donor_reason(row, None, cash, config) is None and donor_capacity(row, cash, 0.0, config) > 0:
                donors.append(cid)
            if any(recipient_reason(row, lever, config) in RECIPIENT_CANDIDATE_REASONS for lever in config.levers):
                recipients.append(cid)
    return {"bottleneck": bottleneck, "structural_flags": structural, "unexplained_ap_delays": unexplained,
            "donor_candidates": donors, "recipient_candidates": recipients}


def _levers_evaluated(pairs):
    return [{"lever": pair.lever, "donor": pair.donor, "recipient": pair.recipient, "donor_currency": pair.donor_currency,
             "recipient_currency": pair.recipient_currency, "fx_applied": pair.fx_applied, "feasible": bool(pair.feasible),
             "need_recipient_ccy": _num(pair.need_recipient_ccy), "donor_capacity": _num(pair.donor_capacity), "reason": pair.reason}
            for pair in pairs]


def _step_evidence(state, action):
    wanted = {(action.donor, field) for field in DONOR_EVIDENCE} | {(action.recipient, field) for field in RECIPIENT_EVIDENCE[action.lever]}
    return sorted(ev_id for ev_id, item in state.evidence.items() if (item["company_id"], item["field"]) in wanted)


def _step_entry(state, subs, greedy_step, config):
    candidate, action = greedy_step.candidate, greedy_step.candidate.action
    momentum = _num(subs[action.recipient]["momentum_adjustment"])
    momentum = 0.0 if math.isnan(momentum) else momentum
    effects = {}
    touches_donor = action.lever in ("D1", "O")
    for k in config.report_k:
        effect = greedy_step.effects[k]
        effects[_k(k)] = {
            "recipient": {"level_before": effect.recipient_level_before, "level_after": effect.recipient_level_after,
                          "score_after": min(max(effect.recipient_level_after + momentum, 0.0), 100.0),
                          "component": LEVER_COMPONENT[action.lever], "signal_before": effect.recipient_signal_before,
                          "signal_after": effect.recipient_signal_after, "component_dropped": bool(effect.recipient_component_dropped)},
            "donor": {"level_before": effect.donor_level_before, "level_after": effect.donor_level_after,
                      "signal_before": effect.donor_signal_before if touches_donor else None,
                      "signal_after": effect.donor_signal_after if touches_donor else None},
            "group_utility_before": greedy_step.utility_before_by_k[k], "group_utility_after": greedy_step.utility_after_by_k[k],
        }
    return {"step": greedy_step.step, "lever": action.lever, "donor": action.donor, "recipient": action.recipient,
            "fraction": action.fraction,
            "amount": {"recipient_ccy": action.amount_recipient_ccy, "donor_ccy": action.amount_donor_ccy,
                       "reporting_ccy": candidate.x_report, "fx_applied": action.fx_applied},
            "effects": effects, "efficiency_per_10k": candidate.efficiency, "binding_constraints": list(candidate.binding),
            "evidence": _step_evidence(state, action)}


def _plan_block(state, subs, result, config, stopped_because):
    working = result.working_final
    committed = {}
    for greedy_step in result.steps:
        action = greedy_step.candidate.action
        entry = committed.setdefault(action.donor, {"donor_ccy": 0.0, "reporting_ccy": 0.0})
        entry["donor_ccy"] += action.amount_donor_ccy
        entry["reporting_ccy"] += greedy_step.candidate.x_report
    return {"steps": [_step_entry(state, subs, greedy_step, config) for greedy_step in result.steps],
            "totals": {_k(k): {"group_utility_after": working.group_utility(k), "min_level_after": working.min_level(k)}
                       for k in config.report_k},
            "cash_committed_by_donor": {donor: committed[donor] for donor in sorted(committed)},
            "stopped_because": stopped_because}


def _assumptions(result, config):
    assumptions = list(ASSUMPTIONS)
    if any(greedy_step.candidate.action.fx_applied is not None for greedy_step in result.steps):
        assumptions.append(f"fx_fixed_rate: tabla {config.fx_source or fx.FX_SOURCE} a {config.fx_asof or fx.FX_ASOF}")
    return assumptions


# ---------------------------------------------------------------- top action y resumen de impacto


def _top_action(subs, result, config):
    """La acción del plan con mayor ΔG en régimen (k=H): la que más mejora al grupo."""
    if not result.steps:
        return None
    horizon = config.horizon_months
    best = max(result.steps, key=lambda step: step.utility_after_by_k[horizon] - step.utility_before_by_k[horizon])
    effect_kh = best.effects[horizon]
    action = best.candidate.action
    delta_g = best.utility_after_by_k[horizon] - best.utility_before_by_k[horizon]
    r_before = _num(subs[action.recipient]["level"])
    d_before = _num(subs[action.donor]["level"])
    from xray.group_advisor.objective import tramo
    return {
        "step": best.step, "lever": action.lever,
        "donor": action.donor, "recipient": action.recipient,
        "donor_level_before": d_before,
        "donor_level_after": effect_kh.donor_level_after,
        "recipient_level_before": r_before,
        "recipient_level_after": effect_kh.recipient_level_after,
        "recipient_tramo_before": tramo(r_before, config),
        "recipient_tramo_after": tramo(effect_kh.recipient_level_after, config),
        "delta_utility_k6": delta_g,
        "amount_reporting_ccy": best.candidate.x_report,
        "efficiency_per_10k": best.candidate.efficiency,
    }


def _group_impact_summary(subs, optimizable, result, config):
    """Resumen del impacto total del plan sobre el grupo: filiales rescatadas y bloqueadores."""
    horizon = config.horizon_months
    working = result.working_final
    baseline_g = result.utility_before
    after_g = working.group_utility(horizon)
    total_cash = sum(step.candidate.x_report for step in result.steps)
    from xray.group_advisor.objective import tramo
    # Filiales que cambian de tramo gracias al plan
    rescued = []
    for cid in optimizable:
        before = _num(subs[cid]["level"])
        after = _num(working.levels_by_k[horizon].get(cid, before))
        tramo_before = tramo(before, config)
        tramo_after = tramo(after, config)
        if tramo_before != tramo_after and tramo_after != "none" and tramo_before in ("red", "amber"):
            rescued.append({"company_id": cid, "tramo_before": tramo_before, "tramo_after": tramo_after,
                            "level_before": before, "level_after": after})
    # Bloqueadores estructurales: filiales con margen < 40 que el plan no puede arreglar
    bound = float(config.tramo_bounds[0])
    blockers = []
    for cid in optimizable:
        ops = _num(subs[cid]["level_operations"])
        if not math.isnan(ops) and ops < bound:
            margin = _num(subs[cid]["op_margin_w"])
            blockers.append({"company_id": cid, "reason": STRUCTURAL_BLOCKER.format(margin=_margin_text(margin))})
    return {
        "utility_before": baseline_g, "utility_after": after_g,
        "delta_utility": after_g - baseline_g,
        "total_steps": len(result.steps), "total_cash_committed": total_cash,
        "subsidiaries_rescued": rescued, "structural_blockers": blockers,
    }


# ---------------------------------------------------------------- plan


def plan_status(state, result):
    if len(state.subsidiaries) == 1:
        return STATUS_SINGLE
    return STATUS_PLAN if result.steps else STATUS_NO_LEVERS


def build_plan(state, config=None, generated_at=None):
    """Plan de grupo (esquema §8.1) para un `GroupState`; `generated_at` ISO UTC (por defecto ahora)."""
    config = config or AdvisorConfig()
    subs = _subsidiary_rows(state)
    optimizable = list(state.optimizable_ids)
    result = optimize_group(state, config)
    status = plan_status(state, result)
    stopped_because = STOP_SINGLE if status == STATUS_SINGLE else result.stopped_because
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    top = _top_action(subs, result, config) if status == STATUS_PLAN else None
    impact = _group_impact_summary(subs, optimizable, result, config) if status == STATUS_PLAN else None
    plan = {
        "schema_version": SCHEMA_VERSION, "method": METHOD, "group_id": str(state.group_id), "month": str(pd.Timestamp(state.month).date()),
        "config": dataclasses.asdict(config),
        "status": status, "reporting_currency": config.reporting_currency,
        "coverage": _coverage(subs, optimizable),
        "baseline": _baseline(state, subs, optimizable, config),
        "diagnosis": _diagnosis(subs, optimizable, config),
        "levers_evaluated": _levers_evaluated(result.pairs),
        "plan": _plan_block(state, subs, result, config, stopped_because),
        "top_action": top, "group_impact_summary": impact,
        "rejected_alternatives": list(result.rejected),
        "certificate": certificate(state, config, result),
        "assumptions": _assumptions(result, config), "limitations": list(LIMITATIONS),
        "evidence": {ev_id: dict(item) for ev_id, item in state.evidence.items()},
        "generated_at": str(generated_at), "inputs_sha256": dict(state.inputs_sha256),
    }
    return _jsonable(plan)


def plan_to_json(plan):
    return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=False)
