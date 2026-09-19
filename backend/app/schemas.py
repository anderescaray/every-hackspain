"""Modelos de respuesta. Admiten campos extra: el equipo de datos añadirá columnas sin avisar."""
from typing import Any

from pydantic import BaseModel, ConfigDict


class Extra(BaseModel):
    model_config = ConfigDict(extra="allow")


class PortfolioItem(Extra):
    company_id: str
    group_id: str | None = None
    currency: str | None = None
    currencies: list[str] | None = None
    month: str | None = None
    score: float | None = None
    level: float | None = None
    momentum: float | None = None
    stability: float | None = None
    trajectory: str | None = None
    episode: str | None = None
    score_status: str | None = None
    score_reason: str | None = None
    delta_vs_prev: float | None = None
    confidence: float | None = None
    confidence_band: str | None = None
    main_signal: str | None = None
    main_signal_delta: float | None = None


class Portfolio(BaseModel):
    latest_month: str | None
    total: int
    items: list[PortfolioItem]


class TimelinePoint(Extra):
    month: str
    score: float | None = None
    level: float | None = None
    momentum: float | None = None
    stability: float | None = None
    trajectory: str | None = None
    episode: str | None = None
    score_status: str | None = None
    score_reason: str | None = None
    delta_vs_prev: float | None = None
    confidence: float | None = None
    confidence_band: str | None = None


class Meta(BaseModel):
    method: str
    manifest_sha256: str | None
    dataset: str


class CompanyDetail(Extra):
    company_id: str
    group_id: str | None = None
    latest_month: str | None = None
    currencies: dict[str, Any]
    meta: Meta


class Health(BaseModel):
    status: str
    latest_month: str | None
    method: str
    manifest_created_at: str | None
    git_commit: str | None
    n_companies: int
    manifest_sha256: str | None


class ImportJob(BaseModel):
    job_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    log_tail: str = ""
    artifacts_dir: str | None = None
    error: str | None = None
