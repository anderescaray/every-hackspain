from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.deps import Registry, get_registry
from app.schemas import ImportJob

router = APIRouter()


@router.post("/import", response_model=ImportJob, status_code=202)
async def create_import(files: list[UploadFile] = File(..., description="CSV originales con los nombres de data/raw/"),
                        registry: Registry = Depends(get_registry)):
    payload = {f.filename: await f.read() for f in files}
    try:
        return registry.jobs.create(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get("/import/{job_id}", response_model=ImportJob)
def get_import(job_id: str, registry: Registry = Depends(get_registry)):
    job = registry.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job desconocido: {job_id}")
    return job
