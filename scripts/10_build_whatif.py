"""Paso 10: escenarios what-if precalculados (una palanca cada vez) -> data/processed/product/whatif_scenarios.parquet."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.paths import PROCESSED_DIR  # noqa: E402
from xray.product.whatif import run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--scores-dir", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--month")
    args = parser.parse_args()
    run(args.features_dir, args.scores_dir, args.out_dir, args.month)


if __name__ == "__main__":
    main()
