# Narrativa LLM anclada (resúmenes deterministas)

**Estado:** implementado 20-09-2026. El producto funciona **sin** API key (solo plantillas).

## Principio

1. El pipeline calcula hechos (score, trayectoria, Cash Truth, drivers…).
2. Una **plantilla** redacta assessment/summary (o el plan/sensibilidad del advisor).
3. Un LLM **opcional** solo parafrasea; `validate_grounding` exige que todo número e id exista en el JSON.
4. Si falla el anclaje o la red → se sirve la plantilla.

El LLM nunca calcula.

## Empresa (ficha / export)

| Pieza | Dónde |
|---|---|
| Hechos + plantilla + `company_brief()` | `src/xray/product/company_brief.py` |
| Uso en export | `frontend_export.company_detail` / `run(..., completer=, llm_companies=)` |
| CLI | `scripts/09_export_frontend.py --llm [--llm-companies COMP_0764,...\|all]` |

Sin `--llm`, assessment/summary son siempre plantilla (deterministas, anclados).

## Advisor (WP6)

| Pieza | Dónde |
|---|---|
| Protocolo + `llm_render` / `grounded_paraphrase` | `src/xray/group_advisor/llm.py` |
| Proveedor OpenAI-compatible (temp 0) | `src/xray/group_advisor/llm_providers.py` |
| CLI | `scripts/08_treasury_advisor.py --llm --group GROUP_xxxx` (o `--company`) |

`--llm` en el run completo del advisor **no** está permitido (coste); solo con `--group` / `--company`.

## Variables de entorno

Preferible en `.env` (gitignored); `completer_from_env()` lo carga solo si la variable no está ya exportada:

```bash
# .env (no commitear)
XRAY_LLM_API_KEY=sk-...
# opcionalmente también:
# OPENAI_API_KEY=sk-...
# XRAY_LLM_BASE_URL=https://api.openai.com/v1
# XRAY_LLM_MODEL=gpt-4o-mini
# XRAY_LLM_TIMEOUT=30
# XRAY_LLM_MAX_TOKENS=800
```

O exportar en la shell:

```bash
export XRAY_LLM_API_KEY=...          # o OPENAI_API_KEY
export XRAY_LLM_BASE_URL=https://api.openai.com/v1   # opcional (gateways compatibles)
export XRAY_LLM_MODEL=gpt-4o-mini    # opcional
```

## Ejemplos

```bash
# Solo plantillas (default, recomendado para regenerar generated/)
python3 -X utf8 scripts/09_export_frontend.py

# Parafrasear empresas demo
python3 -X utf8 scripts/09_export_frontend.py --llm

# Advisor: narrativa de un grupo con LLM
python3 -X utf8 scripts/08_treasury_advisor.py --llm --group GROUP_0067
```

## Tests

`tests/test_company_brief.py`, `tests/test_group_advisor_llm.py` (sin red; HTTP mockeado).
