"""Retrospective V2 stress counterfactuals against one frozen score reference.

Only observed feature months are perturbed. It is never a forecast; all
financial arithmetic and attribution stay in Python, not in the UI.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from math import isfinite

import pandas as pd

from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import METHOD as SCORE_METHOD
from xray.score_v2.core import score_panel
from xray.stress.attribution import exact_shapley, score_term_deltas
from xray.stress.fx import FXStressUnavailable, apply_source_currency_shock
from xray.stress.scenarios import (
    HORIZONS,
    METHOD,
    MIN_FX_STRESS_EUR,
    MIN_FX_STRESS_SHARE,
    REVERSE_GRID,
    SCHEMA_VERSION,
    Shock,
    apply_shocks,
    custom_factor_contract,
    factor_unit,
    health_band,
    observed_horizon_months,
    scenarios,
)


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _key(shocks, horizon):
    return (horizon, tuple(sorted((item.factor, item.relative_pct) for item in shocks)))


def _subsets(shocks):
    for size in range(1, len(shocks)):
        yield from combinations(shocks, size)


def _explanation_map(frame):
    return {str(component): float(value) for component, value in frame.groupby("component").final_contribution.sum().items()}


def _shock_context(exposure):
    collections = exposure.get("collections") or {}
    rates = exposure.get("variable_rate") or {}
    return {
        "top1_share": collections.get("largest_customer_share") if collections.get("score_runnable") else None,
        "variable_outstanding_eur": rates.get("outstanding_eur") if rates.get("score_runnable") else None,
    }


def _base_contract(month, exposure, baseline, status="available", reason=None):
    exposure = deepcopy(exposure)
    if "fx" in exposure:
        exposure["fx"].update(stress_status="context_only", stress_currency=None)
    return {"schema_version": SCHEMA_VERSION, "method": METHOD, "status": status, "reason": reason,
            "as_of": (month + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"),
            "score_version": SCORE_METHOD, "baseline_health": baseline, "baseline_band": health_band(baseline),
            "horizon_semantics": "last_consecutive_quality_months_not_forecast", "horizons": list(HORIZONS),
            "default_scenario_id": None, "custom_factors": [], "reverse_limits": [],
            "scenarios": [], "exposures": exposure}


def _dominant_fx(exposure, fx_context):
    fx = exposure.get("fx") or {}
    if fx_context is None or fx.get("reconciliation_status") != "matched":
        return None
    amounts = {}
    quality = exposure.get("operating", {}).get("quality_months") or []
    monthly = fx.get("monthly_by_currency") or {}
    for month in quality:
        for currency, flows in (monthly.get(month) or {}).items():
            if flows is not None:
                amounts[str(currency)] = amounts.get(str(currency), 0.0) + float(flows.get("inflows") or 0) + float(flows.get("outflows") or 0)
    total = sum(amounts.values())
    candidates = sorted(((str(currency), float(value)) for currency, value in amounts.items()
                         if currency != "EUR" and len(str(currency)) == 3), key=lambda x: (-x[1], x[0]))
    if not candidates or total <= 0:
        return None
    currency, amount = candidates[0]
    return currency if amount >= MIN_FX_STRESS_EUR and amount / total >= MIN_FX_STRESS_SHARE else None


def _apply_variant(base, shocks, months, cost_monthly, context, fx_context, score_config):
    fx = [shock for shock in shocks if shock.factor.startswith("fx_")]
    other = tuple(shock for shock in shocks if not shock.factor.startswith("fx_"))
    if len(fx) > 1:
        raise ValueError("FX stress admits a single source currency")
    frame = base.copy()
    if fx:
        if fx_context is None:
            raise FXStressUnavailable("missing_fx_source_context")
        cutoff = pd.Timestamp(frame.month.max())
        if len(months) == 0 or pd.Timestamp(months[-1]) != cutoff:
            raise FXStressUnavailable("fx_window_must_end_at_scored_month")
        frame, _ = apply_source_currency_shock(
            frame, fx_context["raw_transactions"], fx_context["companies"],
            fx_context["banking_products"], fx_context["debt_products"], fx_context["config"],
            source_currency=fx[0].factor.removeprefix("fx_"), relative_pct=fx[0].relative_pct,
            window_months=pd.DatetimeIndex(months), score_config=score_config)
    if other:
        frame = apply_shocks(frame, other, months, cost_monthly, context)
    return frame


def _horizon_ok(spec, months, quality, base, exposure):
    month_keys = [m.strftime("%Y-%m") for m in months]
    factors = {shock.factor for shock in spec.shocks}
    if "observed_debt_service" in factors or "variable_rate" in factors:
        target = base.loc[base.month.isin(months)]
        service = target.debt_principal_paid.clip(lower=0).sum() + target.debt_interest_paid.clip(lower=0).sum()
        if service <= 0 and "observed_debt_service" in factors:
            return "no_observed_service_in_horizon"
        if "variable_rate" in factors and (not (_shock_context(exposure)["variable_outstanding_eur"] or 0) > 0):
            return "no_variable_rate_outstanding"
    category_factors = [factor.removeprefix("cost_") for factor in factors if factor.startswith("cost_")]
    if category_factors:
        monthly_costs = exposure.get("costs", {}).get("monthly_by_category") or {}
        category_amount = sum((monthly_costs.get(key) or {}).get(category_factors[0], 0) for key in month_keys)
        if category_amount <= 0:
            return "no_identified_category_amount_in_horizon"
    if any(factor.startswith("fx_") for factor in factors):
        currency = next(factor.removeprefix("fx_") for factor in factors if factor.startswith("fx_"))
        monthly_fx = exposure.get("fx", {}).get("monthly_by_currency") or {}
        amount = sum(sum((monthly_fx.get(key) or {}).get(currency, {}).get(side, 0) for side in ("inflows", "outflows"))
                     for key in month_keys)
        if amount <= 0:
            return "no_source_currency_operating_flow_in_horizon"
    if "customer_delay" in factors and not (exposure.get("collections") or {}).get("score_runnable"):
        return "customer_delay_unavailable"
    return None


def _plan(panel, reference, company_id, month, published_score, exposure, fx_context=None):
    config = ScoreV2Config(**reference["config"])
    if config.unit != "company_id" or reference.get("method") != SCORE_METHOD:
        raise ValueError("Stress requires frozen company financial_smoothed_v2 reference")
    as_of = (month + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    if exposure.get("company_id") != company_id or exposure.get("as_of") != as_of:
        raise ValueError("Stress exposure identity/cutoff mismatch")
    published = _number(published_score)
    if published is None:
        return {"insufficient": _base_contract(month, exposure, None, "insufficient_data", "v2_score_unavailable")}
    base = panel.loc[panel.company_id.eq(company_id) & panel.month.le(month)].copy()
    if base.empty or not base.month.eq(month).any() or base.currency.nunique() != 1 or base.currency.iloc[0] != "EUR":
        raise ValueError(f"No comparable EUR feature panel for {company_id} at {month.date()}")
    debt = exposure["debt_service"]
    has_service = debt["status"] == "available" and (debt.get("v2_service_6m") or 0) > 0
    has_delay = bool((exposure.get("collections") or {}).get("score_runnable"))
    has_rate = bool((exposure.get("variable_rate") or {}).get("score_runnable"))
    fx_currency = _dominant_fx(exposure, fx_context)
    specs = scenarios(has_service, exposure.get("costs", {}).get("category_gates"), fx_currency,
                      has_customer_delay=has_delay, has_variable_rate=has_rate)
    quality = set(exposure["operating"].get("quality_months") or [])
    windows = {horizon: observed_horizon_months(quality, month, horizon) for horizon in HORIZONS}
    if not any(windows.values()):
        return {"insufficient": _base_contract(month, exposure, None, "insufficient_data", "insufficient_quality_months")}
    variants = {(0, ()): ("baseline", (), ())}
    runnable, blocked, reverse_index = set(), {}, {}
    context = _shock_context(exposure)

    def register(spec, horizon, months):
        if months is None:
            return
        reason = _horizon_ok(spec, months, quality, base, exposure)
        if reason:
            blocked[(spec.id, horizon)] = reason
            return
        runnable.add((spec.id, horizon))
        variants.setdefault(_key(spec.shocks, horizon), (f"variant-{len(variants)}", spec.shocks, months))
        if horizon == 6 and len(spec.shocks) > 1:
            for subset in _subsets(spec.shocks):
                variants.setdefault(_key(subset, horizon), (f"variant-{len(variants)}", subset, months))

    for spec in specs:
        if not spec.available:
            continue
        for horizon in HORIZONS:
            register(spec, horizon, windows[horizon])
    reverse_factors = []
    if has_delay:
        reverse_factors.append("customer_delay")
    reverse_factors.append("operating_inflow")
    reverse_factors.append("operating_outflow")
    if has_service:
        reverse_factors.append("observed_debt_service")
    months6 = windows[6]
    if months6 is not None:
        for factor in reverse_factors:
            for value in REVERSE_GRID[factor]:
                shock = Shock(factor, value, factor_unit(factor))
                key = _key((shock,), 6)
                variants.setdefault(key, (f"variant-{len(variants)}", (shock,), months6))
                reverse_index.setdefault(factor, []).append((value, key))
    frames, label_to_key, failed = [], {}, {}
    category_monthly = exposure.get("costs", {}).get("monthly_by_category")
    for key, (label, shocks, months) in variants.items():
        try:
            variant = _apply_variant(base, shocks, months, category_monthly, context, fx_context, config) if shocks else base.copy()
        except FXStressUnavailable as error:
            failed[key] = str(error)
            continue
        variant["company_id"] = f"{company_id}|{label}"
        frames.append(variant)
        label_to_key[label] = key
    retained = {key: value for key, value in variants.items() if key not in failed}
    if fx_currency is not None:
        fx_ok = any(key not in failed for key, (_, shocks, _) in variants.items()
                    if len(shocks) == 1 and shocks[0].factor == f"fx_{fx_currency}")
        if not fx_ok:
            fx_currency = None
            specs = scenarios(has_service, exposure.get("costs", {}).get("category_gates"), None,
                              has_customer_delay=has_delay, has_variable_rate=has_rate)
            retained = {key: value for key, value in retained.items()
                        if not any(item.factor.startswith("fx_") for item in value[1])}
            frames = [frame for frame in frames
                      if label_to_key.get(str(frame["company_id"].iloc[0]).split("|", 1)[1]) in retained]
            label_to_key = {label: key for label, key in label_to_key.items() if key in retained}
            runnable = {(sid, horizon) for sid, horizon in runnable if not str(sid).startswith("fx")}
            specs_ids = {spec.id for spec in specs}
            runnable = {(sid, horizon) for sid, horizon in runnable if sid in specs_ids}
    contract = _base_contract(month, exposure, published)
    if fx_currency is not None:
        contract["exposures"]["fx"].update(stress_status="available", stress_currency=fx_currency,
                                            score_runnable=True)
    return {"company_id": company_id, "published": published, "specs": specs, "variants": retained,
            "runnable": runnable, "blocked": blocked, "failed": failed, "frames": frames, "label_to_key": label_to_key,
            "contract": contract, "reverse_index": reverse_index, "exposure": exposure}


def _scenario_path(results, baseline_band):
    path, crossing = [], None
    for row in results:
        if row["status"] != "available" or row["health"] is None:
            continue
        path.append({"observed_months": row["observed_months"], "health": row["health"], "band": row["band"]})
        if crossing is None and row["band"] != baseline_band:
            crossing = row["observed_months"]
    return path, crossing


def _reverse_limits(scores, reverse_index, baseline, baseline_band):
    if baseline_band in (None, "red"):
        return []
    limits = []
    for factor, items in reverse_index.items():
        crossed = None
        for value, key in sorted(items, key=lambda item: abs(item[0])):
            health = scores.get(key)
            if health is None or health_band(health) is None:
                continue
            if health_band(health) != baseline_band and health < baseline:
                crossed = {"factor": factor, "unit": factor_unit(factor), "value": value,
                           "health": health, "band": health_band(health)}
                break
        if crossed:
            limits.append(crossed)
    return limits


def _render(plan, latest, explanations):
    cid = plan["company_id"]
    scores = {}
    for row in latest.itertuples(index=False):
        label = str(row.company_id).split("|", 1)[1]
        scores[plan["label_to_key"][label]] = _number(row.score)
    if len(scores) != len(plan["variants"]):
        raise ValueError(f"V2 stress variants missing/duplicated for {cid}")
    baseline = scores[(0, ())]
    if baseline is None or abs(baseline - plan["published"]) > 1e-6:
        raise ValueError(f"V2 stress baseline does not reconcile for {cid}: {baseline} != {plan['published']}")
    terms = {}
    for variant_id, frame in explanations.groupby("company_id"):
        label = str(variant_id).split("|", 1)[1]
        terms[plan["label_to_key"][label]] = _explanation_map(frame)
    baseline_terms = terms.get((0, ()), {})
    if abs(sum(baseline_terms.values()) - baseline) > 1e-6:
        raise ValueError(f"V2 baseline explanation does not reconcile for {cid}")
    baseline_band = health_band(baseline)
    output = []
    for spec in plan["specs"]:
        item = {"id": spec.id, "kind": spec.kind, "label": spec.label,
                "status": "available" if spec.available else "unavailable", "reason": spec.reason,
                "shocks": [shock.json() for shock in spec.shocks], "results": [],
                "path": [], "band_crossing_horizon": None}
        for horizon in HORIZONS if spec.available else ():
            result = {"observed_months": horizon, "status": "insufficient_quality_months",
                      "reason": "insufficient_quality_months", "health": None, "delta_points": None,
                      "band": None, "attribution": None, "score_terms": None}
            if (spec.id, horizon) in plan["blocked"]:
                result.update(status="unavailable", reason=plan["blocked"][(spec.id, horizon)])
            elif (spec.id, horizon) in plan["runnable"]:
                key = _key(spec.shocks, horizon)
                value = scores.get(key)
                if value is not None:
                    deltas = score_term_deltas(baseline_terms, terms.get(key, {}))
                    delta = value - baseline
                    if abs(sum(x["points"] for x in deltas) - delta) > 1e-6:
                        raise ValueError(f"V2 scenario explanation does not reconcile for {cid} {spec.id}")
                    attribution = None
                    if horizon == 6:
                        def score_subset(names, current_shocks=spec.shocks, current_horizon=horizon):
                            subset = tuple(s for s in current_shocks if s.factor in names)
                            return baseline if not subset else scores.get(_key(subset, current_horizon))
                        attribution = exact_shapley(spec.shocks, score_subset)
                        if attribution is None or abs(sum(x["points"] for x in attribution["factors"]) + attribution["residual"] - delta) > 1e-6:
                            raise ValueError(f"V2 Shapley does not reconcile for {cid} {spec.id}")
                    result.update(status="available", reason=None, health=value, delta_points=delta,
                                  band=health_band(value), attribution=attribution, score_terms=deltas)
                else:
                    result.update(status="unavailable", reason=("fx_source_unavailable:" + plan["failed"][key])
                                  if key in plan["failed"] else "v2_scenario_score_unavailable")
            item["results"].append(result)
        item["path"], item["band_crossing_horizon"] = _scenario_path(item["results"], baseline_band)
        if spec.available and not any(row["status"] == "available" for row in item["results"]):
            item.update(status="unavailable", reason="insufficient_quality_months")
        output.append(item)
    collections = plan["exposure"].get("collections") or {}
    rates = plan["exposure"].get("variable_rate") or {}
    fx = (plan["contract"]["exposures"].get("fx") or {})
    contract = plan["contract"]
    contract["baseline_health"] = baseline
    contract["baseline_band"] = baseline_band
    available = [row for row in output if row["status"] == "available"
                 and any(result["status"] == "available" for result in row["results"])]
    if not available:
        contract.update(status="insufficient_data", reason="insufficient_quality_months",
                        baseline_health=None, baseline_band=None, default_scenario_id=None,
                        custom_factors=[], reverse_limits=[], scenarios=[])
        return contract
    contract["scenarios"] = output
    contract["custom_factors"] = custom_factor_contract(
        plan["specs"], top1_share=collections.get("largest_customer_share"),
        fx_currency=fx.get("stress_currency"), variable_outstanding=rates.get("outstanding_eur"))
    contract["default_scenario_id"] = next((row["id"] for row in available if row["id"] == "adverse"),
                                           available[0]["id"])
    contract["reverse_limits"] = _reverse_limits(scores, plan.get("reverse_index") or {}, baseline, baseline_band)
    return contract


def build_batch_stress(panel, reference, rows, *, month, fx_context_by_company=None):
    """Score multiple companies in one V2 call; rows are (id, published, exposures)."""
    month = pd.Timestamp(month).to_period("M").to_timestamp()
    fx_context_by_company = fx_context_by_company or {}
    plans = [_plan(panel, reference, cid, month, published, exposure, fx_context_by_company.get(cid))
             for cid, published, exposure in rows]
    active = [plan for plan in plans if "insufficient" not in plan]
    if not active:
        return {cid: plan["insufficient"] for (cid, _, _), plan in zip(rows, plans)}
    frames = [frame for plan in active for frame in plan["frames"]]
    scored, explanations = score_panel(pd.concat(frames, ignore_index=True), reference)
    scored = scored.loc[scored.month.eq(month)].copy()
    explanations = explanations.loc[explanations.month.eq(month)].copy()
    scored["_original_company"] = scored.company_id.str.split("|", n=1).str[0]
    explanations["_original_company"] = explanations.company_id.str.split("|", n=1).str[0]
    score_groups = dict(tuple(scored.groupby("_original_company", sort=False)))
    explanation_groups = dict(tuple(explanations.groupby("_original_company", sort=False)))
    result = {plan["company_id"]: _render(plan, score_groups[plan["company_id"]],
              explanation_groups.get(plan["company_id"], explanations.iloc[:0])) for plan in active}
    result.update({cid: plan["insufficient"] for (cid, _, _), plan in zip(rows, plans) if "insufficient" in plan})
    return result


def build_company_stress(panel, reference, published_score, exposures, *, company_id, month, fx_context=None):
    contexts = {company_id: fx_context} if fx_context is not None else None
    return build_batch_stress(panel, reference, [(company_id, published_score, exposures)],
                              month=month, fx_context_by_company=contexts)[company_id]
