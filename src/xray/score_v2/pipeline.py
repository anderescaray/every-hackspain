"""Ejecución y publicación de `financial_smoothed_v2`.

Salida por defecto en `data/processed/scores_v2/`, separada del control V1
(`data/processed/scores/`). Mismo protocolo de publicación (staging, respaldo en
`.history/`, manifiesto con hashes). `fit` ajusta la referencia; `predict` reutiliza
una referencia congelada sin recalibrar con las entidades nuevas.
"""
import hashlib
import json
import platform
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from xray.artifacts import check_output_path, code_manifest, publish_bundle, sha256
from xray.paths import CLEANED_DIR, PROCESSED_DIR
from xray.score.pipeline import read_panel
from xray.score.report import example_cases, json_safe, latest_scores, score_report
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import METHOD, fit_reference_bundle, score_panel, validate_scores
from xray.score_v2.trajectory import LABELS


EXAMPLE_TRAJECTORIES = tuple(label for label in LABELS if label != "insufficient_history")


def v2_report(scores, reference):
    report = score_report(scores, reference)
    valid = scores.score.notna()
    report["episode"] = scores.loc[valid].episode.value_counts().to_dict()
    report["latest_episode"] = scores.loc[valid & scores.month.eq(scores.month.max())].episode.value_counts().to_dict()
    report["confirmation_rule"] = ("Dirección confirmada solo con dos meses seguidos de momentum en el mismo sentido y el mes actual "
                                   "del mismo lado de su nivel de seis meses; un mes atípico aislado se etiqueta one_off, no tendencia.")
    report["limitations"] = report["limitations"] + [
        "Ventanas de seis meses suavizan el nivel: una ruptura real tarda 1–3 meses en reflejarse por completo.",
        "Un mes actual fino se puntúa con la ventana y queda como provisional; no es una observación completa del mes.",
    ]
    return report


def run(features_dir=PROCESSED_DIR, out_dir=None, config=None, mode="fit", reference_file=None, verbose=True):
    if mode not in ("fit", "predict"):
        raise ValueError("mode debe ser fit o predict")
    if mode == "predict":
        if reference_file is None:
            raise ValueError("predict requiere una referencia ya ajustada, no se recalibra con las empresas nuevas")
        reference_file = Path(reference_file)
        reference_bytes = reference_file.read_bytes()
        reference = json.loads(reference_bytes)
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        stored = ScoreV2Config(**reference["config"])
        if config is not None and config != stored:
            raise ValueError("La configuración debe coincidir con la referencia congelada")
        config = stored
    else:
        if reference_file is not None:
            raise ValueError("fit no recibe una referencia; usar predict para reutilizarla")
        config = config or ScoreV2Config()
        reference_hash = None
    features_dir = Path(features_dir)
    out_dir = Path(out_dir) if out_dir is not None else features_dir / "scores_v2"
    check_output_path(out_dir, features_dir / config.feature_file)
    check_output_path(out_dir, CLEANED_DIR)
    check_output_path(out_dir, features_dir.parent / "raw")
    if out_dir.resolve() == (features_dir / "scores").resolve():
        raise ValueError("La salida de V2 no puede sobrescribir el control V1 en scores/")
    panel, source = read_panel(features_dir, config)
    if mode == "fit":
        reference = fit_reference_bundle(panel, config)
    scores, explanations = score_panel(panel, reference)
    latest = latest_scores(scores, config.unit)
    report = v2_report(scores, reference)
    report["mode"] = mode
    prefix = config.panel
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scores-v2-", dir=out_dir.parent) as directory:
        staged = Path(directory)
        scores.to_parquet(staged / f"{prefix}_monthly_scores.parquet", index=False)
        explanations.to_parquet(staged / f"{prefix}_score_explanations.parquet", index=False)
        latest.to_csv(staged / f"{prefix}_latest_scores.csv", index=False)
        documents = {
            f"_{prefix}_score_reference.json": reference,
            f"_{prefix}_score_report.json": report,
            f"{prefix}_score_examples.json": example_cases(scores, explanations, config.unit, EXAMPLE_TRAJECTORIES),
        }
        for filename, content in documents.items():
            if mode == "predict" and filename == f"_{prefix}_score_reference.json":
                (staged / filename).write_bytes(reference_bytes)
            else:
                (staged / filename).write_text(json.dumps(json_safe(content), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "method": METHOD, "mode": mode, "config": asdict(config), "input": source,
                    "inference_reference_sha256": reference_hash, "code": code_manifest(),
                    "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
                    "outputs_sha256": {path.name: sha256(path) for path in sorted(staged.iterdir())}}
        manifest_name = f"_{prefix}_score_manifest.json"
        (staged / manifest_name).write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if (features_dir / ".pipeline.lock").exists() or sha256(features_dir / config.feature_file) != source["feature_sha256"]:
            raise RuntimeError("Las features cambiaron durante el cálculo; no se publica")
        if sha256(features_dir / "_feature_manifest.json") != source["feature_manifest_sha256"]:
            raise RuntimeError("El manifiesto de features cambió durante el cálculo")
        if mode == "predict" and sha256(reference_file) != reference_hash:
            raise RuntimeError("La referencia cambió durante la inferencia")
        publish_bundle(staged, out_dir, manifest_name)
    if verbose:
        print(json.dumps(json_safe({"method": METHOD, "mode": mode, "out_dir": str(out_dir), "latest_month": report["latest_month"],
                                    "reference_groups": report["reference_group_count"], "holdout_groups": report["holdout_group_count"],
                                    "latest": report["latest"], "latest_episode": report["latest_episode"]}),
                         indent=2, ensure_ascii=False, allow_nan=False))
    return report


def validate_saved_scores(scores_dir=None, features_dir=PROCESSED_DIR, panel="company", prefix_month=None):
    features_dir = Path(features_dir)
    scores_dir = Path(scores_dir) if scores_dir is not None else features_dir / "scores_v2"
    if (scores_dir / ".pipeline.lock").exists():
        raise RuntimeError("Publicación de scores en curso")
    manifest = json.loads((scores_dir / f"_{panel}_score_manifest.json").read_text(encoding="utf-8"))
    if manifest["method"] != METHOD:
        raise ValueError(f"El directorio contiene {manifest['method']}, no {METHOD}")
    config = ScoreV2Config(**manifest["config"])
    if config.panel != panel:
        raise ValueError("Panel incompatible con el manifiesto")
    for name, digest in manifest["outputs_sha256"].items():
        if Path(name).name != name or sha256(scores_dir / name) != digest:
            raise ValueError(f"Hash de score incorrecto: {name}")
    features, source = read_panel(features_dir, config)
    if source != manifest["input"]:
        raise ValueError("Los scores se calcularon con otra versión de las features")
    scores = pd.read_parquet(scores_dir / f"{panel}_monthly_scores.parquet")
    explanations = pd.read_parquet(scores_dir / f"{panel}_score_explanations.parquet")
    reference_path = scores_dir / f"_{panel}_score_reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if manifest["mode"] == "predict" and sha256(reference_path) != manifest["inference_reference_sha256"]:
        raise ValueError("La referencia publicada no coincide con la utilizada en predict")
    if set(reference["reference_groups"]) & set(reference["holdout_groups"]):
        raise ValueError("Un grupo está tanto en referencia como en holdout")
    validate_scores(scores, explanations, config)
    keys = [config.unit, "currency", "month"]
    if not scores[keys].equals(features[keys].reset_index(drop=True)):
        raise ValueError("Los scores no conservan todas las filas y claves de entrada")
    if prefix_month is not None:
        cutoff = pd.Timestamp(prefix_month)
        if cutoff < features.month.min() or cutoff >= features.month.max():
            raise ValueError("El corte de prefijo debe estar dentro del panel y antes de su último mes")
        recalculated, _ = score_panel(features.loc[features.month.le(cutoff)], reference)
        pd.testing.assert_frame_equal(recalculated.set_index(keys).sort_index(),
                                      scores.loc[scores.month.le(cutoff)].set_index(keys).sort_index())
    return {"method": METHOD, "rows": len(scores), "scored_rows": int(scores.score.notna().sum()),
            "entities": int(scores[config.unit].nunique()), "prefix_checked": prefix_month,
            "official_score_agreement": None}
