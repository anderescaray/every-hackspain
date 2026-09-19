# Scoring v1 — índice financiero explicable

**Implementado:** primer baseline sin etiquetas oficiales, con nivel 0–100 y tendencia separada. Fuente de verdad: `src/xray/score/`. Estado, resultados reales y decisiones pendientes en [decisiones.md](./decisiones.md).

El usuario ha aclarado que el organizador evaluará nuestros scores frente a resultados que solo él conoce. **No entrenamos un GBM contra un target inventado para aparentar que aprendemos ese score.** Esta versión usa reglas financieras explícitas y una referencia estadística que se fija con grupos y meses anteriores. No es una probabilidad de impago ni una predicción validada a 3/6 meses.

## Ejecutar

```bash
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit
python -X utf8 scripts/04_validate_scores.py --check-prefix 2026-02-01
```

Para grupos, sin mezclar monedas:

```bash
python -X utf8 scripts/03_compute_scores.py fit --panel group_currency
python -X utf8 scripts/04_validate_scores.py --panel group_currency
```

También se admite `--panel company_currency`. El directorio de salida por defecto es `data/processed/scores/`. `fit` significa **ajustar la referencia estadística**, no entrenar con etiquetas.

### Empresas nuevas: no volver a ajustar con el conjunto oculto

Después de ejecutar limpieza/features sobre el nuevo dataset en otra raíz:

```bash
python -X utf8 scripts/03_compute_scores.py predict --features-dir data/hidden/processed --reference data/processed/scores/_company_score_reference.json
```

La ruta `data/hidden/processed` es un ejemplo, no un dataset presente. Se debe mantener el mismo contrato y adaptar coherentemente las fechas de extracción de limpieza/features cuando corresponda. `predict` obtiene la configuración del JSON y no vuelve a calcular cuantiles sobre las nuevas empresas. Pasar la historia mensual completa disponible: un mes aislado no permite reconstruir la tendencia ni verificar el soporte de una media móvil.

API: `fit_reference_bundle(panel, ScoreConfig(...))` y `score_panel(panel, reference)`. La inferencia devuelve scores y explicaciones largas. Claves: entidad, moneda, mes; `group_id` solo determina separación de grupos y balance de referencia, no es una señal financiera. El JSON registra columnas núcleo obligatorias y facturas opcionales: perder una columna bancaria núcleo produce error de esquema, no se disfraza como ausencia de ERP.

## 1. Nivel

Cuatro dimensiones, sin usar saldos retrospectivos, deuda final, texto reservado, ERP ni concentración:

| Dimensión | Peso nominal | Señal |
|---|---:|---|
| Operación | 45% | `(entradas operativas − salidas operativas)/(entradas + salidas)` |
| Servicio de deuda | 25% | `(principal pagado + intereses pagados)/entradas operativas` |
| Cobros | 15% | Mediana de retraso AR realizado: pago − vencimiento |
| Pagos | 15% | Mediana de retraso AP realizado: pago − vencimiento |

No es margen contable ni apalancamiento de balance. Servicio observado cero no demuestra ausencia de deuda. Retrasos realizados tienen sesgo hacia facturas pagadas: no representan toda la cartera impagada.

Margen y servicio usan media de tres meses completos cuando esos meses superan los filtros de calidad; si no, valor actual. Para AR/AP se usa el mes actual con **al menos cinco pagos con vencimiento válido**, acreditados por `inv_ar_delay_count` / `inv_ap_delay_count`, no por el total de pagos. La integración desactiva AR/AP si esos conteos faltan y no usa medias de retraso cuyo soporte temporal no está acreditado.

### Anclas financieras propuestas, no calibradas contra el organizador

Interpolación lineal y saturación en los extremos:

| Señal | Puntos `(valor → nota)` |
|---|---|
| Margen | −1→0; −0,25→20; 0→55; 0,10→75; 0,25→90; 0,50→100; 1→100 |
| Servicio/entradas | 0→100; 0,05→90; 0,15→70; 0,30→40; 0,50→15; 1→0 |
| Retraso AR/AP en días | ≤0→100; 7→85; 15→65; 30→40; 60→15; ≥90→0 |

**Caso especial:** entradas cero con principal + intereses positivos y conocidos → nota de servicio 0, manteniendo su peso. La explicación registra `debt_service_without_inflow=1`, no un ratio ficticio o infinito. Entradas cero y servicio cero/desconocido → componente ausente, no deuda sana.

### Ajuste empírico acotado

Por componente se calculan q10/q90 sobre valores recortados al dominio de las anclas. Cada grupo pesa igual; dentro de grupo cada empresa pesa igual; dentro de empresa sus observaciones pesan igual. La parte empírica interpola 0–100 entre esos cuantiles, invirtiendo la orientación cuando menor es mejor.

`nota_componente = 0,70 × ancla + 0,30 × referencia_empírica`.

Solo se activa con **≥100 observaciones válidas, ≥20 grupos conocidos y dispersión positiva**. Si falta soporte, se usan exclusivamente anclas. El JSON almacena cuantiles, soporte y `empirical_active`; los empates en cero no convierten ausencia de servicio observado en una mala nota.

Se renormalizan pesos entre dimensiones disponibles. `level_coverage` es la suma de sus pesos nominales, no confianza estadística. Un 80 con operación/deuda no equivale en evidencia a un 80 con las cuatro dimensiones; se muestran máscara y pesos efectivos.

## 2. Referencia temporal y empresas no vistas

- Orden de grupos por SHA-256 con semilla fija; 20% de los grupos se reservan completos como holdout. En el dataset actual son 50 de 250, no filiales aleatorias.
- Para puntuar t, cada referencia utiliza solo los grupos restantes y los **12 meses anteriores a t**, nunca el mes t ni su futuro.
- Se guardan todas las referencias mensuales y una para el siguiente mes. Antes de la primera referencia se usan anclas; después del último mes se mantiene la última referencia disponible, sin aprender del batch nuevo.
- La misma empresa y su misma historia deben dar el mismo resultado solas o acompañadas por otras empresas, usando el mismo JSON.
- El holdout permite comprobar transferencia, cobertura y distribución. **No permite medir parecido al score oficial sin sus resultados.**

La referencia puede cambiar entre meses y mover ligeramente el nivel. Por eso la tendencia se calcula con cambios financieros, **no con la diferencia de scores normalizados**. `delta_vs_prev` se conserva como diagnóstico, junto a máscara de componentes y avisos de cambios de cobertura/cuentas.

## 3. Momentum: mejora y deterioro simétricos

Cada señal pasa por `50 + 50 × tanh(orientación × cambio / escala)`:

| Señal | Peso | Escala | Mejora |
|---|---:|---:|---|
| Cambio 3m de margen operativo | 25% | 0,10 | Aumento |
| Cambio 3m de servicio/entradas | 25% | 0,10 | Descenso |
| Cambio 3m de retraso AR | 12,5% | 10 días | Descenso |
| Cambio 3m de retraso AP | 12,5% | 10 días | Descenso |
| Media 3m del crecimiento de entradas en cuentas comunes | 25% | 0,05 | Aumento |

50 = neutral, >50 = mejora relativa de las señales, <50 = deterioro. Los pesos se renormalizan entre señales disponibles y se publica `momentum_coverage`.

Calendario completo por entidad y moneda, sin comprimir huecos. Cuatro meses consecutivos de soporte para deltas3; AR/AP requiere cinco pagos válidos en cada mes. Cuentas comunes exige tres tasas consecutivas y soporte bancario en el mes previo a cada una. Meses con menos de cinco movimientos útiles o rechazados por calidad interrumpen soporte y persistencia.

### Clasificación

- **`improving`:** momentum ≥60 durante al menos dos meses, con alguna señal común que sostenga el signo.
- **`deteriorating`:** momentum ≤40 con la misma confirmación.
- **`watch`:** primer indicio o señales contrapuestas; no equivale a estable.
- **`stable`:** dos meses neutrales con señales comunes sin direcciones significativas enfrentadas.
- **`insufficient_history`:** falta evidencia temporal; no se rellena con 50.

`direction`: up/down/flat/unknown. `trend_months` es firmado: positivo mejora, negativo deterioro. No se confirma un bache en t mirando la recuperación en t+1.

`stability = 100/(1 + dispersión ponderada de cambios estandarizados en tres meses)` es un **diagnóstico de regularidad**, no una nota de salud ni un tercer término del score: una empresa puede empeorar de forma muy estable.

## 4. Score y calidad

`score = clip(level + 0,20 × (momentum − 50), 0, 100)`.

El ajuste de trayectoria está limitado a ±10 puntos y queda visible como `momentum_adjustment`. Si no hay momentum pero sí nivel utilizable, score = nivel y estado provisional; el campo momentum sigue nulo. La estabilidad no penaliza adicionalmente para evitar triple conteo.

Filtros de evidencia del mes actual:

- Al menos cinco movimientos bancarios utilizables.
- Al menos 80% de filas bancarias utilizables y 10% del importe utilizable identificado como operativo.
- Cobertura de filiales observadas igual a 1, en esa moneda.
- Dimensión de operación disponible y peso disponible ≥0,4.

Estos son umbrales de calidad propuestos, no calibración de riesgo. Si fallan, `score=NaN`, `score_status=not_scored` y motivo explícito. Menos de seis meses de historia, falta de tendencia, componentes opcionales ausentes o moneda parcial → `provisional`, sin penalizar financieramente por falta de ERP. No se rellena un mes desconectado con el score anterior.

**Limitaciones:** el score no mide caja real ni todos los aspectos de solvencia; un margen de flujos +1 puede reflejar salidas no observadas. El score primario cubre solo moneda declarada. Las referencias comunes tampoco corrigen automáticamente diferencias sectoriales. Debe iterarse con feedback real del organizador y revisión financiera, no con una distribución objetivo elegida para que resulte atractiva.

## 5. Artefactos y explicación

En `data/processed/scores/`, con prefijo `company`, `company_currency` o `group_currency`:

| Artefacto | Contenido |
|---|---|
| `<prefijo>_monthly_scores.parquet` | Nivel, momentum, score, trayectoria, estabilidad diagnóstica, cobertura, estado, partición y referencia utilizada |
| `<prefijo>_latest_scores.csv` | Universo entidad-moneda observado, incluido si falta su fila del mes final; score nulo sin imputación, `current_month_present`, última fecha puntuable y `staleness_status` current/stale/never_scored |
| `<prefijo>_score_explanations.parquet` | Feature/valor, nota, peso efectivo, definición y contribución exacta al score |
| `<prefijo>_score_examples.json` | Ejemplos ilustrativos del holdout y sus historiales; no son una validación estadística |
| `_<prefijo>_score_reference.json` | Configuración y referencia congelada reutilizable para nuevas entidades |
| `_<prefijo>_score_report.json` | Cobertura, distribuciones, causas de abstención y cohortes; métricas oficiales nulas |
| `_<prefijo>_score_manifest.json` | Hashes, versión de código, configuración, fuentes y modo fit/predict |

Explicación aditiva: contribuciones del nivel + `0,2 × peso_efectivo × (nota_momentum − 50)` + ajuste de recorte a [0,100] = score. No se llaman SHAP: son contribuciones analíticas de esta fórmula. Si se incorpora posteriormente un modelo aprendido, necesitará su explicación propia.

El CSV es un **export genérico de candidatos**, no una submission oficial validada: quedan por confirmar unidad, columnas, mes de corte, escala y tratamiento exigido para entidades sin cobertura suficiente. No se crea un fichero llamado submission para sugerir aceptación inexistente.

## 6. Validación y siguiente iteración

Tests: monotonía financiera, simetría de mejora/deterioro, huecos, mínimo de muestra, cero entradas con deuda, fuente opcional ausente, cambios de composición, referencia congelada, prefijos, serialización, contribuciones exactas, publicación y hashes. El informe no inventa accuracy, probabilidad, correlación con el organizador ni lead time.

Siguiente iteración: revisar casos y cobertura; recibir formato/feedback del leaderboard; comparar variantes predefinidas manteniendo un holdout de grupos. No entrenar un GBM para reproducir nuestra propia fórmula y presentar ese ajuste como generalización a la puntuación oculta.
