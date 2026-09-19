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


def recursive_hashes(directory: Path, *, exclude: tuple[str, ...] = ()) -> dict[str, str]:
    """Hash every descendant using relative POSIX paths; never follow symlinks."""
    directory = Path(directory)
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not immutable artifacts: {path}")
        relative = path.relative_to(directory).as_posix()
        if path.is_file() and relative not in exclude:
            result[relative] = sha256(path)
    return result


def cash_classification_manifest(ai_categories_path=None, ai_min_confidence: float = 0.7) -> dict:
    """Canonical method/evidence provenance shared by legacy feature/product jobs.

    Fingerprint the classifier and its actual ledger dependencies, not unrelated
    repository files or git HEAD. A cache is data; a threshold is methodology.
    """
    from xray.ledger.classify import classification_metadata

    directory = Path(__file__).resolve().parent / "ledger"
    sources = {path.name: sha256(path) for path in sorted(directory.glob("*.py"))}
    return {**classification_metadata(ai_categories_path, ai_min_confidence),
            "source_sha256": sources,
            "code_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()}


def verify_run(directory: Path) -> dict:
    """Verify the complete file set, not just files listed by a manifest."""
    directory = Path(directory)
    if directory.is_symlink() or directory.parent.is_symlink():
        raise ValueError("The immutable run directory or runs parent cannot be a symbolic link")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("The run manifest cannot be a symbolic link")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = recursive_hashes(directory, exclude=("manifest.json",))
    if actual != manifest.get("outputs_sha256"):
        raise ValueError(f"Run integrity check failed: {directory}")
    return manifest


def publish_immutable_run(staged: Path, output: Path, run_id: str) -> Path:
    """Publish a whole run once, then atomically switch ``latest.json``.

    Staging must share the output filesystem. Concurrent publishers serialize
    through an advisory lock that is released by the OS even after a crash.
    A failed pointer update leaves a valid unreferenced run, never a mixed run.
    The manifest deliberately excludes itself; the pointer hashes the manifest.
    """
    import fcntl

    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in run_id):
        raise ValueError("Invalid immutable run ID")
    staged, output = Path(staged), Path(output)
    if output.is_symlink() or (output / "runs").is_symlink() or (output / ".publish.lock").is_symlink():
        raise ValueError("Publication paths cannot be symbolic links")
    manifest = verify_run(staged)
    if manifest.get("run_id") != run_id:
        raise ValueError("Manifest and run ID disagree")
    runs = output / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    if staged.stat().st_dev != runs.stat().st_dev:
        raise ValueError("Atomic publication requires staging on the same filesystem")
    target = runs / run_id
    pointer_tmp = output / f".latest-{uuid4().hex}.tmp"
    descriptor = os.open(output / ".publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if runs.is_symlink():
                raise ValueError("The runs directory cannot be a symbolic link")
            if target.exists():
                verify_run(target)
                if recursive_hashes(target) != recursive_hashes(staged):
                    raise ValueError(f"Immutable run conflict: {run_id}")
            else:
                os.rename(staged, target)
            pointer = {"run_id": run_id, "manifest_sha256": sha256(target / "manifest.json")}
            with pointer_tmp.open("w", encoding="utf-8") as stream:
                json.dump(pointer, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pointer_tmp, output / "latest.json")
        finally:
            pointer_tmp.unlink(missing_ok=True)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return target
