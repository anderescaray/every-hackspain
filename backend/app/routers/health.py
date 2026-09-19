from fastapi import APIRouter, Depends

from app.config import METHOD
from app.deps import get_store
from app.schemas import Health
from app.store import ProductStore

router = APIRouter()


@router.get("/health", response_model=Health)
def health(store: ProductStore = Depends(get_store)):
    manifest = store.manifest or {}
    return Health(status="ok" if store.ready else "degraded", latest_month=store.latest_month, method=METHOD,
                  manifest_created_at=manifest.get("created_at"), git_commit=(manifest.get("code") or {}).get("git_commit"),
                  n_companies=len(store.portfolio["companies"]) if store.ready else 0, manifest_sha256=store.manifest_sha256)
