"""Capa cleaned: data/raw/*.csv -> data/cleaned/*.parquet.

Uso:
    python scripts/00_clean_data.py            # o: python -m xray.clean  (con src en el PYTHONPATH)

Salida en data/cleaned/:
    <tabla>.parquet       una por tabla
    _cleaning_log.csv     qué ha hecho cada regla y a cuántas filas ha afectado
    _manifest.json        cuándo, con qué código y a partir de qué ficheros se generó
"""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import xray
from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.tables import clean_table
from xray.clean.transactions import clean_transactions
from xray.clean.validate import validate
from xray.io import TABLES, read_raw
from xray.paths import CLEANED_DIR, RAW_DIR, ROOT


def clean_all(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], CleaningLog]:
    """Aplica todas las reglas en memoria. No lee ni escribe disco (fácil de testear)."""
    log = CleaningLog()
    cleaned = {name: clean_table(name, raw[name], log)
               for name in TABLES if name not in ("transactions", "invoices")}
    products = pd.concat([raw["banking_products"][["product_id", "company_id"]],
                          raw["debt_products"][["product_id", "company_id"]]])
    company_group = raw["companies"].set_index("company_id").group_id
    cleaned["transactions"] = clean_transactions(raw["transactions"], products, company_group, log)
    cleaned["invoices"] = clean_invoices(raw["invoices"], log)
    validate(cleaned)
    return cleaned, log


def run(raw_dir: Path = RAW_DIR, out_dir: Path = CLEANED_DIR, verbose: bool = True) -> pd.DataFrame:
    """Lee raw, limpia, valida y escribe la capa cleaned de forma atómica. Devuelve el log."""
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    say = print if verbose else (lambda *a, **k: None)

    raw = {}
    for name in TABLES:
        raw[name] = read_raw(name, raw_dir)
        say(f"  leído   {name:22s} {len(raw[name]):>10,} filas")

    cleaned, log = clean_all(raw)

    # Se escribe en una carpeta temporal y se sustituye al final: si algo falla,
    # la versión anterior de data/cleaned/ queda intacta.
    tmp = out_dir.with_name(out_dir.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name, df in cleaned.items():
        df.to_parquet(tmp / f"{name}.parquet", index=False)
        say(f"  escrito {name:22s} {len(df):>10,} filas ({len(raw[name]) - len(df):,} quitadas)")
    log_df = log.to_frame()
    log_df.to_csv(tmp / "_cleaning_log.csv", index=False)
    (tmp / "_manifest.json").write_text(
        json.dumps(_manifest(raw_dir, raw, cleaned), indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(out_dir, ignore_errors=True)
    tmp.rename(out_dir)
    say(f"  OK -> {out_dir}")
    return log_df


def _manifest(raw_dir: Path, raw: dict, cleaned: dict) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "xray_version": xray.__version__,
        "git_commit": _git_commit(),
        "decisions": "docs/decisiones.md",
        "tables": {
            name: {
                "raw_file": f"{name}.csv",
                "raw_sha256": _sha256(raw_dir / f"{name}.csv"),
                "raw_rows": len(raw[name]),
                "cleaned_rows": len(cleaned[name]),
                "columns": list(cleaned[name].columns),
            }
            for name in TABLES
        },
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "src"], cwd=ROOT, capture_output=True, text=True).stdout
        return out.stdout.strip() + ("-dirty" if dirty.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return None
