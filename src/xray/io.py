"""Lectura de las capas raw y cleaned."""
import io
from pathlib import Path

import pandas as pd

from xray.paths import CLEANED_DIR, RAW_DIR

TABLES = (
    "groups",
    "companies",
    "banking_products",
    "debt_products",
    "debt_schedule_config",
    "balances",
    "invoices",
    "transactions",
)

DATE_COLUMNS = {
    "companies": ["created_at"],
    "banking_products": ["created_at"],
    "debt_products": ["created_at"],
    "debt_schedule_config": ["next_payment_date", "last_payment_date"],
    "balances": ["date"],
    "invoices": ["issuance_date", "due_date", "payment_date"],
    "transactions": ["date", "value_date"],
}


def read_raw(table: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Lee un CSV original con las fechas parseadas.

    `transactions.csv` contiene bytes NUL y saltos de línea dentro de campos entrecomillados:
    el parser de pyarrow falla, así que se quitan los NUL y se usa el parser C de pandas.
    """
    if table not in TABLES:
        raise ValueError(f"Tabla desconocida: {table}. Opciones: {TABLES}")
    path = Path(raw_dir) / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Coloca los CSV originales en {raw_dir}")
    source = io.BytesIO(path.read_bytes().replace(b"\x00", b"")) if table == "transactions" else path
    return pd.read_csv(source, parse_dates=DATE_COLUMNS.get(table, []), low_memory=False)


def read_cleaned(table: str, cleaned_dir: Path = CLEANED_DIR) -> pd.DataFrame:
    """Lee una tabla de la capa cleaned (ejecuta antes `python scripts/00_clean_data.py`)."""
    path = Path(cleaned_dir) / f"{table}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Ejecuta antes: python scripts/00_clean_data.py")
    return pd.read_parquet(path)
