import argparse
from pathlib import Path

from xray.features import FeatureConfig, run
from xray.paths import CLEANED_DIR, PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Construye features mensuales causales desde cleaned.")
    parser.add_argument("--cleaned-dir", type=Path, default=CLEANED_DIR)
    parser.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--start-month", default="2024-09-01")
    parser.add_argument("--end-month", default="2026-08-01")
    parser.add_argument("--extraction-date", default="2026-09-01")
    args = parser.parse_args()
    config = FeatureConfig(args.start_month, args.end_month, args.extraction_date)
    run(args.cleaned_dir, args.out_dir, config)


if __name__ == "__main__":
    main()
