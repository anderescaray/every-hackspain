import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from xray.paths import RAW_DIR, ROOT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_manifest() -> dict:
    sources = sorted((ROOT / "src" / "xray").rglob("*.py"))
    sources += sorted((ROOT / "scripts").glob("*.py")) + [ROOT / "pyproject.toml"]
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in sources}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"git_commit": commit, "source_sha256": hashes,
            "code_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def check_output_path(output: Path, source: Path) -> None:
    output = output.resolve()
    for protected in (source.resolve(), RAW_DIR.resolve()):
        if output == protected or output in protected.parents or protected in output.parents:
            raise ValueError(f"La salida {output} se solapa con la entrada protegida {protected}")


def publish_bundle(staged: Path, output: Path, manifest: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(path.name for path in staged.iterdir() if path.name != manifest) + [manifest]
    backup = output / ".history" / uuid4().hex
    replaced = []
    lock = output / ".pipeline.lock"
    handle = lock.open("x", encoding="utf-8")
    try:
        with handle:
            try:
                for name in files:
                    target = output / name
                    if target.exists():
                        backup.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup / name)
                    os.replace(staged / name, target)
                    replaced.append(name)
            except Exception:
                for name in reversed(replaced):
                    if (backup / name).exists():
                        os.replace(backup / name, output / name)
                    else:
                        (output / name).unlink()
                raise
    finally:
        lock.unlink()
