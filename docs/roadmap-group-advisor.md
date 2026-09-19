# Roadmap — `treasury_advisor_v1` (plan de grupo + sensibilidad de empresa)

**Estado (19-09-2026): WP1, WP2, WP3, WP4, WP5 (a: pipeline; b: pulido de narrativa) y WP7 ejecutados** por agentes paralelos según este plan; 422 tests en la suite completa; pipeline real publicado en `data/processed/advisor/`. Desviaciones y resultados por WP en [decisiones.md](./decisiones.md) §18 (GA-01 WP1, GA-02 WP2, GA-03 WP4, GA-04 WP3, GA-05 WP7, GA-06 WP5a, GA-07 WP5b). **WP6 (LLM real) no se ha ejecutado**: falta decidir proveedor; la interfaz `Completer` y el fallback a plantilla están listos en `llm.py`. Los prompts de abajo se conservan como registro de cómo se repartió el trabajo.

Plan de ejecución de la especificación [group-optimization.md](./group-optimization.md). Está pensado para repartirse entre agentes que **no comparten contexto**: cada paquete de trabajo (WP) lleva un prompt autosuficiente, sus ficheros propios (dos WPs nunca escriben el mismo fichero), su contrato de entrada/salida y su definición de hecho. Si lo ejecuta un solo agente, el orden es WP1 → WP2 → WP4 → WP3 → WP7 → WP5.

```
WP0  Spec + roadmap (hecho, 19-09)
 ├── WP1  Estado (config, FX, estado por filial)        state.py, config.py, fx.py        [paralelo]
 ├── WP2  Motor: primitivas + nivel contrafactual        counterfactual.py                 [paralelo]
 └── WP4  Narrativa determinista (plan + sensibilidad)   narrative.py, qa.py, grounding.py, llm.py   [paralelo]
      ├── WP3  Objetivo + optimizador de grupo           objective.py, optimizer.py, plan.py   ← WP1 + WP2
      └── WP7  Sensibilidad de empresa                   sensitivity.py                        ← WP1 + WP2   [paralelo con WP3]
            └── WP5  Pipeline, informe, docs, demo       pipeline.py, scripts/08_*, docs       ← WP3 + WP4 + WP7
                  └── WP6 (opcional)  Adaptador LLM real                                       ← WP4 + WP5
```

## Reglas comunes a todos los WPs

1. Leer antes: `CLAUDE.md` (raíz), `docs/group-optimization.md` completo, `docs/scoring-v2.md` §1–§4 y el código `src/xray/score_v2/signals.py`, `level.py`, `core.py`.
2. **No modificar** `src/xray/score_v2/`, `src/xray/score/`, `src/xray/features/`, `src/xray/clean/` ni sus artefactos. Si hace falta algo de ahí, importarlo; si no existe, recalcularlo en el paquete nuevo y anotarlo.
3. Paquete nuevo `src/xray/group_advisor/`. Salida solo en `data/processed/advisor/`. Nunca escribir en `data/raw/`, `scores/` ni `scores_v2/`.
4. Python 3.14, pandas 3, numpy, pyarrow. Sin dependencias nuevas. dtypes numpy por defecto (no `dtype_backend="pyarrow"`).
5. Ejecutar scripts con `python -X utf8`. Tests: `python -W error -m pytest -q tests/test_group_advisor_*.py` deben pasar; la suite completa (`python -W error -m pytest -q`) no puede romperse.
6. `data/` no está en git y puede no existir en el clon: los tests unitarios usan fixtures sintéticas; los que leen `data/processed/` se marcan `@pytest.mark.skipif(not PROCESSED_DIR.exists(), ...)`.
7. Determinismo: sin aleatoriedad, iteraciones ordenadas por `company_id`; misma entrada → misma salida.
8. No inventar cifras ni "salud" por falta de datos: NaN y motivo explícito.
9. **FX:** nunca usar `transactions.exchange_rate`. Solo la tabla fija `AdvisorConfig.fx_rates_to_eur`, y solo para importes (spec §7).
10. Registrar cualquier desviación de la spec en `docs/decisiones.md` §18 con IDs `GA-xx` (la sección ya existe). No hacer commit ni push.
11. Estilo: código compacto, docstrings en castellano como el resto del repo, sin comentarios superfluos.

## Contratos compartidos (fijados aquí para poder paralelizar)

### `AdvisorConfig` (WP1 en `config.py`; los demás lo importan)

Campos y validaciones exactamente los de la spec §11. `fx_rates_to_eur` por defecto `None`; WP1 añade `default_fx_table()` en `fx.py` (§WP1).

### `SignalRow` (WP2 la define en `counterfactual.py`; WP1 la produce por filial; WP3/WP7 la consumen)

`dict` con claves: `level_inflow_sum`, `window_outflow_sum`, `window_debt_service_sum`, `ar_delay_w`, `ap_delay_w`, y derivadas `op_margin_w`, `debt_service_w`, `debt_without_inflow_w`. `derive(row) -> row` recalcula las tres derivadas desde las cinco base (WP2). WP1 debe producir filas cuyo `derive` reproduzca las señales de `build_signals` (invariantes de la spec §3).

### `GroupState` (WP1 produce; WP2/WP3/WP7 consumen)

```python
@dataclass(frozen=True)
class GroupState:
    group_id: str
    month: pd.Timestamp
    subsidiaries: pd.DataFrame      # una fila por company_id, ordenada e indexada por company_id
    reference_state: dict           # ref["references"][k]["state"] vigente en `month`
    consolidated_scores: dict       # {currency: score grupo-moneda V2 o None}
    evidence: dict                  # {evidence_id: {source, company_id, field, month, value}}
    inputs_sha256: dict
```

Columnas obligatorias de `subsidiaries` (float salvo indicación; NaN cuando no observado):

| Columna | Origen |
|---|---|
| `currency` (str), `group_id` (str) | features |
| `level`, `score`, `momentum_adjustment`, `level_operations`, `level_debt`, `level_collections`, `level_payments`, `level_coverage`, `score_status` (str), `score_reason` (str) | `scores_v2/company_monthly_scores.parquet` |
| `op_margin_w`, `debt_service_w`, `debt_without_inflow_w` (bool), `ar_delay_w`, `ap_delay_w`, `ar_delay_count_w`, `ap_delay_count_w`, `level_inflow_sum` | `xray.score_v2.signals.build_signals` sobre el panel completo, fila del mes |
| `window_outflow_sum`, `window_debt_service_sum` | sumas de `tx_outflow` y de `debt_principal_paid + debt_interest_paid` en los meses con `month_quality_ok` de la ventana t−5..t, calendario natural completo (WP1 con `xray.score_v2.signals.month_quality`) |
| `monthly_debt_service` | `window_debt_service_sum / horizon_months` |
| `reconstructed_cash`, `cash_reliable` (bool), `runway_months` | `company_currency_liquidity_context.parquet` (`reconstructed_cash` solo si `reconstruction_coverage == 1`) |
| `tx_outflow_ma3`, `inv_ap_overdue_amount`, `inv_ap_due_30_amount`, `inv_ap_due_60_amount`, `inv_ar_open_amount` | features |
| `optimizable` (bool) | `level.notna()` |
| `tramo` (str) | `red` <40, `amber` 40–70, `green` ≥70 (`tramo_bounds`), `none` si sin nivel |

`GroupState.signal_row(company_id) -> SignalRow` (método de WP1) devuelve la fila en el formato de WP2.

### `Action` y `ActionEffect` (WP2 define; WP3 usa)

```python
@dataclass(frozen=True)
class Action:
    lever: str          # "D1" | "P"
    donor: str; recipient: str
    donor_currency: str; recipient_currency: str
    fraction: float
    amount_recipient_ccy: float     # D1: horizon*fraction*monthly_debt_service_b ; P: fraction*gap_b
    amount_donor_ccy: float         # convertido con la tabla FX (igual si misma moneda)
    fx_applied: float | None        # tipo aplicado c_b -> c_a, None si misma moneda
    psi: float | None               # solo P

@dataclass(frozen=True)
class ActionEffect:
    k: int
    donor_level_before: float; donor_level_after: float
    recipient_level_before: float; recipient_level_after: float
    donor_components_after: dict; recipient_components_after: dict
    donor_signal_before: float; donor_signal_after: float          # la señal tocada
    recipient_signal_before: float; recipient_signal_after: float
    recipient_component_dropped: bool
    donor_hits_zero_inflow_indicator: bool
```

### JSON de salida (WP3 y WP7 producen; WP4 consume)

Exactamente los esquemas de la spec §8.1 y §8.2. WP4 escribe fixtures de ejemplo en `tests/fixtures/` (`advisor_plan_example.json`, `advisor_plan_no_levers.json`, `advisor_plan_single.json`, `advisor_sensitivity_example.json`, `advisor_sensitivity_not_scored.json`). WP3 y WP7 escriben cada uno un test de esquema que compara claves y tipos de su salida con el fixture correspondiente; si el fixture aún no existe cuando arrancan, lo crean siguiendo la spec y lo anotan en decisiones §18.

---

## WP1 · Estado del grupo, configuración y FX

**Ficheros:** `src/xray/group_advisor/__init__.py`, `config.py`, `fx.py`, `state.py`, `tests/test_group_advisor_state.py`, `tests/advisor_fixtures.py` (builder `make_group_state(...)`).

**Depende de:** nada.

**Prompt para el agente:**

> Implementa la base del paquete `src/xray/group_advisor/` (WP1 del roadmap `docs/roadmap-group-advisor.md`). Lee antes `CLAUDE.md`, `docs/group-optimization.md` (sobre todo §3, §5.2, §7 y §11) y `src/xray/score_v2/{signals,core,pipeline}.py`. **`config.py`:** `AdvisorConfig` con los campos y validaciones de la spec §11. **`fx.py`:** `default_fx_table() -> dict` con unidades de moneda por 1 EUR para todas las monedas de `companies.currency` y `banking_products.currency` del dataset (lista en la spec §1; si necesitas la lista exacta léela de `data_summary/` o de cleaned); toma los valores de una fuente pública de tipos de referencia a fecha 2026-09-01 si tienes acceso y anótala en `fx_source`/`fx_asof`; si no, usa valores aproximados razonables y marca `fx_source="approximate"` — en ambos casos escribe la tabla como constante en el módulo con su fuente en el docstring. `convert(amount, from_ccy, to_ccy, table) -> (amount, rate_applied)`; error claro si falta una moneda. **`state.py`:** `load_inputs(features_dir=PROCESSED_DIR, config)` lee `company_monthly_features.parquet` verificando su hash contra `_feature_manifest.json` como hace `xray.score.pipeline.read_panel`, `scores_v2/company_monthly_scores.parquet`, `scores_v2/group_currency_monthly_scores.parquet`, `company_currency_liquidity_context.parquet` y `scores_v2/_company_score_reference.json`; valida `config.horizon_months == reference["config"]["level_window"]`; calcula **una sola vez** `build_signals(panel, ScoreV2Config(**reference["config"]))` y las sumas de ventana `window_outflow_sum` / `window_debt_service_sum` (meses con `month_quality`, rolling de 6 meses naturales por empresa-moneda sobre el calendario completo, igual que `build_signals` reindexa) y lo cachea en `AdvisorInputs` junto con los sha256 de cada fichero. `reference_state_for(reference, month)` con la regla de `score_panel` (mayor `effective_from ≤ month`; error si `max_observed_month ≥ month`). `build_group_state(inputs, group_id, month, config) -> GroupState` con las columnas exactas de "Contratos compartidos", método `signal_row(company_id)` y `evidence` determinista (ids `ev_0001`… por orden de `company_id` y campo) para caja, runway, AP, AR abierto, sumas de ventana y cuota mensual. `iter_group_states(inputs, month, config)` ordenado por `group_id`. Comprueba los invariantes de la spec §3 (`op_margin_w` frente a `(I−O)/(I+O)` y `debt_service_w` frente a `S/I`); en fixtures deben cumplirse; sobre datos reales, si fallan en alguna fila, registra el hallazgo en `docs/decisiones.md` §18 (`GA-01`) con conteos y usa las sumas directas como verdad. **`tests/advisor_fixtures.py`:** `make_group_state(rows: list[dict], month="2026-08-01", reference_state=None, config=None) -> GroupState` que rellena NaN por defecto, calcula derivadas y `tramo`, y usa por defecto la referencia de anclas puras (`xray.score_v2.level.fit_reference` sobre un DataFrame vacío). **Tests:** columnas y orden; `tramo` en los cortes 40/70; `cash_reliable` falso ⇒ caja NaN; `reference_state_for` correcto y rechazo de futuro; invariantes en una fixture sintética construida con `build_signals`; `convert` ida y vuelta y error por moneda ausente; validaciones de `AdvisorConfig` (concavidad, FX con EUR=1); test sobre datos reales (skip sin `data/processed/`): para agosto 2026 el `level` del estado coincide con `scores_v2` en todas las filas y los invariantes se cumplen en ≥99% o quedan documentados. No modifiques nada fuera de `src/xray/group_advisor/`, `tests/` y `docs/decisiones.md`. Ejecuta `python -W error -m pytest -q tests/test_group_advisor_state.py` y la suite completa. No hagas commit.

**Hecho cuando:** tests pasan; el estado de `GROUP_0064` para 2026-08-01 se construye y sus niveles coinciden con `scores_v2`.

---

## WP2 · Motor: primitivas y nivel contrafactual

**Ficheros:** `src/xray/group_advisor/counterfactual.py`, `tests/test_group_advisor_counterfactual.py`.

**Depende de:** nada (usa `xray.score_v2.level.score_level` y la referencia de anclas puras en tests). No importa de `state.py`/`config.py` (pueden no existir aún): recibe `horizon` y `reference_state` como argumentos.

**Prompt para el agente:**

> Implementa `src/xray/group_advisor/counterfactual.py` (WP2 del roadmap `docs/roadmap-group-advisor.md`). Lee `CLAUDE.md`, `docs/group-optimization.md` §2, §4, §5.1 y §12, y `src/xray/score_v2/level.py` y `signals.py`. Define `SignalRow` (dict, claves en el roadmap) y `derive(row) -> row` que recalcula `op_margin_w = (I−O)/(I+O)` (NaN si `I+O == 0`), `debt_service_w = S/I` (NaN si `I == 0`) y `debt_without_inflow_w = (I == 0 and S > 0)`. Implementa las seis **primitivas** de la spec §4 como funciones puras `name(row, param, k, horizon) -> row` que devuelven una copia derivada y nunca mutan: `inflow_scale`, `outflow_scale`, `debt_service_scale`, `debt_service_add` (error si dejaría `S_k < 0`), `ap_delay_scale`, `ar_delay_scale`; valida rangos de parámetros y `1 ≤ k ≤ horizon`. Implementa `level_from_signals(rows: dict[str, SignalRow], reference_state) -> pd.DataFrame` (índice = ids; columnas `level`, `level_operations`, `level_debt`, `level_collections`, `level_payments`, `level_coverage`, `level_components_available`) que construye el DataFrame con las columnas que `score_level` espera (`op_margin_w`, `debt_service_w`, `debt_without_inflow_w`, `ar_delay_w`, `ap_delay_w`) y llama a `xray.score_v2.level.score_level`. Define las dataclasses `Action` y `ActionEffect` del roadmap. Implementa las **composiciones de grupo**: `apply_d1(row_a, row_b, phi, k, horizon, monthly_service_b_in_donor_ccy)` y `apply_p(row_b, psi, k, horizon)`, y `evaluate_action(rows, reference_state, action: Action, k, horizon, monthly_service_b_in_donor_ccy=None) -> ActionEffect` que compone, recalcula niveles y detecta `recipient_component_dropped` (componente deuda pasa de disponible a no disponible) y `donor_hits_zero_inflow_indicator`. Tests con la referencia de anclas puras (`fit_reference` sobre DataFrame vacío): `derive` reproduce señales de una fila construida a mano; cada primitiva con parámetro 0 es identidad; `debt_service_scale(−1)` con `k=horizon` ⇒ `debt_service_w = 0` y `level_debt = 100`; monotonía en parámetro y en `k` (dirección buena ⇒ nivel no decreciente; `debt_service_add(+)` ⇒ no creciente); `outflow_scale(−r)` sube margen y no toca `debt_service_w`; `inflow_scale(+r)` sube margen **y** baja `debt_service_w`; caso `I→0, S>0` ⇒ indicador activo y nota 0; caso `I=0, S→0` ⇒ componente eliminado y nivel renormalizado (no 100 ni 0 fantasma); `apply_p` no toca al donante; `apply_p(ψ=1, k=horizon)` ⇒ `ap_delay_w = 0` y `level_payments = 100`; `k=1` efecto menor que `k=horizon`; entradas no mutadas; D1 equivale a sus dos primitivas; test opcional sobre datos reales (skip sin `data/processed/`): 20 empresas de agosto 2026, filas desde `build_signals` + sumas de ventana, `level_from_signals` reproduce `scores_v2.level` con tolerancia 1e-6. No modifiques `score_v2`. Ejecuta `python -W error -m pytest -q tests/test_group_advisor_counterfactual.py`. No hagas commit.

**Hecho cuando:** tests pasan; la reproducción del nivel V2 real coincide.

---

## WP4 · Narrativa determinista, Q&A y validador de anclaje

**Ficheros:** `src/xray/group_advisor/narrative.py`, `qa.py`, `grounding.py`, `llm.py`, `tests/fixtures/advisor_*.json` (cinco), `tests/test_group_advisor_narrative.py`.

**Depende de:** solo de los esquemas JSON de la spec §8.

**Prompt para el agente:**

> Implementa la capa de narrativa de `src/xray/group_advisor/` (WP4 del roadmap `docs/roadmap-group-advisor.md`). Lee `CLAUDE.md` y `docs/group-optimization.md` §0, §8, §9, §10 y §13. Primero escribe cinco fixtures JSON en `tests/fixtures/` que cumplan **exactamente** los esquemas de la spec §8.1 y §8.2: un plan con dos pasos (D1 y P, `effects.k1` y `effects.k6` completos, `binding_constraints`, `rejected_alternatives`, `certificate`, `evidence`, y al menos una acción **cruzada de moneda** con `fx_applied` y el supuesto `fx_fixed_rate`), un `status="no_feasible_levers"` con motivos por filial, un `status="single_subsidiary"`, una sensibilidad completa (cinco palancas: tres disponibles con `grid`, `slope_now`, `to_next_tramo` alcanzable y no alcanzable, `feasibility`; dos no disponibles con `reason`; `group_context.has_group_plan=true`) y una `status="not_scored"`. Cifras verosímiles y coherentes (G después ≥ antes; totales = último paso). Implementa `narrative.py`: `render_plan(plan, fmt="markdown"|"text")` y `render_sensitivity(sens, fmt)` con las secciones de la spec §9.1 en su orden, en castellano, con las frases de negocio literales de la spec, una única `fmt_num` (miles «.», decimal «,», código de moneda), el aviso «escenario mecánico bajo supuestos explícitos» en el resumen, importes convertidos siempre acompañados del original y del tipo aplicado, plantilla por `status` cuando no hay plan/sensibilidad. Implementa `grounding.py`: `extract_numbers(text)` (reconoce «1.234,5», «42 %», «−0,80», «7.020 EUR») y `validate_grounding(text, doc)` que comprueba que cada número aparece en el JSON (búsqueda recursiva de valores numéricos; comparación tras redondear ambos a 1 decimal; porcentajes también como fracción; ids `COMP_xxxx`/`GROUP_xxxx` y nombres de palanca deben existir en el JSON); devuelve `GroundingResult(ok, unmatched_numbers, unmatched_ids)`. Implementa `qa.py` con `answer(doc, intent, **args)` para las nueve intenciones de §9.2 leyendo solo las rutas indicadas, y la frase fija para intención desconocida o dato inexistente. Implementa `llm.py`: `class Completer(Protocol): def complete(self, system: str, user: str) -> str`, `SYSTEM_PROMPT` con las reglas cerradas de §9.3, `llm_render(doc, completer, mode="paraphrase"|"qa", question=None) -> NarrativeResult(text, source, grounding, fallback)` que valida con `validate_grounding` y **cae a plantilla si falla**. Sin proveedor real ni dependencias. Tests: secciones en orden en los cinco fixtures; `validate_grounding(render_*(doc), doc).ok` en todos; un texto con cifra inventada falla; cada intención responde desde su ruta y una desconocida devuelve la frase fija; `llm_render` con un completer falso que inventa un número cae a plantilla con `fallback=True`, y con texto anclado mantiene `source="llm"`. Ejecuta `python -W error -m pytest -q tests/test_group_advisor_narrative.py`. No hagas commit.

**Hecho cuando:** tests pasan; los renders de los cinco fixtures se leen bien en consola con `python -X utf8`.

---

## WP3 · Objetivo y optimizador de grupo

**Ficheros:** `src/xray/group_advisor/objective.py`, `optimizer.py`, `plan.py`, `tests/test_group_advisor_optimizer.py`, `tests/test_group_advisor_plan_schema.py`.

**Depende de:** WP1 y WP2 mergeados.

**Prompt para el agente:**

> Implementa el optimizador de grupo de `src/xray/group_advisor/` (WP3 del roadmap `docs/roadmap-group-advisor.md`). Lee `CLAUDE.md`, `docs/group-optimization.md` §4, §5, §7, §8.1 y §12, y el código existente `src/xray/group_advisor/{config,fx,state,counterfactual}.py` y `tests/advisor_fixtures.py`. **`objective.py`:** `utility(level, config)` lineal a tramos cóncava desde `config.utility_knots` (validar concavidad), `group_utility(levels, weights, config)` normalizada a 0–100 (`/ U(100)`), pesos `equal` o `size` (`I + O`), `tramo(level, config)`. **`optimizer.py`:** estado de trabajo mutable por grupo (caja disponible por donante en su moneda, fracción acumulada por `(palanca, receptora)`, `SignalRow` actual por filial); `generate_candidates(state, working, config)` aplica precondiciones y R1–R5 de la spec §5.1–§5.2: R1 con `fx.convert` cuando las monedas difieren y la tabla existe (`fx_applied`), infactible con motivo `fx_rate_unavailable` si falta la moneda; colchón `B_a` con κ, términos NaN omitidos y las cuotas asumidas convertidas a moneda del donante; donante requiere `cash_reliable`, `tx_outflow_ma3` finito y `level_inflow_sum > 0`; P exige receptora restringida por liquidez y calcula `ψ`; descarta acciones con `donor_hits_zero_inflow_indicator` o `L_a' < L_a − δ`; evalúa cada candidato con `evaluate_action` en `k=horizon` y en cada `k` de `report_k`; eficiencia `ΔG / (x_report / 10.000)` con `x_report` en `reporting_currency` (o moneda común si no hay tabla). Greedy determinista con clave `(−e, −ΔG, fx_applied is not None, x_report, donante, receptora, palanca, fracción)`, `min_gain_utility`, `max_steps`; por paso registra `binding_constraints` (`donor_buffer`, `need_fully_covered`, `donor_level_floor`, `fraction_cap`) y las `rejected_alternatives_kept` siguientes con motivo; `certificate` enumera acciones únicas y pares compatibles cuando `optimizable ≤ exhaustive_max_subsidiaries`. **`plan.py`:** ensambla el JSON exacto de la spec §8.1 (`diagnosis` con cuello de botella, `structural_flags` para `level_operations < 40`, `unexplained_ap_delays`, candidatos; `levers_evaluated` con motivo por par; `assumptions`/`limitations` literales, añadiendo `fx_fixed_rate: tabla <fx_source> a <fx_asof>` si hay acción cruzada; `evidence`; `inputs_sha256`; `reporting_currency`); `status` `single_subsidiary` / `no_feasible_levers` / `plan`. **`tests/test_group_advisor_plan_schema.py`:** compara claves y tipos, nivel a nivel, de `optimize_group` sobre fixture sintética con `tests/fixtures/advisor_plan_example.json` (si no existe aún, créalo según la spec y anótalo en decisiones §18). **Tests del optimizador:** los de la spec §12 «Objetivo y optimizador» (concavidad, filial de 30 antes que la de 90, colchón activo y reportado, R4 con dos donantes, misma moneda preferida en empate, acción cruzada convierte y añade el supuesto, sin tabla ⇒ `fx_rate_unavailable`, determinismo e invariancia al orden de filas, fixture con `greedy_gap > 0`, unipersonal y sin caja fiable, `group_utility_after` recomputable). Test sobre datos reales (skip sin `data/processed/`): `optimize_group` en `GROUP_0064` y en cinco grupos más por `group_id` ordenado, sin excepciones y con `G` no decreciente por paso. Ejecuta `python -W error -m pytest -q tests/test_group_advisor_*.py`. No hagas commit.

**Hecho cuando:** tests pasan; `optimize_group(GROUP_0064)` produce un plan que `render_plan` renderiza y `validate_grounding` acepta.

---

## WP7 · Sensibilidad de empresa

**Ficheros:** `src/xray/group_advisor/sensitivity.py`, `tests/test_group_advisor_sensitivity.py`, `tests/test_group_advisor_sensitivity_schema.py`.

**Depende de:** WP1 y WP2 mergeados. Paralelo con WP3 (ficheros disjuntos; comparte `objective.tramo` solo si WP3 ya existe, si no define la función localmente y WP5 unifica).

**Prompt para el agente:**

> Implementa la sensibilidad de empresa de `src/xray/group_advisor/` (WP7 del roadmap `docs/roadmap-group-advisor.md`). Lee `CLAUDE.md`, `docs/group-optimization.md` §4, §6, §8.2, §9.1 (frases) y §12 «Sensibilidad», y el código `src/xray/group_advisor/{config,state,counterfactual}.py`. Implementa `company_sensitivity(state: GroupState, company_id, config) -> dict` con el JSON exacto de la spec §8.2 (sin `group_context`, que rellena WP5; deja `{"has_group_plan": null}`). Para cada una de las cinco palancas de §6.1: disponibilidad con motivo; rejilla `config.sensitivity_grid` en la dirección buena evaluada con `level_from_signals` en `k=1` y `k=horizon` (nivel, score con `momentum_adjustment` del baseline, magnitud resultante, `cash_equivalent` según §6.2.1); `slope_now` por diferencia finita `config.finite_difference_eps` en `k=horizon` expresada por 1% (`level_per_pct`), por unidad natural (`level_per_unit`: por día o por unidad monetaria mensual) y por 10.000 de equivalente de caja (`level_per_10k`, `null` sin equivalente); `valid_until` = siguiente nudo en la dirección buena (abscisas de las anclas de la señal ∪ `{reference_low, reference_high}` si `empirical_active`, convertidas a magnitud según §6.2.3) y `slope_after` por diferencia finita justo después del nudo; `to_next_tramo` por bisección en `r ∈ [0, r_max]` con `config.bisection_tol` (objetivo = siguiente `tramo_bounds` por encima del nivel; `reachable=false` si `L(r_max) < objetivo`); `feasibility` para `ap_on_time` según §6.2.5 con el colchón `B_i = max(κ·(tx_outflow_ma3 + monthly_debt_service), D30 + D60)`; `ranking.by_pct` y `ranking.by_cash`; `structural_note` si `level_operations < 40`; `assumptions`, `limitations`, `evidence`. `status="not_scored"` con `score_reason` si la empresa no tiene nivel. Función `iter_company_sensitivities(inputs, month, config)` ordenada por `company_id`. **Tests:** pendiente coincide con `(L(r+ε) − L(r))/ε`; `valid_until` es un nudo real (pendiente cambia justo después y no antes, comprobado con la referencia de anclas puras donde los nudos son las anclas); bisección devuelve el mínimo (`L(r*−tol) < objetivo ≤ L(r*)`); `reachable=false` cuando corresponde; palanca no disponible ⇒ `available=false` con motivo y no rompe el ranking; `by_cash` excluye palancas sin equivalente; `feasible_alone` según caja propia y `unknown` sin caja fiable; `raise_inflow` baja también `debt_service_w`; `not_scored` correcto; determinismo. Test de esquema contra `tests/fixtures/advisor_sensitivity_example.json` (si no existe, créalo según la spec y anótalo). Test sobre datos reales (skip sin datos): 10 empresas de agosto 2026 sin excepciones, monotonía de la rejilla. Ejecuta `python -W error -m pytest -q tests/test_group_advisor_*.py`. No hagas commit.

**Hecho cuando:** tests pasan; la sensibilidad de `COMP_0007` y `COMP_0738` se renderiza con `render_sensitivity` y pasa `validate_grounding`.

---

## WP5 · Pipeline, informe global, documentación y demo

**Ficheros:** `src/xray/group_advisor/pipeline.py`, `scripts/08_treasury_advisor.py`, `tests/test_group_advisor_pipeline.py`; actualizaciones en `docs/decisiones.md` (§18), `docs/README.md`, `README.md`, `docs/embat_pulse_mvp_propuesta_final.md` (§12, §18), `docs/product-and-demo.md`, `docs/group-optimization.md` (§15 casos), `CLAUDE.md` (bloque de relevo).

**Depende de:** WP3, WP4 y WP7.

**Prompt para el agente:**

> Cierra el módulo `treasury_advisor_v1` (WP5 del roadmap `docs/roadmap-group-advisor.md`). Lee `CLAUDE.md`, `docs/group-optimization.md` completo, `src/xray/group_advisor/` completo y `src/xray/score_v2/pipeline.py` como modelo de publicación. Implementa `pipeline.py` con `run(features_dir=PROCESSED_DIR, out_dir=None, config=None, verbose=True)`: carga entradas (WP1); itera los 250 grupos ordenados y optimiza (WP3); itera todas las empresas y calcula sensibilidad (WP7), rellenando `group_context` con el papel de la empresa en el plan de su grupo (`role` donor/recipient/none, pasos) y `feasibility.covered_by_group_plan` para `ap_on_time` cuando un paso P la cubre; renderiza narrativas (WP4) y valida su anclaje; publica con `xray.artifacts.publish_bundle` en `data/processed/advisor/` todos los ficheros de la spec §8 (`group_plans/*.json|.md`, `company_sensitivity/*.json|.md`, `advisor_steps.parquet`, `advisor_groups.parquet`, `sensitivity_levers.parquet`, `_advisor_report.json`, `_advisor_manifest.json` con hashes de entradas, código, parámetros y tabla FX). Rechaza `out_dir` que coincida con `scores/`, `scores_v2/` o `cleaned`. El informe global contiene lo listado en la spec §8 más la tasa de fallos del validador de anclaje (debe ser 0) y `limitations` literal de §10. Escribe `scripts/08_treasury_advisor.py` (argparse: `--features-dir`, `--out-dir`, `--month`, `--group`, `--company`; los dos últimos imprimen la narrativa en consola). Ejecuta el pipeline completo y anota resultados reales en `docs/decisiones.md` §18 (`GA-xx`): cobertura por `status`, motivos, distribución de `ΔG`, filiales que cambian de tramo, caja comprometida, `greedy_gap > 0`, cobertura de sensibilidad, palanca top por tramo, y todo lo que no funciona o queda sin palancas y por qué. Elige casos demo reales y documéntalos en `docs/group-optimization.md` §15 «Casos ilustrativos»: un grupo con D1 eficaz, uno con P, uno «sin palancas» honesto, y dos empresas (una que alcanza el siguiente tramo con una palanca de tesorería, otra cuyo componente que arrastra es estructural). Actualiza `embat_pulse_mvp_propuesta_final.md` §12 y §18 (vista de grupo = «escenario mecánico intragrupo» con supuestos en pantalla; bloque «Qué mueve tu nivel» en la ficha; copiloto con plantillas y LLM opcional con validador), `product-and-demo.md` (pantallas y endpoints de la spec §13), `docs/README.md` y `README.md` (estado, comando 08, flujo), y añade a `CLAUDE.md` un bloque «Relevo tras el advisor» con lo imprescindible. Tests de pipeline: publicación en directorio temporal con fixtures, manifiesto con hashes, no escribe fuera de `out_dir`, `--group` y `--company` funcionan, `group_context` coherente con los pasos del plan. Suite completa con `-W error` verde. No hagas commit ni push.

**Hecho cuando:** `python -X utf8 scripts/08_treasury_advisor.py` publica planes y sensibilidades; el informe global existe con 0 fallos de anclaje; docs actualizados; suite verde.

---

## WP6 (opcional) · Adaptador LLM real

**Ficheros:** `src/xray/group_advisor/llm_providers.py`, `tests/test_group_advisor_llm.py` (con completer falso; sin llamadas de red en tests).

**Depende de:** WP4 y WP5; de una decisión de proveedor y clave (no tomada).

**Prompt (resumen):** implementar un `Completer` para el proveedor elegido leyendo la clave de una variable de entorno, temperatura 0, `max_tokens` acotado, timeout; nunca registrar la clave ni el prompt completo en logs; `llm_render` sigue siendo la única entrada y el fallback a plantilla se mantiene. Añadir a `scripts/08_treasury_advisor.py` la opción `--llm`, activa solo si la variable existe. Documentar en decisiones §18 la tasa de fallback observada.

---

## Variante opcional posterior (no es un WP; requiere decisión)

Panel `company_consolidated` con todas las cuentas convertidas a la tabla FX fija y V2 `--panel company_consolidated` como artefacto separado, para medir cuánta cobertura ganan las 299 empresas multimoneda y los 42 grupos. No sustituye al panel primario ni al candidato del leaderboard; reabre D07 y debe registrarse como decisión nueva.

## Criterios de aceptación del conjunto

- Para los 250 grupos y todas las empresas puntuadas hay una salida con `status` y motivos; ninguna ausencia de datos se convierte en "sin problemas".
- Cada JSON es reproducible byte a byte (salvo `generated_at`) desde los mismos artefactos.
- La narrativa de cada plan y de cada sensibilidad pasa el validador de anclaje.
- `scores_v2/` y `scores/` intactos (hashes iguales antes y después).
- Importes convertidos siempre con original y tipo aplicado; `transactions.exchange_rate` no se usa en ningún sitio del paquete.
- Documentación actualizada y decisiones §18 con resultados reales y límites.
- Vocabulario: «escenario mecánico bajo supuestos explícitos»; las palancas de negocio son sensibilidad, no recomendación.
