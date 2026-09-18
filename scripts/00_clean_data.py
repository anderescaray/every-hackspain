"""Paso 0 del pipeline: data/raw/*.csv -> data/cleaned/*.parquet.

    python scripts/00_clean_data.py

La lógica vive en src/xray/clean/. Este script solo la ejecuta sin necesidad de instalar el paquete.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.clean.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
