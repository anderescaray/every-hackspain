"""Estado por filial del advisor (spec `docs/group-optimization.md` §3).

`load_inputs` lee una sola vez las entradas (features con verificación de hash, scores V2,
scores grupo-moneda, contexto de liquidez y referencia congelada), recalcula las señales de
ventana con `xray.score_v2.signals.build_signals` y las sumas `window_outflow_sum` /
`window_debt_service_sum`, y deja todo cacheado en `AdvisorInputs`. `build_group_state`
selecciona las filas de un grupo y un mes y las ensambla en un `GroupState` con las
columnas del contrato compartido del roadmap.

Las sumas de ventana usan exactamente las máscaras de `_flow_aggregates` de V2 (mes con
calidad y flujos observados; el servicio de deuda exige además principal e intereses
observados en todos los meses de la ventana y queda NaN si no, como `debt_service_w`), de
modo que las derivadas `(I−O)/(I+O)` y `S/I` reproducen las señales de V2 sin excepciones.
Los invariantes se comprueban en cada estado (`invariants_report`); un incumplimiento se
registra con `logging`, no interrumpe, y las sumas directas son la verdad.
"""
import bisect
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from xray.artifacts import sha256
from xray.group_advisor.config import TRAMO_LABELS, AdvisorConfig
from xray.paths import PROCESSED_DIR
from xray.score.pipeline import read_panel
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import METHOD, SCHEMA_VERSION, prepare_panel
from xray.score_v2.signals import build_signals, month_quality


log = logging.getLogger(__name__)

SCORES_FILE = "scores_v2/company_monthly_scores.parquet"
GROUP_SCORES_FILE = "scores_v2/group_currency_monthly_scores.parquet"
LIQUIDITY_FILE = "company_currency_liquidity_context.parquet"
REFERENCE_FILE = "scores_v2/_company_score_reference.json"
SCORES_MANIFEST_FILE = "scores_v2/_company_score_manifest.json"
KEYS = ["company_id", "currency", "month"]

SCORE_COLUMNS = ("level", "score", "momentum_adjustment", "level_operations", "level_debt", "level_collections",
                 "level_payments", "level_coverage", "score_status", "score_reason")
SIGNAL_COLUMNS = ("op_margin_w", "debt_service_w", "debt_without_inflow_w", "ar_delay_w", "ap_delay_w",
                  "ar_delay_count_w", "ap_delay_count_w", "level_inflow_sum")
WINDOW_COLUMNS = ("window_outflow_sum", "window_debt_service_sum")
LIQUIDITY_COLUMNS = ("reconstructed_cash", "cash_reliable", "runway_months")
FEATURE_COLUMNS = ("tx_outflow_ma3", "inv_ap_overdue_amount", "inv_ap_due_30_amount", "inv_ap_due_60_amount", "inv_ar_open_amount")
DERIVED_COLUMNS = ("monthly_debt_service", "optimizable", "tramo")
SUBSIDIARY_COLUMNS = ("currency", "group_id", *SCORE_COLUMNS, *SIGNAL_COLUMNS, *WINDOW_COLUMNS, "monthly_debt_service",
                      *LIQUIDITY_COLUMNS, *FEATURE_COLUMNS, "optimizable", "tramo")
BASE_COLUMNS = tuple(c for c in SUBSIDIARY_COLUMNS if c not in DERIVED_COLUMNS)
TEXT_COLUMNS = ("currency", "group_id", "score_status", "score_reason", "tramo")
BOOL_COLUMNS = ("debt_without_inflow_w", "cash_reliable", "optimizable")
NUMERIC_BASE_COLUMNS = tuple(c for c in BASE_COLUMNS if c not in TEXT_COLUMNS and c not in BOOL_COLUMNS)
SIGNAL_ROW_KEYS = ("level_inflow_sum", "window_outflow_sum", "window_debt_service_sum", "ar_delay_w", "ap_delay_w",
                   "op_margin_w", "debt_service_w", "debt_without_inflow_w")
EVIDENCE_FIELDS = ("reconstructed_cash", "runway_months", "inv_ap_overdue_amount", "inv_ap_due_30_amount",
                   "inv_ap_due_60_amount", "inv_ar_open_amount", "window_debt_service_sum", "window_outflow_sum", "level_inflow_sum")
EVIDENCE_SOURCES = {
    "reconstructed_cash": LIQUIDITY_FILE, "runway_months": LIQUIDITY_FILE,
    "inv_ap_overdue_amount": "company_monthly_features.parquet", "inv_ap_due_30_amount": "company_monthly_features.parquet",
    "inv_ap_due_60_amount": "company_monthly_features.parquet", "inv_ar_open_amount": "company_monthly_features.parquet",
    "window_debt_service_sum": "xray.group_advisor.state.window_sums", "window_outflow_sum": "xray.group_advisor.state.window_sums",
    "level_inflow_sum": "xray.score_v2.signals.build_signals",
}
INVARIANT_RTOL = 1e-6


# ---------------------------------------------------------------- sumas de ventana


def _numeric(frame, column):
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return values.where(np.isfinite(values))


def _window_sums_frame(frame, config):
    """Sumas O y S para el calendario completo de una entidad-moneda, con las máscaras de `_flow_aggregates`."""
    ok = month_quality(frame, config)
    inflow, outflow = _numeric(frame, "tx_inflow"), _numeric(frame, "tx_outflow")
    principal, interest = _numeric(frame, "debt_principal_paid"), _numeric(frame, "debt_interest_paid")
    complete = ok & inflow.notna() & outflow.notna()
    debt_complete = complete & principal.notna() & interest.notna()
    w = config.level_window
    months = complete.astype(float).rolling(w, min_periods=1).sum()
    debt_months = debt_complete.astype(float).rolling(w, min_periods=1).sum()
    enough = months.ge(config.level_min_months)
    outflow_sum = outflow.where(complete, 0.).rolling(w, min_periods=1).sum()
    service_sum = (principal + interest).where(debt_complete, 0.).rolling(w, min_periods=1).sum()
    return pd.DataFrame({"window_outflow_sum": outflow_sum.where(enough),
                         "window_debt_service_sum": service_sum.where(enough & debt_months.eq(months))}, index=frame.index)


def window_sums(panel, config_v2):
    """`window_outflow_sum` y `window_debt_service_sum` por fila de un panel preparado, alineadas con `panel.index`.

    Misma iteración que `build_signals`: por entidad-moneda, reindexando al calendario natural
    completo (`pd.date_range(min, max, freq="MS")`) para que la ventana rolling de
    `level_window` meses nunca comprima huecos.
    """
    keys = [config_v2.unit, "currency"]
    pieces = []
    for _, group in panel.groupby(keys, sort=False, observed=True):
        ordered = group.sort_values("month")
        frame = ordered.set_index("month")
        calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="MS", name="month")
        sums = _window_sums_frame(frame.reindex(calendar), config_v2).loc[frame.index]
        sums.index = ordered.index.to_numpy()
        pieces.append(sums)
    if not pieces:
        return pd.DataFrame({c: pd.Series(dtype=float) for c in WINDOW_COLUMNS})
    return pd.concat(pieces).reindex(panel.index)


# ---------------------------------------------------------------- referencia, tramos, invariantes


def reference_state_for(reference, month):
    """Estado de referencia vigente en `month`: mayor `effective_from <= month` (regla de `score_panel`).

    Sin referencia aplicable devuelve `anchor_reference`. Si la referencia elegida contiene el
    mes puntuado o posteriores (`max_observed_month >= month`) lanza `ValueError`.
    """
    month = pd.Timestamp(month)
    entries = reference["references"]
    dates = [pd.Timestamp(item["effective_from"]) for item in entries]
    if dates != sorted(set(dates)):
        raise ValueError("El calendario de referencia no está ordenado o tiene duplicados")
    selected = bisect.bisect_right(dates, month) - 1
    if selected < 0:
        return reference["anchor_reference"]
    entry = entries[selected]
    if entry["max_observed_month"] is not None and pd.Timestamp(entry["max_observed_month"]) >= month:
        raise ValueError(f"La referencia vigente en {month.date()} contiene datos del mes puntuado o del futuro")
    return entry["state"]


def tramo_of(level, bounds):
    """`red` < bounds[0] ≤ `amber` < bounds[1] ≤ `green`; `none` sin nivel."""
    if level is None or not np.isfinite(level):
        return "none"
    return TRAMO_LABELS[int(np.searchsorted(np.asarray(bounds, dtype=float), level, side="right"))]


def tramos(levels, bounds):
    values = pd.to_numeric(levels, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    finite = np.isfinite(values)
    positions = np.searchsorted(np.asarray(bounds, dtype=float), np.where(finite, values, -1.0), side="right")
    labels = np.where(finite, np.array(TRAMO_LABELS, dtype=object)[positions], "none")
    return pd.Series(labels, index=levels.index, dtype="str")


def check_invariants(frame, rtol=INVARIANT_RTOL):
    """Comprueba fila a fila `m = (I−O)/(I+O)` (si `I+O > 0`), `d = S/I` (si `I > 0` y `d` finito) y el indicador."""
    i, o, s = (_numeric(frame, c) for c in ("level_inflow_sum", "window_outflow_sum", "window_debt_service_sum"))
    m, d = _numeric(frame, "op_margin_w"), _numeric(frame, "debt_service_w")
    indicator = frame["debt_without_inflow_w"].eq(True) if "debt_without_inflow_w" in frame else pd.Series(False, index=frame.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        margin_checked = (i + o).gt(0)
        margin_ok = margin_checked & np.isclose(m, (i - o) / (i + o), rtol=rtol, atol=0.)
        debt_checked = i.gt(0) & d.notna()
        debt_ok = debt_checked & np.isclose(d, s / i, rtol=rtol, atol=0.)
    indicator_ok = indicator.eq(i.eq(0) & s.gt(0))
    return pd.DataFrame({"margin_checked": margin_checked, "margin_ok": margin_ok, "debt_checked": debt_checked,
                         "debt_ok": debt_ok, "indicator_ok": indicator_ok}, index=frame.index)


def invariants_summary(frame, rtol=INVARIANT_RTOL):
    checks = check_invariants(frame, rtol)
    failed = checks.index[(checks.margin_checked & ~checks.margin_ok) | (checks.debt_checked & ~checks.debt_ok) | ~checks.indicator_ok]
    return {"rows": int(len(checks)), "margin_checked": int(checks.margin_checked.sum()), "margin_ok": int(checks.margin_ok.sum()),
            "debt_checked": int(checks.debt_checked.sum()), "debt_ok": int(checks.debt_ok.sum()),
            "indicator_ok": int(checks.indicator_ok.sum()), "failed": sorted(str(x) for x in failed), "ok": not len(failed)}


# ---------------------------------------------------------------- estado


@dataclass(frozen=True, eq=False)
class GroupState:
    group_id: str
    month: pd.Timestamp
    subsidiaries: pd.DataFrame
    reference_state: dict
    consolidated_scores: dict
    evidence: dict
    inputs_sha256: dict

    def signal_row(self, company_id):
        """Fila de señales en el formato `SignalRow` de WP2 (cinco base + tres derivadas)."""
        if company_id not in self.subsidiaries.index:
            raise KeyError(f"{company_id} no pertenece al estado de {self.group_id}")
        row = self.subsidiaries.loc[company_id]
        return {key: bool(row[key]) if key == "debt_without_inflow_w" else float(row[key]) for key in SIGNAL_ROW_KEYS}

    @property
    def optimizable_ids(self):
        return list(self.subsidiaries.index[self.subsidiaries.optimizable.to_numpy(dtype=bool)])

    def invariants_report(self, rtol=INVARIANT_RTOL):
        return invariants_summary(self.subsidiaries, rtol)


def build_evidence(subsidiaries, month):
    """Evidencia determinista: ids `ev_0001`… por `company_id` ordenado y `EVIDENCE_FIELDS`, solo valores observados."""
    month_text = str(pd.Timestamp(month).date())
    values = subsidiaries.loc[:, list(EVIDENCE_FIELDS)].astype(float)
    evidence = {}
    for company_id, row in zip(values.index, values.to_numpy()):
        for field, value in zip(EVIDENCE_FIELDS, row):
            if np.isfinite(value):
                evidence[f"ev_{len(evidence) + 1:04d}"] = {"source": EVIDENCE_SOURCES[field], "company_id": str(company_id),
                                                           "field": field, "month": month_text, "value": float(value)}
    return evidence


def assemble_group_state(group_id, month, subsidiaries, reference_state, consolidated_scores, inputs_sha256, config):
    """Ensambla un `GroupState` desde las columnas base: deriva cuota mensual, `optimizable` y `tramo`, fija dtypes y orden.

    `reconstructed_cash` se anula cuando `cash_reliable` es falso. Comprueba los invariantes de
    la spec §3 y registra un aviso (sin excepción) si alguna fila no los cumple.
    """
    frame = subsidiaries.copy()
    if "company_id" in frame.columns:
        frame = frame.set_index("company_id")
    frame.index = frame.index.astype(str)
    frame.index.name = "company_id"
    if not frame.index.is_unique:
        raise ValueError(f"El estado de {group_id} tiene company_id repetidos")
    missing = set(BASE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Faltan columnas del estado: {sorted(missing)}")
    frame = frame.sort_index()
    for column in NUMERIC_BASE_COLUMNS:
        frame[column] = _numeric(frame, column)
    frame["cash_reliable"] = frame.cash_reliable.eq(True)
    frame["reconstructed_cash"] = frame.reconstructed_cash.where(frame.cash_reliable)
    frame["debt_without_inflow_w"] = frame.debt_without_inflow_w.eq(True)
    frame["monthly_debt_service"] = frame.window_debt_service_sum / config.horizon_months
    frame["optimizable"] = frame.level.notna()
    frame["tramo"] = tramos(frame.level, config.tramo_bounds)
    for column in TEXT_COLUMNS:
        frame[column] = frame[column].astype("str")
    frame = frame.loc[:, list(SUBSIDIARY_COLUMNS)]
    month = pd.Timestamp(month)
    state = GroupState(group_id=str(group_id), month=month, subsidiaries=frame, reference_state=reference_state,
                       consolidated_scores=dict(consolidated_scores), evidence=build_evidence(frame, month),
                       inputs_sha256=dict(inputs_sha256))
    report = state.invariants_report()
    if not report["ok"]:
        log.warning("Invariantes del estado incumplidos en %s (%s): %s; se usan las sumas directas",
                    group_id, month.date(), report["failed"])
    return state


# ---------------------------------------------------------------- entradas


@dataclass(frozen=True, eq=False)
class AdvisorInputs:
    panel: pd.DataFrame
    scores: pd.DataFrame
    group_scores: pd.DataFrame
    liquidity: pd.DataFrame
    reference: dict
    config_v2: ScoreV2Config
    signals: pd.DataFrame
    window_sums: pd.DataFrame
    rows: pd.DataFrame
    inputs_sha256: dict

    @property
    def last_month(self):
        return self.panel.month.max()

    def group_ids(self, month):
        month = pd.Timestamp(month)
        return sorted(self.rows.loc[self.rows.month.eq(month), "group_id"].unique().tolist())


def _state_rows(panel, signals, sums, scores, liquidity):
    """Tabla por fila del panel con las columnas base del estado, alineada con `panel.index`."""
    score_columns = list(SCORE_COLUMNS)
    merged_scores = panel[KEYS].merge(scores[KEYS + score_columns], on=KEYS, how="left", validate="one_to_one")
    if merged_scores.score_status.isna().any():
        raise ValueError("scores_v2 no cubre todas las filas del panel de features")
    liquidity_columns = ["reconstructed_cash", "reconstruction_coverage", "cash_runway_months_retrospective"]
    merged_liquidity = panel[KEYS].merge(liquidity[KEYS + liquidity_columns], on=KEYS, how="left", validate="one_to_one")
    rows = panel[["company_id", "month", "currency", "group_id"]].copy()
    for column in score_columns:
        rows[column] = merged_scores[column].to_numpy()
    for column in SIGNAL_COLUMNS:
        rows[column] = signals[column].to_numpy()
    for column in WINDOW_COLUMNS:
        rows[column] = sums[column].to_numpy()
    coverage = pd.to_numeric(merged_liquidity.reconstruction_coverage, errors="coerce").to_numpy(dtype=float)
    reliable = np.nan_to_num(coverage, nan=-1.0) == 1.0
    rows["cash_reliable"] = reliable
    rows["reconstructed_cash"] = np.where(reliable, merged_liquidity.reconstructed_cash.to_numpy(dtype=float), np.nan)
    rows["runway_months"] = merged_liquidity.cash_runway_months_retrospective.to_numpy(dtype=float)
    for column in FEATURE_COLUMNS:
        rows[column] = _numeric(panel, column).to_numpy()
    return rows


def load_inputs(features_dir=PROCESSED_DIR, config=None):
    """Lee y verifica las entradas, calcula señales y sumas de ventana una sola vez y las cachea.

    Verifica el hash de `company_monthly_features.parquet` contra `_feature_manifest.json`
    (vía `xray.score.pipeline.read_panel`) y que `scores_v2` se calculó sobre esas mismas
    features (`_company_score_manifest.json`); valida `config.horizon_months` contra
    `level_window` de la referencia congelada.
    """
    config = config or AdvisorConfig()
    features_dir = Path(features_dir)
    reference_path = features_dir / REFERENCE_FILE
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference.get("method") != METHOD or reference.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("La referencia de scores_v2 no es compatible con financial_smoothed_v2")
    config_v2 = ScoreV2Config(**reference["config"])
    if config_v2.panel != "company":
        raise ValueError("El advisor trabaja sobre el panel de empresa en moneda declarada")
    if config.horizon_months != config_v2.level_window:
        raise ValueError(f"horizon_months={config.horizon_months} debe coincidir con level_window={config_v2.level_window} de la referencia V2")
    raw, source = read_panel(features_dir, config_v2)
    hashes = {source["feature_file"]: source["feature_sha256"], "_feature_manifest.json": source["feature_manifest_sha256"],
              REFERENCE_FILE: sha256(reference_path)}
    manifest_path = features_dir / SCORES_MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("input", {}).get("feature_sha256") != source["feature_sha256"]:
        raise ValueError("scores_v2 se calcularon con otra versión de las features; regenerar antes de construir el estado")
    hashes[SCORES_MANIFEST_FILE] = sha256(manifest_path)
    frames = {}
    for name in (SCORES_FILE, GROUP_SCORES_FILE, LIQUIDITY_FILE):
        path = features_dir / name
        hashes[name] = sha256(path)
        frames[name] = pd.read_parquet(path)
    panel = prepare_panel(raw, config_v2)
    signals = build_signals(panel, config_v2)
    sums = window_sums(panel, config_v2)
    rows = _state_rows(panel, signals, sums, frames[SCORES_FILE], frames[LIQUIDITY_FILE])
    return AdvisorInputs(panel=panel, scores=frames[SCORES_FILE], group_scores=frames[GROUP_SCORES_FILE],
                         liquidity=frames[LIQUIDITY_FILE], reference=reference, config_v2=config_v2, signals=signals,
                         window_sums=sums, rows=rows, inputs_sha256=hashes)


def _resolve_month(inputs, month, config):
    chosen = month if month is not None else config.month
    stamp = pd.Timestamp(chosen) if chosen is not None else inputs.last_month
    if stamp != stamp.to_period("M").to_timestamp():
        raise ValueError("month debe ser el primer día de un mes")
    return stamp


def _consolidated_scores(group_scores, group_id, month):
    selected = group_scores.loc[group_scores.group_id.eq(group_id) & group_scores.month.eq(month)].sort_values("currency")
    return {str(currency): (None if pd.isna(score) else float(score)) for currency, score in zip(selected.currency, selected.score)}


def build_group_state(inputs, group_id, month=None, config=None):
    """`GroupState` de `group_id` en `month` (por defecto `config.month` o el último cierre del panel)."""
    config = config or AdvisorConfig()
    if config.horizon_months != inputs.config_v2.level_window:
        raise ValueError("horizon_months debe coincidir con level_window de la referencia V2")
    month = _resolve_month(inputs, month, config)
    selected = inputs.rows.loc[inputs.rows.group_id.eq(group_id) & inputs.rows.month.eq(month)]
    if selected.empty:
        raise ValueError(f"{group_id} no tiene filas en el panel para {month.date()}")
    reference_state = reference_state_for(inputs.reference, month)
    consolidated = _consolidated_scores(inputs.group_scores, group_id, month)
    subsidiaries = selected.drop(columns=["month"]).set_index("company_id")
    return assemble_group_state(group_id, month, subsidiaries, reference_state, consolidated, inputs.inputs_sha256, config)


def iter_group_states(inputs, month=None, config=None):
    """Genera el `GroupState` de cada grupo con filas en `month`, ordenado por `group_id`."""
    config = config or AdvisorConfig()
    month = _resolve_month(inputs, month, config)
    for group_id in inputs.group_ids(month):
        yield build_group_state(inputs, group_id, month, config)
