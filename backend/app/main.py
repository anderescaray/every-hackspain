"""API de solo lectura sobre los artefactos de Embat Pulse. Arranque:

    uvicorn app.main:app --app-dir backend --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.deps import Registry
from app.jobs import JobRunner
from app.routers import admin, alerts, companies, export, groups, health, imports, portfolio


def create_app(settings: Settings | None = None, job_runner=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.registry.main.load()
        yield

    app = FastAPI(title="Embat Pulse API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.registry = Registry(settings)
    app.state.registry.jobs = JobRunner(settings, runner=job_runner)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["X-Xray-Manifest", "X-Xray-Dataset"])

    @app.middleware("http")
    async def manifest_header(request: Request, call_next):
        response = await call_next(request)
        sha = getattr(request.state, "manifest_sha256", None) or app.state.registry.main.manifest_sha256
        if sha:
            response.headers["X-Xray-Manifest"] = sha
        response.headers["X-Xray-Dataset"] = getattr(request.state, "dataset", "main")
        return response

    for module in (health, portfolio, companies, groups, alerts, export, admin, imports):
        app.include_router(module.router)
    return app


app = create_app()
