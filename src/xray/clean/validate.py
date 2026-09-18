"""Comprobaciones de integridad sobre la capa cleaned. Fallan en voz alta si algo no cuadra."""
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

    if errors:
        raise ValidationError("La capa cleaned no pasa la validación:\n- " + "\n- ".join(errors))
