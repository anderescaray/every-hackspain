"""Configuración por variables de entorno. Misma raíz de datos que `src/xray/paths.py` (XRAY_DATA_DIR)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METHOD = "financial_smoothed_v2"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("XRAY_DATA_DIR", REPO_ROOT / "data")))
    cors_origins: tuple = field(default_factory=lambda: tuple(
        o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()))
    admin_token: str = field(default_factory=lambda: os.environ.get("ADMIN_TOKEN", ""))
    uploads_dirname: str = "uploads"

    @property
    def product_dir(self) -> Path:
        return self.data_dir / "processed" / "product"

    @property
    def scores_dir(self) -> Path:
        return self.data_dir / "processed" / "scores_v2"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / self.uploads_dirname


def get_settings() -> Settings:
    return Settings()
