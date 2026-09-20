"""Build immutable retrospective V2 Stress Test artifacts before frontend export."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.paths import CLEANED_DIR, PROCESSED_DIR
from xray.stress.pipeline import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--scores-dir", type=Path)
    parser.add_argument("--cleaned-dir", type=Path, default=CLEANED_DIR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--month")
    parser.add_argument("--company", action="append")
    args = parser.parse_args()
    run(args.features_dir, args.scores_dir, args.cleaned_dir, args.out_dir, args.month, args.company)


if __name__ == "__main__":
    main()
