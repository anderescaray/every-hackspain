from fastapi import APIRouter, Depends, Query

from app.deps import get_store
from app.store import ProductStore

router = APIRouter()


@router.get("/alerts")
def alerts(store: ProductStore = Depends(get_store), severity: str | None = None, type: str | None = None,
           company_id: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """Sirve `alerts.json` si existe; hasta entonces devuelve una lista vacía (no bloquea la demo)."""
    store.require()
    raw = store.alerts
    items = raw if isinstance(raw, list) else (raw or {}).get("alerts") or (raw or {}).get("items") or []
    filters = {"severity": severity, "type": type, "company_id": company_id}
    items = [a for a in items if all(v is None or a.get(k) == v for k, v in filters.items())]
    return {"available": raw is not None, "total": len(items), "items": items[offset:offset + limit]}
