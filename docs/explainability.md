# Explicabilidad del score v1

**Implementado:** contribuciones analíticas exactas del baseline financiero, en `data/processed/scores/*_score_explanations.parquet`. No se llaman SHAP: no hay un GBM entrenado contra etiquetas. Los detalles del score y su estado están en [scoring.md](./scoring.md) y [decisiones.md](./decisiones.md).

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
