import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from xray.artifacts import sha256
from xray.features import INPUTS, FeatureConfig, build_features, model_columns, validate_features
from xray.io import read_cleaned
from xray.paths import CLEANED_DIR, PROCESSED_DIR


def validate_saved_features(out_dir=PROCESSED_DIR, cleaned_dir=CLEANED_DIR, prefix_month=None):
    out_dir, cleaned_dir = Path(out_dir), Path(cleaned_dir)
    for directory in (out_dir, cleaned_dir):
        if (directory / ".pipeline.lock").exists():
            raise RuntimeError(f"Publicación en curso: {directory}")
    manifest = json.loads((out_dir / "_feature_manifest.json").read_text(encoding="utf-8"))
    config = FeatureConfig(**manifest["config"])
    for directory, field in ((out_dir, "outputs_sha256"), (cleaned_dir, "inputs_sha256")):
        for name, digest in manifest[field].items():
            if Path(name).name != name or sha256(directory / name) != digest:
                raise ValueError(f"Hash incorrecto: {name}")
    if sha256(cleaned_dir / "_manifest.json") != manifest["cleaning_manifest_sha256"]:
        raise ValueError("El manifiesto cleaned cambió desde la generación de features")
    artifacts = {Path(name).stem: pd.read_parquet(out_dir / name)
                 for name in manifest["outputs_sha256"] if name.endswith(".parquet")}
    companies = read_cleaned("companies", cleaned_dir)
    validate_features(artifacts, companies, config)
    catalog = json.loads((out_dir / "_feature_catalog.json").read_text(encoding="utf-8"))
    expected = model_columns(artifacts["company_monthly_features"].columns)
    if catalog["model_features"] != expected:
        raise ValueError("El catálogo no corresponde a la lista explícita de features del código")
    if prefix_month is not None:
        prefix_config = replace(config, end_month=prefix_month)
        if pd.Timestamp(prefix_month) >= pd.Timestamp(config.end_month):
            raise ValueError("El prefijo debe terminar antes que el panel completo")
        tables = {name: read_cleaned(name, cleaned_dir) for name in INPUTS}
        prefix = build_features(tables, prefix_config)
        for name in ("company_monthly_features", "company_currency_monthly_features", "group_currency_monthly_features"):
            unit = "group_id" if name.startswith("group") else "company_id"
            keys = [unit, "currency", "month"]
            earlier = prefix[name].set_index(keys).sort_index()
            original = artifacts[name].set_index(keys).reindex(earlier.index).sort_index()
            pd.testing.assert_frame_equal(earlier, original, check_dtype=False, rtol=1e-10, atol=1e-10)
    return {"companies": len(companies), "months": len(config.months),
            "rows": len(artifacts["company_monthly_features"]), "model_candidates": len(expected),
            "prefix_checked": prefix_month}


def main():
    parser = argparse.ArgumentParser(description="Verifica hashes, contrato del panel y opcionalmente invariancia de prefijo.")
    parser.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--cleaned-dir", type=Path, default=CLEANED_DIR)
    parser.add_argument("--check-prefix", metavar="YYYY-MM-01")
    args = parser.parse_args()
    print(json.dumps(validate_saved_features(args.out_dir, args.cleaned_dir, args.check_prefix), indent=2))


if __name__ == "__main__":
    main()
