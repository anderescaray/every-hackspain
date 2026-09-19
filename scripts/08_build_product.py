"""Paso 8: artefactos de producto (Embat Pulse) sobre scores_v2 -> data/processed/product/.

    python -X utf8 scripts/08_build_product.py
    python -X utf8 scripts/08_build_product.py --scores-dir data/processed/scores_v2 --out-dir data/processed/product

No recalcula scores; compone «por qué ha cambiado», confidence, portfolio y fichas por empresa/grupo.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.paths import PROCESSED_DIR  # noqa: E402
from xray.product.bundle import run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--scores-dir", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    run(args.scores_dir, args.features_dir, args.out_dir)


if __name__ == "__main__":
    main()
