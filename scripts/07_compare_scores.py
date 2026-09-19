import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.evaluation.compare import compare
from xray.paths import PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Compara el control V1 con V2: estabilidad, proxy de estrés, riesgo por etiqueta y anticipación.")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--v1-dir", type=Path)
    parser.add_argument("--v2-dir", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--no-sensitivity", action="store_true", help="Omite la tabla de sensibilidad al umbral (más rápido)")
    args = parser.parse_args()
    report = compare(args.features_dir, args.v1_dir, args.v2_dir, args.out_dir, not args.no_sensitivity)
    out_dir = args.out_dir or args.features_dir / "evaluation"
    print((out_dir / "score_comparison.md").read_text(encoding="utf-8"))
    print(f"JSON: {out_dir / 'score_comparison.json'}")


if __name__ == "__main__":
    main()
