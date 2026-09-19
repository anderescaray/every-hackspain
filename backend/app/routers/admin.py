from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.deps import Registry, get_registry

router = APIRouter()


@router.post("/reload")
def reload(request: Request, registry: Registry = Depends(get_registry), x_admin_token: str | None = Header(None)):
    token = registry.settings.admin_token
    if token and x_admin_token != token:
        raise HTTPException(401, "Token de administración inválido")
    registry.main.load()
    request.state.manifest_sha256 = registry.main.manifest_sha256
    return {"reloaded": True, "manifest_sha256": registry.main.manifest_sha256, "ready": registry.main.ready}
