"""Exporta product/ al contrato JSON del frontend (frontend/public/generated/).

Por defecto assessment/summary son plantillas deterministas ancladas.
Con --llm (y XRAY_LLM_API_KEY u OPENAI_API_KEY) el resumen en viñetas que va bajo el
Health Score lo escribe el LLM leyendo el informe completo de cada empresa; una llamada
por empresa y TODAS las empresas salvo que se acote con --llm-companies. Si un número no
existe en el informe, o falla la red, esa empresa se queda con su plantilla.
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
    parser.add_argument("--advisor-dir", type=Path, default=PROCESSED_DIR / "advisor_production",
                        help="solo se exportan planes generados con --production-safe")
    parser.add_argument("--stress-dir", type=Path, default=PROCESSED_DIR / "stress",
                        help="run 10b opcional; sin latest.json se omite stress_test")
    parser.add_argument("--llm", action="store_true",
                        help="redactar el resumen en viñetas con LLM desde el informe de cada "
                             "empresa (requiere API key en env; 1 llamada por empresa)")
    parser.add_argument("--llm-companies", default=None,
                        help="acota el LLM: IDs separados por coma, o 'demo' para las de demo. "
                             "Por defecto, todas las empresas exportadas")
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
        selection = (args.llm_companies or "").strip().lower()
        if args.llm_companies is None or selection == "all":
            llm_companies = None
        elif selection == "demo":
            llm_companies = list(DEMO_LLM_COMPANIES)
        else:
            llm_companies = [c.strip() for c in args.llm_companies.split(",") if c.strip()]
    run(args.product_dir, args.out_dir, advisor_dir=args.advisor_dir, stress_dir=args.stress_dir,
        completer=completer, llm_companies=llm_companies)


if __name__ == "__main__":
    main()
