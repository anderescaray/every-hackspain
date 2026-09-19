"""Pipeline `treasury_advisor_v1`: planes de grupo, sensibilidades de empresa, tablas, informe y publicación (spec §8).

`run` carga las entradas **una sola vez** (`state.load_inputs`), recorre los grupos del mes en orden
(`iter_group_states`) y, por cada estado, construye el plan (`plan.build_plan`), lo renderiza y valida su
anclaje, y calcula la sensibilidad de cada filial (`sensitivity.company_sensitivity`) completando
`group_context` (papel de la empresa en el plan de su grupo) y `feasibility.covered_by_group_plan` en
`ap_on_time`. Todo se escribe en un staging **dentro de `out_dir`** y se publica con
`xray.artifacts.publish_bundle` (respaldo en `.history/`, manifiesto al final); las carpetas `group_plans/`
y `company_sensitivity/` se sustituyen enteras porque `publish_bundle` trabaja fichero a fichero.
`run_from_states` es el núcleo sin lectura de entradas, para ejecutarlo sobre estados sintéticos en tests.

Configuración por defecto: `AdvisorConfig` con la tabla FX fija de `xray.fx` (solo importes). Con el panel
D32 100 % EUR el resultado es idéntico al de la configuración sin tabla; la tabla queda documentada en el
manifiesto para cuando vuelvan monedas.
"""
import hashlib
import json
import os
import platform
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from xray.artifacts import check_output_path, code_manifest, publish_bundle, sha256
from xray.group_advisor import fx
from xray.group_advisor.config import SENSITIVITY_LEVERS, TRAMO_LABELS, AdvisorConfig
from xray.group_advisor.grounding import validate_grounding
from xray.group_advisor.narrative import render_plan, render_sensitivity
from xray.group_advisor.plan import STATUS_NO_LEVERS, STATUS_PLAN, STATUS_SINGLE, build_plan, plan_to_json
from xray.group_advisor.sensitivity import company_sensitivity, sensitivity_to_json
from xray.group_advisor.state import iter_group_states, load_inputs, tramo_of
from xray.paths import CLEANED_DIR, PROCESSED_DIR
from xray.score.report import json_safe

METHOD = "treasury_advisor_v1"
DEFAULT_OUT_DIRNAME = "advisor"
FEATURE_FILE = "company_monthly_features.parquet"
PLANS_DIR = "group_plans"
SENSITIVITY_DIR = "company_sensitivity"
DIRECTORIES = (PLANS_DIR, SENSITIVITY_DIR)
STEPS_FILE = "advisor_steps.parquet"
GROUPS_FILE = "advisor_groups.parquet"
LEVERS_FILE = "sensitivity_levers.parquet"
REPORT_FILE = "_advisor_report.json"
MANIFEST_FILE = "_advisor_manifest.json"
STATUSES = (STATUS_PLAN, STATUS_NO_LEVERS, STATUS_SINGLE)
ROLE_RECIPIENT, ROLE_DONOR, ROLE_BOTH, ROLE_NONE = "recipient", "donor", "both", "none"
AP_LEVER = "ap_on_time"
LIMITATIONS = (
    "Escenario mecánico sobre el nivel V2, no recomendación ejecutable ni predicción.",
    "D1 no cambia el servicio externo del grupo: redistribuye. La ganancia es de resiliencia, no de coste financiero.",
    "Estacionariedad: flujos, cuotas y número de pagos del último semestre se repiten.",
    "Palancas de negocio (cut_outflow, raise_inflow): sensibilidad con «todo lo demás igual»; no se recomienda recortar ni se "
    "supone que vender más no cueste.",
    "Caja reconstruida hacia atrás desde la foto de 2026-09-01 (FE06); no es saldo observado. Sin fiabilidad no hay palanca.",
    "Momentum no simulado; el score contrafactual mantiene el ajuste de momentum del baseline.",
    "FX fijo solo para importes; señales dentro de cada moneda. transactions.exchange_rate no se usa.",
    "Fiscalidad, legal, covenants, precio intragrupo, reacción de clientes/proveedores: fuera de los datos, fuera del modelo.",
    "El AP pagado tarde puede ser política o higiene ERP: P solo si la receptora está restringida por liquidez.",
    "Greedy con certificado hasta pares; sin garantía de óptimo global. Bisección de tramo por palanca aislada: combinaciones "
    "no se exploran.",
    "Nada contrastado con Embat ni con la nota oculta del leaderboard.",
)

STEP_SCHEMA = {"group_id": "str", "month": "datetime64[ns]", "step": "int64", "lever": "str", "donor": "str", "recipient": "str",
               "fraction": "float64", "amount_recipient_ccy": "float64", "amount_donor_ccy": "float64", "amount_reporting_ccy": "float64",
               "fx_applied": "float64", "recipient_level_before_k6": "float64", "recipient_level_after_k6": "float64",
               "donor_level_before_k6": "float64", "donor_level_after_k6": "float64", "delta_utility_k6": "float64",
               "delta_utility_k1": "float64", "efficiency_per_10k": "float64", "binding_constraints": "str"}
GROUP_SCHEMA = {"group_id": "str", "month": "datetime64[ns]", "status": "str", "subsidiaries": "int64", "optimizable": "int64",
                "with_reliable_cash": "int64", "with_debt_component": "int64", "with_ap_component": "int64", "utility_before": "float64",
                "utility_after_k1": "float64", "utility_after_k6": "float64", "min_level_before": "float64", "min_level_after_k6": "float64",
                "steps": "int64", "cash_committed_reporting_ccy": "float64", "stopped_because": "str", "greedy_gap": "float64",
                "grounding_ok": "bool"}
LEVER_SCHEMA = {"company_id": "str", "group_id": "str", "month": "datetime64[ns]", "level": "float64", "tramo": "str", "lever": "str",
                "type": "str", "component": "str", "current": "float64", "unit": "str", "level_per_pct": "float64", "level_per_10k": "float64",
                "valid_until": "float64", "next_tramo_target": "float64", "reachable": "boolean", "rel_change_needed": "float64",
                "quantity_needed": "float64", "cash_equivalent": "float64", "feasible_alone": "boolean", "covered_by_group_plan": "boolean"}


# ---------------------------------------------------------------- configuración, rutas, utilidades


def default_config(**overrides):
    """`AdvisorConfig` de ejecución: tabla FX fija de `xray.fx` (solo importes) salvo que `overrides` diga otra cosa."""
    fx_fields = {"fx_rates_to_eur": fx.default_fx_table(), "fx_source": fx.FX_SOURCE, "fx_asof": fx.FX_ASOF}
    return AdvisorConfig(**{**fx_fields, **overrides})


def resolve_out_dir(features_dir, out_dir=None):
    return Path(out_dir) if out_dir is not None else Path(features_dir) / DEFAULT_OUT_DIRNAME


def check_out_dir(out_dir, features_dir=None):
    """Rechaza salidas que se solapen con `scores/`, `scores_v2/`, las features, `cleaned/` o `raw/`."""
    out_dir = Path(out_dir)
    protected = [CLEANED_DIR]
    if features_dir is not None:
        features_dir = Path(features_dir)
        protected += [features_dir / "scores", features_dir / "scores_v2", features_dir / FEATURE_FILE, features_dir.parent / "raw"]
    for source in protected:
        check_output_path(out_dir, source)


def resolve_month(inputs, month=None, config=None):
    chosen = month if month is not None else (config.month if config is not None else None)
    stamp = pd.Timestamp(chosen) if chosen is not None else pd.Timestamp(inputs.last_month)
    if stamp != stamp.to_period("M").to_timestamp():
        raise ValueError("month debe ser el primer día de un mes")
    return stamp


def verify_inputs_unchanged(features_dir, inputs_sha256):
    """Antes de publicar: ninguna entrada cambió durante el cálculo y las features no se están regenerando."""
    features_dir = Path(features_dir)
    if (features_dir / ".pipeline.lock").exists():
        raise RuntimeError("Las features se están regenerando; no se publica")
    for name, digest in inputs_sha256.items():
        path = features_dir / name
        if path.exists() and sha256(path) != digest:
            raise RuntimeError(f"La entrada {name} cambió durante el cálculo; no se publica")


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _frame(rows, schema):
    """DataFrame con dtypes fijos (también vacío); `None` → NaN / <NA> según el dtype."""
    return pd.DataFrame({column: pd.Series([row.get(column) for row in rows], dtype=dtype) for column, dtype in schema.items()})


def _distribution(values):
    values = [v for v in (_num(v) for v in values) if v is not None]
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {"count": len(array), "min": float(array.min()), "p25": float(np.percentile(array, 25)), "median": float(np.median(array)),
            "p75": float(np.percentile(array, 75)), "max": float(array.max())}


def _sorted_counts(counter):
    return {key: counter[key] for key in sorted(counter, key=lambda k: (-counter[k], k))}


def _k(k):
    return f"k{int(k)}"


# ---------------------------------------------------------------- filas por grupo y por paso


def _step_rows(plan, config):
    kh, k1 = _k(config.horizon_months), _k(1)
    rows = []
    for step in plan["plan"]["steps"]:
        effects, amount = step["effects"], step["amount"]
        eh, e1 = effects.get(kh) or {}, effects.get(k1) or {}
        rows.append({"group_id": plan["group_id"], "month": pd.Timestamp(plan["month"]), "step": int(step["step"]), "lever": step["lever"],
                     "donor": step["donor"], "recipient": step["recipient"], "fraction": _num(step["fraction"]),
                     "amount_recipient_ccy": _num(amount.get("recipient_ccy")), "amount_donor_ccy": _num(amount.get("donor_ccy")),
                     "amount_reporting_ccy": _num(amount.get("reporting_ccy")), "fx_applied": _num(amount.get("fx_applied")),
                     "recipient_level_before_k6": _num((eh.get("recipient") or {}).get("level_before")),
                     "recipient_level_after_k6": _num((eh.get("recipient") or {}).get("level_after")),
                     "donor_level_before_k6": _num((eh.get("donor") or {}).get("level_before")),
                     "donor_level_after_k6": _num((eh.get("donor") or {}).get("level_after")),
                     "delta_utility_k6": _delta(eh), "delta_utility_k1": _delta(e1),
                     "efficiency_per_10k": _num(step.get("efficiency_per_10k")),
                     "binding_constraints": "|".join(step.get("binding_constraints") or [])})
    return rows


def _delta(effect):
    before, after = _num(effect.get("group_utility_before")), _num(effect.get("group_utility_after"))
    return None if before is None or after is None else after - before


def _group_row(plan, grounding_ok, config):
    kh, k1 = _k(config.horizon_months), _k(1)
    coverage, baseline, block = plan["coverage"], plan["baseline"], plan["plan"]
    totals = block.get("totals") or {}
    committed = sum(_num(item.get("reporting_ccy")) or 0.0 for item in (block.get("cash_committed_by_donor") or {}).values())
    return {"group_id": plan["group_id"], "month": pd.Timestamp(plan["month"]), "status": plan["status"],
            "subsidiaries": int(coverage["subsidiaries"]), "optimizable": int(coverage["optimizable"]),
            "with_reliable_cash": int(coverage["with_reliable_cash"]), "with_debt_component": int(coverage["with_debt_component"]),
            "with_ap_component": int(coverage["with_ap_component"]), "utility_before": _num(baseline.get("group_utility_0_100")),
            "utility_after_k1": _num((totals.get(k1) or {}).get("group_utility_after")),
            "utility_after_k6": _num((totals.get(kh) or {}).get("group_utility_after")),
            "min_level_before": _num(baseline.get("min_level")), "min_level_after_k6": _num((totals.get(kh) or {}).get("min_level_after")),
            "steps": len(block["steps"]), "cash_committed_reporting_ccy": committed if block["steps"] else 0.0,
            "stopped_because": block.get("stopped_because"), "greedy_gap": _num((plan.get("certificate") or {}).get("greedy_gap")),
            "grounding_ok": bool(grounding_ok)}


def _tramo_changes(plan, config):
    """Filiales cuyo tramo en régimen (nivel tras su último paso en k=H) difiere del tramo de partida."""
    kh = _k(config.horizon_months)
    final = {}
    for step in plan["plan"]["steps"]:
        effect = step["effects"].get(kh) or {}
        for role in (ROLE_RECIPIENT, ROLE_DONOR):
            level = _num((effect.get(role) or {}).get("level_after"))
            if level is not None:
                final[step[role]] = level
    before = {item["company_id"]: item for item in plan["baseline"]["subsidiaries"]}
    changes = []
    for company_id in sorted(final):
        start = before.get(company_id, {})
        after = tramo_of(final[company_id], config.tramo_bounds)
        if start.get("tramo") in TRAMO_LABELS and start["tramo"] != after:
            changes.append({"group_id": plan["group_id"], "company_id": company_id, "from": start["tramo"], "to": after,
                            "level_before": _num(start.get("level")), "level_after": final[company_id]})
    return changes


# ---------------------------------------------------------------- papel en el grupo y filas de sensibilidad


def plan_roles(plan):
    """`{company_id: {"donor": [pasos], "recipient": [pasos]}}` y receptoras de algún paso P."""
    roles, covered = {}, set()
    for step in plan["plan"]["steps"]:
        for role in (ROLE_DONOR, ROLE_RECIPIENT):
            roles.setdefault(step[role], {ROLE_DONOR: [], ROLE_RECIPIENT: []})[role].append(int(step["step"]))
        if step["lever"] == "P":
            covered.add(step["recipient"])
    return roles, covered


def group_context(plan, company_id, roles=None):
    """`{"has_group_plan", "role", "steps"}`: `donor` si solo dona, `recipient` si solo recibe, `both` si hace ambas cosas en pasos distintos."""
    roles = roles if roles is not None else plan_roles(plan)[0]
    own = roles.get(company_id, {ROLE_DONOR: [], ROLE_RECIPIENT: []})
    donates, receives = bool(own[ROLE_DONOR]), bool(own[ROLE_RECIPIENT])
    role = ROLE_BOTH if donates and receives else ROLE_DONOR if donates else ROLE_RECIPIENT if receives else ROLE_NONE
    return {"has_group_plan": plan["status"] == STATUS_PLAN, "role": role, "steps": sorted(set(own[ROLE_DONOR]) | set(own[ROLE_RECIPIENT]))}


def mark_covered_by_group_plan(sens, covered):
    """`feasibility.covered_by_group_plan` en `ap_on_time` disponible: `True` si un paso P del plan tiene a la empresa como receptora."""
    for lever in sens.get("levers", []):
        if lever.get("lever") == AP_LEVER and lever.get("available") and isinstance(lever.get("feasibility"), dict):
            lever["feasibility"]["covered_by_group_plan"] = sens["company_id"] in covered
    return sens


def _lever_rows(sens):
    baseline = sens.get("baseline") or {}
    rows = []
    for lever in sens.get("levers", []):
        if not lever.get("available"):
            continue
        slope, target, feasibility = lever.get("slope_now") or {}, lever.get("to_next_tramo") or {}, lever.get("feasibility") or {}
        rows.append({"company_id": sens["company_id"], "group_id": sens.get("group_id"), "month": pd.Timestamp(sens["month"]),
                     "level": _num(baseline.get("level")), "tramo": baseline.get("tramo"), "lever": lever["lever"], "type": lever.get("type"),
                     "component": lever.get("component"), "current": _num(lever.get("current")), "unit": lever.get("unit"),
                     "level_per_pct": _num(slope.get("level_per_pct")), "level_per_10k": _num(slope.get("level_per_10k")),
                     "valid_until": _num(slope.get("valid_until")), "next_tramo_target": _num(target.get("target")),
                     "reachable": None if target.get("reachable") is None else bool(target.get("reachable")),
                     "rel_change_needed": _num(target.get("rel_change_needed")), "quantity_needed": _num(target.get("quantity_needed")),
                     "cash_equivalent": _num(target.get("cash_equivalent")), "feasible_alone": feasibility.get("feasible_alone"),
                     "covered_by_group_plan": feasibility.get("covered_by_group_plan")})
    return rows


# ---------------------------------------------------------------- acumuladores del informe


class _Summary:
    """Agregados del informe global, alimentados plan a plan y sensibilidad a sensibilidad."""

    def __init__(self, config):
        self.config = config
        self.by_status = {status: 0 for status in STATUSES}
        self.reasons, self.reasons_by_lever = {}, {lever: {} for lever in config.levers}
        self.steps_by_lever, self.cash_by_lever = {lever: 0 for lever in config.levers}, {lever: 0.0 for lever in config.levers}
        self.delta_k6, self.delta_k1, self.tramo_changes, self.gap_positive = [], [], [], []
        self.plan_count = self.steps_total = 0
        self.group_grounding_failed, self.company_grounding_failed = [], []
        self.companies = self.scored = self.with_any_lever = self.reachable_companies = 0
        self.available_by_lever = {lever: 0 for lever in SENSITIVITY_LEVERS}
        self.reachable_by_lever = {lever: 0 for lever in SENSITIVITY_LEVERS}
        self.rel_change_by_lever = {lever: [] for lever in SENSITIVITY_LEVERS}
        self.unavailable_reasons = {}
        self.top_by_tramo = {label: {} for label in TRAMO_LABELS}
        self.roles = {ROLE_RECIPIENT: 0, ROLE_DONOR: 0, ROLE_BOTH: 0, ROLE_NONE: 0}
        self.ap_feasibility = {"feasible_alone": 0, "requires_financing": 0, "unknown": 0, "covered_by_group_plan": 0}

    def add_plan(self, plan, grounding_ok):
        self.by_status[plan["status"]] = self.by_status.get(plan["status"], 0) + 1
        if not grounding_ok:
            self.group_grounding_failed.append(plan["group_id"])
        for item in plan.get("levers_evaluated", []):
            if not item.get("feasible") and item.get("reason"):
                self.reasons[item["reason"]] = self.reasons.get(item["reason"], 0) + 1
                by_lever = self.reasons_by_lever.setdefault(item["lever"], {})
                by_lever[item["reason"]] = by_lever.get(item["reason"], 0) + 1
        if plan["status"] != STATUS_PLAN:
            return
        kh, k1 = _k(self.config.horizon_months), _k(1)
        self.plan_count += 1
        steps = plan["plan"]["steps"]
        self.steps_total += len(steps)
        for step in steps:
            self.steps_by_lever[step["lever"]] = self.steps_by_lever.get(step["lever"], 0) + 1
            self.cash_by_lever[step["lever"]] = self.cash_by_lever.get(step["lever"], 0.0) + (_num(step["amount"].get("reporting_ccy")) or 0.0)
        before = _num(plan["baseline"].get("group_utility_0_100"))
        totals = plan["plan"].get("totals") or {}
        for key, sink in ((kh, self.delta_k6), (k1, self.delta_k1)):
            after = _num((totals.get(key) or {}).get("group_utility_after"))
            if before is not None and after is not None:
                sink.append(after - before)
        self.tramo_changes += _tramo_changes(plan, self.config)
        certificate = plan.get("certificate") or {}
        if certificate.get("checked") and (_num(certificate.get("greedy_gap")) or 0.0) > 0:
            self.gap_positive.append(plan["group_id"])

    def add_sensitivity(self, sens, grounding_ok):
        self.companies += 1
        if not grounding_ok:
            self.company_grounding_failed.append(sens["company_id"])
        context = sens.get("group_context") or {}
        if context.get("has_group_plan"):
            self.roles[context.get("role")] = self.roles.get(context.get("role"), 0) + 1
        if sens.get("status") != "sensitivity":
            return
        self.scored += 1
        levers = sens.get("levers", [])
        available = [lever for lever in levers if lever.get("available")]
        if available:
            self.with_any_lever += 1
        for lever in levers:
            if not lever.get("available"):
                reason = lever.get("reason") or "unknown"
                self.unavailable_reasons[reason] = self.unavailable_reasons.get(reason, 0) + 1
                continue
            name = lever["lever"]
            self.available_by_lever[name] = self.available_by_lever.get(name, 0) + 1
            target = lever.get("to_next_tramo") or {}
            if target.get("reachable"):
                self.reachable_by_lever[name] = self.reachable_by_lever.get(name, 0) + 1
                self.rel_change_by_lever.setdefault(name, []).append(target.get("rel_change_needed"))
            if name == AP_LEVER:
                feasibility = lever.get("feasibility") or {}
                verdict = feasibility.get("feasible_alone")
                key = "unknown" if verdict is None else "feasible_alone" if verdict else "requires_financing"
                self.ap_feasibility[key] += 1
                if feasibility.get("covered_by_group_plan"):
                    self.ap_feasibility["covered_by_group_plan"] += 1
        if any((lever.get("to_next_tramo") or {}).get("reachable") for lever in available):
            self.reachable_companies += 1
        ranking = (sens.get("ranking") or {}).get("by_pct") or []
        tramo = (sens.get("baseline") or {}).get("tramo")
        if ranking and tramo in self.top_by_tramo:
            self.top_by_tramo[tramo][ranking[0]] = self.top_by_tramo[tramo].get(ranking[0], 0) + 1

    def report(self):
        groups = {"total": sum(self.by_status.values()), "by_status": dict(self.by_status), "reasons": _sorted_counts(self.reasons),
                  "reasons_by_lever": {lever: _sorted_counts(counts) for lever, counts in self.reasons_by_lever.items()},
                  "plans": {"count": self.plan_count, "steps_total": self.steps_total, "steps_by_lever": dict(self.steps_by_lever),
                            "delta_utility_k6": _distribution(self.delta_k6), "delta_utility_k1": _distribution(self.delta_k1),
                            "subsidiaries_changing_tramo": len(self.tramo_changes), "tramo_changes": list(self.tramo_changes),
                            "cash_committed_reporting_ccy": {"total": float(sum(self.cash_by_lever.values())), "by_lever": dict(self.cash_by_lever)}},
                  "greedy_gap_positive": list(self.gap_positive),
                  "grounding_failures": len(self.group_grounding_failed), "grounding_failed": list(self.group_grounding_failed)}
        companies = {"total": self.companies, "scored": self.scored, "not_scored": self.companies - self.scored,
                     "with_any_lever": self.with_any_lever, "available_by_lever": dict(self.available_by_lever),
                     "unavailable_reasons": _sorted_counts(self.unavailable_reasons),
                     "top_lever_by_pct_by_tramo": {label: _sorted_counts(counts) for label, counts in self.top_by_tramo.items()},
                     "reachable_next_tramo": self.reachable_companies, "reachable_by_lever": dict(self.reachable_by_lever),
                     "rel_change_needed_by_lever": {lever: _distribution(values) for lever, values in self.rel_change_by_lever.items()},
                     "ap_on_time_feasibility": dict(self.ap_feasibility), "roles_in_group_plans": dict(self.roles),
                     "grounding_failures": len(self.company_grounding_failed), "grounding_failed": list(self.company_grounding_failed)}
        return groups, companies


# ---------------------------------------------------------------- publicación


def _code_manifest():
    code = code_manifest()
    package = {name: digest for name, digest in code["source_sha256"].items() if name.startswith("src/xray/group_advisor/")}
    code["group_advisor"] = {"source_sha256": package,
                             "code_sha256": hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest()}
    return code


def _outputs_sha256(staged):
    return {path.relative_to(staged).as_posix(): sha256(path) for path in sorted(staged.rglob("*")) if path.is_file()}


def _dump(path, content):
    path.write_text(json.dumps(json_safe(content), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def _publish(staged, out_dir, manifest_name):
    """Carpetas enteras con respaldo en `.history/<id>/` y, después, ficheros planos y manifiesto vía `publish_bundle`."""
    if (out_dir / ".pipeline.lock").exists():
        raise RuntimeError("Publicación del advisor en curso")
    backup = out_dir / ".history" / uuid4().hex
    for name in DIRECTORIES:
        target = out_dir / name
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True)
            os.replace(target, backup / name)
        os.replace(staged / name, target)
    publish_bundle(staged, out_dir, manifest_name)


# ---------------------------------------------------------------- ejecución


def run_from_states(states, inputs_sha256, config, out_dir, month=None, features_dir=None, before_publish=None, verbose=True,
                    extra_timings=None):
    """Núcleo del pipeline sobre un iterable de `GroupState`; publica en `out_dir` y devuelve el informe global.

    `before_publish` (opcional) se invoca con el staging completo justo antes de publicar (p. ej. para comprobar que
    las entradas no cambiaron). `month` es informativo (por defecto el del primer estado).
    """
    config = config or default_config()
    out_dir = Path(out_dir)
    check_out_dir(out_dir, features_dir)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.perf_counter()
    summary = _Summary(config)
    group_rows, step_rows, lever_rows = [], [], []
    month = pd.Timestamp(month) if month is not None else None
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=out_dir) as directory:
        staged = Path(directory)
        plans_dir, sens_dir = staged / PLANS_DIR, staged / SENSITIVITY_DIR
        plans_dir.mkdir()
        sens_dir.mkdir()
        for state in states:
            if month is None:
                month = pd.Timestamp(state.month)
            plan = build_plan(state, config, generated_at)
            text = render_plan(plan, "markdown")
            grounding = validate_grounding(text, plan)
            (plans_dir / f"{plan['group_id']}.json").write_text(plan_to_json(plan), encoding="utf-8")
            (plans_dir / f"{plan['group_id']}.md").write_text(text, encoding="utf-8")
            summary.add_plan(plan, grounding.ok)
            group_rows.append(_group_row(plan, grounding.ok, config))
            step_rows += _step_rows(plan, config)
            roles, covered = plan_roles(plan)
            for company_id in state.subsidiaries.index:
                sens = company_sensitivity(state, str(company_id), config)
                sens["generated_at"] = generated_at
                sens["group_context"] = group_context(plan, str(company_id), roles)
                mark_covered_by_group_plan(sens, covered)
                text = render_sensitivity(sens, "markdown")
                grounding = validate_grounding(text, sens)
                (sens_dir / f"{sens['company_id']}.json").write_text(sensitivity_to_json(sens), encoding="utf-8")
                (sens_dir / f"{sens['company_id']}.md").write_text(text, encoding="utf-8")
                summary.add_sensitivity(sens, grounding.ok)
                lever_rows += _lever_rows(sens)
        if month is None:
            raise ValueError("No hay estados de grupo que procesar")
        compute_seconds = time.perf_counter() - started
        steps = _frame(step_rows, STEP_SCHEMA).sort_values(["group_id", "step"], kind="stable").reset_index(drop=True)
        groups = _frame(group_rows, GROUP_SCHEMA).sort_values("group_id", kind="stable").reset_index(drop=True)
        levers = _frame(lever_rows, LEVER_SCHEMA).sort_values("company_id", kind="stable").reset_index(drop=True)
        steps.to_parquet(staged / STEPS_FILE, index=False)
        groups.to_parquet(staged / GROUPS_FILE, index=False)
        levers.to_parquet(staged / LEVERS_FILE, index=False)
        group_report, company_report = summary.report()
        timings = {**(extra_timings or {}), "compute_s": compute_seconds}
        report = {"method": METHOD, "generated_at": generated_at, "month": str(month.date()), "config": asdict(config),
                  "groups": group_report, "companies": company_report, "limitations": list(LIMITATIONS),
                  "timings": timings, "inputs_sha256": dict(inputs_sha256)}
        _dump(staged / REPORT_FILE, report)
        manifest = {"created_at": generated_at, "method": METHOD, "month": str(month.date()), "config": asdict(config),
                    "fx": {"fx_rates_to_eur": config.fx_rates_to_eur, "fx_source": config.fx_source, "fx_asof": config.fx_asof},
                    "inputs_sha256": dict(inputs_sha256), "code": _code_manifest(),
                    "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
                    "outputs_sha256": _outputs_sha256(staged)}
        _dump(staged / MANIFEST_FILE, manifest)
        if before_publish is not None:
            before_publish()
        publish_started = time.perf_counter()
        _publish(staged, out_dir, MANIFEST_FILE)
        publish_seconds = time.perf_counter() - publish_started
    if verbose:
        shown = {**timings, "publish_s": publish_seconds, "total_s": time.perf_counter() - started + timings.get("load_inputs_s", 0.0)}
        print(json.dumps(json_safe({"method": METHOD, "out_dir": str(out_dir), "month": report["month"],
                                    "groups": {"by_status": group_report["by_status"], "plans": group_report["plans"]["count"],
                                               "steps_total": group_report["plans"]["steps_total"],
                                               "grounding_failures": group_report["grounding_failures"]},
                                    "companies": {"scored": company_report["scored"], "not_scored": company_report["not_scored"],
                                                  "with_any_lever": company_report["with_any_lever"],
                                                  "reachable_next_tramo": company_report["reachable_next_tramo"],
                                                  "grounding_failures": company_report["grounding_failures"]},
                                    "timings": {key: round(value, 1) for key, value in shown.items()}}),
                         indent=2, ensure_ascii=False, allow_nan=False))
    return report


def run(features_dir=PROCESSED_DIR, out_dir=None, config=None, month=None, verbose=True):
    """Pipeline completo: carga entradas una vez, planes y sensibilidades del mes, publicación en `out_dir` (por defecto
    `features_dir/advisor`). Devuelve el informe global (`_advisor_report.json`)."""
    config = config or default_config()
    features_dir = Path(features_dir)
    out_dir = resolve_out_dir(features_dir, out_dir)
    check_out_dir(out_dir, features_dir)
    started = time.perf_counter()
    inputs = load_inputs(features_dir, config)
    load_seconds = time.perf_counter() - started
    month = resolve_month(inputs, month, config)
    states = iter_group_states(inputs, month, config)
    return run_from_states(states, inputs.inputs_sha256, config, out_dir, month=month, features_dir=features_dir,
                           before_publish=lambda: verify_inputs_unchanged(features_dir, inputs.inputs_sha256),
                           verbose=verbose, extra_timings={"load_inputs_s": load_seconds})
