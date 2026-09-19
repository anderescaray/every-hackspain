"""CLI for immutable Pulse artifacts; legacy scorers remain separate."""
import argparse
from pathlib import Path

from xray.paths import PROCESSED_DIR, RAW_DIR
from xray.pulse.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical Cash Truth → PulseFourPillars immutable batch")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=PROCESSED_DIR / "pulse")
    parser.add_argument("--as-of", required=True, help="Economic date YYYY-MM-DD; only complete months are scored")
    parser.add_argument("--data-vintage", required=True, help="Date of the source snapshot, not the economic cutoff")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--previous-run", type=Path, help="Verified immutable run directory for comparison")
    parser.add_argument("--ai-categories", type=Path, help="Optional frozen category cache; never calls an AI service")
    parser.add_argument("--ai-min-confidence", type=float, default=0.7)
    parser.add_argument("--company-id", action="append", dest="company_ids", help="Repeat to select companies; group peers are retained for classification")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    manifest = run(args.raw_dir, args.out_dir, as_of=args.as_of, data_vintage=args.data_vintage,
                   config_path=args.config, previous_run=args.previous_run, company_ids=args.company_ids,
                   ai_categories_path=args.ai_categories, ai_min_confidence=args.ai_min_confidence,
                   verbose=not args.quiet)
    print(f"Published {manifest['run_id']}")


if __name__ == "__main__":
    main()
