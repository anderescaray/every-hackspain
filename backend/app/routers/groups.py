from fastapi import APIRouter, Depends

from app.deps import get_store
from app.store import ProductStore

router = APIRouter()


@router.get("/groups/{group_id}")
def group(group_id: str, store: ProductStore = Depends(get_store)):
    return store.group(group_id)
