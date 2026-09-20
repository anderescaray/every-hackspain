"""Exporta product/ al contrato JSON del frontend (frontend/public/generated/).

Por defecto assessment/summary son plantillas deterministas ancladas.
Con --llm (y XRAY_LLM_API_KEY u OPENAI_API_KEY) se parafrasean solo las empresas
indicadas en --llm-companies (por defecto las de demo). Si el anclaje falla, plantilla.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.group_advisor.llm_providers import completer_from_env  # noqa: E402
from xray.paths import PROCESSED_DIR  # noqa: E402
from xray.product.frontend_export import FRONTEND_GENERATED, run  # noqa: E402

DEMO_LLM_COMPANIES = (
    "COMP_0764",
    "COMP_0001",
    "COMP_0647",
    "COMP_0045",
    "COMP_0006",
    "COMP_0037",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product-dir", type=Path, default=PROCESSED_DIR / "product")
    parser.add_argument("--out-dir", type=Path, default=FRONTEND_GENERATED)
    parser.add_argument("--llm", action="store_true",
                        help="parafrasear assessment/summary con LLM (requiere API key en env)")
    parser.add_argument("--llm-companies", default=None,
                        help="IDs separados por coma; por defecto empresas demo. 'all' = todas")
    args = parser.parse_args()
    completer = None
    llm_companies = None
    if args.llm:
        completer = completer_from_env()
        if completer is None:
            raise SystemExit(
                "--llm requiere XRAY_LLM_API_KEY u OPENAI_API_KEY; "
                "sin clave el export usa solo plantillas (omite --llm)."
            )
        if args.llm_companies is None:
            llm_companies = list(DEMO_LLM_COMPANIES)
        elif args.llm_companies.strip().lower() == "all":
            llm_companies = None
        else:
            llm_companies = [c.strip() for c in args.llm_companies.split(",") if c.strip()]
    run(args.product_dir, args.out_dir, completer=completer, llm_companies=llm_companies)


if __name__ == "__main__":
    main()
