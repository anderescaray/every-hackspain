# Advisor — optimización de grupo y sensibilidad de empresa (`treasury_advisor_v1`)

**Estado: implementado el 19-09-2026 en `src/xray/group_advisor/` (WP1–WP5 del [roadmap](./roadmap-group-advisor.md)); ejecutado sobre los datos D32 con `python -X utf8 scripts/08_treasury_advisor.py` → `data/processed/advisor/`.** Resultados, desviaciones y decisiones de implementación en [decisiones.md](./decisiones.md) §18 (GA-00 a GA-07; cifras vigentes en GA-06). Casos reales en §15. Este documento sigue siendo el contrato: fórmulas, palancas, restricciones, objetivo, algoritmos, salidas JSON y reglas de narrativa; donde la implementación se apartó de él, lo dice GA-xx y prevalece el código.

Nota D32: tras la especificación, el pipeline de features pasó a convertir todas las monedas a EUR con tipo fijo (`src/xray/fx.py`), de modo que el panel primario es 100 % EUR. La restricción de moneda R1 y la tabla FX del advisor (§7) quedan operativas pero sin efecto sobre este dataset (`fx_rate_unavailable` = 0 acciones).

## 0. Qué es y qué no es

Un **motor determinista** con dos ámbitos y una sola mecánica:

| Ámbito | Pregunta que responde | Unidad | Cuándo se muestra |
|---|---|---|---|
| **Sensibilidad de empresa** (`company_sensitivity_v1`) | *"¿Qué magnitudes, con el menor cambio, mueven más mi nivel V2? ¿Cuánto haría falta para cambiar de tramo?"* | empresa × mes | Siempre, en la ficha de cada empresa puntuada |
| **Plan de grupo** (`group_treasury_advisor_v1`) | *"¿Qué movimientos de tesorería intragrupo mejorarían más la salud del conjunto, cuánto, para quién, con qué evidencia y por qué no otros?"* | grupo × mes | Solo si el grupo tiene ≥2 filiales puntuadas |

Ambos valoran escenarios con **la misma función de nivel de V2** (`xray.score_v2.level.score_level` con la referencia congelada del mes) aplicada a **perturbaciones primitivas** de las señales de ventana (§4). La vista de empresa es *sensibilidad* (dónde está la pendiente); la de grupo es *acciones coordinadas* (requieren la decisión de otra filial). No compiten: la ficha de una filial enlaza su papel en el plan de grupo y el plan enlaza cada ficha.

**No es** una instrucción ejecutable ni una predicción. Cada salida se etiqueta **"escenario mecánico bajo supuestos explícitos"**: no incorpora fiscalidad, restricciones legales, covenants, precio del préstamo intragrupo ni reacción de clientes/proveedores, porque no están en los datos. Dice qué haría el nivel V2 si los flujos cambiaran como se describe y se sostuvieran.

**El LLM nunca calcula.** La narrativa canónica la produce un renderizador de plantillas desde el JSON del motor. Un LLM, si se conecta después, parafrasea y responde preguntas **solo** con hechos del JSON, con validador posterior; si falla, se sirve la plantilla.

Esto sustituye la reserva de `embat_pulse_mvp_propuesta_final.md` §12 («no generar “transfiere X de B a A”») por la fórmula de §11 (What-if: *"resultado mecánico bajo este escenario"*). Ese documento debe actualizarse en §12 y §18 al implementar (WP5).

## 1. Hechos que motivan el módulo (agosto 2026, V2, lectura del 19-09)

| Hecho | Cifra |
|---|---|
| Grupos con más de una filial | 179 de 250; 157 con ≥2 filiales puntuadas; 71 unipersonales |
| Dispersión intra-grupo del score (máx − mín) | mediana 36,6; 97 grupos ≥30; **47 grupos con una filial <40 y otra >70** |
| Correlación score grupo-moneda con media simple / ponderada por flujo de sus filiales | 0,73 / 0,84 → el consolidado lo domina la filial grande |
| Caja reconstruida fiable | 1.176 de 2.047 pares empresa-moneda; runway en 822; 49 con caja <0; 441 con runway <1 mes |
| Componente deuda / pagos / cobros presente | 931 / 587 / 461 empresas puntuadas |
| Monedas | 90,2% de las filas en EUR (USD 3,8%, GBP 1,7%); 1.149 empresas declaradas EUR; **299 empresas con alguna cuenta en moneda distinta a la declarada**; 42 grupos con más de una moneda declarada |
| `exchange_rate` de transacciones | ≠1 en el 4,0% de filas; **ambiguo** (USD con rate 1 y con rate ≠1; EUR con rate ≠1; máx 6.500) → no es un tipo de cambio utilizable (D07) |
| Flujo intragrupo en agosto | 530 empresas; 5.244 M nominales frente a 3.687 M de entradas operativas |

Ejemplo: `GROUP_0064` (EUR): COMP_0222 nivel 100, COMP_0007 57, COMP_0738 38 (margen 6m −0,80); consolidado grupo-moneda 51.

## 2. Lo que mueve y lo que no mueve el score V2

- **Una transferencia intragrupo, por sí sola, no mueve ningún componente de V2.** D05 excluye los flujos intragrupo del margen operativo de la filial y del consolidado. Es correcto: mover caja no crea margen.
- Lo que mueve el nivel es **qué hace la receptora con la caja**, y eso mapea a componentes:

| Palanca de grupo | Componente V2 | Peso | Evidencia |
|---|---|---:|---|
| **D1 · Asunción del servicio de deuda** | `debt_service_w` (receptora ↓, donante ↑) | 25% | `debt_principal_paid`, `debt_interest_paid`, `level_inflow_sum` |
| **P · Financiar el pago de proveedores a tiempo** | `ap_delay_w` (receptora ↓) | 15% | `inv_ap_delay_median/count`, `inv_ap_overdue_amount`, `inv_ap_due_30/60_amount`, caja reconstruida |

- **Cancelación anticipada de deuda (D2) queda descartada**: V2 mide servicio observado y una cancelación aparece como pico de principal que penaliza el nivel los seis meses de ventana aunque ahorre intereses. No reabrir sin nueva decisión.
- El **margen operativo** (45%) y el **retraso AR** (15%) no son palancas *de grupo* en esta versión (el margen no se mueve con tesorería; el coste de acelerar cobros no está en los datos). Sí aparecen en la **sensibilidad de empresa** (§6), etiquetados por tipo.
- El donante **no pierde nivel** por transferir (salida intragrupo excluida), pero **sí pierde caja**: su restricción es de liquidez, no de score. Si liquidez entra algún día como dimensión de V2 (decisiones §12 V2-01), esa restricción se convierte también en restricción de nivel sin cambiar el diseño.

## 3. Estado por filial

Para el grupo `g`, mes `t` (por defecto el último cierre del panel, agosto 2026) y cada filial `i` en su moneda declarada `c_i`:

| Símbolo | Fuente | Definición |
|---|---|---|
| `L_i`, componentes, `momentum_adjustment_i`, `score_status_i` | `scores_v2/company_monthly_scores.parquet` | Nivel V2 y notas por componente. Solo se optimizan filiales con `L_i` no nulo (`scored` o `provisional`) |
| `m_i, d_i, a_i, p_i, I_i` | `xray.score_v2.signals.build_signals(panel, ScoreV2Config(**ref["config"]))` | `op_margin_w`, `debt_service_w`, `ar_delay_w`, `ap_delay_w`, `level_inflow_sum` (ventana `H=6`, meses con calidad). Recalculadas, no leídas |
| `O_i` | panel + `month_quality` | `window_outflow_sum`: suma de `tx_outflow` en los meses con calidad de la ventana (no está en `build_signals`) |
| `S_i`; `s_i = S_i / H` | panel + `month_quality` | `window_debt_service_sum`: suma de `debt_principal_paid + debt_interest_paid` en los meses con calidad de la ventana; media mensual |
| `C_i`, `fiable_i`, `runway_i` | `company_currency_liquidity_context.parquet` | `reconstructed_cash` (solo si `reconstruction_coverage == 1`), `cash_runway_months_retrospective` |
| `O3_i` | features | `tx_outflow_ma3` |
| `V_i, D30_i, D60_i, AR_i` | features | `inv_ap_overdue_amount`, `inv_ap_due_30_amount`, `inv_ap_due_60_amount`, `inv_ar_open_amount` (NaN sin ERP) |
| `n^AP_i, n^AR_i` | `build_signals` | `ap_delay_count_w`, `ar_delay_count_w` |

Invariantes que el estado comprueba: `m_i = (I_i − O_i)/(I_i + O_i)` y `d_i = S_i / I_i` (cuando `I_i > 0`) con tolerancia relativa 1e-6. Si fallan en datos reales se documenta (GA-01) y las sumas directas son la verdad.

`estado_referencia_t` = `ref["references"][k]["state"]` con el mayor `effective_from ≤ t` (misma regla que `score_panel`). Si `max_observed_month ≥ t` se aborta: la referencia contendría el mes puntuado.

## 4. Perturbaciones primitivas (motor común)

Una **fila de señales** (`SignalRow`) tiene: `level_inflow_sum (I)`, `window_outflow_sum (O)`, `window_debt_service_sum (S)`, `ar_delay_w (a)`, `ap_delay_w (p)`, y las derivadas `op_margin_w = (I−O)/(I+O)`, `debt_service_w = S/I`, `debt_without_inflow_w = (I == 0 and S > 0)`.

Cada primitiva describe un cambio **sostenido** de los flujos mensuales; su efecto tras `k` meses (`1 ≤ k ≤ H`) es la mezcla de `(H−k)` meses antiguos y `k` nuevos en los **agregados de ventana**. Hipótesis explícita: **estacionariedad** de flujos, cuotas y número de pagos.

| Primitiva | Parámetro | Efecto en la ventana tras `k` meses |
|---|---|---|
| `inflow_scale(β)` | β ≥ −1 | `I_k = I · (1 + kβ/H)` |
| `outflow_scale(α)` | α ≥ −1 | `O_k = O · (1 + kα/H)` |
| `debt_service_scale(φ)` | φ ≥ −1 | `S_k = S · (1 + kφ/H)` |
| `debt_service_add(Δ)` | Δ mensual | `S_k = S + k·Δ` (Δ<0 no puede dejar `S_k < 0`) |
| `ap_delay_scale(ψ)` | 0 ≤ ψ ≤ 1 | `p_k = p · (1 − kψ/H)` |
| `ar_delay_scale(θ)` | 0 ≤ θ ≤ 1 | `a_k = a · (1 − kθ/H)` |

Tras aplicar, se recalculan `op_margin_w`, `debt_service_w` y `debt_without_inflow_w`. **Casos límite:** si `I_k = 0` y `S_k > 0` → indicador activo (nota de deuda 0, como V2); si `I_k = 0` y `S_k = 0` → `debt_service_w = NaN`, indicador falso → componente **no disponible** y el nivel se renormaliza (se informa `component_dropped`, nunca nota 100). Las primitivas no mutan su entrada.

Las palancas de ambos ámbitos son **composiciones** de primitivas:

| Palanca | Composición |
|---|---|
| **D1** (grupo) | `debt_service_scale(−φ)` en la receptora `b` y `debt_service_add(+φ·fx(s_b, c_b→c_a))` en la donante `a` |
| **P** (grupo) | `ap_delay_scale(ψ)` en `b`, con `ψ = x / (V_b + D30_b)` |
| `cut_outflow` (empresa, negocio) | `outflow_scale(−r)` |
| `raise_inflow` (empresa, negocio) | `inflow_scale(+r)` |
| `ap_on_time` (empresa, tesorería) | `ap_delay_scale(r)` |
| `ar_faster` (empresa, tesorería) | `ar_delay_scale(r)` |
| `debt_service_cut` (empresa, tesorería; alargar plazo / renegociar cuota) | `debt_service_scale(−r)` |

El nivel de cualquier escenario es `score_level(filas_perturbadas, estado_referencia_t)`. **Momentum no se simula**: `score' = clip(L' + momentum_adjustment(baseline), 0, 100)`. La narrativa puede decir que la trayectoria sería positiva *por construcción* si la acción se sostiene, sin cuantificarlo. Se reportan **k=1 (próximo cierre)** y **k=H (régimen)**; los rankings se hacen en k=H.

## 5. Plan de grupo (`group_treasury_advisor_v1`)

### 5.1 Palancas: precondiciones y necesidad

**D1 · Asunción del servicio de deuda de `b` por `a`.** `a` paga directamente las cuotas de la deuda externa de `b` en fracción `φ` (crédito intragrupo que no se liquida por banco en el horizonte). El servicio externo del grupo **no cambia**: se redistribuye hacia quien puede llevarlo. Precondiciones: `s_b > 0`; `fiable_a`; `O3_a` finito; `I_a > 0`; `a ≠ b`; moneda según R1. Caja comprometida (en moneda de `a`): `x_a = fx(H · φ · s_b, c_b → c_a)`. Descartada si la donante activaría el indicador de deuda sin entradas o si `L_a' < L_a − δ`.

**P · Financiar el pago de proveedores a tiempo en `b`.** Los importes pagados no cambian, solo su fecha: `m_b` y `O_b` no se tocan. Precondiciones de honestidad: `p_b` disponible (`n^AP_b ≥ 5`) y `p_b > 0`; `V_b + D30_b > 0`; `fiable_b`; **`b` restringida por liquidez**: `C_b < V_b + D30_b` **o** `runway_b < 1`. Si `b` tiene caja y aun así paga tarde, no se propone nada y el diagnóstico lo etiqueta `"retraso AP no explicado por liquidez (política de pago o higiene ERP)"`. Necesidad `gap_b = max(0, V_b + D30_b − max(0, C_b))`; importe `x_b = φ · gap_b`; `ψ = x_b / (V_b + D30_b)`; caja comprometida `x_a = fx(x_b, c_b → c_a)`.

### 5.2 Restricciones

| ID | Restricción | Detalle |
|---|---|---|
| R1 · moneda | misma moneda, o **FX fijo declarado** | Si `c_a ≠ c_b`, la acción es factible solo si ambas monedas están en `fx_rates_to_eur`; lleva `fx_applied` y el supuesto `fx_fixed_rate`. Empate de eficiencia → se prefiere misma moneda |
| R2 · colchón del donante | `C_a − Σ x_a ≥ B_a` | `B_a = max(κ·(O3_a + s_a + Σ_b φ_b·fx(s_b)), D30_a + D60_a)`, `κ = 2` meses. Términos NaN se omiten; `O3_a` NaN → donante no evaluable |
| R3 · fiabilidad | `fiable_a` siempre; `fiable_b` en P | `reconstruction_coverage == 1`. Sin caja fiable no hay palanca: `"no identificable con suficiente confianza"` |
| R4 · no sobrefinanciar | `Σ φ ≤ 1` por `(palanca, receptora)` | Varias donantes pueden repartir una necesidad |
| R5 · nivel del donante | `L_a' ≥ L_a − δ`, `δ = 5` | Solo D1 puede bajar `L_a` |
| R6 · no observables | fiscalidad, legal, covenants, precio intragrupo, moneda funcional | **No se modelan.** Se listan en `assumptions` y en la narrativa |

### 5.3 Objetivo: utilidad cóncava por tramos

```
U(L) = 3·min(L, 40) + 2·clip(L − 40, 0, 30) + 1·clip(L − 70, 0, 30)
U(0) = 0 · U(40) = 120 · U(70) = 180 · U(100) = 210
G = Σ_i ω_i · U(L_i) / (2,1 · Σ_i ω_i)        ∈ [0, 100]
```

Un punto ganado en zona roja (<40) vale tres veces uno en zona verde (≥70): **"ayudar a la que se hunde" emerge de la concavidad**. `ω_i = 1` por defecto (`"equal"`); opción `"size"` = `I_i + O_i`. Filiales sin nivel no entran en `G` ni en las acciones; se listan con su `score_reason`. `G` se llama `group_utility_0_100`; **no es el consolidado grupo-moneda de V2**, que se reporta aparte sin recalcular (`consolidated_group_currency_score`, con la nota de que D1 no lo altera). Se reportan también `min_level`, `mean_level`, `levels_by_tramo` antes/después y, si hay `fx_rates_to_eur`, la caja comprometida total en `reporting_currency`.

Desempate: mayor `ΔG`, misma moneda antes que cruzada, menor caja comprometida (en `reporting_currency`), menos pasos, orden lexicográfico `(donante, receptora, palanca, fracción)`.

### 5.4 Algoritmo

1. **Estado** (§3). Una filial → `status="single_subsidiary"`. Sin filial optimizable o sin donante factible → `"no_feasible_levers"` con motivos por filial. Ambos cuentan en la cobertura.
2. **Candidatos** `(a, b, ℓ ∈ {D1, P}, φ ∈ {0,25, 0,5, 0,75, 1})` que cumplan precondiciones y R1–R5 dado el estado actual; cada uno se evalúa con `score_level` en k=1 y k=H. Eficiencia `e = ΔG_kH / (x_report / 10.000)` con `x_report` la caja comprometida en `reporting_currency` (o en la moneda común si no hay tabla FX).
3. **Greedy determinista:** orden `(−e, −ΔG_kH, fx_applied, x_report, a, b, ℓ, φ)`; aplicar si `ΔG_kH ≥ min_gain` (0,25); actualizar caja del donante, `φ` acumulado por `(ℓ, b)` y filas de señales; repetir hasta `max_steps = 10` o sin candidatos. Cada paso guarda **restricciones activas** (`donor_buffer`, `need_fully_covered`, `donor_level_floor`, `fraction_cap`) y las **alternativas rechazadas** (5 siguientes con `ΔG` y motivo).
4. **Certificado** (grupos con ≤6 filiales optimizables): mejor acción única y mejor par compatible por enumeración; `greedy_gap = mejor_par − greedy_2_pasos`. Sin garantía de óptimo global; se dice.
5. **Salida** (§8).

Complejidad: ≤22 filiales → ≤3.696 candidatos por paso. **Determinismo:** misma entrada → mismo JSON salvo `generated_at`; iteración ordenada por `company_id`.

## 6. Sensibilidad de empresa (`company_sensitivity_v1`)

Para cada empresa puntuada (`L_i` no nulo), en su moneda declarada, sin depender del grupo.

### 6.1 Palancas y tipo

| id | Tipo | Primitiva | Magnitud mostrada | Unidad | Dirección buena | Disponible si |
|---|---|---|---|---|---|---|
| `cut_outflow` | negocio | `outflow_scale(−r)` | salidas operativas mensuales `O/H` | moneda | ↓ | `O > 0` |
| `raise_inflow` | negocio | `inflow_scale(+r)` | entradas operativas mensuales `I/H` | moneda | ↑ | `I > 0` |
| `debt_service_cut` | tesorería | `debt_service_scale(−r)` | cuota mensual `s` | moneda | ↓ | `S > 0` |
| `ap_on_time` | tesorería | `ap_delay_scale(r)` | retraso AP `p` | días | ↓ | `p` disponible y `> 0` |
| `ar_faster` | tesorería | `ar_delay_scale(r)` | retraso AR `a` | días | ↓ | `a` disponible y `> 0` |

Las palancas de **negocio** se muestran como sensibilidad ("si las salidas bajaran un 5%, el nivel subiría X"), **nunca como recomendación de recortar**; llevan el supuesto `"las demás magnitudes no cambian"` (p. ej. recortar salidas sin que caigan entradas). Un componente no disponible (sin ERP, sin deuda) aparece como `"no evaluable"` con motivo, no se omite.

### 6.2 Qué se calcula por palanca

Todo con `score_level` y la referencia del mes; `H = 6`.

1. **Rejilla:** `r ∈ {0,01, 0,05, 0,10, 0,25}` en la dirección buena; para cada `r`: magnitud resultante, `L'` en k=1 y k=H, `score'` en k=H, y **equivalente de caja** cuando exista: `cut_outflow` → `r·O` (menos gasto en la ventana); `debt_service_cut` → `r·S`; `ap_on_time` → caja necesaria `r·(V + D30)`; `raise_inflow` y `ar_faster` → `null` (sin equivalente limpio).
2. **Pendiente actual:** `∂L/∂r` por diferencia finita `ε = 1e-4` en k=H (`level_per_pct`), y en unidad natural (`level_per_day`, `level_per_10k`). Piecewise-lineal ⇒ constante hasta el siguiente nudo.
3. **Siguiente nudo:** valor de la magnitud en el que cambia la pendiente en la dirección buena. Nudos = abscisas de las anclas de la señal ∪ `{reference_low, reference_high}` si `empirical_active`, convertidos de señal a magnitud (`margen → O` con `I` fijo: `O* = I·(1−m*)/(1+m*)`; `d → S* = d*·I`; retrasos: identidad). Se reporta `valid_until` (magnitud) y `slope_after` (pendiente tras el nudo, por diferencia finita justo después).
4. **Cuánto para cambiar de tramo:** objetivo = siguiente frontera por encima de `L` (40 o 70). Bisección sobre `r ∈ [0, r_max]` en k=H (la función es monótona en la dirección buena): `r*` mínimo con `L(r*) ≥ objetivo`; tolerancia 1e-4; `r_max` = 1,0 (retrasos, deuda), 0,5 (`cut_outflow`), 1,0 (`raise_inflow`). Si no se alcanza → `reachable=false`. Se expresa en unidad natural y equivalente de caja. Frase objetivo: *"para pasar a verde: −4 días de retraso AP **o** −8% de salidas **o** …"*.
5. **Factibilidad sola** (`ap_on_time`): `own_excess_cash = max(0, C − B_i)` con el mismo colchón `B_i` de R2 (sin términos de terceros); `feasible_alone = own_excess_cash ≥ cash_needed`; si no, `requires_financing`; WP5 añade `covered_by_group_plan` si el plan del grupo la cubre. Sin caja fiable → `unknown`.
6. **Ranking:** `by_pct` (pendiente por 1% de cambio relativo, k=H) y `by_cash` (nivel por 10.000 de equivalente de caja; solo palancas con equivalente). Se publican los dos; la narrativa dice cuál usa en cada frase.
7. **Nota estructural:** si `level_operations < 40`, se explica que el margen es el componente que arrastra y que **no es palanca de tesorería**.

## 7. Moneda y FX

- Las **señales** de V2 son ratios y retrasos dentro de una moneda: **no necesitan FX**. Ninguna perturbación convierte moneda.
- Los **importes** (caja comprometida, necesidades, equivalentes de caja, totales de grupo) se convierten solo en el advisor con una **tabla fija** `fx_rates_to_eur` = unidades de moneda por 1 EUR (`EUR: 1.0`), con `fx_source` y `fx_asof` documentados. `fx(x, c_from → c_to) = x / rate[c_from] · rate[c_to]`. **Nunca se usa `transactions.exchange_rate`** (ambiguo, §1).
- Moneda ausente en la tabla → palancas cruzadas con esa moneda infactibles (`fx_rate_unavailable`); nada de lo intra-moneda se ve afectado.
- Toda cifra convertida lleva su original y el tipo aplicado; el plan añade el supuesto `fx_fixed_rate` cuando alguna acción es cruzada. Error esperado: ±5% en EUR/USD/GBP en 24 meses; ±15–30% en monedas latinoamericanas (volúmenes residuales).
- **Fuera de alcance ahora:** convertir en features/V2 (cambiaría el candidato del leaderboard y la política de tests; requiere reabrir D07). Variante opcional tras WP5: panel `company_consolidated` con todas las cuentas a tipo fijo, V2 `--panel company_consolidated` como artefacto separado, comparando cobertura (299 empresas, 42 grupos) **sin sustituir el primario**. Futuro: tabla FX diaria.

## 8. Contrato de salida

Directorio `data/processed/advisor/` (publicación con `xray.artifacts.publish_bundle`, staging y `.history/`):

| Fichero | Contenido |
|---|---|
| `group_plans/{group_id}.json` · `.md` | Plan por grupo (esquema 8.1) y su narrativa |
| `company_sensitivity/{company_id}.json` · `.md` | Sensibilidad por empresa puntuada (esquema 8.2) y su narrativa |
| `advisor_steps.parquet` | Fila por (grupo, paso) |
| `advisor_groups.parquet` | Fila por grupo: `status`, cobertura, `G` antes/después, min/mean, pasos, motivo |
| `sensitivity_levers.parquet` | Fila por (empresa, palanca): pendiente, nudo, `r*` a siguiente tramo, factibilidad |
| `_advisor_report.json` | Cobertura por `status`; motivos agregados; distribución de `ΔG` k=1/k=H; filiales que cambian de tramo; caja comprometida por palanca y en `reporting_currency`; `greedy_gap > 0`; sensibilidad: empresas con ≥1 palanca, palanca top más frecuente por tramo, distribución de `r*`; `limitations` literal de §10 |
| `_advisor_manifest.json` | Hashes de entradas (features, scores_v2, referencia, liquidez), código, parámetros, tabla FX |

### 8.1 `group_plans/{group_id}.json` (v1)

```jsonc
{
  "schema_version": 1, "method": "group_treasury_advisor_v1",
  "group_id": "GROUP_0064", "month": "2026-08-01",
  "config": { /* AdvisorConfig serializado, incluida la tabla FX */ },
  "status": "plan" | "no_feasible_levers" | "single_subsidiary",
  "reporting_currency": "EUR",
  "coverage": {"subsidiaries": 3, "optimizable": 3, "not_scored": 0, "with_reliable_cash": 2,
               "with_debt_component": 3, "with_ap_component": 0, "currencies": ["EUR"]},
  "baseline": {
    "group_utility_0_100": 61.2, "min_level": 38.1, "mean_level": 65.1,
    "levels_by_tramo": {"red": 1, "amber": 1, "green": 1},
    "consolidated_group_currency_score": {"EUR": 51.2},
    "subsidiaries": [{
      "company_id": "COMP_0738", "currency": "EUR", "level": 38.1, "score": 38.1, "momentum_adjustment": 0.0,
      "tramo": "red", "score_status": "provisional", "score_reason": "trend_unavailable",
      "components": {"operations": 3.7, "debt": 100.0, "collections": null, "payments": null},
      "signals": {"op_margin_w": -0.80, "debt_service_w": 0.0, "ar_delay_w": null, "ap_delay_w": null,
                  "level_inflow_sum": 123456.0, "window_outflow_sum": 1111104.0, "monthly_debt_service": 0.0},
      "liquidity": {"reconstructed_cash": 12000.0, "reliable": true, "runway_months": 0.4, "buffer": 61000.0, "excess_cash": 0.0},
      "ap": {"overdue_amount": null, "due_30": null, "due_60": null, "gap": null}
    }]
  },
  "diagnosis": {
    "bottleneck": {"company_id": "COMP_0738", "level": 38.1, "weakest_components": ["operations"]},
    "structural_flags": [{"company_id": "COMP_0738", "component": "operations", "note": "margen 6m -0,80: no es palanca de tesoreria"}],
    "unexplained_ap_delays": [],
    "donor_candidates": ["COMP_0222"], "recipient_candidates": ["COMP_0007", "COMP_0738"]
  },
  "levers_evaluated": [{"lever": "D1", "donor": "COMP_0222", "recipient": "COMP_0007",
                        "donor_currency": "EUR", "recipient_currency": "EUR", "fx_applied": null,
                        "feasible": true, "need_recipient_ccy": 42000.0, "donor_capacity": 310000.0, "reason": null}],
  "plan": {
    "steps": [{
      "step": 1, "lever": "D1", "donor": "COMP_0222", "recipient": "COMP_0007",
      "fraction": 1.0,
      "amount": {"recipient_ccy": 42000.0, "donor_ccy": 42000.0, "reporting_ccy": 42000.0, "fx_applied": null},
      "effects": {
        "k1": {"recipient": {"level_before": 57.2, "level_after": 57.9, "score_after": 53.0, "component": "debt", "signal_before": 0.078, "signal_after": 0.065, "component_dropped": false},
               "donor": {"level_before": 100.0, "level_after": 100.0, "signal_before": 0.0, "signal_after": 0.003},
               "group_utility_before": 61.2, "group_utility_after": 61.4},
        "k6": {"...": "..."}
      },
      "efficiency_per_10k": 0.76,
      "binding_constraints": ["need_fully_covered"],
      "evidence": ["ev_0001", "ev_0002"]
    }],
    "totals": {"k1": {"group_utility_after": 61.4, "min_level_after": 38.1},
               "k6": {"group_utility_after": 64.4, "min_level_after": 38.1}},
    "cash_committed_by_donor": {"COMP_0222": {"donor_ccy": 42000.0, "reporting_ccy": 42000.0}},
    "stopped_because": "no_candidate_above_min_gain"
  },
  "rejected_alternatives": [{"lever": "P", "donor": "COMP_0222", "recipient": "COMP_0738",
                             "reason": "recipient_ap_component_unavailable", "delta_utility_k6": null}],
  "certificate": {"checked": true, "best_single_utility": 64.4, "best_pair_utility": 64.4, "greedy_utility": 64.4, "greedy_gap": 0.0},
  "assumptions": ["estacionariedad de flujos y servicio en la ventana",
                  "el credito intragrupo no se liquida por banco en el horizonte",
                  "no se modelan fiscalidad, legal, covenants ni precio intragrupo"],
  "limitations": ["caja reconstruida retrospectivamente; no saldo observado", "momentum no simulado",
                  "el consolidado grupo-moneda no cambia con D1 y no se recalcula con P"],
  "evidence": {"ev_0001": {"source": "company_currency_liquidity_context", "company_id": "COMP_0222",
                           "field": "reconstructed_cash", "month": "2026-08-01", "value": 371000.0}},
  "generated_at": "2026-09-19T18:00:00+00:00",
  "inputs_sha256": {"company_monthly_features.parquet": "...", "scores_v2/company_monthly_scores.parquet": "..."}
}
```

Si alguna acción es cruzada, `assumptions` incluye `"fx_fixed_rate: tabla <fx_source> a <fx_asof>"`.

### 8.2 `company_sensitivity/{company_id}.json` (v1)

```jsonc
{
  "schema_version": 1, "method": "company_sensitivity_v1",
  "company_id": "COMP_0007", "group_id": "GROUP_0064", "currency": "EUR", "month": "2026-08-01",
  "status": "sensitivity" | "not_scored",
  "score_reason": "trend_unavailable",
  "baseline": {"level": 57.2, "score": 52.4, "momentum_adjustment": -4.8, "tramo": "amber",
               "components": {"operations": 42.2, "debt": 84.3, "collections": null, "payments": null},
               "signals": {"op_margin_w": -0.10, "debt_service_w": 0.078, "ar_delay_w": null, "ap_delay_w": null,
                           "level_inflow_sum": 540000.0, "window_outflow_sum": 660000.0, "monthly_debt_service": 7020.0},
               "liquidity": {"reconstructed_cash": 25000.0, "reliable": true, "buffer": 48000.0, "excess_cash": 0.0},
               "ap": {"overdue_amount": null, "due_30": null, "due_60": null}},
  "group_context": {"has_group_plan": true, "role": "recipient", "steps": [1]},   // lo rellena WP5
  "next_tramo_target": 70,
  "levers": [{
    "lever": "debt_service_cut", "type": "treasury", "component": "debt", "available": true,
    "quantity": "monthly_debt_service", "unit": "EUR", "current": 7020.0, "direction": "decrease",
    "slope_now": {"level_per_pct": 0.19, "level_per_unit": null, "level_per_10k": 0.27, "valid_until": 4500.0, "slope_after": 0.19},
    "grid": [{"rel_change": 0.05, "quantity_after": 6669.0, "level_after_k1": 57.4, "level_after_k6": 58.2,
              "score_after_k6": 53.4, "cash_equivalent": 2106.0}],
    "to_next_tramo": {"target": 70, "rel_change_needed": null, "quantity_needed": null, "reachable": false, "cash_equivalent": null},
    "feasibility": {"feasible_alone": null, "cash_needed": null, "own_excess_cash": 0.0, "note": "renegociacion con el acreedor"},
    "assumptions": ["estacionariedad", "las demas magnitudes no cambian"], "evidence": ["ev_0003"]
  }, {
    "lever": "ap_on_time", "type": "treasury", "component": "payments", "available": false,
    "reason": "ap_component_unavailable"
  }],
  "ranking": {"by_pct": ["cut_outflow", "debt_service_cut", "raise_inflow"], "by_cash": ["debt_service_cut", "cut_outflow"]},
  "structural_note": "El margen 6m (-0,10) es el componente que arrastra el nivel; recortar salidas o subir entradas son decisiones de negocio, no de tesoreria.",
  "assumptions": ["..."], "limitations": ["..."], "evidence": {"ev_0003": {"...": "..."}},
  "generated_at": "...", "inputs_sha256": {"...": "..."}
}
```

Todos los números de la narrativa deben ser localizables en estos JSON (validador, §9.3).

## 9. Narrativa

### 9.1 Plantillas deterministas (obligatorio)

`render_plan(plan, fmt)` — secciones fijas en este orden: **Resumen** (grupo, mes, filiales optimizables/total, `G` antes → después k=H, filiales que cambian de tramo, caja comprometida total, aviso "escenario mecánico bajo supuestos explícitos") · **Diagnóstico** · **Plan paso a paso** (por paso: frase de negocio, importe con moneda y, si procede, tipo aplicado, efecto en receptora y donante en k=1 y k=H, eficiencia por 10.000, restricción activa, evidencia) · **Por qué no más / por qué no otras** · **Supuestos y límites** · **Cobertura de datos**. Sin plan: plantilla por `status`, con motivos por filial.

`render_sensitivity(sens, fmt)` — **Dónde estás** (nivel, tramo, componentes, qué arrastra) · **Qué mueve más tu nivel** (ranking por 1%, tres primeras palancas con pendiente actual y hasta dónde vale) · **Qué mueve más por cada 10.000** (ranking por caja; solo palancas con equivalente) · **Cuánto para cambiar de tramo** (una frase por palanca alcanzable, unidas por "o") · **Papel en el grupo** (si `group_context.has_group_plan`) · **Palancas no evaluables** · **Supuestos y límites**.

Frases de negocio (única fuente de vocabulario):

- D1: *"{donor} asume {fraction} de las cuotas de deuda de {recipient} ({monthly} al mes durante {H} meses, {amount} comprometido). El servicio externo del grupo no cambia; se traslada a quien puede llevarlo."*
- P: *"{donor} financia a {recipient} con {amount} para pagar a proveedores en plazo ({coverage} del AP vencido y próximo). Los importes no cambian, solo la fecha."*
- `cut_outflow`: *"Si las salidas operativas bajaran un {pct} ({amount} al mes) y todo lo demás siguiera igual, el nivel pasaría de {before} a {after} en régimen."*
- `raise_inflow`: *"Si las entradas operativas subieran un {pct} y todo lo demás siguiera igual, …"*
- `debt_service_cut`: *"Si la cuota mensual de deuda bajara de {before_q} a {after_q} (renegociación o plazo más largo), …"*
- `ap_on_time` / `ar_faster`: *"Si el retraso medio de {pago a proveedores | cobro a clientes} bajara de {before_q} a {after_q} días, …"*
- Cambio de tramo: *"Para pasar a {tramo}: {frase_1} o {frase_2} o …"*; si ninguna: *"Ninguna palanca por sí sola alcanza {tramo} dentro de los límites evaluados."*

Números con separador de miles «.» y decimal «,»; monedas con su código; una única `fmt_num`.

### 9.2 Preguntas cerradas (Q&A determinista)

| Intención | Argumentos | Fuente en el JSON |
|---|---|---|
| `why_not_more` | receptora | `plan.steps[*].binding_constraints`, `levers_evaluated` |
| `why_not_pair` | donante, receptora | `rejected_alternatives`, `levers_evaluated[*].reason` |
| `what_changes_for` | filial | `plan.steps[*].effects`, `baseline.subsidiaries` |
| `what_is_assumed` | — | `assumptions`, `limitations` |
| `what_data_missing` | — | `coverage`, `diagnosis`, `rejected_alternatives` / `levers[*].reason` |
| `is_it_optimal` | — | `certificate` |
| `what_moves_most` | (empresa) `by="pct"\|"cash"` | `ranking`, `levers[*].slope_now` |
| `how_to_reach_tramo` | (empresa) | `levers[*].to_next_tramo` |
| `group_role` | (empresa) | `group_context` |

Respuesta fija si la intención no está soportada o el dato no existe: *"Ese dato no forma parte del análisis de {entidad} para {month}."*

### 9.3 Adaptador LLM (posterior; diseño fijado)

Entrada: JSON + petición. Temperatura 0. System prompt con reglas cerradas: solo números presentes en el JSON; citar `evidence` ids; no proponer acciones fuera de `plan.steps` / `levers`; castellano; frase fija si no está en el JSON. **Validador de anclaje** obligatorio: todos los números del texto (tolerancia de redondeo a 1 decimal, separadores, porcentajes también como fracción) y todos los `COMP_xxxx`/`GROUP_xxxx`/ids de palanca deben existir en el JSON; si falla → plantilla y registro del fallo. Interfaz `complete(system, user) -> str`; sin API key el producto funciona íntegramente con 9.1.

## 10. Supuestos y límites que se dicen antes de que los pregunten

- **Escenario mecánico** sobre el nivel V2, no recomendación ejecutable ni predicción.
- **D1 no cambia el servicio externo del grupo**: redistribuye. La ganancia es de resiliencia, no de coste financiero.
- **Estacionariedad**: flujos, cuotas y número de pagos del último semestre se repiten.
- **Palancas de negocio** (`cut_outflow`, `raise_inflow`): sensibilidad con "todo lo demás igual"; no se recomienda recortar ni se supone que vender más no cueste.
- **Caja reconstruida hacia atrás** desde la foto de 2026-09-01 (FE06); no es saldo observado. Sin fiabilidad no hay palanca.
- **Momentum no simulado**; el score contrafactual mantiene el ajuste de momentum del baseline.
- **FX fijo** solo para importes; señales dentro de cada moneda. `transactions.exchange_rate` no se usa.
- Fiscalidad, legal, covenants, precio intragrupo, reacción de clientes/proveedores: fuera de los datos, fuera del modelo.
- El AP pagado tarde puede ser política o higiene ERP: P solo si la receptora está restringida por liquidez.
- Greedy con certificado hasta pares; sin garantía de óptimo global. Bisección de tramo por palanca **aislada**: combinaciones no se exploran.
- Nada contrastado con Embat ni con la nota oculta del leaderboard.

## 11. Parámetros (`AdvisorConfig`)

```python
@dataclass(frozen=True)
class AdvisorConfig:
    month: str | None = None                 # None -> ultimo cierre del panel
    levers: tuple = ("D1", "P")              # palancas de grupo
    fractions: tuple = (0.25, 0.5, 0.75, 1.0)
    donor_buffer_months: float = 2.0         # kappa (R2)
    donor_level_floor_drop: float = 5.0      # delta (R5)
    horizon_months: int = 6                  # H = level_window de V2; validado contra ref["config"]
    report_k: tuple = (1, 6)
    utility_knots: tuple = ((0, 3.0), (40, 2.0), (70, 1.0))  # (inicio_tramo, pendiente)
    tramo_bounds: tuple = (40.0, 70.0)
    subsidiary_weighting: str = "equal"      # | "size"
    min_gain_utility: float = 0.25           # escala 0-100 de G
    max_steps: int = 10
    exhaustive_max_subsidiaries: int = 6
    liquidity_constrained_runway: float = 1.0
    rejected_alternatives_kept: int = 5
    # sensibilidad de empresa
    sensitivity_grid: tuple = (0.01, 0.05, 0.10, 0.25)
    sensitivity_r_max: dict = {"cut_outflow": 0.5, "raise_inflow": 1.0, "debt_service_cut": 1.0, "ap_on_time": 1.0, "ar_faster": 1.0}
    finite_difference_eps: float = 1e-4
    bisection_tol: float = 1e-4
    # FX solo para importes
    reporting_currency: str = "EUR"
    fx_rates_to_eur: dict | None = None      # {"EUR": 1.0, "USD": ..., ...}; None -> solo misma moneda
    fx_source: str | None = None
    fx_asof: str | None = None
```

Validaciones: fracciones y rejilla en (0,1] crecientes; `horizon_months == ref["config"]["level_window"]`; pendientes de utilidad positivas y no crecientes (concavidad); `tramo_bounds` coherente con `utility_knots`; `report_k ⊆ 1..H`; `fx_rates_to_eur` con `EUR: 1.0` y valores positivos si no es `None`; `reporting_currency` en la tabla.

## 12. Tests exigidos (mínimos; cada WP añade los suyos)

**Primitivas y motor** — acción nula reproduce el nivel V2 de `score_panel` (1e-9); `debt_service_scale(−1)` con `k=H` ⇒ `debt_service_w = 0` y `level_debt = 100`; monotonía en parámetro y en `k` (buena dirección ⇒ nivel no decreciente; `debt_service_add(+)` ⇒ no creciente); `I_k = 0, S_k > 0` ⇒ indicador; `I_k = 0, S_k = 0` ⇒ componente eliminado y renormalización (no 100 ni 0 fantasma); `outflow_scale` y `inflow_scale` recalculan margen y servicio coherentemente; `k=1` efecto menor que `k=H`; entradas no mutadas; composiciones D1 y P equivalen a sus primitivas; reproducción del nivel V2 sobre 20 empresas reales (skip sin datos).

**Objetivo y optimizador** — concavidad de `U`; `U(100) = 210`; `G ∈ [0,100]`; una unidad de mejora va a la filial de 30 antes que a la de 90; R2 activa y reportada (`donor_buffer`); R4 con dos donantes; misma moneda preferida en empate; acción cruzada con tabla FX convierte importes y añade `fx_fixed_rate`; sin tabla ⇒ `fx_rate_unavailable`; determinismo e invariancia al orden de filas; fixture con `greedy_gap > 0`; unipersonal y sin caja fiable ⇒ `status` correcto; `group_utility_after` recomputable desde niveles finales.

**Sensibilidad** — pendiente por diferencia finita coincide con `(L(r+ε) − L(r))/ε`; `valid_until` es un nudo real (la pendiente cambia justo después y no antes); bisección devuelve el `r*` mínimo (verificar `L(r*−tol) < objetivo ≤ L(r*)`); `reachable=false` cuando `L(r_max) < objetivo`; palanca no disponible ⇒ `available=false` con motivo; ranking `by_cash` excluye palancas sin equivalente; `feasible_alone` según caja propia; `raise_inflow` también baja `debt_service_w`.

**Narrativa** — toda cifra del texto existe en el JSON (plantillas de plan y de sensibilidad); secciones en orden; sin plan ⇒ plantilla de `status`; cada intención responde desde su ruta; intención desconocida ⇒ frase fija; `llm_render` con completer que inventa un número cae a plantilla.

**Pipeline** — publicación con staging y manifiesto (incluida tabla FX); no escribe fuera de `data/processed/advisor/`; no toca `scores/` ni `scores_v2/`; suite completa con `python -W error -m pytest -q`.

## 13. Producto: dónde aparece cada cosa

- **Ficha de empresa** (`/companies/[id]`, siempre): score V2, trayectoria, contribuciones **+ bloque "Qué mueve tu nivel"** (`render_sensitivity`): tres palancas top por 1%, tres por 10.000, frase de cambio de tramo, palancas no evaluables. Si la empresa pertenece a un grupo con plan: banner *"En el plan de grupo esta filial {recibe|aporta} {amount} (paso {n})"* con enlace.
- **Vista de grupo** (`/groups/[id]`, solo si `status != "single_subsidiary"`): filiales con nivel/tramo, `G` antes/después, plan paso a paso (`render_plan`), diagnóstico, supuestos **en pantalla**, enlaces a cada ficha. Si `no_feasible_levers`: motivos por filial, sin "todo bien" implícito.
- **Cartera** (`/`): lista de empresas con agrupador por grupo y contador de grupos con plan.
- Navegación: CFO de grupo → Cartera → Grupo → Filial; CFO de empresa suelta → Ficha directa. Rol elegido en la demo, no inferido.
- Endpoints: `GET /companies/{id}/sensitivity`, `GET /groups/{id}/plan`.

## 14. Relación con el resto del proyecto

- No modifica `src/xray/score_v2/` ni sus artefactos; consume `scores_v2/`, `company_monthly_features`, `company_currency_liquidity_context` y la referencia congelada. `load_inputs` rechaza mezclar unas features con unos scores calculados sobre otras (hash del manifiesto de `scores_v2`): si se regeneran features hay que regenerar `03`/`05` (empresa y `--panel group_currency`) antes de `08`.
- Resultados sobre los 250 grupos y las 949 empresas puntuadas: `decisiones.md` §18 GA-06. Producto: `embat_pulse_mvp_propuesta_final.md` §12/§18 y `product-and-demo.md`.
- Ejecución: `python -X utf8 scripts/08_treasury_advisor.py` (≈2,5 min; `load_inputs` ≈45 s); `--group GROUP_xxxx` / `--company COMP_xxxx` imprimen la narrativa sin publicar. Tests: `python -W error -m pytest -q tests/test_group_advisor_*.py` (≈220 tests, ≈3 min con los de datos reales).

## 15. Casos ilustrativos (agosto 2026, datos D32; cifras de `data/processed/advisor/`)

Resumen global: **19 grupos con plan, 160 sin palancas factibles, 71 unipersonales**; 25 pasos (20 D1 + 5 P); ΔG por plan mediana 2,6 (máx 7,6); 5 filiales pasan de rojo a ámbar en régimen; caja comprometida 3,34 M EUR. Sensibilidad: 949 empresas con ≥1 palanca; 311 alcanzan el siguiente tramo con una sola palanca (`raise_inflow` 292, `cut_outflow` 277, `debt_service_cut` 90, `ar_faster` 28, `ap_on_time` 27); 0 fallos de anclaje en 250 planes y 1.286 sensibilidades. Motivos dominantes de infactibilidad: caja del donante no fiable (3.038 pares), receptora sin servicio de deuda (2.706), receptora sin componente AP (2.549), colchón del donante (2.434).

**D1 con sentido de negocio — `GROUP_0067`** (6 filiales, todas EUR). COMP_1048 (nivel 88, caja fiable 2,07 M, runway 4 meses) asume el 100 % de las cuotas de COMP_1275 (12.340 EUR/mes; servicio/entradas = **1,17**, nivel 31): COMP_1275 pasa a **66,7** en régimen y COMP_1048 baja a 86,8; después asume las cuotas de COMP_0407 y COMP_0929 y el 25 % de COMP_0216 hasta tocar el suelo de nivel del donante (δ = 5). G del grupo 60,1 → 67,7 en cuatro pasos; 254 k EUR comprometidos; certificado hasta pares con brecha 0,08. Lo que el plan **no** puede arreglar y dice: COMP_0407 y COMP_0929 tienen margen 6m negativo (−0,27 / −0,22), etiquetado como estructural.

**P — `GROUP_0022`** (13 filiales, 4 optimizables). COMP_0640 (nivel 43, caja fiable) financia a COMP_0764 con 1,93 M EUR para pagar a proveedores en plazo: su retraso AP de ventana (**199 días**) baja a 0 y su nivel pasa de 40,2 a **57,8** en régimen; también financia a COMP_0908 (retraso 9,8 días, nivel 12,8) en tres fracciones con efecto pequeño (nivel 12,8 → 16,1), porque su problema es el margen, no la fecha de pago. G 51,2 → 56,6; el donante no pierde nivel (la salida intragrupo no es operativa) pero compromete 2,45 M. Certificado: brecha greedy 5,08 (existe un par mejor que los dos primeros pasos del greedy; se reporta, no se oculta).

**Sin palancas, honesto — `GROUP_0064`** (12 filiales, 4 optimizables; el ejemplo del enunciado de esta spec). COMP_0222 (nivel 100, caja 342 k) es la única donante; COMP_0007 (56,5) necesita 1,77 M para D1 completa (colchón del donante lo impide) y no tiene componente AP; COMP_0738 y COMP_1115 (38) tienen deuda 0 y margen −0,80/−0,81: **problema estructural, no de tesorería**. El plan lo dice filial por filial en «Motivos por filial» y no propone nada. `COMP_0007` en su ficha: para llegar a verde necesita −27 % de salidas o +34 % de entradas; la cuota no basta.

**Mecánica correcta, negocio débil — `GROUP_0102` y `GROUP_0044`**. COMP_0071 (entradas de ventana 358 EUR, cuota 148 EUR/mes) pasa de 30 a 55 cuando COMP_0431 asume 885 EUR: el indicador `debt_without_inflow` deja de activarse y el componente deuda desaparece del nivel. Es exactamente la regla de V2 (§4), y el plan lo marca (`component_dropped`, eficiencia 80 puntos por 10.000), pero una filial sin entradas operativas no está más sana por 885 EUR. Se deja visible como límite del score, no se maquilla (GA-06).

**Sensibilidad de empresa — `COMP_0007`** (ámbar 56,5): ranking por 1 % → `raise_inflow` 0,43 puntos, `cut_outflow` 0,37, `debt_service_cut` 0,05; por 10.000 EUR → `debt_service_cut` primero. «Para pasar a verde: un 27,3 % menos de salidas operativas o un 34 % más de entradas». AP/AR no evaluables (sin ERP). **`COMP_1275`** (rojo 31) en su ficha: «Para pasar a ámbar: un 17,9 % menos de salidas, o un 21,2 % más de entradas, o una cuota mensual de deuda de 3.495 EUR (desde 12.340, un 71,7 % menos)»; la pendiente de `debt_service_cut` es 0 al principio porque su ratio (1,17) está por encima del último nudo de las anclas (1,0) y solo empieza a puntuar al bajar de ahí. «Papel en el grupo: recibe apoyo en el paso 1» enlaza al plan de `GROUP_0067`.

Lectura para el pitch: la vista de grupo encuentra pocos planes porque las palancas son estrictas por diseño (caja fiable, colchón de dos meses, receptora con deuda o con AP restringido por liquidez); cuando propone algo, cada euro y cada punto están anclados a una evidencia y a la función exacta de V2. La vista de empresa cubre a todas las puntuadas y separa lo que es tesorería de lo que es negocio.
