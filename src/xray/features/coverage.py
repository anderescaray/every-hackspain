"""FE10 · Estado de cobertura por entidad-moneda-mes.

La exploración (docs/hallazgos-datos.md §1) muestra que las trayectorias más extremas del panel son
artefactos de cobertura: cuentas que solo registran comisiones antes de conectarse de verdad,
altas de cuentas nuevas y cierres o desconexiones. `coverage_state` etiqueta cada mes para que
las dinámicas (deltas, pendientes, momentum) se calculen solo sobre meses comparables.

Estados, por prioridad:
    no_data         sin movimientos observados en el mes
    pre_activity    solo cuentas dormidas (≤ N movimientos y < X importe) y aún no ha habido actividad real
    dormant         solo cuentas dormidas después de haber tenido actividad real
    onboarding      primeros meses tras la primera actividad real
    account_change  entran o salen cuentas activas que pesan >= X del volumen del mes en que estaban activas
    ok              comparable con el mes anterior

Todo se calcula con datos ≤ mes: `dormant` cubre tanto una pausa como una desconexión definitiva,
porque distinguirlas exigiría mirar el futuro.
"""
import numpy as np
import pandas as pd

STATES = ("no_data", "pre_activity", "dormant", "onboarding", "account_change", "ok")


def account_activity(t, unit, config):
    """Una fila por entidad-moneda-mes-cuenta con movimientos utilizables y su marca de cuenta dormida."""
    keys = [unit, "currency", "month", "product_id"]
    usable = t.loc[t.usable, keys + ["amount"]]
    a = usable.assign(absolute=usable.amount.abs()).groupby(keys).agg(rows=("amount", "size"), absolute=("absolute", "sum"))
    a["dormant"] = a.rows.le(config.dormant_max_transactions) & a.absolute.lt(config.dormant_max_amount)
    return a.reset_index()


def add_coverage_state(panel, t, unit, config):
    p = panel.sort_values([unit, "currency", "month"]).reset_index(drop=True)
    keys = [unit, "currency", "month"]
    accounts = account_activity(t, unit, config)
    active = accounts.loc[~accounts.dormant, keys + ["product_id"]]
    counts = accounts.groupby(keys).dormant.agg(tx_dormant_accounts="sum", total="size")
    counts["tx_active_accounts_real"] = counts.total - counts.tx_dormant_accounts
    p = p.merge(counts.drop(columns="total").reset_index(), on=keys, how="left")
    p[["tx_dormant_accounts", "tx_active_accounts_real"]] = p[["tx_dormant_accounts", "tx_active_accounts_real"]].fillna(0).astype(int)

    # Cuentas que entran (activas hoy, no el mes pasado) y salen (activas el mes pasado, no hoy), con su peso
    # en el volumen del mes en que estaban activas: un cambio solo es material si pesa >= account_change_min_share.
    volume = accounts.groupby(keys).absolute.sum().rename("volume")
    active = active.merge(accounts[keys + ["product_id", "absolute"]], on=keys + ["product_id"])
    previous = active.assign(month=active.month + pd.offsets.MonthBegin(1))
    both = active.merge(previous, on=keys + ["product_id"], how="outer", indicator=True, suffixes=("", "_prev"))
    both["_merge"] = both["_merge"].astype(str)
    both["tx_new_active_accounts"] = both["_merge"].eq("left_only").astype(int)
    both["tx_dropped_active_accounts"] = both["_merge"].eq("right_only").astype(int)
    both["new_volume"] = both.absolute.where(both["_merge"].eq("left_only"), 0.)
    both["dropped_volume"] = both.absolute_prev.where(both["_merge"].eq("right_only"), 0.)
    change = both.groupby(keys)[["tx_new_active_accounts", "tx_dropped_active_accounts", "new_volume", "dropped_volume"]].sum()
    change = change.join(volume)
    previous_volume = volume.reset_index().assign(month=lambda d: d.month + pd.offsets.MonthBegin(1)).set_index(keys).volume
    change = change.join(previous_volume.rename("previous_volume"))
    change["tx_account_change_share"] = np.fmax(change.new_volume / change.volume.where(change.volume > 0),
                                                change.dropped_volume / change.previous_volume.where(change.previous_volume > 0))
    p = p.merge(change[["tx_new_active_accounts", "tx_dropped_active_accounts", "tx_account_change_share"]].reset_index(),
                on=keys, how="left")
    p[["tx_new_active_accounts", "tx_dropped_active_accounts"]] = p[["tx_new_active_accounts", "tx_dropped_active_accounts"]].fillna(0).astype(int)
    material = p.tx_account_change_share.ge(config.account_change_min_share)

    group_keys = [p[unit], p.currency]
    month_number = p.month.dt.year * 12 + p.month.dt.month
    real = p.tx_active_accounts_real.gt(0)
    # Primera actividad real conocida *a fecha del mes*: antes de observarla es NaN (sin mirar el futuro).
    first_real = month_number.where(real).groupby(group_keys).cummin().groupby(group_keys).ffill()
    since_first = (month_number - first_real).astype(float)
    p["months_since_first_activity"] = since_first
    previous_real = real.groupby(group_keys).shift(1).astype("boolean").fillna(False)

    state = pd.Series("ok", index=p.index, dtype="string")
    state = state.mask(material & (p.tx_new_active_accounts.gt(0) | (p.tx_dropped_active_accounts.gt(0) & previous_real)), "account_change")
    state = state.mask(since_first.lt(config.onboarding_months), "onboarding")
    state = state.mask(~real & since_first.gt(0), "dormant")
    state = state.mask(~real & first_real.isna(), "pre_activity")
    state = state.mask(p.tx_count.eq(0), "no_data")
    p["coverage_state"] = state
    p["is_coverage_comparable"] = state.eq("ok").fillna(False).astype(bool)
    return p
