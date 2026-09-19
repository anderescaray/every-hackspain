import argparse
from pathlib import Path

from xray.paths import PROCESSED_DIR
from xray.score.config import PANELS
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Score financiero suavizado V2; referencia e inferencia separadas. No sobrescribe V1.")
    parser.add_argument("mode", choices=("fit", "predict"))
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--panel", choices=tuple(PANELS))
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if args.mode == "predict" and args.reference is None:
        parser.error("predict requiere --reference; no se aprende con el conjunto oculto")
    if args.mode == "predict" and args.panel is not None:
        parser.error("En predict el panel se toma de --reference")
    config = ScoreV2Config(panel=args.panel or "company") if args.mode == "fit" else None
    run(args.features_dir, args.out_dir, config, args.mode, args.reference)


if __name__ == "__main__":
    main()
