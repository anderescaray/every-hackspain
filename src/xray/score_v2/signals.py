"""Señales suavizadas de `financial_smoothed_v2`.

Todas las funciones trabajan sobre el calendario mensual completo de una entidad-moneda
(una fila por mes natural, con NaN en los meses sin datos). Las ventanas son de meses
naturales: nunca se comprimen huecos. Ninguna señal mira meses posteriores a t.

Nivel (ventana `level_window`, por defecto 6 meses, t-5..t):
    op_margin_w      (ΣI − ΣO) / (ΣI + ΣO)          sumas de flujos operativos de los meses con calidad
    debt_service_w   (ΣP + ΣR) / ΣI                  servicio de deuda observado sobre entradas de la ventana
    ar_delay_w       Σ(mediana_m · n_m) / Σ n_m      retraso AR ponderado por número de pagos con vencimiento válido
    ap_delay_w       ídem AP

Momentum (trimestre reciente t-2..t frente a trimestre anterior t-5..t-3):
    *_qoq            diferencia de los mismos agregados entre trimestres
    inflow_growth_q  Σ_{k=0..2} clip(log(1 + g_{t-k}))   crecimiento compuesto en cuentas comunes
    *_qoq_z          cambio dividido por la variabilidad mensual propia de la empresa (σ, ventana
                     `volatility_window`, con suelo) ajustada al tamaño de la ventana: σ·√(2/q) para
                     medias trimestrales y σ·√q para la suma de crecimientos. Es una razón señal/ruido
                     por empresa: una empresa volátil necesita un cambio mayor para marcar dirección.

Diagnóstico del mes actual (bache frente a tendencia):
    *_deviation      valor mensual − valor de la ventana de nivel
    *_deviation_z    desviación / σ propia
    is_atypical_month  |op_margin_deviation_z| ≥ `atypical_z`
"""
import numpy as np
import pandas as pd


LEVEL_SIGNALS = ("op_margin_w", "debt_service_w", "ar_delay_w", "ap_delay_w")
MOMENTUM_SIGNALS = ("op_margin_qoq", "debt_service_qoq", "ar_delay_qoq", "ap_delay_qoq", "inflow_growth_q")
QUALITY_FIELDS = ["tx_count", "tx_usable_count", "tx_usable_row_share", "tx_operating_amount_share", "tx_company_coverage"]
FLOW_FIELDS = ["tx_inflow", "tx_outflow", "debt_principal_paid", "debt_interest_paid"]
CORE_FEATURES = FLOW_FIELDS + ["tx_operating_margin", "tx_lfl_inflow_growth", "has_sufficient_history"]
OPTIONAL_FEATURES = [f"inv_{side}_{metric}" for side in ("ar", "ap") for metric in ("delay_median", "delay_count")]


def _numeric(frame, column):
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return values.where(np.isfinite(values))


def month_quality(frame, config):
    """Mes con calidad bancaria suficiente para entrar en los agregados (mismos umbrales que V1)."""
    usable = _numeric(frame, "tx_usable_count").fillna(0)
    return (usable.ge(config.min_transactions)
            & _numeric(frame, "tx_usable_row_share").fillna(0).ge(config.min_usable_share)
            & _numeric(frame, "tx_operating_amount_share").fillna(0).ge(config.min_operating_share)
            & _numeric(frame, "tx_company_coverage").eq(1))


def _window_sum(values, mask, window):
    return values.where(mask, 0.).rolling(window, min_periods=1).sum()


def _window_count(mask, window):
    return mask.astype(float).rolling(window, min_periods=1).sum()


def _ratio(numerator, denominator):
    return (numerator / denominator.where(denominator > 0)).replace([np.inf, -np.inf], np.nan)


def _sigma(values, config, floor):
    """Desviación típica muestral de la serie mensual en la ventana de volatilidad, con suelo.

    La ventana termina en t − momentum_window: la volatilidad se mide **antes** del trimestre
    reciente. Si incluyera el propio cambio, una ruptura grande inflaría σ y se anularía a sí
    misma; con la referencia previa, cuanto mayor es la ruptura mayor es su z.
    """
    history = values.shift(config.momentum_window)
    sigma = history.rolling(config.volatility_window, min_periods=config.volatility_min_months).std(ddof=1)
    return sigma.clip(lower=floor).where(sigma.notna())


def _flow_aggregates(frame, ok, window, min_months):
    inflow, outflow = _numeric(frame, "tx_inflow"), _numeric(frame, "tx_outflow")
    principal, interest = _numeric(frame, "debt_principal_paid"), _numeric(frame, "debt_interest_paid")
    complete = ok & inflow.notna() & outflow.notna()
    debt_complete = complete & principal.notna() & interest.notna()
    months = _window_count(complete, window)
    debt_months = _window_count(debt_complete, window)
    enough = months.ge(min_months)
    i, o = _window_sum(inflow, complete, window), _window_sum(outflow, complete, window)
    service = _window_sum(principal + interest, debt_complete, window)
    debt_inflow = _window_sum(inflow, debt_complete, window)
    return pd.DataFrame({
        "margin": _ratio(i - o, i + o).where(enough),
        "debt_service": _ratio(service, debt_inflow).where(enough & debt_months.eq(months)),
        "debt_without_inflow": (enough & debt_months.eq(months) & debt_inflow.eq(0) & service.gt(0)),
        "inflow": i.where(enough), "months": months,
    }, index=frame.index)


def _delay_aggregates(frame, side, window, min_count):
    median = _numeric(frame, f"inv_{side}_delay_median")
    count = _numeric(frame, f"inv_{side}_delay_count").fillna(0)
    valid = median.notna() & count.ge(1)
    total = _window_sum(count, valid, window)
    weighted = _window_sum(median * count, valid, window)
    return _ratio(weighted, total).where(total.ge(min_count)), total


def _log_growth(frame, ok, clip):
    growth = _numeric(frame, "tx_lfl_inflow_growth").where(ok & ok.shift(1, fill_value=False))
    with np.errstate(divide="ignore", invalid="ignore"):
        logged = np.log1p(growth.where(growth.ge(-1)))
    return logged.clip(-clip, clip)


def smoothed_signals(frame, config):
    """Señales de nivel, momentum y diagnóstico para un calendario completo de una entidad-moneda."""
    ok = month_quality(frame, config)
    w, q = config.level_window, config.momentum_window
    level = _flow_aggregates(frame, ok, w, config.level_min_months)
    recent = _flow_aggregates(frame, ok, q, config.momentum_min_months)
    prior = recent.shift(q)
    ar_w, ar_n = _delay_aggregates(frame, "ar", w, config.min_delay_count)
    ap_w, ap_n = _delay_aggregates(frame, "ap", w, config.min_delay_count)
    ar_q, _ = _delay_aggregates(frame, "ar", q, config.min_delay_count)
    ap_q, _ = _delay_aggregates(frame, "ap", q, config.min_delay_count)
    log_growth = _log_growth(frame, ok, config.growth_log_clip)
    margin_m1 = _numeric(frame, "tx_operating_margin").where(ok)
    debt_m1 = _ratio(_numeric(frame, "debt_principal_paid") + _numeric(frame, "debt_interest_paid"),
                     _numeric(frame, "tx_inflow")).where(ok)
    ar_m1 = _numeric(frame, "inv_ar_delay_median").where(_numeric(frame, "inv_ar_delay_count").ge(config.min_delay_count))
    ap_m1 = _numeric(frame, "inv_ap_delay_median").where(_numeric(frame, "inv_ap_delay_count").ge(config.min_delay_count))
    sigma = {
        "op_margin": _sigma(margin_m1, config, config.sigma_floor_margin),
        "debt_service": _sigma(debt_m1, config, config.sigma_floor_debt),
        "ar_delay": _sigma(ar_m1, config, config.sigma_floor_delay),
        "ap_delay": _sigma(ap_m1, config, config.sigma_floor_delay),
        "inflow_growth": _sigma(log_growth, config, config.sigma_floor_growth),
    }
    quarter_scale, growth_scale = np.sqrt(2.0 / q), np.sqrt(q)
    signals = pd.DataFrame({
        "month_quality_ok": ok,
        "level_months": level.months,
        "level_inflow_sum": level.inflow,
        "op_margin_w": level.margin,
        "debt_service_w": level.debt_service,
        "debt_without_inflow_w": level.debt_without_inflow,
        "ar_delay_w": ar_w, "ar_delay_count_w": ar_n,
        "ap_delay_w": ap_w, "ap_delay_count_w": ap_n,
        "op_margin_q_recent": recent.margin, "op_margin_q_prior": prior.margin,
        "op_margin_qoq": recent.margin - prior.margin,
        "debt_service_q_recent": recent.debt_service, "debt_service_q_prior": prior.debt_service,
        "debt_service_qoq": recent.debt_service - prior.debt_service,
        "ar_delay_qoq": ar_q - ar_q.shift(q),
        "ap_delay_qoq": ap_q - ap_q.shift(q),
        "inflow_growth_q": log_growth.rolling(q, min_periods=q).sum(),
        "op_margin_m1": margin_m1,
        "op_margin_deviation": margin_m1 - level.margin,
        "debt_service_deviation": debt_m1 - level.debt_service,
        "ar_delay_deviation": ar_m1 - ar_w,
        "ap_delay_deviation": ap_m1 - ap_w,
        "inflow_growth_m1": log_growth,
    }, index=frame.index)
    for name, base in sigma.items():
        signals[f"{name}_sigma"] = base
        change = signals["inflow_growth_q"] if name == "inflow_growth" else signals[f"{name}_qoq"]
        deviation = signals["inflow_growth_m1"] if name == "inflow_growth" else signals[f"{name}_deviation"]
        scale = growth_scale if name == "inflow_growth" else quarter_scale
        signals[f"{name}_change_z"] = change / (base * scale)
        signals[f"{name}_deviation_z"] = deviation / base
    signals["is_atypical_month"] = signals.op_margin_deviation_z.abs().ge(config.atypical_z).fillna(False)
    signals["atypical_months_in_window"] = signals.is_atypical_month.astype(float).rolling(w, min_periods=1).sum().astype(int)
    return signals.replace([np.inf, -np.inf], np.nan)


def build_signals(panel, config):
    """Calcula las señales por entidad-moneda sobre calendarios completos y las devuelve alineadas con `panel.index`."""
    keys = [config.unit, "currency"]
    pieces = []
    for _, group in panel.groupby(keys, sort=False, observed=True):
        ordered = group.sort_values("month")
        frame = ordered.set_index("month")
        calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="MS", name="month")
        signals = smoothed_signals(frame.reindex(calendar), config)
        selected = signals.loc[frame.index]
        selected.index = ordered.index.to_numpy()
        pieces.append(selected)
    if not pieces:
        return smoothed_signals(panel.iloc[:0].set_index("month"), config).iloc[:0]
    return pd.concat(pieces).reindex(panel.index)
