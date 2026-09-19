"""Cola mínima (un job a la vez) que ejecuta el pipeline existente en subproceso con XRAY_DATA_DIR.

Usa `predict` con la referencia congelada del dataset principal: nunca `fit` con empresas nuevas.
El job no sustituye los artefactos principales; deja los suyos en data/uploads/{job_id}/processed/product.
"""
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import REPO_ROOT, Settings

RAW_FILES = ("groups.csv", "companies.csv", "banking_products.csv", "debt_products.csv",
             "debt_schedule_config.csv", "balances.csv", "invoices.csv", "transactions.csv")


def pipeline_commands(reference: Path) -> list[list[str]]:
    scripts = REPO_ROOT / "scripts"
    py = [sys.executable, "-X", "utf8"]
    return [py + [str(scripts / "00_clean_data.py")],
            py + [str(scripts / "01_build_monthly_features.py")],
            py + [str(scripts / "05_compute_scores_v2.py"), "predict", "--reference", str(reference.resolve())],
            py + [str(scripts / "08_build_product.py")]]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRunner:
    def __init__(self, settings: Settings, runner=None):
        self.settings = settings
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._active: str | None = None
        self._run_commands = runner or self._subprocess_runner

    def job_dir(self, job_id: str) -> Path:
        return self.settings.uploads_dir / job_id

    def create(self, files: dict[str, bytes]) -> dict:
        missing = sorted(set(RAW_FILES) - set(files))
        if missing:
            raise ValueError(f"Faltan ficheros: {missing}")
        with self._lock:
            if self._active is not None:
                raise RuntimeError(f"Ya hay un job en curso: {self._active}")
            job_id = uuid4().hex[:12]
            self._active = job_id
        raw = self.job_dir(job_id) / "raw"
        raw.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            (raw / Path(name).name).write_bytes(content)
        job = {"job_id": job_id, "status": "queued", "started_at": None, "finished_at": None,
               "log_tail": "", "artifacts_dir": None, "error": None}
        self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        return job

    def _run(self, job_id: str):
        job = self.jobs[job_id]
        job["status"], job["started_at"] = "running", _now()
        log_path = self.job_dir(job_id) / "log.txt"
        reference = self.settings.scores_dir / "_company_score_reference.json"
        try:
            if not reference.exists():
                raise FileNotFoundError(f"Referencia congelada no encontrada: {reference}")
            env = {**os.environ, "XRAY_DATA_DIR": str(self.job_dir(job_id))}
            self._run_commands(pipeline_commands(reference), env, log_path)
            job["artifacts_dir"] = str(self.job_dir(job_id) / "processed" / "product")
            job["status"] = "done"
        except Exception as exc:  # el job informa; no tumba la API
            job["status"], job["error"] = "failed", str(exc)
        finally:
            job["finished_at"] = _now()
            job["log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.exists() else ""
            with self._lock:
                self._active = None

    @staticmethod
    def _subprocess_runner(commands, env, log_path: Path):
        with log_path.open("w", encoding="utf-8") as log:
            for cmd in commands:
                log.write(f"$ {' '.join(cmd)}\n")
                log.flush()
                result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Fallo ({result.returncode}) en: {' '.join(cmd)}")

    def get(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)
