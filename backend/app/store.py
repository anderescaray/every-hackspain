"""Carga en memoria de `data/processed/product/` y recarga cuando cambia el manifiesto.

La API no calcula nada: si falta un artefacto se responde 503 indicando el script a ejecutar.
"""
import hashlib
import json
import threading
from pathlib import Path

from fastapi import HTTPException

MISSING_HINT = ("Artefactos de producto no disponibles en {path}. Ejecuta: python -X utf8 scripts/00_clean_data.py && "
                "python -X utf8 scripts/01_build_monthly_features.py && python -X utf8 scripts/05_compute_scores_v2.py fit && "
                "python -X utf8 scripts/08_build_product.py")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductStore:
    """Un dataset publicado (el principal o el de un job de import)."""

    def __init__(self, product_dir: Path, scores_dir: Path | None = None):
        self.product_dir = Path(product_dir)
        self.scores_dir = Path(scores_dir) if scores_dir else self.product_dir.parent / "scores_v2"
        self._lock = threading.Lock()
        self.manifest: dict | None = None
        self.manifest_sha256: str | None = None
        self.portfolio: dict | None = None
        self._companies: dict[str, dict] = {}
        self._groups: dict[str, dict] = {}
        self.alerts: dict | None = None

    # --- carga ---------------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.product_dir / "_product_manifest.json"

    def load(self) -> bool:
        """Carga (o recarga) si el manifiesto existe. Devuelve True si había algo que cargar."""
        with self._lock:
            if not self.manifest_path.exists():
                self.manifest = self.portfolio = None
                self.manifest_sha256 = None
                self._companies.clear()
                self._groups.clear()
                return False
            self.manifest_sha256 = _sha256(self.manifest_path)
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.portfolio = json.loads((self.product_dir / "portfolio.json").read_text(encoding="utf-8"))
            self._companies.clear()
            self._groups.clear()
            alerts = self.product_dir / "alerts.json"
            self.alerts = json.loads(alerts.read_text(encoding="utf-8")) if alerts.exists() else None
            return True

    def refresh_if_changed(self) -> bool:
        if not self.manifest_path.exists():
            return self.load() if self.manifest is not None else False
        if _sha256(self.manifest_path) != self.manifest_sha256:
            return self.load()
        return False

    @property
    def ready(self) -> bool:
        return self.portfolio is not None

    def require(self):
        if not self.ready:
            raise HTTPException(503, MISSING_HINT.format(path=self.product_dir))

    # --- lecturas ------------------------------------------------------------
    @property
    def latest_month(self):
        return self.portfolio["latest_month"] if self.portfolio else None

    @property
    def items(self) -> list[dict]:
        self.require()
        return self.portfolio["companies"]

    def _read_entity(self, cache: dict, folder: str, entity_id: str, label: str) -> dict:
        self.require()
        if entity_id not in cache:
            path = self.product_dir / folder / f"{entity_id}.json"
            if not path.exists() or not path.resolve().is_relative_to((self.product_dir / folder).resolve()):
                raise HTTPException(404, f"{label} desconocida: {entity_id}")
            cache[entity_id] = json.loads(path.read_text(encoding="utf-8"))
        return cache[entity_id]

    def company(self, company_id: str) -> dict:
        return self._read_entity(self._companies, "companies", company_id, "Empresa")

    def group(self, group_id: str) -> dict:
        return self._read_entity(self._groups, "groups", group_id, "Grupo")

    def company_currency(self, company_id: str, currency: str | None) -> tuple[str, dict]:
        payload = self.company(company_id)
        currencies = payload.get("currencies", {})
        if currency is None:
            row = next((r for r in self.items if r["company_id"] == company_id), None)
            currency = row["currency"] if row else next(iter(currencies), None)
        if currency not in currencies:
            raise HTTPException(400, f"Moneda {currency!r} no disponible para {company_id}; opciones: {sorted(currencies)}")
        return currency, currencies[currency]

    @property
    def latest_csv(self) -> Path:
        path = self.scores_dir / "company_latest_scores.csv"
        if not path.exists():
            raise HTTPException(503, f"No existe {path}. Ejecuta scripts/05_compute_scores_v2.py")
        return path
