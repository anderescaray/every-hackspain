"""Dependencias FastAPI: acceso al registro de datasets (principal + jobs) y al runner de import."""
from fastapi import HTTPException, Query, Request

from app.store import ProductStore


class Registry:
    def __init__(self, settings):
        self.settings = settings
        self.main = ProductStore(settings.product_dir, settings.scores_dir)
        self.jobs = None  # JobRunner, se asigna en main
        self._job_stores: dict[str, ProductStore] = {}

    def store(self, dataset: str | None) -> ProductStore:
        if dataset in (None, "", "main"):
            self.main.refresh_if_changed()
            return self.main
        if dataset not in self._job_stores:
            job = self.jobs.get(dataset) if self.jobs else None
            if job is None:
                raise HTTPException(404, f"Dataset desconocido: {dataset}")
            if job["status"] != "done":
                raise HTTPException(409, f"El job {dataset} está en estado {job['status']}")
            self._job_stores[dataset] = ProductStore(self.jobs.job_dir(dataset) / "processed" / "product")
        store = self._job_stores[dataset]
        store.refresh_if_changed() if store.ready else store.load()
        return store


def get_registry(request: Request) -> Registry:
    return request.app.state.registry


def get_store(request: Request, dataset: str | None = Query(None, description="'main' o job_id de /import")) -> ProductStore:
    store = get_registry(request).store(dataset)
    request.state.manifest_sha256 = store.manifest_sha256
    request.state.dataset = dataset or "main"
    return store
