import pandas as pd

from xray.features.temporal import divide
from xray.fx import REPORTING_CURRENCY, to_eur


INVOICE_AMOUNTS = ["inv_issued_amount", "inv_received_amount"]
for _direction in ("ar", "ap"):
    INVOICE_AMOUNTS += [f"inv_{_direction}_{metric}_amount" for metric in ("open", "overdue", "overdue_90", "due_30", "due_60", "due_90")]


def prepare_invoices(tables, config):
    f = tables["invoices"].copy()
    f = f.loc[f.issuance_date.lt(config.stop)].rename(columns={"currency": "source_currency"})
    # D32: importes en EUR con tipo fijo según la moneda de la factura.
    f["amount"] = to_eur(f.amount.astype(float), f.source_currency)
    f["currency"] = REPORTING_CURRENCY
    f["currency"] = f.currency.where(f.source_currency.notna())
    f["group_id"] = f.company_id.map(tables["companies"].set_index("company_id").group_id)
    f["absolute"] = f.amount.abs()
    f["valid_document"] = f.document_type.eq("invoice") & ~f.is_possible_duplicate
    f["valid_due"] = ~f.has_anomalous_term & f.due_date.notna()
    f["valid_payment"] = (f.payment_date.notna() & ~f.is_payment_before_issuance & ~f.is_future_payment)
    f["unknown_settlement"] = f.status.eq("paid") & f.payment_date.isna()
    f["counterparty"] = f.company_id.astype("string") + ":" + f.counterparty_id.astype("string")
    return f


def invoice_features(f, skeleton, unit):
    keys = [unit, "currency"]
    valid = f.loc[f.valid_document]
    results = []
    for month in sorted(skeleton.month.unique()):
        end = month + pd.offsets.MonthBegin(1)
        p = skeleton.loc[skeleton.month == month].set_index(keys).copy()
        known = f.loc[f.issuance_date.lt(end)]
        history = valid.loc[valid.issuance_date.lt(end)]
        issued = history.loc[history.issuance_date.ge(month)]
        paid = history.loc[history.valid_payment & history.payment_date.ge(month) & history.payment_date.lt(end)]
        opened = history.loc[~history.unknown_settlement & (history.payment_date.isna() | history.payment_date.ge(end))]
        p["inv_source_seen"] = known.groupby(keys).size().reindex(p.index).fillna(0).gt(0)
        p["inv_standard_history_seen"] = history.groupby(keys).size().reindex(p.index).fillna(0).gt(0)
        p["inv_unknown_settlement_count"] = history.loc[history.unknown_settlement].groupby(keys).size().reindex(p.index).fillna(0)
        p["inv_document_coverage"] = divide(history.groupby(keys).size().reindex(p.index).fillna(0),
                                             known.groupby(keys).size().reindex(p.index))
        for direction, label, days_name in (("AR", "ar", "inv_dso_median"), ("AP", "ap", "inv_dpo_median")):
            issued_side = issued.loc[issued.direction == direction]
            open_side = opened.loc[opened.direction == direction]
            due_known = open_side.loc[open_side.valid_due]
            overdue = due_known.loc[due_known.due_date.lt(end - pd.Timedelta(days=1))]
            old = overdue.loc[overdue.due_date.lt(end - pd.Timedelta(days=91))]
            issued_name = "issued" if direction == "AR" else "received"
            p[f"inv_{issued_name}_amount"] = issued_side.groupby(keys).absolute.sum().reindex(p.index).fillna(0)
            p[f"inv_{issued_name}_count"] = issued_side.groupby(keys).size().reindex(p.index).fillna(0)
            p[f"inv_{label}_open_amount"] = open_side.groupby(keys).absolute.sum().reindex(p.index).fillna(0)
            p[f"inv_{label}_open_count"] = open_side.groupby(keys).size().reindex(p.index).fillna(0)
            denominator = due_known.groupby(keys).absolute.sum().reindex(p.index).fillna(0)
            for name, subset in (("overdue", overdue), ("overdue_90", old)):
                numerator = subset.groupby(keys).absolute.sum().reindex(p.index).fillna(0)
                p[f"inv_{label}_{name}_amount"] = numerator
                p[f"inv_{label}_{name}_ratio"] = divide(numerator, denominator)
            p[f"inv_{label}_open_due_coverage"] = divide(denominator, p[f"inv_{label}_open_amount"])
            for horizon in (30, 60, 90):
                due = due_known.loc[due_known.due_date.ge(end) & due_known.due_date.lt(end + pd.Timedelta(days=horizon))]
                p[f"inv_{label}_due_{horizon}_amount"] = due.groupby(keys).absolute.sum().reindex(p.index).fillna(0)
            paid_side = paid.loc[paid.direction == direction].copy()
            paid_side["days"] = (paid_side.payment_date - paid_side.issuance_date).dt.days.clip(0, 365)
            p[days_name] = paid_side.groupby(keys).days.median().reindex(p.index)
            p[f"inv_{label}_paid_count"] = paid_side.groupby(keys).size().reindex(p.index).fillna(0)
            delays = paid_side.loc[paid_side.valid_due].copy()
            p[f"inv_{label}_delay_count"] = delays.groupby(keys).size().reindex(p.index).fillna(0)
            delays["delay"] = (delays.payment_date - delays.due_date).dt.days.clip(-60, 365)
            delays["late"] = delays.delay.gt(0)
            p[f"inv_{label}_delay_median"] = delays.groupby(keys).delay.median().reindex(p.index)
            p[f"inv_{label}_delay_p90"] = delays.groupby(keys).delay.quantile(0.9).reindex(p.index)
            p[f"inv_{label}_late_paid_ratio"] = delays.groupby(keys).late.mean().reindex(p.index)
            cp = issued_side.loc[issued_side.counterparty.notna()].groupby(keys + ["counterparty"]).absolute.sum()
            shares = cp / cp.groupby(level=[0, 1]).transform("sum")
            p[f"inv_{label}_counterparty_hhi"] = shares.pow(2).groupby(level=[0, 1]).sum().reindex(p.index)
        numeric = [col for col in p if col not in ("month", "inv_source_seen", "inv_standard_history_seen", "inv_document_coverage")]
        p[numeric] = p[numeric].where(p.inv_standard_history_seen, axis=0)
        results.append(p.reset_index())
    return pd.concat(results, ignore_index=True)
