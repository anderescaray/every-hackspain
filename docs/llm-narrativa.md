# Narrativa LLM anclada (resúmenes deterministas)

**Estado:** implementado 20-09-2026. El producto funciona **sin** API key (solo plantillas).

## Principio

1. El pipeline calcula hechos (score, trayectoria, Cash Truth, drivers…).
2. Una **plantilla** redacta assessment/summary (o el plan/sensibilidad del advisor).
3. Un LLM **opcional** solo parafrasea; `validate_grounding` exige que todo número e id exista en el JSON.
4. Si falla el anclaje o la red → se sirve la plantilla.

El LLM nunca calcula.

## Empresa (ficha / export)

Las **viñetas que van debajo del Health Score** son el campo `summary` del contrato; el frontend
las pinta en `SummaryBullets` (`components/insights/CompanyInsights.tsx`), una por línea.

| Pieza | Dónde |
|---|---|
| Hechos + plantilla + `company_brief()` | `src/xray/product/company_brief.py` |
| **Viñetas desde el informe completo** (`compose_summary`) | mismo fichero, sección final |
| Uso en export | `frontend_export.company_detail` / `run(..., completer=, llm_companies=)` |
| CLI | `scripts/09_export_frontend.py --llm [--llm-companies COMP_0764,... \| demo]` |

Sin `--llm`, assessment/summary son siempre plantilla (deterministas, anclados).

### Los dos modos de LLM (20-09-2026)

1. **Paráfrasis** (`company_brief(..., completer=...)`): reescribe la plantilla sin cambiar hechos.
   Sigue existiendo y con tests, pero **el export ya no la usa** para el resumen.
2. **Redacción desde el informe** (`compose_summary(detail, template, completer)`): **es la que
   alimenta la ficha**. Recibe el informe entero de la empresa —Health Score y dimensiones,
   trayectoria, historia mensual, factores con su impacto en puntos, Origen de la caja con sus
   importes y la confianza— y escribe 3–4 viñetas eligiendo qué contar. Una llamada por empresa.
   `--llm` sin `--llm-companies` cubre **todas** las empresas exportadas (`demo` acota a las seis
   de demostración). El manifiesto publica `llm_summaries_written` frente a
   `llm_companies_attempted`: la diferencia son las que cayeron a plantilla.

Instrucciones fijas: `REPORT_SYSTEM_PROMPT` (`company_brief.py`). El assessment del hero sigue
siendo plantilla: es una línea corta y no justificaba una segunda llamada.

### Qué se le permite escribir

`validate_grounding` se aplica al texto contra el informe. Dos permisos acotados, en `_anchor_doc`,
porque la regla literal obligaba a escribir mal en castellano:

- **Magnitud sin signo**: «resta 4,3 puntos» con −4,3 en el informe. La dirección la lleva el verbo
  y la regla 6 del prompt obliga a que concuerde con el signo o con `direction`/`trajectory`.
- **Redondeo de presentación**: euros enteros, miles o millones de un importe del informe — las
  mismas formas que ya pinta `money()` en la ficha. 80.000 EUR para 79.979,49 pasa; 85.000 no.

Todo lo demás lo tumba: una variación calculada, un porcentaje deducido o una cifra recordada
descartan la respuesta y esa empresa se queda con su plantilla. El LLM nunca calcula.

### Aviso operativo

`frontend/public/generated/` es reproducible y está fuera de git, así que **se queda atrás cuando
cambia el redactor**. En septiembre pasó: `render_summary` pasó de un párrafo que empezaba por
«Health Score N: …» a viñetas, no se regeneró el export, y como `SummaryBullets` filtra justo esa
línea, el cuadro bajo el score salía **vacío** en las 1.161 fichas. Tras tocar `company_brief.py` o
`frontend_export.py` hay que ejecutar `scripts/09_export_frontend.py` y revisar una ficha.

## Advisor (WP6)

| Pieza | Dónde |
|---|---|
| Protocolo + `llm_render` / `grounded_paraphrase` | `src/xray/group_advisor/llm.py` |
| Proveedor OpenAI-compatible (temp 0) | `src/xray/group_advisor/llm_providers.py` |
| CLI | `scripts/08_treasury_advisor.py --llm --group GROUP_xxxx` (o `--company`) |

`--llm` en el run completo del advisor **no** está permitido (coste); solo con `--group` / `--company`.

## Proveedor y clave (20-09-2026)

`completer_from_env()` elige proveedor solo. **Sin ninguna clave devuelve `None` y todo sigue con
plantillas**: la clave añade la redacción del LLM, no es un requisito para que la ficha funcione.

| Proveedor | Cuándo se elige | Implementación |
|---|---|---|
| **Anthropic** (SDK oficial) | hay `ANTHROPIC_API_KEY`, o `XRAY_LLM_API_KEY` empieza por `sk-ant-`, o `XRAY_LLM_PROVIDER=anthropic` | `AnthropicCompleter` |
| OpenAI-compatible (HTTP) | el resto | `OpenAICompatibleCompleter` |

Ambos en `src/xray/group_advisor/llm_providers.py`. `anthropic` es un extra opcional del
`pyproject` (`pip install -e ".[llm]"`), ya instalado en el entorno.

### Dónde va la clave

`.env` en la raíz del repo (gitignored; `_load_dotenv` lo carga y **no pisa** variables ya
exportadas). Una línea basta:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### Variables de entorno

```bash
ANTHROPIC_API_KEY=sk-ant-...     # activa el proveedor Anthropic
# XRAY_LLM_PROVIDER=openai       # fuerza proveedor cuando hay varias claves
# XRAY_LLM_MODEL=claude-haiku-4-5  # por defecto claude-opus-5
# XRAY_LLM_EFFORT=low            # low|medium|high|xhigh|max (solo Anthropic)
# XRAY_LLM_MAX_TOKENS=4000       # el razonamiento adaptativo consume parte del techo
# XRAY_LLM_TIMEOUT=30
# XRAY_LLM_API_KEY / OPENAI_API_KEY / XRAY_LLM_BASE_URL   # rama OpenAI-compatible
```

Detalles que costaron tiempo y conviene no volver a descubrir: `temperature` **no se envía** al
proveedor Anthropic (está retirado en Opus 5 y devuelve 400); el razonamiento adaptativo consume
parte de `max_tokens`, de ahí el techo de 4.000 para cuatro viñetas; y `effort` va en `low` porque
la tarea es redactar con hechos ya calculados, no razonar.

### Coste de un run completo

El informe podado que viaja en cada prompt tiene ~4.300 caracteres de mediana (p95 4.863), es
decir **~1,2 M tokens de entrada** para las 1.161 empresas, una llamada por empresa. Con
`claude-opus-5` (5 $/MTok de entrada) salen unos **6-10 $** contando salida y razonamiento;
`claude-haiku-4-5` lo deja en torno a 1-2 $. `--llm-companies demo` limita a seis empresas.

## Ejemplos

```bash
# Solo plantillas (default, recomendado para regenerar generated/)
python3 -X utf8 scripts/09_export_frontend.py

# Viñetas redactadas por el LLM para TODAS las empresas (1 llamada por empresa)
python3 -X utf8 scripts/09_export_frontend.py --llm

# Acotar el gasto: solo las seis de demostración, o una lista explícita
python3 -X utf8 scripts/09_export_frontend.py --llm --llm-companies demo
python3 -X utf8 scripts/09_export_frontend.py --llm --llm-companies COMP_0764,COMP_0001

# Advisor: narrativa de un grupo con LLM
python3 -X utf8 scripts/08_treasury_advisor.py --llm --group GROUP_0067
```

## Tests

`tests/test_company_brief.py` (incluye `compose_summary`: anclaje, magnitudes, redondeo de
presentación y fallback por red, formato o cifra inventada), `tests/test_group_advisor_llm.py`.
Sin red; HTTP mockeado.
