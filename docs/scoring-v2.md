# Scoring V2 — `financial_smoothed_v2`: nivel suavizado, dirección confirmada y bache frente a tendencia

**Implementado el 19-09-2026 en `src/xray/score_v2/`.** V1 (`src/xray/score/`) se conserva intacto como control en `data/processed/scores/`; V2 publica en `data/processed/scores_v2/`. Resultados comparados en `data/processed/evaluation/score_comparison.md` (generado por `scripts/07_compare_scores.py`). Estado, decisiones y límites en [decisiones.md](./decisiones.md) §13.

## Qué problema resuelve

V1 puntuaba cada mes con el ratio de ese mes (o una media de tres ratios mensuales cuando había soporte) y calculaba la tendencia como diferencia de valores mensuales. En este dataset la volatilidad mensual del margen operativo dentro de una empresa es enorme (desviación típica mediana **0,29** en ventanas de seis meses; 0,44 en las empresas pequeñas), por lo que el score de V1 saltaba una mediana de 8,8 puntos al mes (p95 44) y las etiquetas de trayectoria cambiaban el 33% de los meses. Un mes malo y una tendencia mala eran indistinguibles.

V2 separa las tres preguntas con tres capas explícitas:

| Capa | Qué mide | Cómo |
|---|---|---|
| **Nivel** | Dónde está la empresa | Ratios de **flujos agregados en seis meses** (no medias de ratios) |
| **Momentum** | Hacia dónde va | Trimestre reciente frente a trimestre anterior, **estandarizado por la volatilidad propia** de la empresa |
| **Episodio** | Bache o tendencia | Confirmación en dos meses + evidencia del mes actual; meses atípicos etiquetados |

## Ejecutar

```bash
python -X utf8 scripts/05_compute_scores_v2.py fit
python -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python -X utf8 scripts/05_compute_scores_v2.py fit --panel group_currency
python -X utf8 scripts/06_validate_scores_v2.py --panel group_currency --check-prefix 2026-02-01
python -X utf8 scripts/07_compare_scores.py            # V1 frente a V2; --no-sensitivity es más rápido
```

Empresas nuevas, con la referencia congelada (no se recalibra con ellas):

```bash
python -X utf8 scripts/05_compute_scores_v2.py predict --features-dir data/hidden/processed --reference data/processed/scores_v2/_company_score_reference.json
```

API: `xray.score_v2.fit_reference_bundle(panel, ScoreV2Config(...))` y `xray.score_v2.score_panel(panel, reference)`. Parámetros en `ScoreV2Config` (`src/xray/score_v2/config.py`); todos quedan en el JSON de referencia y en el manifiesto.

## 1. Señales (`signals.py`)

Todo se calcula por entidad-moneda sobre el calendario natural completo: los huecos no se comprimen y ninguna señal mira meses posteriores a t. Un mes cuenta como **mes con calidad** con los mismos umbrales que V1 (≥5 movimientos utilizables, ≥80% de filas utilizables, ≥10% del importe identificado como operativo, cobertura de filiales = 1).

### Nivel: ventana de seis meses (t−5..t), mínimo tres meses con calidad

| Señal | Definición |
|---|---|
| `op_margin_w` | (Σ entradas − Σ salidas) / (Σ entradas + Σ salidas) sobre los meses con calidad de la ventana |
| `debt_service_w` | (Σ principal + Σ intereses) / Σ entradas de la ventana; entradas 0 con servicio > 0 → indicador `debt_without_inflow_w`, nota 0 |
| `ar_delay_w`, `ap_delay_w` | Media de las medianas mensuales de retraso (pago − vencimiento) ponderada por número de pagos con vencimiento válido; mínimo 5 pagos en la ventana |

Agregar flujos antes de dividir es lo que hace robusto el nivel: un mes minúsculo con margen −1 pesa lo que pesa su importe, no un tercio de una media de ratios (test `test_window_margin_aggregates_flows_instead_of_averaging_ratios`).

### Momentum: trimestre reciente (t−2..t) frente a trimestre anterior (t−5..t−3)

| Señal | Cambio | Orientación |
|---|---|---|
| `op_margin_qoq` | margen del trimestre reciente − margen del anterior (cada trimestre con ≥2 meses con calidad) | mayor mejora |
| `debt_service_qoq` | ídem con servicio/entradas | menor mejora |
| `ar_delay_qoq`, `ap_delay_qoq` | ídem con retraso ponderado (≥5 pagos por trimestre) | menor mejora |
| `inflow_growth_q` | Σ<sub>k=0..2</sub> clip(log(1 + g<sub>t−k</sub>), ±1,5), con g el crecimiento mes a mes en cuentas comunes | mayor mejora |

El crecimiento compuesto en logaritmos corrige el sesgo alcista de V1 (RV03.1): el ciclo `100→200→100→100` da exactamente 0 donde la media de retornos simples daba +16,7% (test `test_inflow_cycle_100_200_100_100_has_zero_compound_growth`).

### Estandarización por la volatilidad propia

Cada cambio se divide por la desviación típica mensual de la propia empresa (`*_sigma`), medida en los 12 meses **anteriores al trimestre reciente** (mínimo 4 meses, suelos: margen 0,05; servicio 0,02; retraso 3 días; crecimiento 0,05) y ajustada al tamaño de la ventana (σ·√(2/3) para diferencias de medias trimestrales, σ·√3 para la suma de tres crecimientos):

`z = cambio / (σ · ajuste)`

Es una razón señal/ruido por empresa: una empresa volátil necesita un cambio mayor para marcar dirección; una estable, uno pequeño. σ se mide antes del trimestre reciente para que una ruptura grande no infle su propia σ y se anule (test `test_bigger_break_gives_bigger_standardized_change`).

### Diagnóstico del mes actual

`*_deviation = valor mensual − valor de la ventana de nivel` y `*_deviation_z = deviation / σ`. `is_atypical_month = |op_margin_deviation_z| ≥ 2`. Con σ estimada antes del trimestre reciente, el 8,9% de los meses con momentum resultan atípicos en el dataset (frente al 44% que daba un umbral absoluto de 0,20 de margen).

## 2. Nivel (`level.py`)

Idéntico en estructura a V1: anclas financieras (las mismas de V1, ver [scoring.md](./scoring.md) §1) + referencia empírica q10/q90 con peso 70/30, pesos nominales operación 45% · deuda 25% · cobros 15% · pagos 15%, renormalizados entre componentes disponibles. Cambian solo las entradas: los agregados de ventana en vez de valores mensuales. La referencia usa `reference_months=24` (expansiva en este dataset) para que la escala no cambie mes a mes; los mismos 200/50 grupos que V1, semilla 20260918 (el holdout ya fue inspeccionado en la auditoría de V1; se declara en el JSON).

## 3. Momentum y trayectoria (`trajectory.py`)

Pesos: margen 0,35 · crecimiento 0,25 · servicio de deuda 0,20 · retraso AR 0,10 · retraso AP 0,10. Los cambios estandarizados, orientados (positivo = mejora) y recortados a ±4 se combinan con el **Z ponderado de Stouffer**:

`z̄ = Σ wᵢ zᵢ / √Σ wᵢ²`  (sobre las señales disponibles; se exige ≥50% del peso nominal)

Bajo ruido independiente N(0,1), z̄ también es N(0,1) **con cualquier subconjunto de señales**: el umbral de dirección no depende de cuántas fuentes tenga la empresa (una empresa sin ERP no queda ni penalizada ni favorecida). Con las cinco señales, una ruptura clara solo del margen (z ≈ 2,1) o del crecimiento (z ≈ 3,0) basta para marcar dirección; los retrasos AR/AP por sí solos no.

`momentum = 50 + 50·tanh(z̄ / 2)`. Dirección: `|z̄| ≥ 1,5` (momentum fuera de 50 ± 31,7); bajo ruido puro eso son ≈13% de falsos positivos mensuales antes de la confirmación.

### Regla bache/tendencia

Una dirección se **confirma** (`improving` / `deteriorating`) solo cuando:

1. el momentum mantiene el mismo signo **dos meses seguidos**, y
2. el **mes actual** sigue del mismo lado de su propio nivel de seis meses (`current_month_support_z`, Z de Stouffer de las desviaciones del mes actual, con el mismo signo).

Un mes atípico aislado mueve el trimestre reciente durante tres meses, pero cuando la empresa vuelve a su nivel la condición 2 impide confirmar la tendencia: el caso queda como `emerging_*` con episodio `not_sustained_by_current_month`, y nunca como `deteriorating` (test `test_one_off_dip_is_flagged_but_never_confirmed_as_deterioration`). Una ruptura real se confirma al segundo o tercer mes y el score baja de forma monótona mientras dura (test `test_step_down_is_confirmed_as_deterioration_within_three_months`). Una dirección confirmada se mantiene mientras `|z̄| ≥ 0,75` con el mismo signo (histéresis), para no alternar etiquetas por una oscilación leve.

| `trajectory` | Significado |
|---|---|
| `improving` / `deteriorating` | Dirección confirmada (dos meses + mes actual) |
| `emerging_improvement` / `emerging_deterioration` | Dirección este mes, aún sin confirmar |
| `mixed_signals` | Agregado neutral con señales individuales enfrentadas |
| `stable` | Agregado neutral sin conflicto |
| `insufficient_history` | Sin momentum publicable (menos de 7 meses de historia útil o cobertura de señales < 50%) |

| `episode` | Significado |
|---|---|
| `trend_deterioration` / `trend_improvement` | Tendencia confirmada |
| `one_off_dip` / `one_off_spike` | Mes atípico (|desviación| ≥ 2σ) sin tendencia confirmada |
| `not_sustained_by_current_month` | El trimestre marca dirección dos meses, pero el mes actual ya no la sostiene |
| `none` | Nada que señalar |

`stability` (100/(1 + desviación de z̄ en tres meses)) sigue siendo un diagnóstico de regularidad, no un sumando.

## 4. Score, calidad y explicación (`core.py`)

`score = clip(nivel + 0,20·(momentum − 50), 0, 100)`, ±10 puntos como V1.

Elegibilidad: el mes actual debe tener ≥1 movimiento utilizable y cobertura de filiales = 1, y la ventana ≥3 meses con calidad (`insufficient_window_history` si no). **A diferencia de V1**, un mes actual que no alcanza los umbrales de calidad no anula el score si la ventana tiene soporte: se puntúa con la ventana y queda `provisional` con motivo `thin_current_month`. Las dos primeras observaciones de una empresa nunca se puntúan: un nivel de un mes no es un nivel.

Explicación aditiva exacta, validada automáticamente: `Σ contribuciones de nivel + Σ contribuciones de momentum + recorte = score`. Las contribuciones de momentum se reparten con un factor de saturación común, `k(z̄)·wᵢzᵢ/‖w‖`, de modo que suman exactamente `momentum − 50` y cada término conserva el signo de su propia señal. La tabla de explicaciones incluye `standardized_value` (el z usado) además del valor bruto del cambio. Ejemplo real (COMP_0516, agosto 2026, score 51,2):

| Capa | Señal | Valor | z | Nota | Contribución |
|---|---|---:|---:|---:|---:|
| nivel | margen 6m | −0,119 | — | 39,4 | +25,3 |
| nivel | servicio de deuda 6m | 0,000 | — | 100,0 | +35,7 |
| momentum | margen trimestre −0,58 (de +0,20 a −0,38) | −0,582 | −4,0 | 1,8 | −6,1 |
| momentum | crecimiento compuesto 3m | −1,56 | −3,4 | 3,2 | −3,7 |

Historia: `stable` hasta mayo (score 86), `emerging_deterioration` + `one_off_dip` en junio (68), `not_sustained_by_current_month` en julio (64), `deteriorating` + `trend_deterioration` en agosto (51). El relato que sale de las columnas: *"el margen de los últimos seis meses ha pasado de +0,25 a −0,12; el último trimestre es 0,58 peor que el anterior, casi cuatro veces su variabilidad habitual; el mes actual sigue por debajo; deterioro confirmado desde agosto"*.

## 5. Artefactos

En `data/processed/scores_v2/` (prefijo `company` o `group_currency`): los mismos ficheros que V1 más columnas nuevas en `*_monthly_scores.parquet`: `episode`, `momentum_z`, `current_month_support_z`, `current_month_supports_direction`, `direction_held`, `month_quality_ok`, `level_months`, `op_margin_w`, `op_margin_m1`, `op_margin_sigma`, `op_margin_deviation(_z)`, `is_atypical_month`, `atypical_months_in_window`, `op_margin_q_recent/prior`, `op_margin_qoq`, `op_margin_change_z`, `inflow_growth_q`, `inflow_growth_change_z`. El informe JSON añade `episode`, `latest_episode` y `confirmation_rule`.

## 6. Resultados comparados (19-09-2026, panel empresa)

Detalle y denominadores en `data/processed/evaluation/score_comparison.md` y en decisiones §13.

| Métrica | V1 | V2 |
|---|---:|---:|
| Mediana / p75 / p95 de cambio mensual absoluto | 8,77 / 17,94 / 44,26 | **3,31 / 7,26 / 17,87** |
| Cambios > 10 puntos | 20,0% | **6,5%** |
| Scores exactamente 0 o 100 | 1.617 | **716** |
| Cambio de etiqueta mes a mes | 32,5% | **25,8%** |
| Empresas puntuadas en agosto 2026 | 876 | **922** |
| Filas puntuadas en toda la historia | 15.782 | 14.084 |

En las 13.198 filas comunes, mediana de |Δ| 8,64 (V1) frente a 3,46 (V2); Spearman entre ambos scores 0,79. V2 pierde los dos primeros meses de cada empresa (ventana mínima) y gana meses actuales finos y la ventana de seis meses en agosto.

Trayectorias V2 en agosto (922 puntuadas): 554 stable · 68 emerging_deterioration · 53 emerging_improvement · **19 deteriorating · 15 improving** · 10 mixed · 203 sin momentum. Episodios: 36 one_off_dip, 24 one_off_spike, 22 not_sustained, 19 trend_deterioration, 15 trend_improvement.

**Lo que V2 no mejora, dicho claramente:** frente a los dos proxies independientes disponibles (menciones textuales de estrés en t+1..t+h y caja reconstruida negativa en t+1..t+h), ni V1 ni V2 discriminan: AUC 0,51–0,52 en filas comunes para ambos, con IC95 de la diferencia V2−V1 que incluye 0 en todos los horizontes. La actividad bancaria sola predice las menciones textuales (AUC 0,70 en la dirección "más movimientos, más menciones"), lo que indica que ese proxy mide sobre todo exposición. La persistencia de la caja actual predice la caja negativa futura (AUC 0,86–0,93), pero la caja no es feature de ninguna de las dos versiones. Con la regla independiente de inicio de episodio, V2 confirmado detecta menos inicios que V1 (11% frente a 26% en texto) porque marca menos veces; el lead mediano es de 2,5–3 meses en ambas versiones y las falsas alarmas a seis meses son ≈75% con una tasa base del 20%. **V2 se adopta por estabilidad, explicabilidad y separación bache/tendencia, no por discriminación demostrada.** La comparación con la nota del organizador sigue pendiente.

## 7. Límites y pendientes

- Las ventanas de seis meses retrasan el nivel: una ruptura real tarda 1–3 meses en confirmarse y hasta seis en reflejarse por completo en el nivel. Se acepta a cambio de estabilidad; el momentum y las etiquetas `emerging_*` avisan antes.
- Tras un mes atípico, el trimestre siguiente se compara contra un trimestre que lo contiene: el momentum rebota de forma simétrica (≈ −7 y luego +5 puntos de score en el caso sintético). `atypical_months_in_window` lo señala; no se ha suavizado adicionalmente para no ocultar shocks legítimos.
- σ propia requiere 4 meses antes del trimestre reciente: el momentum existe desde el séptimo mes de historia útil (V1: cuarto). Es la razón principal de los 5.577 `insufficient_history` entre las filas puntuadas.
- Umbrales (`direction_z=1,5`, `atypical_z=2`, `z_scale=2`, histéresis 0,5) elegidos por razonamiento estadístico bajo ruido, no calibrados contra etiquetas; la sensibilidad al umbral está en el comparador (§5 del informe).
- Liquidez como dimensión del nivel (variante D de decisiones §12), fallback de exportación (E) y contacto con Embat siguen pendientes. HHI sigue descriptivo; país sigue eliminado.
