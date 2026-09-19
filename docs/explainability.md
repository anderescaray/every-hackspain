# Explicabilidad del score (V1 y V2)

**Implementado:** contribuciones analíticas exactas, en `data/processed/scores/*_score_explanations.parquet` (V1) y `data/processed/scores_v2/*_score_explanations.parquet` (V2). No se llaman SHAP: no hay un GBM entrenado contra etiquetas. Los detalles del score y su estado están en [scoring.md](./scoring.md), [scoring-v2.md](./scoring-v2.md) y [decisiones.md](./decisiones.md).

## Qué añade V2

- Columna `standardized_value`: el cambio dividido por la volatilidad propia de la empresa (z) que realmente entra en el momentum; `value` sigue siendo el cambio bruto (p. ej. margen del trimestre reciente − anterior). Vacía en la capa de nivel.
- Las contribuciones de momentum ya están centradas (suman exactamente `momentum − 50`) y se reparten con un factor de saturación común `k(z̄)`: cada término conserva el signo de su señal y `final_contribution = 0,2 × contribution`.
- Las features del nivel son agregados de ventana (`op_margin_w`, `debt_service_w`, `ar_delay_w`, `ap_delay_w`, o el indicador `debt_without_inflow_w`); las de momentum son `op_margin_qoq`, `debt_service_qoq`, `ar_delay_qoq`, `ap_delay_qoq`, `inflow_growth_q`.
- El «por qué ha cambiado» tiene ahora columnas propias en `*_monthly_scores.parquet`: `trajectory`, `episode`, `momentum_z`, `current_month_support_z`, `op_margin_w`, `op_margin_q_recent`, `op_margin_q_prior`, `op_margin_m1`, `op_margin_deviation_z`, `is_atypical_month`, `direction_held`. Relato tipo: *"nivel 6m de margen X; trimestre reciente Y frente a Z anterior (k desviaciones propias); el mes actual sigue/no sigue del mismo lado; tendencia confirmada / bache aislado"*. Ejemplo real en [scoring-v2.md](./scoring-v2.md) §4.

El resto de este documento describe la estructura común a ambas versiones.

## Qué explica cada fila

| Campo | Significado |
|---|---|
| Entidad, moneda, mes | La misma clave del score |
| `layer` | `level`, `momentum` o `boundary` |
| `feature` | Fuente realmente utilizada: actual, media3 válida, delta o condición explícita |
| `value` | Valor observado; en el caso de deuda sin entradas, indicador1, no un ratio inventado |
| `feature_score` | Transformación a nota0–100 |
| `effective_weight` | Peso tras renormalizar entre señales disponibles |
| `contribution` | Contribución a nivel o momentum, antes de combinarlos |
| `final_contribution` | Contribución exacta al score final |
| `direction` / `definition` | Orientación y fórmula utilizada; no conclusión causal |

Para cada empresa-moneda-mes puntuado:

```text
score = suma(contribuciones_nivel)
        + suma(0,20 × peso_momentum × (nota_momentum − 50))
        + ajuste_de_recorte_a_[0,100]
```

La suma se valida automáticamente con tolerancia numérica y sin redondear los términos intermedios. La estabilidad es un diagnóstico separado, no otro sumando del baseline.

## Cómo leerlo

- Una contribución de nivel positiva **no significa mejora mensual**: ayuda a formar el nivel actual. Una nota de deuda 0 con su peso es evidencia desfavorable aunque su contribución aditiva sea 0.
- Las contribuciones de momentum están centradas en 50: pueden aumentar o reducir el score. Su suma es `momentum_adjustment`.
- El recorte limita la nota a 0–100, no es una causa financiera.
- Sin componente no hay una supuesta contribución sana. Consultar `level_coverage`, `momentum_coverage`, `component_mask` y `score_status`.
- Sin score por falta de evidencia no se generan drivers ficticios; se explica `score_reason`.

## Por qué ha cambiado

Hay historial mensual de términos para comparar meses, pero no se ha implementado aún un relato automático de «top3 cambios». Una futura interfaz puede comparar contribuciones entre **meses naturales consecutivos con score**, separando cambios del valor financiero, de disponibilidad/pesos y de referencia estadística.

`delta_vs_prev` por sí solo no distingue esas causas. `component_set_changed` y `delta_requires_review` son avisos parciales, no explicación causal exhaustiva. La trayectoria se determina con cambios financieros comparables, no con este delta del score.

Los JSON `*_score_examples.json` incluyen historial y todos los términos de casos ilustrativos del holdout. No son una muestra representativa ni validación predictiva; no hay notas oficiales contra las que afirmar acierto.

## Lo que queda pendiente para el producto

- Etiquetas de negocio y presentación de factores principales sin confundir aporte al nivel con efecto mensual.
- Recorrido de solicitud/expediente/revisión y sus explicaciones de política, distintas de las del score.
- Simulación de escenarios coherentes, si se incorpora: recalcular derivadas desde variables fuente y no prometer causalidad ni aprobación de financiación.
- SHAP u otra explicación adecuada si posteriormente se entrena un modelo supervisado; no reutilizar estos pesos como si fueran los de ese modelo.

No hay anticipación medida en estas explicaciones: un giro del propio score no constituye evidencia independiente de que se anticipó un evento financiero.
