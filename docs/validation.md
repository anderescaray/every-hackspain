# Validación — X-Ray

Estado y resultados comprobados: [decisiones.md](./decisiones.md). Esta revisión separa la **validación de datos/features ya implementada** de la **evaluación de modelo todavía pendiente**. Las métricas numéricas ilustrativas del diseño anterior no eran resultados experimentales y se han retirado.

## Implementado

```bash
python -m pytest -q
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
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

## Lo que la validación temporal no demuestra

El dataset contiene estados finales y carece de timestamps de ingestión/revisiones:

- No podemos reconstruir exactamente lo que Embat sabía en t.
- T02 elimina provisionales al encontrar el booked final; F02 elimina cancelaciones finales sin fecha de cancelación.
- Las facturas pueden haberse importado tarde; faltan pagos parciales y fecha de desconexión del ERP.
- Los saldos se reconstruyen desde una foto posterior y no prueban que el libro esté completo.

Por tanto, el test de prefijo protege los cálculos sobre `cleaned`; no certifica un backtest histórico de producción. Los artefactos retrospectivos están fuera de `model_features`.

## Próximo paso: etiquetas y split

Antes de modelar, registrar en decisiones:

1. Unidad que evalúa el leaderboard, formato, etiqueta, horizonte, métrica y desempate.
2. Si no hay etiqueta oficial disponible: elegir 2–3 eventos observables y reglas fijas para t+3 / t+6.
3. Separar columnas reservadas para el target y predictores. Los eventos bancarios están en un fichero aparte para facilitar esa separación.
4. Censurar futuros incompletos y desapariciones de datos. Agosto de 2026 no tiene seis meses de seguimiento; nunca rellenar esa etiqueta con 0.

Split **siempre por `group_id`**, conservando todas las filiales en el mismo fold. Añadir cortes temporales y purgar del train los ejemplos cuyo horizonte de etiqueta atraviese el inicio de validación. Imputación, escalado, selección de columnas y calibración se ajustan solo con train; no usar distribuciones del test oculto.

La selección de `is_training_eligible` garantiza un mínimo de cobertura bancaria, no que exista target ni información suficiente en ERP o en otras monedas. Informar sensibilidad a cobertura parcial y tamaño del universo de entrenamiento.

## Anticipación sin circularidad (pendiente)

Definir **antes** de ajustar parámetros:

- `t_señal`: primer cruce del umbral de alerta del modelo.
- `t_evidente`: evento observable según regla independiente del modelo, sin recurrir al propio score ni a sus features reservadas.
- `lead_time = t_evidente - t_señal`.

Reportar mediana, p25/p75, falsas alarmas con el mismo umbral, cobertura y censura. Una recuperación observada en t+1 puede etiquetar retrospectivamente un bache, pero no puede suprimir en el backtest una alerta que se habría emitido en t.

Comparar momentum(t) con el futuro **score del mismo modelo** sirve como diagnóstico interno, no demuestra anticipación financiera. Tampoco son falsas alarmas las candidatas suprimidas por un filtro.

## Criterio de comunicación

No hay score entrenado, métrica del leaderboard, lead time ni tasa de falsas alarmas verificados todavía. No utilizar cifras de ejemplo en el pitch. Sí se puede mostrar el pipeline, las trayectorias de features, su trazabilidad y los límites de los datos sintéticos.
