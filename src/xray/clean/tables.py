"""Limpieza de las tablas pequeñas: solo columnas vacías, constantes o redundantes (S*)."""
import pandas as pd

from xray.clean.log import CleaningLog

# tabla -> [(regla, columnas, motivo)]
DROP_COLUMNS = {
    "companies": [("S01", ["country"], "82% nulo y sin normalizar (ES / ESPAÑA / Espanya)")],
    "banking_products": [("S02", ["label", "service"], "label = tipo + número; service = código del conector")],
    "debt_products": [("S02", ["label", "service"], "label = tipo + número; service = código del conector")],
    "balances": [("S03", ["available"], "100% nulo")],
    "debt_schedule_config": [("S04", ["amortization_type"], "constante ('constant quote')")],
}


def clean_table(name: str, df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    out = df.copy()
    for rule, columns, reason in DROP_COLUMNS.get(name, []):
        out = out.drop(columns=columns)
        log.add(name, rule, "drop_column", 0, f"{', '.join(columns)}: {reason}")
    return out
