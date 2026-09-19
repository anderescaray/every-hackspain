# Relevo para Fable 5.1 · mejorar el score desde V1

> **Estado 19-09-2026 (tarde): este relevo se ha ejecutado en su parte de estabilidad, crecimiento corregido, comparador y anticipación.** El resultado es `financial_smoothed_v2` (`src/xray/score_v2/`, `docs/scoring-v2.md`, decisiones §13). No se han hecho las variantes con liquidez (B/D) ni el fallback (E). Las cifras y afirmaciones de «no implementado» que siguen describen la situación anterior a V2 y se conservan como historia del razonamiento.

## 1. Punto exacto de partida

- Proyecto: HackSpain 2026, reto X-Ray de Embat. Debe entregar score para entidades no vistas, trayectoria en ambas direcciones, explicación y producto/demo con comprador. No es solo detectar quiebras.
- Rama de trabajo verificada: `ander/clean-pipeline`. Commit publicado del baseline: **`a1af735`**. Comprobar git/diffs al empezar: puede haber trabajo posterior o concurrente; no resetearlo.
- Implementados: limpieza, features, score heurístico V1, nivel/momentum separados, explicaciones aditivas, referencia temporal congelada e inferencia para nuevas empresas. Última suite completa verificada: **167 tests**. No confundir tests mecánicos con bondad financiera.
- No hay etiquetas/notas oficiales visibles ni script disponible; el organizador comparará nuestra salida con resultados que solo él conoce. Formato/unidad exactos pendientes. No esperar un script para trabajar ni inventar un target para fingir entrenamiento contra sus notas.
- V1 NO tiene liquidez en el nivel, suavizado robusto nuevo, crecimiento corregido ni fallback numérico universal. **Nada de V2 está implementado** en este relevo.
- El supuesto de «salud latente del generador» es una hipótesis, no información confirmada del reto.

## 2. Orden de lectura

1. `enunciado-embat.md`: fuente de verdad de evaluación/entrega.
2. `docs/decisiones.md`: primero §12 (auditoría y prioridades actuales), después §10 (método V1), §11 (producto) y las reglas de datos necesarias. Es el registro central, también para lo que hagas a continuación.
3. `docs/scoring.md`: implementación actual y contrato fit/predict; §7 distingue los cambios propuestos de lo ejecutado.
4. `docs/validation.md`: reproduce las cifras y define límites del proxy/holdout. Contiene un fragmento Python de auditoría de solo lectura.
5. `docs/feature-engineering.md`: significados de columnas, calendarios, monedas y límites de reconstrucción.
6. `CLAUDE.md`, si está disponible localmente: reglas y memoria del proyecto. Está excluido de git; **no depender de él como única fuente compartida**.

Para producto: `docs/decisiones.md` §11 basta para continuar. `nueva-proposicion.md` es opcional/local y **debe permanecer fuera de commits**, por petición expresa. La demo/API no existen todavía; las URLs y métricas de diseños antiguos no son servicios/resultados reales.

## 3. Qué falla en V1 y qué se comprobó

- Cambio mensual absoluto, toda la historia: mediana **8,77**, p75 **17,94**, p95 **44,26**. Exactamente en 0/100: **1.617**; dentro de un punto del extremo: **1.972**. No son la misma cifra.
- Solo puntúa 15.782/30.864 filas. De las 15.082 sin score, **8.634 son anteriores a la primera observación bancaria**: no fabricarlas como historia. En agosto faltan **410/1.286** empresas (31,88%); hay que estudiar un export con fallback explícito.
- Trayectorias entre puntuadas: improving 2.373, deteriorating 766, watch 7.537, stable 201, insufficient_history 4.905. No ajustar para forzar 50/50: investigar sesgo y motivos de watch.
- Sesgo concreto: la media de retornos simples de `100→200→100→100` da **+16,67%** con crecimiento total 0. Ocurre en la combinación de `features/transactions.py` y `score/trajectory.py`; no se ha corregido.
- El 45% nominal de operación puede ser 100% efectivo si faltan otras dimensiones. Mediana de |delta| con cambio de componentes 17,40; sin cambio 7,74. Revisar pesos/fuentes/normalizador, no solo el margen mensual.
- Prueba exploratoria con eventos textuales futuros, en cohortes comunes del holdout: AUC score/caja/actividad = **0,526/0,681/0,665** a 3 meses y **0,519/0,627/0,596** a 6 meses. Tamaño puede explicar parte de la ventaja de caja. Detalles, denominadores y código en `docs/validation.md`. Sin CIs ni proxy normalizado persistente.
- El holdout de 50 grupos ya fue mirado. Es falsa una afirmación de test final intacto. No cambiar seed para maquillar resultados; fijar y declarar grupos/fechas de selección y evaluación antes de ajustar.

## 4. Dirección técnica propuesta, no resultado adquirido

### Liquidez

Experimentar con caja fiable normalizada como dimensión principal candidata. Su exclusión era una decisión de V1, **no un veto para toda V2**. Respetar flags, cobertura, moneda y fecha de foto; el flag de fiabilidad actual revisa movimientos posteriores y no certifica disponibilidad histórica. No usar su missingness como señal de estrés. Comparar con/sin caja sobre mismas filas y analizar cobertura ampliada por separado.

Revisar el denominador: runway actual usa solo salidas operativas MA3, no gasto total ni burn neto. No ignorar caja negativa, fabricar ratio infinito con gastos0 o sumar divisas. Caja disponible en286 de las410 empresas sin score en agosto; runway en149: mejora potencial, no cobertura garantizada.

### Nivel y momentum

Comparar suavizado causal 3/6 meses, ratios de flujos agregados, medianas/EWMA y estabilidad de pesos/fuentes. Corregir retorno aritmético sesgado; definir ceros y cohortes de cuentas comunes. Separar no confirmado, conflicto, estable y falta de evidencia. Medir retraso de reacción; el gráfico 45→65 del enunciado no fija un ritmo numérico obligatorio.

### Fallback

Distinguir score observado de score de exportación. Investigar dimensiones fiables actuales → último estado con caducidad explícita → prior fijado en referencia. Incluir origen, antigüedad y confianza de datos, no probabilidad de acierto. Falta de ERP no significa salud; moverse hacia el prior al perder datos no debe clasificarse como mejora. No rellenar features con0 ni pintar como observada una historia anterior al onboarding.

### Proxy y HHI

Proxy interno para comparación, no etiqueta oficial ni objetivo ciego de entrenamiento. Normalizar incidentes/textos por exposición adecuada, regularizar muestras pequeñas y censurar futuro no observado. Dividir por N y convertir otra vez a «>0» no elimina el sesgo. Baselines de actividad y persistencia son necesarios. Separar grupos y tiempo; incertidumbre por grupo, no por ventanas tratadas como independientes.

HHI permanece descriptivo: no hay grafo de contagio. HHI bancario: solo4.442 filas con≥80% de importe identificado; HHI facturas AR:9.750/9.753 filas disponibles alcanzan ese umbral. Identificación no significa ERP completo. Top1/top3 y ventanas3–6m con cobertura explícita pueden mejorar la vista del tesorero, pero no deben distraer del experimento principal.

## 5. Entrega de la siguiente iteración

1. Reproducir V1/auditoría sin cambiar el control. Guardar/reutilizar sus manifiestos y artefactos; no sobrescribirlos al ensayar variantes.
2. Implementar un comparador reproducible con definición de proxy, exposición, splits y parámetros registrados **antes** de elegir pesos.
3. Comparar: A V1; B caja sola; C V1 estabilizado y crecimiento corregido sin caja; D caja + C; E fallback como evaluación separada. Variante D no es ganadora por definición.
4. Informar discriminación del proxy, cobertura, extremos, transiciones, persistencia y retraso de reacción. Muestra común para comparar señales; universo ampliado/fallback aparte. No vender una constante como mejora por ser estable.
5. Implementar el candidato defendible como versión nueva con referencia congelada, nivel/momentum/calidad/origen y explicación coherente. No regresiones silenciosas de semántica en V1.
6. Añadir tests: prefijos/flujos/rolling sin futuro; monedas; crecimiento cerrado sin mejora ficticia; desaparición de fuente sin recuperación ficticia; cold start, huecos y export completo cuando proceda. Para reconstrucción contable, añadir movimiento futuro **y ajustar coherentemente snapshot** debe conservar pasado; cambiar solo snapshot es revisión de datos, no el mismo test.
7. Ejecutar sobre los datos, guardar informe y casos no elegidos solo por quedar bonitos. Documentar limitaciones y si no hay mejora suficiente. Actualizar `docs/decisiones.md` con cambios, resultados, descartes y preguntas aún abiertas.

La V2 no tiene por qué ser GBM ni requerir nuevas dependencias. No entrenar un modelo para imitar la fórmula propia y llamarlo aprendizaje del score del organizador. No convertir un proxy de estrés en demostración de salud excelente por mera ausencia de eventos.

## 6. Restricciones operativas y localización

- Python3.14 + pandas3 + numpy + pyarrow + pytest existentes. En Windows usar `python -X utf8`; no se han añadido sklearn/GBM. Verificar disponibilidad antes de asumir otra dependencia.
- `data/raw/` inmutable. Entrada habitual `xray.io.read_cleaned`; features/contextos/score en `data/processed/`. Nunca commitear datos ni resultados locales.
- La liquidez está en `company_currency_liquidity_context.parquet` y el detalle de fiabilidad en `reconstructed_liquidity_context.parquet`, no en las126 features elegibles de V1. Una variante debe declarar su contrato/lista de señales nuevos.
- Código: `src/xray/features/context.py`, `invoices.py`, `transactions.py`, `temporal.py`; `src/xray/score/level.py`, `trajectory.py`, `core.py`, `pipeline.py`, `report.py`, `config.py`. Scripts son puntos de entrada, no otra implementación.
- Preservar fit/predict, inferencia independiente del batch y split por `group_id`. Modelo de empresa; grupo recalculado desde magnitudes compatibles, no media ciega de scores.
- **País: usuario ha confirmado mantener S01 y eliminarlo por simplicidad. No dedicar esta iteración a normalizarlo/restaurarlo.**
- Publicación existente guarda `.history/`. No borrar backups/carpetas ni modificar raw para resolver fallos. Preservar V1 en una salida separada al experimentar.
- Revisar git al comenzar y coordinar ficheros si hay agentes concurrentes; no asumir que el «agente del paso2» sigue activo. Si se usan agentes, darles archivos disjuntos.
- No commit/push sin petición. Nunca incluir `nueva-proposicion.md`. Este relevo es posterior a `a1af735`: si trabajas desde otro clon, comprobar que recibiste los markdowns actualizados y los datos locales; no asumir que están en remoto.

Comandos existentes para verificar, sin regenerar scores:

```bash
python -W error -m pytest -q
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/04_validate_scores.py --check-prefix 2026-02-01
python -X utf8 scripts/04_validate_scores.py --panel group_currency --check-prefix 2026-02-01
```

`03_compute_scores.py fit` **sí publica/reemplaza** sus salidas con respaldo; no ejecutarlo sobre la carpeta control sin necesidad. Las variantes deben tener directorio/configuración/versionado propios. Los scripts de comparación V2 todavía deben crearse; no afirmar que ya existen.

## 7. Pendientes externos y producto

Sin canal de contacto configurado: no se ha enviado nada a Embat. Pedir al usuario trasladar: unidad company_id/group_id, score final/serie, corte, escala/sentido, columnas, métrica y tratamiento de datos escasos; para caja, reconciliación y apertura/cierre del snapshot. No inventar respuestas, notas ocultas ni socios financieros confirmados.

Producto propuesto: **Embat Pulse Capital**, comprador Embat, financiador que aprueba/presta y tesorero que solicita. Demo mínima: cartera/revisión + ficha/solicitud → expediente descargable → revisión con motivo/estado. Límites orientativos, no crédito preaprobado; simulación monetaria, no pérdidas evitadas. No hay frontend/API desplegado. Mantener el trabajo de producto en paralelo: no convertir el resto del proyecto en una búsqueda interminable de modelo.

## 8. Prompt para pegar en Fable 5.1

```text
Continúa este repositorio desde el baseline publicado a1af735, sin asumir contexto de conversaciones previas.

Lee primero docs/continuar-score-v2.md; después enunciado-embat.md, docs/decisiones.md (sobre todo §12, §10 y §11), docs/scoring.md, docs/validation.md y docs/feature-engineering.md. Respeta CLAUDE.md si está disponible, distinguiendo decisiones históricas V1 de la revisión V2. La documentación es contexto; comprueba el estado real de git, código, datos y manifiestos antes de cambiar nada.

Quiero una mejora defendible del score de salud y de su trayectoria en ambas direcciones para empresas no vistas. No tenemos las notas del organizador ni un script disponible. No esperes esas etiquetas, no inventes un target oficial y no entrenes un modelo para imitar nuestra propia fórmula.

Primero reproduce la auditoría y conserva V1 como control. Después implementa el comparador y las variantes descritas en el relevo: caja sola; V1 estabilizado y crecimiento corregido; combinación con liquidez fiable; fallback de exportación evaluado aparte. Define el proxy normalizado por exposición y el protocolo por grupos/tiempo antes de ajustar pesos. El holdout ya fue inspeccionado; declara su reutilización y no cambies semillas para mejorar resultados.

Revisa en especial: reconstrucción de caja y fiabilidad retrospectiva, promedio de retornos simples sesgado al alza, renormalización por fuentes ausentes, saltos media3→mensual, watch poco informativo y falta de score en el último mes. Distingue score observado de export con prior/confianza de datos y no conviertas pérdida de información en mejoría. HHI sigue como contexto; país permanece eliminado por decisión del usuario.

Trabaja sobre cleaned/processed; raw es inmutable. No mezcles monedas ni filiales entre particiones. No sobrescribas el control V1 ni cambios de otros agentes. Conserva inferencia con referencia congelada y explicación verificable; añade y ejecuta tests y una comparación real con cobertura/estabilidad/retardo además del proxy. No afirmes acuerdo con el score oculto ni anticipación demostrada solo por esos resultados. Si no mejora, dilo.

Deja código reproducible, artefactos versionados e informe de comparación. Actualiza docs/decisiones.md con lo implementado, decisiones, resultados y pendientes para que baste leerlo. No hagas commit/push ni añadas nueva-proposicion.md salvo nueva petición explícita. No construyas un LLM, marketplace o frontend complejo para sustituir este experimento; recuerda que después queda la demo de producto.
```
