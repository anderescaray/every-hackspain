"""Exporta product/ al contrato JSON del frontend (frontend/public/generated/)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.paths import PROCESSED_DIR  # noqa: E402
from xray.product.frontend_export import FRONTEND_GENERATED, run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product-dir", type=Path, default=PROCESSED_DIR / "product")
    parser.add_argument("--out-dir", type=Path, default=FRONTEND_GENERATED)
    args = parser.parse_args()
    run(args.product_dir, args.out_dir)


if __name__ == "__main__":
    main()
