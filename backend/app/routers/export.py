from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.deps import get_store
from app.store import ProductStore

router = APIRouter()


@router.get("/export/latest.csv")
def latest_csv(store: ProductStore = Depends(get_store)):
    return FileResponse(store.latest_csv, media_type="text/csv", filename="company_latest_scores.csv")
