from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_store
from app.schemas import Portfolio
from app.store import ProductStore

router = APIRouter()
SORTABLE = ("score", "delta_vs_prev", "confidence", "level", "momentum", "company_id")


@router.get("/portfolio", response_model=Portfolio)
def portfolio(store: ProductStore = Depends(get_store),
              trajectory: str | None = None, episode: str | None = None, score_status: str | None = None,
              group_id: str | None = None, confidence_band: str | None = None, currency: str | None = None,
              min_score: float | None = None, max_score: float | None = None,
              sort: str = Query("score", description=f"uno de {SORTABLE}"), order: Literal["asc", "desc"] = "desc",
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if sort not in SORTABLE:
        raise HTTPException(400, f"sort debe ser uno de {SORTABLE}")
    exact = {"trajectory": trajectory, "episode": episode, "score_status": score_status, "group_id": group_id,
             "confidence_band": confidence_band, "currency": currency}
    items = [r for r in store.items if all(v is None or r.get(k) == v for k, v in exact.items())]
    if min_score is not None:
        items = [r for r in items if r.get("score") is not None and r["score"] >= min_score]
    if max_score is not None:
        items = [r for r in items if r.get("score") is not None and r["score"] <= max_score]
    # null siempre al final, independientemente del orden
    with_value = [r for r in items if r.get(sort) is not None]
    without = [r for r in items if r.get(sort) is None]
    with_value.sort(key=lambda r: r[sort], reverse=(order == "desc"))
    items = with_value + without
    return Portfolio(latest_month=store.latest_month, total=len(items), items=items[offset:offset + limit])
