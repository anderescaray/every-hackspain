"""Advisor de tesorería (`treasury_advisor_v1`): planes de grupo y sensibilidades de empresa sobre el nivel V2.

Sin opciones publica todo en `data/processed/advisor/`. `--group GROUP_xxxx` / `--company COMP_xxxx`
construyen solo ese estado, imprimen la narrativa por consola y no publican nada.

`--llm` (WP6): parafrasea la narrativa impresa con un Completer real si hay
`XRAY_LLM_API_KEY` u `OPENAI_API_KEY`; temperatura 0 y fallback a plantilla si el anclaje falla.
En la publicación completa `--llm` no se aplica (coste); usar `--group` / `--company`.
"""
import argparse
from dataclasses import replace
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xray.group_advisor.grounding import validate_grounding
from xray.group_advisor.llm import llm_render
from xray.group_advisor.llm_providers import completer_from_env
from xray.group_advisor.narrative import render_plan, render_sensitivity
from xray.group_advisor.pipeline import check_out_dir, default_config, group_context, mark_covered_by_group_plan, plan_roles, \
    resolve_month, resolve_out_dir, run
from xray.group_advisor.plan import build_plan
from xray.group_advisor.sensitivity import company_sensitivity
from xray.group_advisor.state import build_group_state, load_inputs
from xray.paths import PROCESSED_DIR


def _print_grounding(result):
    if not result.ok:
        print(f"\n[anclaje] números sin respaldo: {result.unmatched_numbers}; ids sin respaldo: {result.unmatched_ids}", file=sys.stderr)


def _maybe_llm(doc, template_text, completer):
    if completer is None:
        print(template_text)
        _print_grounding(validate_grounding(template_text, doc))
        return
    result = llm_render(doc, completer, mode="paraphrase", fmt="markdown")
    print(result.text)
    if result.fallback:
        print(f"\n[llm] fallback a plantilla (source={result.source})", file=sys.stderr)
    _print_grounding(result.grounding)


def show_group(inputs, group_id, month, config, completer=None):
    state = build_group_state(inputs, group_id, month, config)
    plan = build_plan(state, config)
    text = render_plan(plan, "markdown")
    _maybe_llm(plan, text, completer)


def show_company(inputs, company_id, month, config, completer=None):
    rows = inputs.rows.loc[inputs.rows.company_id.eq(company_id) & inputs.rows.month.eq(month)]
    if rows.empty:
        raise SystemExit(f"{company_id} no tiene fila en el panel para {month.date()}")
    state = build_group_state(inputs, str(rows.group_id.iloc[0]), month, config)
    plan = build_plan(state, config)
    roles, covered = plan_roles(plan)
    sens = company_sensitivity(state, company_id, config)
    sens["group_context"] = group_context(plan, company_id, roles)
    mark_covered_by_group_plan(sens, covered)
    text = render_sensitivity(sens, "markdown")
    _maybe_llm(sens, text, completer)


def main():
    parser = argparse.ArgumentParser(description="Plan de tesorería de grupo y sensibilidad de empresa (escenario mecánico sobre V2).")
    parser.add_argument("--features-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--out-dir", type=Path, help="por defecto <features-dir>/advisor")
    parser.add_argument("--month", help="primer día del mes (YYYY-MM-01); por defecto el último cierre del panel")
    parser.add_argument("--group", metavar="GROUP_xxxx", help="imprime el plan de ese grupo y no publica")
    parser.add_argument("--company", metavar="COMP_xxxx", help="imprime la sensibilidad de esa empresa y no publica")
    parser.add_argument("--levers",
                        help="palancas de grupo separadas por coma; D1,P por defecto, D1,P,O añade la asunción de pagos operativos (D48)")
    parser.add_argument("--production-safe", action="store_true",
                        help="perfil estricto para UI: D1,P,O con actividad mínima, mejora a k=1, protección de tramo y de la peor filial")
    parser.add_argument("--llm", action="store_true",
                        help="parafrasear narrativa de --group/--company (requiere API key); no aplica al run completo")
    args = parser.parse_args()
    config = default_config(month=args.month, production_safe=args.production_safe) if args.month else \
        default_config(production_safe=args.production_safe)
    raw_levers = args.levers or ("D1,P,O" if args.production_safe else "D1,P")
    levers = tuple(x.strip() for x in raw_levers.split(",") if x.strip())
    if levers != config.levers:
        config = replace(config, levers=levers)
    completer = None
    if args.llm:
        completer = completer_from_env()
        if completer is None:
            raise SystemExit("--llm requiere XRAY_LLM_API_KEY u OPENAI_API_KEY")
        if args.group is None and args.company is None:
            raise SystemExit("--llm solo con --group o --company (el run completo sigue siendo plantilla)")
    if args.group is None and args.company is None:
        out_dir = args.out_dir or (args.features_dir / "advisor_production" if args.production_safe else None)
        run(args.features_dir, out_dir, config, args.month)
        return
    if args.out_dir is not None:
        check_out_dir(resolve_out_dir(args.features_dir, args.out_dir), args.features_dir)
    inputs = load_inputs(args.features_dir, config)
    month = resolve_month(inputs, args.month, config)
    if args.group is not None:
        show_group(inputs, args.group, month, config, completer=completer)
    if args.company is not None:
        show_company(inputs, args.company, month, config, completer=completer)


if __name__ == "__main__":
    main()
