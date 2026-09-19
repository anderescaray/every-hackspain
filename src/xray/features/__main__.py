import argparse
from pathlib import Path

from xray.features import FeatureConfig, run
from xray.paths import AI_CATEGORIES_PATH, CLEANED_DIR, PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description="Construye features mensuales causales desde cleaned.")
    parser.add_argument("--cleaned-dir", type=Path, default=CLEANED_DIR)
    parser.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--start-month", default="2024-09-01")
    parser.add_argument("--end-month", default="2026-08-01")
    parser.add_argument("--extraction-date", default="2026-09-01")
    parser.add_argument("--ai-categories", type=Path, default=AI_CATEGORIES_PATH,
                        help="D31: template_categories.parquet generado una vez con Jev; rellena filas uncategorized "
                             "(default: el artefacto versionado en resources/)")
    parser.add_argument("--no-ai-categories", action="store_true", help="Desactiva D31 (solo categoría del banco)")
    parser.add_argument("--ai-min-confidence", type=float, default=0.7)
    args = parser.parse_args()
    ai_path = None if args.no_ai_categories else args.ai_categories
    if ai_path is not None and not Path(ai_path).exists():
        raise FileNotFoundError(f"No existe el artefacto D31 {ai_path}; usa --no-ai-categories o --ai-categories RUTA")
    config = FeatureConfig(args.start_month, args.end_month, args.extraction_date,
                           ai_categories_path=str(ai_path) if ai_path else None,
                           ai_min_confidence=args.ai_min_confidence)
    run(args.cleaned_dir, args.out_dir, config)


if __name__ == "__main__":
    main()
