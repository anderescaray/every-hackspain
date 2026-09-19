# Validación — X-Ray

Estado y resultados comprobados: [decisiones.md](./decisiones.md). Se separan **validación de datos y mecánica del score ya implementadas** de **acierto frente al organizador y anticipación todavía no medidos**. El score v1 es heurístico, no un modelo entrenado contra etiquetas. Las métricas ilustrativas del diseño anterior no eran resultados experimentales.

## Implementado

```bash
python -m pytest -q
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
python -X utf8 scripts/04_validate_scores.py --check-prefix 2026-02-01
python -X utf8 scripts/04_validate_scores.py --panel group_currency --check-prefix 2026-02-01
```

La validación de ficheros comprueba:

- Hashes de las entradas y salidas; mismo manifiesto de limpieza que durante el build.
- Calendario completo septiembre de 2024–agosto de 2026 por unidad y moneda; 30.864 filas en el panel primario de este dataset.
- Unicidad de claves, proporciones en [0,1], importes de entrada/salida no negativos, conteos consistentes y vencido no mayor que abierto.
- Ausencia de infinitos. `NaN` es correcto para datos no observados, ventanas incompletas y denominadores cero.
- Ausencia de snapshots en el panel y correspondencia del catálogo con la allowlist del código.
- Opcionalmente, regeneración hasta un corte anterior y comparación de todas las columnas históricas de los tres paneles para las mismas claves. Las monedas nuevas solo añaden filas vacías antes de aparecer.

Tests sintéticos adicionales: independencia respecto a futuros movimientos/facturas y al saldo final; fechas de pago a cierre y vencimientos conocidos; ventanas naturales con huecos; pendientes OLS y z-score excluyendo t; separación de monedas; ratios de grupo recalculados; cobertura de cuentas; cambios de universo por onboarding; liquidaciones de deuda; preservación de artefactos, rollback y detección de manipulación de Parquet. Repetir el build de la misma fixture produce los mismos hashes de artefactos (el timestamp del manifiesto sí cambia).

El informe `_feature_quality.json` cuantifica missingness y cobertura. **No mide acierto predictivo**.

### Score v1: qué se ha verificado

La suite ampliada tiene 167 tests. Se comprueban monotonía financiera, mejora/deterioro simétricos, confirmación temporal, huecos, deuda positiva con entradas cero, conteos exactos de retrasos, cambio de componentes, columnas núcleo obligatorias, inferencia sin recalibrar y empresas nuevas independientes del batch. Las contribuciones suman el score, los hashes coinciden y un prefijo hasta febrero de 2026 reproduce los scores históricos de empresa y grupo-moneda.

La referencia usa 200 grupos y reserva 50 completos (257 empresas). Cuantiles por mes solo con los 12 meses anteriores; soporte insuficiente implica anclas fijas. Los informes `data/processed/scores/*_score_report.json` muestran distribución, cobertura, causas de abstención y cohortes, con `official_score_agreement`, `predictive_accuracy` y `lead_time` nulos.

El CSV más reciente conserva pares entidad-moneda observados aunque falte la fila del mes final; distingue current/stale/never_scored sin imputar scores. No detecta por sí solo IDs que nunca llegaron al panel: contrastar el universo con el maestro del test. Los hashes son trazabilidad/integridad accidental, no autenticación frente a la modificación coordinada de datos y manifiestos.

La validación detecta fallos mecánicos, no certifica calidad del índice: hay 410 empresas sin score en agosto, muchos scores provisionales y saltos grandes entre meses. Los ejemplos de mejora/deterioro sirven para inspección, no para afirmar éxito frente a una etiqueta oculta.

## Lo que la validación temporal no demuestra

El dataset contiene estados finales y carece de timestamps de ingestión/revisiones:

- No podemos reconstruir exactamente lo que Embat sabía en t.
- T02 elimina provisionales al encontrar el booked final; F02 elimina cancelaciones finales sin fecha de cancelación.
- Las facturas pueden haberse importado tarde; faltan pagos parciales y fecha de desconexión del ERP.
- Los saldos se reconstruyen desde una foto posterior y no prueban que el libro esté completo.

Por tanto, el test de prefijo protege los cálculos sobre `cleaned`; no certifica un backtest histórico de producción. Los artefactos retrospectivos están fuera de `model_features` en V1. La inclusión de liquidez que se investigará en V2 necesita auditoría específica: ese límite de V1 no es una prueba de que reconstruir un saldo sea siempre fuga.

## Auditoría exploratoria posterior a V1: reproducir antes de mejorar

La revisión de solo lectura del 19-09-2026 está consolidada en `docs/decisiones.md` §12. **No hay todavía comparador V2, proxy normalizado persistente ni resultados V2.** Las AUC siguientes miden eventos textuales brutos futuros, no la nota oculta. El holdout ya fue inspeccionado: no llamarlo test final intacto después de usar estos resultados para orientar cambios.

### Protocolo de la comparación existente

- Panel primario empresa-mes, moneda declarada; unir por `company_id,currency,month` score y contexto de caja, y por `company_id,month` eventos reservados.
- `stress_total = sum(stress_*, min_count=1)`: solo para presencia, no para contar incidentes únicos.
- Para h=3/6, etiqueta = algún evento en t+1..t+h; exigir registro en todos los meses futuros. Ausencia de futuro observable → censura, no negativo.
- Subconjunto `reference_partition == holdout`, con score y runway no nulos: la misma muestra para los tres riesgos de cada horizonte.
- Riesgos: `-score`, `-runway` y `log1p(tx_all_currency_count)`. AUC calculada por rangos medios para empates.
- Sin bootstrap, control por tamaño, selección de episodios incidentes ni confirmación semántica del texto. La disponibilidad del saldo es retrospectiva; esta selección puede sesgar la muestra.

| h | Filas | Grupos | Eventos positivos | AUC score | AUC runway | AUC actividad |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 1.398 | 36 | 170 | 0,5261 | 0,6811 | 0,6650 |
| 6 | 973 | 25 | 161 | 0,5185 | 0,6273 | 0,5961 |

La señal del score es débil en esta prueba. El resultado de actividad impide atribuir sin más la mejora de caja a salud financiera. No se ha probado que el score oficial sea un estado latente del generador.

### Fragmento de reproducción, solo lectura

Python desde la raíz del repositorio; usa las dependencias existentes, no sklearn/scipy. Es un fragmento de auditoría, **no un script ya integrado en el pipeline**. No ejecuta fit ni escribe datos. Las rutas y claves corresponden a V1; comprobar manifiestos antes de ejecutarlo si los artefactos han cambiado.

```python
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd() / "src"))
from xray.paths import PROCESSED_DIR

features = pd.read_parquet(PROCESSED_DIR / "company_monthly_features.parquet")
scores = pd.read_parquet(PROCESSED_DIR / "scores/company_monthly_scores.parquet")
liquidity = pd.read_parquet(PROCESSED_DIR / "company_currency_liquidity_context.parquet")
events = pd.read_parquet(PROCESSED_DIR / "stress_events_reserved.parquet")
keys = ["company_id", "currency", "month"]
score_fields = ["score", "trajectory", "reference_partition", "delta_vs_prev", "component_set_changed"]
d = features.merge(scores[keys + score_fields], on=keys, validate="one_to_one")
d = d.merge(liquidity[keys + ["reconstructed_cash", "cash_runway_months_retrospective"]],
            on=keys, validate="one_to_one")
events["stress_total"] = events.filter(regex="^stress_").sum(axis=1, min_count=1)
d = d.merge(events[["company_id", "month", "stress_total"]],
            on=["company_id", "month"], validate="one_to_one")
d = d.sort_values(["company_id", "month"]).reset_index(drop=True)

print("delta", d.delta_vs_prev.abs().quantile([.5, .75, .95]).to_dict())
print("exact_extremes", int((d.score.eq(0) | d.score.eq(100)).sum()))
print("near_extremes", int((d.score.le(1) | d.score.ge(99)).sum()))
print("trajectories", d.loc[d.score.notna(), "trajectory"].value_counts().to_dict())
first = d.loc[d.tx_all_currency_count.gt(0)].groupby("company_id").month.min()
pre_onboarding = d.month.lt(d.company_id.map(first))
print("not_scored", int(d.score.isna().sum()))
print("not_scored_before_first_bank_data", int((d.score.isna() & pre_onboarding).sum()))
print("component_change_delta", d.assign(abs_delta=d.delta_vs_prev.abs())
      .groupby("component_set_changed").abs_delta.agg(["count", "median"]).to_dict())


def auc(y, risk):
    valid = y.notna() & risk.notna()
    y, risk = y[valid].astype(int), risk[valid]
    positives = int(y.sum())
    negatives = len(y) - positives
    if not positives or not negatives:
        return None
    return float((risk.rank(method="average")[y.eq(1)].sum()
                  - positives * (positives + 1) / 2) / (positives * negatives))


for horizon in (3, 6):
    future = pd.concat([d.groupby("company_id").stress_total.shift(-k)
                        for k in range(1, horizon + 1)], axis=1)
    observed = future.notna().all(axis=1)
    y = future.sum(axis=1, min_count=horizon).gt(0).astype(float).where(observed)
    common = (d.reference_partition.eq("holdout") & observed
              & d.score.notna() & d.cash_runway_months_retrospective.notna())
    x, target = d.loc[common], y.loc[common]
    print({"horizon": horizon, "rows": len(x), "groups": x.group_id.nunique(),
           "positives": int(target.sum()), "auc_score": auc(target, -x.score),
           "auc_cash": auc(target, -x.cash_runway_months_retrospective),
           "auc_activity": auc(target, np.log1p(x.tx_all_currency_count))})
```

### Reproducir el contraste de identificación HHI

Banco: dentro del panel primario, seleccionar HHI no nulo y describir `tx_counterparty_known_share`; contar cuántas filas tienen share≥0,8. Resultado: 11.606 HHI, mediana de share0,5135 y 4.442 con ≥0,8.

Facturas: leer `invoices` con `read_cleaned`; filtrar `document_type == invoice`, no `is_possible_duplicate`, `direction == AR`, `issuance_date < 2026-09-01`. Agrupar importe total e importe con `counterparty_id` no nulo por empresa, moneda y mes de emisión. Dividir conocidos/total dentro de cada moneda y unir al panel primario. Entre filas con `inv_ar_counterparty_hhi` no nulo: 9.753 filas, 9.750 con share≥0,8; q25/q50/q75 de share=1. La identificación no mide completitud de sincronización ERP.

## Comparador V1/V2 implementado (19-09-2026)

`scripts/07_compare_scores.py` → `src/xray/evaluation/compare.py` → `data/processed/evaluation/score_comparison.{json,md}`. Protocolo fijado en código antes de mirar resultados; cifras y lectura en `decisiones.md` §13 (SC10–SC11) y `docs/scoring-v2.md` §6.

- **Estabilidad y cobertura:** cambio mensual absoluto (mediana/p75/p95), cuota de cambios >10/>20, extremos exactos y a ≤1/≥99, tasa de cambio de etiqueta entre meses consecutivos puntuados, filas puntuadas, último mes; además sobre las **filas comunes** a ambas versiones.
- **Proxy de texto de estrés** (`stress_events_reserved`): `y = algún evento en t+1..t+h` con los h meses observables (NaN futuro = censura); tasa = eventos / `tx_all_currency_count` de esos meses. Riesgos: −score V1, −score V2, −nivel V2, −momentum V2, −log(1+actividad). AUC global, AUC dentro de terciles de actividad (control de tamaño), Spearman con la tasa, bootstrap por grupos completos (200 remuestreos, semilla 20260919) de AUC V2 − AUC V1. Partición de desarrollo = grupos de referencia; holdout reportado aparte y etiquetado como ya inspeccionado.
- **Proxy de caja negativa futura** (`company_currency_liquidity_context.reconstructed_cash < 0` en t+1..t+h). Independiente del score: la caja no es feature de V1 ni V2. Se eligió caja < 0 (7,5% de las filas con caja) y no runway < 1 (51%, no discrimina). Baselines: actividad y persistencia de la caja actual.
- **Riesgo relativo por etiqueta:** tasa de eventos a 6 meses por `trajectory` y `episode` frente a la etiqueta neutral de cada versión.
- **Anticipación con regla independiente:** `t_evidente` = primer mes con evento tras seis meses observados sin eventos (texto) o primer mes con caja < 0 tras seis con caja ≥ 0; `t_señal` = primer mes marcado en los seis previos; lead = diferencia en meses (mediana, p25, p75), cuota detectada, falsas alarmas = filas marcadas sin evento en los seis meses siguientes (solo con futuro observable). Simétrico para mejora: recuperación = inicio de seis meses limpios tras un evento.
- **Sensibilidad:** cuotas de etiqueta y falsas alarmas de `deteriorating` con `direction_z` 1,0/1,5/2,0.

Resultado resumido: V2 reduce la mediana de |Δ| de 8,77 a 3,31 y los extremos de 1.617 a 716; frente a los dos proxies, ni V1 ni V2 discriminan (AUC 0,49–0,56; IC95 de la diferencia incluyen 0) y la actividad sola explica gran parte del proxy textual. **La estabilidad se ha comprobado; la anticipación está medida desde el 19-09 (D41/D42) y es débil: 32% de detección con 3 meses de mediana y 78% de falsas alarmas.** Tests del comparador en `tests/test_evaluation_compare.py`.

## Diseño de comparación V2 original (ejecutado parcialmente: sin variantes de liquidez ni fallback)

1. Fijar definición del proxy antes de elegir pesos: operaciones/episodios deduplicados, exposición de textos booked observables, semántica y horizontes. Evitar varios términos contados como incidentes diferentes. Nulo futuro sigue censurado.
2. Comparar tasas con regularización para pocos datos, residuos o estratos de exposición. Prior/umbrales solo en desarrollo. Dividir por N y convertir de nuevo a «>0» no elimina sesgo de tamaño. Comparar contra actividad y persistencia además de caja.
3. Mantener grupos completos y purgar solapamientos temporales del horizonte. Identificar los grupos/fechas usados para desarrollo y para evaluación final. El holdout explorado no vuelve a ser virgen cambiando el nombre; no elegir otra semilla por conveniencia.
4. A: V1; B: caja sola; C: V1 estabilizado y crecimiento simétrico, sin caja; D: caja + C; E: fallback de exportación, evaluado separadamente. Todos versionados, mismas filas para discriminación comparativa y cobertura ampliada reportada aparte.
5. Medir estabilidad, extremos, cobertura, transiciones, retraso de reacción y valor incremental del proxy. Si se calculan intervalos, agrupar/resamplear por grupo, no asumir independencia de ventanas solapadas.
6. Testear ciclo `100→200→100→100` sin mejora ficticia; ceros, desaparición de fuente sin falsa recuperación, componentes comparables y pesos estables. La estabilidad de una constante no prueba utilidad.
7. Liquidez: verificar identidad contable, cierre de foto, moneda, cuentas y flags. Adición de movimiento futuro **con ajuste coherente del saldo final** debe conservar el saldo anterior. Cambiar solo el saldo final es una revisión de la historia inferida, no un test de invariancia aplicable. Probar por separado cálculos temporales realmente causales y dependencia retrospectiva de la máscara de fiabilidad.
8. Export completo si el contrato exige un número por entidad, con origen/confianza de datos/antigüedad. No fabricar observaciones previas al onboarding ni interpretar retorno al prior como mejoría. El score interno observado y el score de exportación deben distinguirse.

El comparador persistente y la V2 deben ser entregables nuevos. No modificar `_company_score_report.json` para aparentar que contiene validación oficial, ni sobrescribir el control V1 mientras se comparan versiones. El compromiso del usuario de mantener país eliminado sigue vigente.

## Para una futura variante supervisada: etiquetas y split

No es requisito para ejecutar el baseline. Si se desarrolla predicción de eventos, registrar antes en decisiones:

1. Unidad que evalúa el leaderboard, formato, etiqueta, horizonte, métrica y desempate.
2. Si no hay etiqueta oficial disponible: elegir 2–3 eventos observables y reglas fijas para t+3 / t+6.
3. Separar columnas reservadas para el target y predictores. Los eventos bancarios están en un fichero aparte para facilitar esa separación.
4. Censurar futuros incompletos y desapariciones de datos. Agosto de 2026 no tiene seis meses de seguimiento; nunca rellenar esa etiqueta con 0.

Split **siempre por `group_id`**, conservando todas las filiales en el mismo fold. Añadir cortes temporales y purgar del train los ejemplos cuyo horizonte de etiqueta atraviese el inicio de validación. Imputación, escalado, selección de columnas y calibración se ajustan solo con train; no usar distribuciones del test oculto.

La selección de `is_training_eligible` garantiza un mínimo de cobertura bancaria, no que exista target ni información suficiente en ERP o en otras monedas. Informar sensibilidad a cobertura parcial y tamaño del universo de entrenamiento.

## Anticipación medida (D41/D42) y su protocolo

Definir **antes** de ajustar parámetros:

- `t_señal`: primer cruce del umbral de alerta del modelo.
- `t_evidente`: evento observable según regla independiente del modelo, sin recurrir al propio score ni a sus features reservadas.
- `lead_time = t_evidente - t_señal`.

**Medido el 19-09-2026** (`scripts/11_lead_time.py` → `evaluation/lead_time.{json,md}` y `lead_time_events.parquet`, decisión D41). Evento = primer estrés **propio** (cuota impagada, embargo propio —sin los embargos a terceros de D41—, aplazamiento, descubierto, recargo de apremio, demora) tras seis meses observados sin estrés; señal = primera etiqueta `emerging_deterioration`/`deteriorating` en los seis meses previos, con el umbral vigente de V2 y sin calibrar contra los eventos. Resultado: **153 inicios (142 evaluables, 11 censurados), 45 detectados (32%), antelación mediana 3 meses (p25–p75 2–5), 78% de falsas alarmas y ×1,2 sobre la tasa base**. Por tipo, aplazamiento (41%, 5 meses) y recargo de apremio (50%, 5 meses) son los que más se anticipan.

**Comparación de alertas (D42, `scripts/12_early_warning.py`).** Con el mismo protocolo y sobre los mismos 43 eventos comunes: `runway<1m` detecta el 93% pero está encendida el 53% de los meses (×1,1: alarma trivial); `score_z ≤ −1` detecta 67% con 20% de meses en alarma; a igual coste (~7% de meses) la intersección score+caja detecta 35% frente al 28% del `score_z ≤ −2`, con ×1,5 de lift y 2 meses de antelación. **La caja sola no mejora al score.** Se publica `alarm_rate` justamente para no confundir detección con estar siempre encendido.

**Alerta de presión de deuda (D43).** Iterando solo en 175 grupos de desarrollo y midiendo una vez en los 75 de reserva: el servicio de deuda que se come 5 puntos más de las entradas que la mediana propia de seis meses detecta el **44% de los eventos con el 9% de los meses en alarma, ×1,8 sobre la tasa base y 3,5 meses de antelación** en la reserva (×2,2 y 5 meses en desarrollo). Mejora la alarma vigente del score (43%, 14% de meses, ×1,1) y baja las falsas alarmas del 78% al 65%. Descartadas por no anticipar: interrupción de pagos a Hacienda/Seguridad Social, retraso AP y AR, y todas las votaciones y combinaciones probadas.

Las 123 empresas que dejan de tener datos **no se usan como evento**: 53 cortan de golpe con actividad normal (baja en Embat) y 52 se apagan (cobros al 5%), y el apagado se define con los mismos flujos que alimentan el score, así que validarlo con ellas sería circular.

Reportar mediana, p25/p75, falsas alarmas con el mismo umbral, cobertura y censura. Una recuperación observada en t+1 puede etiquetar retrospectivamente un bache, pero no puede suprimir en el backtest una alerta que se habría emitido en t.

Comparar momentum(t) con el futuro **score del mismo modelo** sirve como diagnóstico interno, no demuestra anticipación financiera. Tampoco son falsas alarmas las candidatas suprimidas por un filtro.

## Criterio de comunicación

Hay dos scores heurísticos ejecutados (V1 control, V2 suavizado) con explicaciones verificadas aritméticamente y un comparador con proxies internos. No hay modelo supervisado ni métrica del leaderboard. El lead time y las falsas alarmas medidos en el comparador son frente a proxies sintéticos (texto de estrés, caja reconstruida) y muestran que **ninguna versión anticipa esos proxies**: comunicarlo así. Sí mostrar los scores, trayectorias, episodios, cobertura, estabilidad y límites reales sobre datos sintéticos.
