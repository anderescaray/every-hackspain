from fastapi import APIRouter, Depends, Request

from app.config import METHOD
from app.deps import get_store
from app.schemas import CompanyDetail, Meta, TimelinePoint
from app.store import ProductStore

router = APIRouter()


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def company(company_id: str, request: Request, store: ProductStore = Depends(get_store)):
    payload = store.company(company_id)
    meta = Meta(method=METHOD, manifest_sha256=store.manifest_sha256, dataset=request.state.dataset)
    return CompanyDetail(**payload, meta=meta)


@router.get("/companies/{company_id}/timeline", response_model=list[TimelinePoint])
def timeline(company_id: str, currency: str | None = None, store: ProductStore = Depends(get_store)):
    _, block = store.company_currency(company_id, currency)
    return block.get("timeline", [])


@router.get("/companies/{company_id}/why")
def why_changed(company_id: str, currency: str | None = None, store: ProductStore = Depends(get_store)):
    currency, block = store.company_currency(company_id, currency)
    return {"company_id": company_id, "currency": currency, **(block.get("why_changed") or {"month": None, "terms": []})}
