"""Optimizador greedy del plan de grupo (spec `docs/group-optimization.md` §5).

Un `WorkingState` mutable lleva, para cada `k` reportado (siempre incluye `H`), las filas de
señales y los niveles de las filiales optimizables tras los pasos ya aplicados, además de la caja
disponible de cada donante (su moneda), la fracción acumulada por `(palanca, receptora)` (R4) y
las cuotas asumidas por donante (entran en el colchón R2). `generate_candidates` aplica las
precondiciones y R1–R5 y evalúa cada candidato factible con las mismas primitivas que
`counterfactual.evaluate_action`, pero en un solo `level_from_signals` por `k` (una llamada por
candidato costaría ≈9 ms y un grupo de 22 filiales genera 3.696 candidatos por paso). El paso
elegido se vuelve a evaluar con `evaluate_action`, que es la referencia.

Las fracciones `φ` del plan son siempre fracciones de la necesidad **original** de la receptora
(`Σφ ≤ 1` significa necesidad cubierta). Cuando una receptora ya tiene parte de su servicio
asumido, el parámetro pasado a `debt_service_scale` se reexpresa sobre la fila de trabajo para
que el efecto siga siendo aditivo y el servicio externo del grupo se conserve exactamente.
"""
import math
from dataclasses import dataclass, replace

from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.counterfactual import (COMPONENTS, Action, ActionEffect, apply_d1, apply_o, apply_p, evaluate_action,
                                               level_from_signals)
from xray.group_advisor.fx import MissingFXRateError, convert
from xray.group_advisor.objective import group_utility, subsidiary_weights

REASON_DONOR_CASH = "donor_cash_unreliable"
REASON_DONOR_OUTFLOW = "donor_outflow_unavailable"
REASON_DONOR_INFLOW = "donor_no_inflow"
REASON_DONOR_SERVICE = "donor_debt_service_unavailable"
REASON_DONOR_BUFFER = "donor_buffer"
REASON_DONOR_FLOOR = "donor_level_floor"
REASON_DONOR_INDICATOR = "donor_would_hit_zero_inflow_indicator"
REASON_RECIPIENT_NO_DEBT = "recipient_no_debt_service"
REASON_RECIPIENT_NO_OUTFLOW = "recipient_no_operating_outflow"
REASON_RECIPIENT_MARGIN = "recipient_margin_unavailable"
REASON_RECIPIENT_AP = "recipient_ap_component_unavailable"
REASON_RECIPIENT_NO_DELAY = "recipient_no_ap_delay"
REASON_RECIPIENT_NO_NEED = "recipient_no_ap_need"
REASON_RECIPIENT_CASH = "recipient_cash_unreliable"
REASON_RECIPIENT_NOT_CONSTRAINED = "recipient_not_liquidity_constrained"
REASON_RECIPIENT_LEVEL = "recipient_level_unavailable"
REASON_FX = "fx_rate_unavailable"
REASON_FRACTION_CAP = "fraction_cap"
REASON_LOWER_EFFICIENCY = "lower_efficiency"
REASON_BELOW_MIN_GAIN = "below_min_gain"
STATE_REASONS = frozenset({REASON_DONOR_BUFFER, REASON_DONOR_FLOOR, REASON_DONOR_INDICATOR, REASON_FRACTION_CAP})

BINDING_COVERED = "need_fully_covered"
BINDING_BUFFER = "donor_buffer"
BINDING_FLOOR = "donor_level_floor"
BINDING_CAP = "fraction_cap"
BINDING_ORDER = (BINDING_COVERED, BINDING_BUFFER, BINDING_FLOOR, BINDING_CAP)

STOP_NO_CANDIDATES = "no_feasible_candidates"
STOP_MIN_GAIN = "no_candidate_above_min_gain"
STOP_MAX_STEPS = "max_steps_reached"

LEVER_COMPONENT = {"D1": "debt", "P": "payments", "O": "operations"}
LEVER_SIGNAL = {"D1": "debt_service_w", "P": "ap_delay_w", "O": "op_margin_w"}
DEFAULT_MIN_DELAY_COUNT = 5
FLOOR_WARNING_MARGIN = 0.5
EFFICIENCY_UNIT = 10_000.0
_TOL = 1e-9


def _num(value):
    if value is None:
        return math.nan
    try:
        value = float(value)
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def _flag(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return bool(value)


def _tol(reference):
    return _TOL * max(1.0, abs(reference))


# ---------------------------------------------------------------- estado de trabajo


class WorkingState:
    """Estado mutable del greedy: filas y niveles por `k`, caja, fracciones usadas y cuotas asumidas."""

    def __init__(self, ids, rows_by_k, levels_by_k, cash, baseline_levels, weights, config, fraction_used=None, assumed_service=None):
        self.ids = list(ids)
        self.rows_by_k = rows_by_k
        self.levels_by_k = levels_by_k
        self.cash = cash
        self.baseline_levels = baseline_levels
        self.weights = weights
        self.config = config
        self.fraction_used = dict(fraction_used or {})
        self.assumed_service = dict(assumed_service or {})

    @classmethod
    def from_state(cls, state, config=None, ks=None):
        """Estado inicial desde `GroupState`: solo filiales optimizables; caja solo si `cash_reliable`."""
        config = config or AdvisorConfig()
        horizon = config.horizon_months
        ks = tuple(sorted(set(ks if ks is not None else config.report_k) | {horizon}))
        ids = list(state.optimizable_ids)
        frame = state.subsidiaries
        levels = {cid: _num(frame.at[cid, "level"]) for cid in ids}
        rows = {cid: state.signal_row(cid) for cid in ids}
        cash = {}
        for cid in ids:
            value = _num(frame.at[cid, "reconstructed_cash"])
            if bool(frame.at[cid, "cash_reliable"]) and not math.isnan(value):
                cash[cid] = value
        weights = subsidiary_weights(state, config)
        return cls(ids, {k: {cid: dict(row) for cid, row in rows.items()} for k in ks}, {k: dict(levels) for k in ks},
                   cash, dict(levels), {cid: weights[cid] for cid in ids}, config)

    @property
    def horizon(self):
        return self.config.horizon_months

    @property
    def ks(self):
        return tuple(self.rows_by_k)

    @property
    def rows(self):
        return self.rows_by_k[self.horizon]

    @property
    def levels(self):
        return self.levels_by_k[self.horizon]

    def copy(self):
        return WorkingState(self.ids, {k: {cid: dict(row) for cid, row in rows.items()} for k, rows in self.rows_by_k.items()},
                            {k: dict(levels) for k, levels in self.levels_by_k.items()}, dict(self.cash), dict(self.baseline_levels),
                            dict(self.weights), self.config, self.fraction_used, self.assumed_service)

    def group_utility(self, k=None, overrides=None):
        """`G` con los niveles de trabajo en `k` (por defecto `H`), sustituyendo los de `overrides`."""
        levels = self.levels_by_k[self.horizon if k is None else k]
        values = [(overrides or {}).get(cid, levels[cid]) for cid in self.ids]
        return group_utility(values, [self.weights[cid] for cid in self.ids], self.config)

    def min_level(self, k=None):
        values = [v for v in self.levels_by_k[self.horizon if k is None else k].values() if not math.isnan(_num(v))]
        return min(values) if values else math.nan


# ---------------------------------------------------------------- colchón, liquidez, necesidad


def donor_buffer(sub_row, assumed_service=0.0, config=None):
    """`B_a = max(κ·(O3 + s_a + cuotas asumidas), D30 + D60)`; términos NaN omitidos; NaN si `O3` no está observado."""
    config = config or AdvisorConfig()
    outflow = _num(sub_row.get("tx_outflow_ma3"))
    if math.isnan(outflow):
        return math.nan
    monthly = outflow
    for term in (_num(sub_row.get("monthly_debt_service")), _num(assumed_service)):
        if not math.isnan(term):
            monthly += term
    buffer = config.donor_buffer_months * monthly
    due = [v for v in (_num(sub_row.get("inv_ap_due_30_amount")), _num(sub_row.get("inv_ap_due_60_amount"))) if not math.isnan(v)]
    return max(buffer, sum(due)) if due else buffer


def ap_need(sub_row):
    """`V + D30` (AP vencido más próximo a 30 días) con NaN omitidos; NaN si ambos faltan."""
    terms = [v for v in (_num(sub_row.get("inv_ap_overdue_amount")), _num(sub_row.get("inv_ap_due_30_amount"))) if not math.isnan(v)]
    return sum(terms) if terms else math.nan


def reliable_cash(sub_row):
    return _num(sub_row.get("reconstructed_cash")) if _flag(sub_row.get("cash_reliable")) else math.nan


def is_liquidity_constrained(sub_row, config=None):
    """`C < V + D30` o `runway < liquidity_constrained_runway`; `None` si no hay caja fiable ni runway para juzgar."""
    config = config or AdvisorConfig()
    cash, need, runway = reliable_cash(sub_row), ap_need(sub_row), _num(sub_row.get("runway_months"))
    checks = []
    if not math.isnan(cash) and not math.isnan(need):
        checks.append(cash < need)
    if not math.isnan(runway):
        checks.append(runway < config.liquidity_constrained_runway)
    return any(checks) if checks else None


def recipient_need(sub_row, lever, config=None):
    """Necesidad de la receptora en su moneda: D1 → `H·s_b`; P → `max(0, V + D30 − max(0, C))` (NaN sin caja fiable)."""
    config = config or AdvisorConfig()
    if lever == "D1":
        return config.horizon_months * _num(sub_row.get("monthly_debt_service"))
    if lever == "O":
        monthly = _num(sub_row.get("window_outflow_sum")) / config.horizon_months
        return monthly if monthly > 0 else math.nan
    if lever == "P":
        need, cash = ap_need(sub_row), reliable_cash(sub_row)
        if math.isnan(need) or math.isnan(cash):
            return math.nan
        return max(0.0, need - max(0.0, cash))
    raise ValueError(f"Palanca desconocida: {lever!r}")


def _min_delay_count(config):
    return getattr(config, "min_delay_count", DEFAULT_MIN_DELAY_COUNT)


def ap_delay_observed(sub_row, config=None):
    """`ap_delay_w` finito con al menos `min_delay_count` pagos (si el conteo está disponible)."""
    delay, count = _num(sub_row.get("ap_delay_w")), _num(sub_row.get("ap_delay_count_w"))
    return not math.isnan(delay) and (math.isnan(count) or count >= _min_delay_count(config or AdvisorConfig()))


def ap_delay_unexplained(sub_row, config=None):
    """Paga tarde (`p > 0`) con caja fiable y sin restricción de liquidez: política de pago o higiene ERP, no palanca."""
    config = config or AdvisorConfig()
    return (ap_delay_observed(sub_row, config) and _num(sub_row.get("ap_delay_w")) > 0 and not math.isnan(reliable_cash(sub_row))
            and is_liquidity_constrained(sub_row, config) is False)


def donor_reason(sub_row, lever, cash, config=None):
    """Primer motivo por el que `a` no puede ser donante para `lever`; `None` si es elegible (sin mirar el colchón)."""
    config = config or AdvisorConfig()
    if not _flag(sub_row.get("cash_reliable")) or math.isnan(_num(cash)):
        return REASON_DONOR_CASH
    if math.isnan(_num(sub_row.get("tx_outflow_ma3"))):
        return REASON_DONOR_OUTFLOW
    if not _num(sub_row.get("level_inflow_sum")) > 0:
        return REASON_DONOR_INFLOW
    if lever == "D1" and math.isnan(_num(sub_row.get("window_debt_service_sum"))):
        return REASON_DONOR_SERVICE
    if lever == "O" and math.isnan(_num(sub_row.get("window_outflow_sum"))):
        return REASON_DONOR_OUTFLOW
    return None


def recipient_reason(sub_row, lever, config=None):
    """Primer motivo por el que `b` no es receptora de `lever`; `None` si tiene necesidad evaluable."""
    config = config or AdvisorConfig()
    if lever == "D1":
        return None if _num(sub_row.get("monthly_debt_service")) > 0 else REASON_RECIPIENT_NO_DEBT
    if lever == "O":
        if not _num(sub_row.get("window_outflow_sum")) > 0:
            return REASON_RECIPIENT_NO_OUTFLOW
        return None if not math.isnan(_num(sub_row.get("op_margin_w"))) else REASON_RECIPIENT_MARGIN
    if not ap_delay_observed(sub_row, config):
        return REASON_RECIPIENT_AP
    if not _num(sub_row.get("ap_delay_w")) > 0:
        return REASON_RECIPIENT_NO_DELAY
    if not ap_need(sub_row) > 0:
        return REASON_RECIPIENT_NO_NEED
    if math.isnan(reliable_cash(sub_row)):
        return REASON_RECIPIENT_CASH
    constrained = is_liquidity_constrained(sub_row, config)
    if constrained is None:
        return REASON_RECIPIENT_CASH
    if constrained is False:
        return REASON_RECIPIENT_NOT_CONSTRAINED
    return None if recipient_need(sub_row, "P", config) > 0 else REASON_RECIPIENT_NO_NEED


def donor_capacity(sub_row, cash, assumed_service=0.0, config=None):
    """`max(0, C_a − B_a)` en moneda del donante; NaN sin caja fiable o sin colchón evaluable."""
    cash, buffer = _num(cash), donor_buffer(sub_row, assumed_service, config)
    if math.isnan(cash) or math.isnan(buffer):
        return math.nan
    return max(0.0, cash - buffer)


def report_amount(amount, currency, config):
    """Importe en `reporting_currency` si hay tabla y tipo; si no, en la moneda del donante (spec §5.4)."""
    if config.fx_rates_to_eur is None or currency == config.reporting_currency:
        return amount
    try:
        return convert(amount, currency, config.reporting_currency, config.fx_rates_to_eur)[0]
    except MissingFXRateError:
        return amount


# ---------------------------------------------------------------- candidatos


@dataclass
class PairEvaluation:
    lever: str
    donor: str
    recipient: str
    donor_currency: str
    recipient_currency: str
    fx_applied: float | None
    feasible: bool
    need_recipient_ccy: float
    donor_capacity: float
    reason: str | None


@dataclass(frozen=True)
class Candidate:
    action: Action
    effects: dict                   # {k: ActionEffect}
    delta_utility: float            # ΔG en k=H
    efficiency: float               # ΔG por 10.000 de `x_report`
    x_report: float                 # caja comprometida en `reporting_currency` (o moneda del donante)
    binding: tuple
    reason: str | None
    d1_params: dict | None = None   # {k: (φ relativa a la fila de trabajo, cuota mensual de b en moneda de a)}


@dataclass
class CandidateSet:
    candidates: list        # factibles, ya ordenados
    pairs: list             # PairEvaluation por (palanca, donante, receptora)


@dataclass
class _Spec:
    lever: str
    donor: str
    recipient: str
    fraction: float
    x_b: float
    x_a: float
    fx_applied: float | None
    psi: float | None
    d1_params: dict | None
    binding: list
    pair: PairEvaluation


def order_key(candidate):
    """Clave del greedy: `(−e, −ΔG, cruzada, x_report, donante, receptora, palanca, fracción)` con floats redondeados."""
    action = candidate.action
    return (-round(candidate.efficiency, 9), -round(candidate.delta_utility, 9), action.fx_applied is not None,
            round(candidate.x_report, 6), action.donor, action.recipient, action.lever, round(action.fraction, 9))


def _subsidiary_rows(state):
    frame = state.subsidiaries
    return {str(cid): dict(zip(frame.columns, values)) for cid, values in zip(frame.index, frame.to_numpy(dtype=object))}


def _d1_params(working, recipient, fraction, need_original, rate):
    """Por `k`: `(φ_rel, s_b^k·fx)` tales que `apply_d1` sobre la fila de trabajo asume exactamente `φ·s_b` originales."""
    params = {}
    for k in working.ks:
        service = _num(working.rows_by_k[k][recipient].get("window_debt_service_sum"))
        if math.isnan(service) or service <= 0:
            return None
        phi_rel = min(fraction * need_original / service, 1.0)
        params[k] = (phi_rel, service / working.horizon * rate)
    return params


def _o_params(working, recipient, fraction, need_original, rate):
    """Por `k`: `(ω_rel, o_b^k·fx)` tales que `apply_o` asume exactamente `fraction·H·o_b` originales."""
    params = {}
    for k in working.ks:
        outflow = _num(working.rows_by_k[k][recipient].get("window_outflow_sum"))
        if math.isnan(outflow) or outflow <= 0:
            return None
        params[k] = (min(fraction * need_original * working.horizon / outflow, 1.0), outflow / working.horizon * rate)
    return params


def _perturb(rows, lever, donor, recipient, k, horizon, d1_params=None, psi=None):
    row_a, row_b = rows[donor], rows[recipient]
    if lever == "D1":
        phi_rel, monthly = d1_params[k]
        return apply_d1(row_a, row_b, phi_rel, k, horizon, monthly)
    if lever == "O":
        omega_rel, monthly = d1_params[k]
        return apply_o(row_a, row_b, omega_rel, k, horizon, monthly)
    return dict(row_a), apply_p(row_b, psi, k, horizon)


def _components(arrays, position):
    out = {}
    for component in COMPONENTS:
        value = float(arrays[component][position])
        out[component] = None if math.isnan(value) else value
    return out


def _effects_batch(specs, working, reference_state, ks):
    """`ActionEffect` por candidato y `k` con un solo `level_from_signals` por `k` (misma matemática que `evaluate_action`)."""
    horizon = working.horizon
    effects = [dict() for _ in specs]
    if not specs:
        return effects
    for k in ks:
        rows = working.rows_by_k[k]
        base = level_from_signals(rows, reference_state)
        base_level, base_debt = base.level.to_dict(), base.level_debt.to_dict()
        perturbed, after = {}, []
        for index, spec in enumerate(specs):
            row_a2, row_b2 = _perturb(rows, spec.lever, spec.donor, spec.recipient, k, horizon, spec.d1_params, spec.psi)
            perturbed[f"{index}|a"], perturbed[f"{index}|b"] = row_a2, row_b2
            after.append((row_a2, row_b2))
        result = level_from_signals(perturbed, reference_state)
        level, debt = result.level.to_numpy(dtype=float), result.level_debt.to_numpy(dtype=float)
        arrays = {component: result[f"level_{component}"].to_numpy(dtype=float) for component in COMPONENTS}
        for index, spec in enumerate(specs):
            row_a, row_b = rows[spec.donor], rows[spec.recipient]
            row_a2, row_b2 = after[index]
            signal = LEVER_SIGNAL[spec.lever]
            pa, pb = 2 * index, 2 * index + 1
            effects[index][k] = ActionEffect(
                k=int(k), donor_level_before=_num(base_level[spec.donor]), donor_level_after=float(level[pa]),
                recipient_level_before=_num(base_level[spec.recipient]), recipient_level_after=float(level[pb]),
                donor_components_after=_components(arrays, pa), recipient_components_after=_components(arrays, pb),
                donor_signal_before=_num(row_a.get(signal)), donor_signal_after=_num(row_a2.get(signal)),
                recipient_signal_before=_num(row_b.get(signal)), recipient_signal_after=_num(row_b2.get(signal)),
                recipient_component_dropped=bool(spec.lever == "D1" and not math.isnan(_num(base_debt[spec.recipient]))
                                                 and math.isnan(debt[pb])),
                donor_hits_zero_inflow_indicator=bool(_flag(row_a2.get("debt_without_inflow_w"))
                                                      and not _flag(row_a.get("debt_without_inflow_w"))))
    return effects


def authoritative_effects(state, working, candidate):
    """Efectos del candidato con `counterfactual.evaluate_action` (referencia) en cada `k` del estado de trabajo."""
    horizon, action = working.horizon, candidate.action
    effects = {}
    for k in working.ks:
        rows = working.rows_by_k[k]
        if action.lever in ("D1", "O"):
            phi_rel, monthly = candidate.d1_params[k]
            effects[k] = evaluate_action(rows, state.reference_state, replace(action, fraction=phi_rel), k, horizon, monthly)
        else:
            effects[k] = evaluate_action(rows, state.reference_state, action, k, horizon)
    return effects


def generate_candidates(state, working, config=None, ks=None):
    """Candidatos factibles ordenados y evaluación por par `(palanca, donante, receptora)` desde el estado de trabajo.

    Precedencia de motivos: donante (`donor_cash_unreliable`, `donor_outflow_unavailable`,
    `donor_no_inflow`, `donor_debt_service_unavailable`), receptora, R1 (`fx_rate_unavailable`), R4
    (`fraction_cap`), R2 (`donor_buffer`), y tras evaluar R5 (`donor_level_floor`) e indicador.
    """
    config = config or working.config
    horizon = config.horizon_months
    ks = tuple(sorted(set(ks if ks is not None else working.ks) | {horizon}))
    subs = _subsidiary_rows(state)
    pairs, specs = [], []
    for lever in config.levers:
        for donor in working.ids:
            sub_a = subs[donor]
            cash_a = working.cash.get(donor, math.nan)
            reason_a = donor_reason(sub_a, lever, cash_a, config)
            capacity = donor_capacity(sub_a, cash_a, working.assumed_service.get(donor, 0.0), config)
            for recipient in working.ids:
                if recipient == donor:
                    continue
                sub_b = subs[recipient]
                need = recipient_need(sub_b, lever, config)
                pair = PairEvaluation(lever, donor, recipient, str(sub_a["currency"]), str(sub_b["currency"]), None, False,
                                      need, capacity, None)
                pairs.append(pair)
                pair.reason = reason_a or recipient_reason(sub_b, lever, config)
                if pair.reason:
                    continue
                try:
                    _, rate = convert(1.0, pair.recipient_currency, pair.donor_currency, config.fx_rates_to_eur)
                except MissingFXRateError:
                    pair.reason = REASON_FX
                    continue
                pair.fx_applied = None if pair.donor_currency == pair.recipient_currency else rate
                monthly_b = (_num(sub_b.get("monthly_debt_service")) * rate if lever == "D1"
                             else need * rate if lever == "O" else 0.0)
                fraction_specs, reason = _grid_specs(lever, donor, recipient, pair, working, sub_a, sub_b, need, rate, monthly_b, config)
                if reason:
                    pair.reason = reason
                    continue
                specs.extend(fraction_specs)
    effects = _effects_batch(specs, working, state.reference_state, ks)
    survivors = {}
    candidates = []
    for spec, spec_effects in zip(specs, effects):
        key = (spec.lever, spec.donor, spec.recipient)
        effect = spec_effects[horizon]
        reason = None
        if math.isnan(effect.recipient_level_after) or math.isnan(effect.donor_level_after):
            reason = REASON_RECIPIENT_LEVEL
        elif effect.donor_hits_zero_inflow_indicator:
            reason = REASON_DONOR_INDICATOR
        drop = working.baseline_levels[spec.donor] - effect.donor_level_after
        if reason is None and drop > config.donor_level_floor_drop + _TOL:
            reason = REASON_DONOR_FLOOR
        if reason:
            survivors.setdefault(key, [False, reason])
            survivors[key][1] = reason
            continue
        binding = list(spec.binding)
        if drop > config.donor_level_floor_drop - FLOOR_WARNING_MARGIN:
            binding.append(BINDING_FLOOR)
        before = working.group_utility(horizon)
        after = working.group_utility(horizon, {spec.donor: effect.donor_level_after, spec.recipient: effect.recipient_level_after})
        delta = after - before
        x_report = report_amount(spec.x_a, spec.pair.donor_currency, config)
        if not x_report > 0:
            continue
        action = Action(lever=spec.lever, donor=spec.donor, recipient=spec.recipient, donor_currency=spec.pair.donor_currency,
                        recipient_currency=spec.pair.recipient_currency, fraction=spec.fraction, amount_recipient_ccy=spec.x_b,
                        amount_donor_ccy=spec.x_a, fx_applied=spec.fx_applied, psi=spec.psi)
        candidates.append(Candidate(action=action, effects=spec_effects, delta_utility=delta,
                                    efficiency=delta / (x_report / EFFICIENCY_UNIT), x_report=x_report,
                                    binding=tuple(b for b in BINDING_ORDER if b in binding), reason=None, d1_params=spec.d1_params))
        survivors[key] = [True, None]
    for pair in pairs:
        key = (pair.lever, pair.donor, pair.recipient)
        if key in survivors:
            pair.feasible, pair.reason = bool(survivors[key][0]), survivors[key][1]
    candidates.sort(key=order_key)
    return CandidateSet(candidates, pairs)


def _grid_specs(lever, donor, recipient, pair, working, sub_a, sub_b, need, rate, monthly_b_donor_ccy, config):
    """Fracciones efectivas de la rejilla que respetan R4 (remanente) y R2 (colchón); marca `fraction_cap` y `donor_buffer`."""
    used = working.fraction_used.get((lever, recipient), 0.0)
    remaining = 1.0 - used
    if remaining <= _TOL:
        return [], REASON_FRACTION_CAP
    effective = sorted({min(float(phi), remaining) for phi in config.fractions})
    fits = []
    for phi in effective:
        x_a = phi * need * rate * (config.horizon_months if lever == "O" else 1.0)
        assumed = working.assumed_service.get(donor, 0.0) + (phi * monthly_b_donor_ccy if lever in ("D1", "O") else 0.0)
        buffer = donor_buffer(sub_a, assumed, config)
        if working.cash[donor] - x_a >= buffer - _tol(buffer):
            fits.append(phi)
    if not fits:
        return [], REASON_DONOR_BUFFER
    limited = len(fits) < len(effective)
    specs = []
    for phi in fits:
        binding = []
        if used + phi >= 1.0 - _TOL:
            binding.append(BINDING_COVERED)
        if limited and phi == fits[-1]:
            binding.append(BINDING_BUFFER)
        if remaining < 1.0 - _TOL and phi == remaining:
            binding.append(BINDING_CAP)
        x_b = phi * need * (config.horizon_months if lever == "O" else 1.0)
        d1_params = psi = None
        if lever == "D1":
            d1_params = _d1_params(working, recipient, phi, need, rate)
            if d1_params is None:
                continue
        elif lever == "O":
            d1_params = _o_params(working, recipient, phi, need, rate)
            if d1_params is None:
                continue
        else:
            psi = min(x_b / ap_need(sub_b), 1.0)
        specs.append(_Spec(lever, donor, recipient, phi, x_b, x_b * rate, pair.fx_applied, psi, d1_params, binding, pair))
    return specs, None


def apply_candidate(working, candidate, effects=None):
    """Aplica el candidato al estado de trabajo: caja, fracción usada, cuotas asumidas, filas y niveles en cada `k`."""
    effects = effects or candidate.effects
    action = candidate.action
    working.cash[action.donor] -= action.amount_donor_ccy
    working.fraction_used[(action.lever, action.recipient)] = working.fraction_used.get((action.lever, action.recipient), 0.0) + action.fraction
    if action.lever in ("D1", "O"):
        working.assumed_service[action.donor] = working.assumed_service.get(action.donor, 0.0) + action.amount_donor_ccy / working.horizon
    for k in working.ks:
        rows = working.rows_by_k[k]
        row_a2, row_b2 = _perturb(rows, action.lever, action.donor, action.recipient, k, working.horizon, candidate.d1_params, action.psi)
        rows[action.donor], rows[action.recipient] = row_a2, row_b2
        working.levels_by_k[k][action.donor] = effects[k].donor_level_after
        working.levels_by_k[k][action.recipient] = effects[k].recipient_level_after


# ---------------------------------------------------------------- greedy


@dataclass
class GreedyStep:
    step: int
    candidate: Candidate
    effects: dict                   # {k: ActionEffect} de `evaluate_action`
    utility_before_by_k: dict
    utility_after_by_k: dict


@dataclass
class GreedyResult:
    steps: list
    rejected: list
    stopped_because: str
    working_final: WorkingState
    utility_before: float
    utility_after_by_k: dict
    pairs: list                     # evaluación por par desde el estado inicial (`levers_evaluated`)


def _delta_key(config):
    return f"delta_utility_k{config.horizon_months}"


def _record(rejected, config, lever, donor, recipient, reason, delta):
    rejected[(lever, donor, recipient)] = {"lever": lever, "donor": donor, "recipient": recipient, "reason": reason,
                                           _delta_key(config): delta}


def _record_alternatives(rejected, alternatives, pairs, config, only_reasons=None, first=()):
    """Guarda hasta `rejected_alternatives_kept` alternativas: candidatos factibles por par y luego pares infactibles.

    `first` son claves `(palanca, donante, receptora)` ya aplicadas en el plan: sus motivos finales
    (p. ej. `fraction_cap`, `below_min_gain`) explican «por qué no más» y se registran antes que el resto.
    """
    kept, seen = config.rejected_alternatives_kept, set()
    order = {key: index for index, key in enumerate(first)}
    alternatives = sorted(alternatives, key=lambda c: (order.get((c.action.lever, c.action.donor, c.action.recipient), len(order)),))
    pairs = sorted(pairs, key=lambda p: (order.get((p.lever, p.donor, p.recipient), len(order)),))
    for candidate in alternatives:
        if len(seen) >= kept:
            return
        action = candidate.action
        key = (action.lever, action.donor, action.recipient)
        if key in seen:
            continue
        seen.add(key)
        reason = REASON_LOWER_EFFICIENCY if candidate.delta_utility >= config.min_gain_utility else REASON_BELOW_MIN_GAIN
        _record(rejected, config, *key, reason, candidate.delta_utility)
    for pair in pairs:
        if len(seen) >= kept:
            return
        key = (pair.lever, pair.donor, pair.recipient)
        if pair.feasible or key in seen or (only_reasons is not None and pair.reason not in only_reasons):
            continue
        seen.add(key)
        _record(rejected, config, *key, pair.reason, None)


def optimize_group(state, config=None):
    """Greedy determinista de la spec §5.4; devuelve `GreedyResult` (el JSON lo ensambla `plan.build_plan`)."""
    config = config or AdvisorConfig()
    working = WorkingState.from_state(state, config)
    utility_before = working.group_utility()
    candidates = generate_candidates(state, working, config)
    pairs = candidates.pairs
    steps, rejected, applied = [], {}, []
    stopped = STOP_MAX_STEPS
    for step_number in range(1, config.max_steps + 1):
        feasible = candidates.candidates
        if not feasible:
            stopped = STOP_NO_CANDIDATES
            if steps:
                _record_alternatives(rejected, [], candidates.pairs, config, only_reasons=STATE_REASONS, first=applied)
            break
        best = feasible[0]
        if best.delta_utility < config.min_gain_utility:
            stopped = STOP_MIN_GAIN
            _record_alternatives(rejected, feasible, candidates.pairs, config, first=applied)
            break
        effects = authoritative_effects(state, working, best)
        before = {k: working.group_utility(k) for k in working.ks}
        apply_candidate(working, best, effects)
        after = {k: working.group_utility(k) for k in working.ks}
        steps.append(GreedyStep(step_number, best, effects, before, after))
        key = (best.action.lever, best.action.donor, best.action.recipient)
        rejected.pop(key, None)
        if key not in applied:
            applied.append(key)
        _record_alternatives(rejected, feasible[1:], candidates.pairs, config)
        if step_number == config.max_steps:
            stopped = STOP_MAX_STEPS
            break
        candidates = generate_candidates(state, working, config)
    return GreedyResult(steps=steps, rejected=list(rejected.values()), stopped_because=stopped, working_final=working,
                        utility_before=utility_before, utility_after_by_k={k: working.group_utility(k) for k in working.ks},
                        pairs=pairs)


# ---------------------------------------------------------------- certificado


def _above_min_gain(candidates, config):
    return [c for c in candidates if c.delta_utility >= config.min_gain_utility]


def certificate(state, config=None, result=None):
    """Mejor acción única y mejor par compatible por enumeración cuando `optimizable ≤ exhaustive_max_subsidiaries`.

    Las acciones enumeradas respetan las mismas reglas que el greedy (R1–R5 acumuladas y
    `min_gain_utility`); `greedy_utility` es `G` tras los dos primeros pasos (o todos si hay menos)
    y `greedy_gap = max(0, mejor_par − greedy)`. Sin pasos, o fuera del límite, `checked=False`.
    """
    config = config or AdvisorConfig()
    result = result if result is not None else optimize_group(state, config)
    horizon = config.horizon_months
    if result.steps:
        greedy_utility = result.steps[min(2, len(result.steps)) - 1].utility_after_by_k[horizon]
    else:
        greedy_utility = result.utility_before
    count = len(state.optimizable_ids)
    if not result.steps or count < 2 or count > config.exhaustive_max_subsidiaries:
        return {"checked": False, "best_single_utility": None, "best_pair_utility": None,
                "greedy_utility": greedy_utility, "greedy_gap": None}
    initial = WorkingState.from_state(state, config, ks=(horizon,))
    base = initial.group_utility()
    singles = _above_min_gain(generate_candidates(state, initial, config).candidates, config)
    best_single = max([base + c.delta_utility for c in singles], default=base)
    best_pair = best_single
    for first in singles:
        working = initial.copy()
        apply_candidate(working, first)
        after_first = working.group_utility()
        seconds = _above_min_gain(generate_candidates(state, working, config).candidates, config)
        if seconds:
            best_pair = max(best_pair, after_first + max(c.delta_utility for c in seconds))
    return {"checked": True, "best_single_utility": best_single, "best_pair_utility": best_pair,
            "greedy_utility": greedy_utility, "greedy_gap": round(max(0.0, best_pair - greedy_utility), 6)}
