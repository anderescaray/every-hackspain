"""Rutas y constantes del proyecto.

Estructura de datos (todo bajo `data/`, en .gitignore):
    data/raw/        CSV originales tal cual llegan. Nunca se modifican.
    data/cleaned/    Salida de `xray.clean`: parquet por tabla + log + manifiesto.
    data/processed/  Features, scores y artefactos para el producto.

`XRAY_DATA_DIR` permite apuntar a otra carpeta de datos (p. ej. un disco externo).
"""
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("XRAY_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"
PROCESSED_DIR = DATA_DIR / "processed"

# Fecha de la foto final (balances, status de facturas).
EXTRACTION_DATE = pd.Timestamp("2026-09-01")
