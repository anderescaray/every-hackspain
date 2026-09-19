import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.paths import PROCESSED_DIR
from xray.score.config import PANELS
from xray.score.pipeline import validate_saved_scores


def main():
    parser = argparse.ArgumentParser(description="Verifica integridad, explicaciones y causalidad del score.")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--scores-dir", type=Path)
    parser.add_argument("--panel", choices=tuple(PANELS), default="company")
    parser.add_argument("--check-prefix")
    args = parser.parse_args()
    print(json.dumps(validate_saved_scores(args.scores_dir, args.features_dir, args.panel, args.check_prefix), indent=2))


if __name__ == "__main__":
    main()
