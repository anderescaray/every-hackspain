"""Comprobaciones de integridad sobre la capa cleaned. Fallan en voz alta si algo no cuadra."""
import numpy as np
import pandas as pd

PRIMARY_KEYS = {
    "groups": "group_id",
    "companies": "company_id",
    "banking_products": "product_id",
    "debt_products": "product_id",
    "debt_schedule_config": "product_id",
    "balances": "product_id",
    "invoices": "operation_id",
    "transactions": "transaction_id",
}


class ValidationError(Exception):
    pass


def validate(tables: dict[str, pd.DataFrame]) -> None:
    errors = []
    for name, key in PRIMARY_KEYS.items():
        df = tables[name]
        if df[key].isna().any():
            errors.append(f"{name}.{key} tiene nulos")
        if df[key].duplicated().any():
            errors.append(f"{name}.{key} no es único ({df[key].duplicated().sum()} repetidos)")

    companies = set(tables["companies"].company_id)
    for name, df in tables.items():
        if "company_id" in df and name != "companies":
            orphans = ~df.company_id.isin(companies)
            if orphans.any():
                errors.append(f"{name}: {orphans.sum()} filas con company_id que no está en companies")
    if not set(tables["companies"].group_id) <= set(tables["groups"].group_id):
        errors.append("companies tiene group_id que no están en groups")

    products = pd.concat([tables["banking_products"], tables["debt_products"]], ignore_index=True)
    if products.product_id.duplicated().any():
        errors.append("product_id repetido entre banking_products y debt_products")
    else:
        owners = products.set_index("product_id").company_id
        for name in ("transactions", "balances", "debt_schedule_config"):
            df = tables[name]
            owner = df.product_id.map(owners)
            mismatch = owner.notna() & owner.ne(df.company_id)
            if mismatch.any():
                errors.append(f"{name}: {mismatch.sum()} productos pertenecen a otra empresa")
            if name == "debt_schedule_config" and owner.isna().any():
                errors.append(f"{name}: product_id desconocido")

    for name, dates in {"transactions": ["date"], "invoices": ["issuance_date"], "balances": ["date"]}.items():
        df = tables[name]
        for col in dates:
            if col in df and (not pd.api.types.is_datetime64_any_dtype(df[col]) or df[col].isna().any()):
                errors.append(f"{name}.{col}: fecha obligatoria inválida")
        for col in ("amount", "balance"):
            if col in df and not np.isfinite(df[col].to_numpy(dtype=float)).all():
                errors.append(f"{name}.{col}: importes no finitos")

    if errors:
        raise ValidationError("La capa cleaned no pasa la validación:\n- " + "\n- ".join(errors))
