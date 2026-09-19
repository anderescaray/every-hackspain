"""Exporta un run Pulse verificado al snapshot único del frontend."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.product.frontend_export import FRONTEND_GENERATED, run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True, help="Directorio inmutable con manifest.json de Pulse")
    parser.add_argument("--out-dir", type=Path, default=FRONTEND_GENERATED)
    parser.add_argument("--currency", choices=("EUR",), default="EUR", help="Vista explícita; no se consolidan monedas")
    args = parser.parse_args()
    run(args.run_dir, args.out_dir, currency=args.currency)


if __name__ == "__main__":
    main()
