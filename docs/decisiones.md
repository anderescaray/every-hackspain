# Decisiones del proyecto: datos, score y producto

**Estado al 19-09-2026: limpieza, feature engineering y primer score financiero explicable implementados; ver §10 para método, resultados y límites del baseline.** Este documento es autosuficiente para saber qué está hecho, qué ha cambiado, cómo reproducirlo y qué falta decidir. La lógica ejecutable está en `src/xray/`; los notebooks conservan la evidencia exploratoria, no son otra implementación del pipeline.

## 1. Resumen: qué tienes ya

- `data/raw/` intacto: **los hashes SHA-256 de los 8 CSV coinciden con los existentes antes de esta revisión**.
- Limpieza regenerada: **2.554.288 transacciones** y **876.756 facturas**; no se han añadido eliminaciones de filas a las reglas originales.
- Panel primario: **30.864 filas × 252 columnas**, empresa × mes, septiembre de 2024–agosto de 2026. El 19-09 se añadieron dos contadores exactos de soporte AR/AP (FE09, §10). Contiene importes, ratios, dinámicas y diagnósticos; **no son 252 predictores**.
- Lista explícita de **126 candidatos de modelo**, sin IDs, fotos finales de deuda/saldos, niveles absolutos de vencidas ERP ni concentración descriptiva.
- Paneles auxiliares empresa-moneda y grupo-moneda, eventos reservados y contexto de liquidez/deuda separados.
- **167 tests pasando**, también con warnings tratados como errores; compilación de `src`, `scripts` y `tests` correcta. Incluyen nivel, trayectoria, inferencia congelada, calidad, publicación y contadores FE09.
- **Validación sobre datos completos y prueba de prefijo hasta febrero de 2026 correctas**: regenerar solo hasta ese mes da los mismos valores históricos para las mismas claves en los tres paneles.
- Manifiestos con hashes de inputs, outputs y código real, parámetros y versiones. Copias anteriores preservadas en `.history/`.

**Nuevo: primer score 0–100 con nivel, momentum, trayectoria y explicación aditiva**, exportado para empresa y grupo-moneda. Es un índice heurístico con referencia estadística, no un GBM aprendido contra etiquetas. El usuario aclara que los resultados de referencia solo los tiene el organizador: no esperamos un script/target para ejecutar esta primera versión ni fabricamos etiquetas para imitar un score desconocido.

**Sigue pendiente y no se presenta como hecho:** parecido al score oficial, modelo supervisado, probabilidades/predicción validada 3/6 meses, SHAP, submission aceptada, anticipación medida, monitor de acciones, API o demo. Hay clasificación de trayectoria, no un monitor de producto desplegado. Los artefactos de scores son reales; las métricas/URLs ilustrativas de diseños antiguos siguen sin ser resultados ni servicios comprobados.

**Propuesta comercial revisada, pendiente de aprobación:** `nueva-proposicion.md` plantea Pulse Capital como precalificación y expediente de circulante para Embat: oportunidad → solicitud → revisión, con financiador responsable de aprobar y prestar. Propone licencia B2B/piloto, dos vistas conectadas para la demo y simulación económica sin afirmar pérdidas evitadas. Incluye criterios de aceptación contra cada requisito del enunciado. No hay socio confirmado, crédito preaprobado ni cambios en el pipeline derivados de esta propuesta; las decisiones comerciales quedan pendientes en su §12.

## 2. Lo que tienes que decidir o preguntar

No hace falta resolverlo para regenerar esta v1. Sí antes de cerrar el modelo, la consolidación económica o el pitch.

| Prioridad / ID | Pregunta pendiente | Decisión provisional implementada | Qué desbloquea |
|---|---|---|---|
| 1 · D18 / M01 | Confirmar unidad, escala/sentido, mes de corte, métrica y formato de envío del leaderboard; los resultados oficiales no están disponibles | Baseline ejecutable por empresa y grupo-moneda, referencia congelada para nuevas entidades; CSV genérico, sin submission aceptada | Adaptación de salida y feedback externo. No bloquea el primer score ni autoriza inventar sus etiquetas |
| 2 · D07 | ¿En qué moneda viene `transactions.amount` cuando FX ≠ 1? ¿Cómo convertir y con qué fecha/tasa? | No convertir ni sumar monedas distintas. Excluir FX ≠ 1 y productos desconocidos de importes bancarios | Recuperar cobertura y consolidar grupos/empresas multimoneda |
| 3 · D17 | ¿Último movimiento significa cese, desconexión o baja de Embat? ¿Hay logs de cobertura bancaria/ERP? | Ausencia = dato no observado; no etiquetar cese/churn ni rellenar caja con 0 | Targets de actividad y censura; distinguir deterioro de pérdida de conexión |
| 4 · D11/D13/D22 | ¿Qué representan `paymentDocument`, `invoiceGroup`, `note/refund`, pagos futuros y pagos anteriores a emisión? | Solo facturas estándar; documentos ambiguos fuera; anticipos fuera de DSO/DPO; fechas futuras no son pagos realizados | Facturación neta correcta, abonos y más cobertura de comportamiento de pago |
| 5 · FE06 | ¿La foto de saldos es apertura o cierre del día? ¿Está completo el libro de movimientos? | Asumir cierre del día únicamente en contexto retrospectivo; no usarlo como predictor histórico | Validar liquidez y eventualmente una variante del modelo con saldos auditados |
| 6 · M02 | Si hay que definir target propio, ¿qué 2–3 eventos y reglas fijas se usarán a 3/6 meses? | Eventos textuales reservados en artefacto separado; ningún target construido | Modelo de producto, medición independiente de anticipación y falsas alarmas |

**Cambio de prioridad (SC01):** el primer score ya se calcula sin etiquetas. M01 sirve para adaptar/evaluar la entrega y M02 sería un trabajo posterior si se necesita predicción supervisada de eventos, no un requisito previo del baseline. No aprender un GBM sobre nuestra propia fórmula y llamarlo validación contra el organizador; no evaluar anticipación contra una caída del propio score. Nunca dividir filiales entre referencia y holdout.

## 3. Cómo reproducir y consumir

Desde la raíz del repositorio, con el entorno actual:

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit
python -X utf8 scripts/04_validate_scores.py
python -m pytest -q
```

Comprobaciones ampliadas, ya ejecutadas:

```bash
python -W error -m pytest -q
python -m compileall -q src scripts tests
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
python -X utf8 scripts/04_validate_scores.py --check-prefix 2026-02-01
python -X utf8 scripts/04_validate_scores.py --panel group_currency --check-prefix 2026-02-01
```

`-X utf8` evita problemas con los caracteres del log en consola Windows. Entorno verificado: **Python 3.14.4, pandas 3.0.3, numpy 2.4.6, pyarrow 24.0.0**. No se han añadido dependencias. No se ha verificado esta implementación con pandas 2.x.

`XRAY_DATA_DIR` cambia la raíz de datos. Limpieza acepta `--raw-dir/--out-dir`; features acepta `--cleaned-dir/--out-dir`, `--start-month`, `--end-month`, `--extraction-date`. Para otro dataset no basta con cambiar esta última: la fecha de extracción de la limpieza también está en `xray.paths.EXTRACTION_DATE` y debe adaptarse coherentemente.

Código importable: `xray.features.build_features(tables, FeatureConfig(...))` para cálculo puro y `xray.features.run(...)` para lectura, validación y publicación. La entrada de features usa exclusivamente `xray.io.read_cleaned`, nunca CSV raw.

### Artefactos actuales en `data/processed/`

| Fichero Parquet | Filas × columnas | Uso |
|---|---:|---|
| `company_monthly_features` | 30.864 × 252 | Empresa × mes en su moneda declarada; panel primario |
| `company_currency_monthly_features` | 49.128 × 246 | Todas las monedas observadas hasta el corte, separadas, más la moneda declarada |
| `group_currency_monthly_features` | 15.600 × 245 | Consolidación de flujos por grupo **y moneda**, con ratios/medianas/dinámicas recalculados |
| `stress_events_reserved` | 30.864 × 8 | Conteos de eventos bancarios para estudiar targets; no son etiquetas confirmadas |
| `reconstructed_liquidity_context` | 116.496 × 8 | Cuenta corriente × mes, saldo retrospectivo y fiabilidad; incluye cuentas sin snapshot con valor nulo |
| `company_currency_liquidity_context` | 49.128 × 12 | Caja retrospectiva, cobertura de cuentas, runway y cobertura de vencimientos |
| `debt_snapshot_context` | 2.239 × 10 | Producto de deuda a fecha de extracción, sin inventar historia |

Además:

- `_feature_catalog.json`: `model_features`, tipos y rol por columna; **usar esta lista, no todas las columnas numéricas**.
- `_feature_quality.json`: tamaños, missingness, elegibilidad y cobertura por panel.
- `_feature_manifest.json`: parámetros, versiones, hashes de código y archivos, referencia a la limpieza exacta.
- `data/cleaned/_cleaning_log.csv`: acciones y conteos por regla; `_manifest.json`: hashes de raw y cleaned.

### Cobertura observada, no interpretación financiera

| Medida | Panel primario |
|---|---:|
| Empresa-mes con algún movimiento en la moneda declarada | 20.701 |
| Empresa-mes con algún movimiento utilizable | 20.530 |
| Filas con mínimo de historia/cobertura para modelar | 12.583 |
| Meses finos: entre 1 y 4 movimientos | 2.320 |
| Meses ausentes tras observar historia utilizable | 902 |
| Filas con fuente de facturas observada | 15.821 |
| Filas con cobertura parcial de moneda/FX | 3.064 |

En agosto de 2026: 1.286 empresas, 1.134 con movimientos en moneda declarada, **986 elegibles**, 780 con fuente de facturas observada y 192 con cobertura parcial de moneda/FX. A lo largo de la ventana, 1.253 empresas tienen algún movimiento utilizable en su moneda declarada.

En panel empresa-moneda hay 12.682 filas elegibles; en grupo-moneda, 2.711. La cobertura grupal exige alguna transacción utilizable de cada filial observada hasta ese mes en esa moneda. No confundir una cobertura en número de filas/filiales con porcentaje del valor económico en euros.

El contexto de caja ofrece valor agregado para **15.401 de 49.128 filas empresa-moneda-mes**, bajo sus hipótesis; el resto queda nulo. Esto no demuestra que las demás empresas no tengan caja.

## 4. Arquitectura y trazabilidad

| ID | Decisión vigente |
|---|---|
| A01 | Tres capas: raw inmutable → cleaned → processed. Cada paso escribe solo su capa; rutas solapadas con la entrada/raw se rechazan |
| A02 | Parquet conserva tipos y evita releer el CSV problemático. pandas/numpy existentes; no DuckDB/Polars ni dependencias nuevas |
| A03 | Quitar solo errores evidentes; marcar lo dudoso. La política financiera de uso se aplica en features, no borrando raw |
| A04 | IDs T/F/S para acciones de limpieza, D para decisiones/flags y FE para contrato de features. D ya no significa necesariamente «pendiente»: el estado está escrito abajo |
| A05 | Manifiestos identifican raw, cleaned, fuentes de código incluso sin commit, parámetros y outputs. El commit por sí solo no identifica cambios sin guardar en git |
| A06 | Fuente de verdad en `src/xray/clean/` y `src/xray/features/`; scripts de entrada finos. Notebooks = análisis y justificación |
| A07 · ampliada | Claves únicas/no nulas, integridad empresa/grupo, propiedad de productos conocidos, IDs sin colisión entre banking/debt, fechas obligatorias tipadas y valores monetarios finitos. Huérfanos reales y FX dudoso se marcan en vez de abortar |
| A08 · corregida | Staging + reemplazo atómico por archivo + manifiesto al final + rollback ante excepciones. Versiones previas preservadas en `.history/`; no se borran carpetas ni artefactos de otros pasos |

**Corrección de la garantía anterior:** la implementación original borraba la carpeta destino antes de renombrar, por lo que no era una publicación atómica segura. Ahora se preserva la versión anterior, pero **tampoco se afirma una transacción ACID de toda la carpeta**. `.pipeline.lock` evita publicaciones simultáneas; no ejecutar consumidores durante publicación. Validar hashes antes de consumir. Ante interrupción abrupta, revisar lock y backups manualmente, no borrar a ciegas. Los backups ocupan disco y no se purgan automáticamente.

La sospecha inicial sobre la ruta `ROOT` se descartó mediante test: apuntaba correctamente al repositorio y no se cambió.

## 5. Limpieza: acciones aplicadas que se mantienen

### Transacciones: 2.556.437 → 2.554.288

| ID | Acción | Filas / detalle |
|---|---|---|
| Lectura | Quitar bytes NUL y parser C de pandas | 6 bytes NUL en la exploración original; no reescribir CSV |
| T01 | Quitar `amount == 0` | 369 |
| T02 | Quitar pending con booked de misma empresa, cuenta, importe y concepto a ±5 días | 1.780; conciliación heurística, no historial de estados |
| T03 | Quitar `value_date` | Usar `date`; contiene fechas basura |
| T04 | Categoría `-` o nula → `uncategorized` | 635.424 |

No se eliminan indiscriminadamente movimientos idénticos: la anonimización hace coincidir pagos/comisiones reales. D03 conserva la heurística de meses de resincronización, no deduplicación global.

### Facturas: 897.894 → 876.756

| ID | Acción | Filas / valores |
|---|---|---:|
| F01 | Quitar importe cero | 1.183 |
| F02 | Quitar `status == cancel` | 13.583 |
| F03 | Quitar `deliveryNote` / `purchaseOrder` | 6.372 |
| F04 | Anular `payment_date` si no está paid | 219.367 |
| F05 | Anular due/payment fuera de 2020–2030 | 208: 198 vencimientos y 10 pagos |
| F06 | Añadir `direction`: positivo AR, negativo AP | Todas |

La emisión y el nominal sobreviven a un vencimiento imposible: no se borra la factura por ese motivo. Eliminar cancelaciones finales es una limitación de reconstrucción histórica porque no hay fecha de cancelación.

### Tablas pequeñas

- S01: fuera `companies.country` (82% nulo y no normalizado). **Revisión del 19-09, mejora pendiente, no aplicada en este commit:** auditoría de solo lectura confirma 1.056 nulos de 1.286 empresas (82,1%); 230 tienen país, 170 corresponden a variantes de España, y la cobertura alcanza 62 grupos. Como separación de capas, es preferible conservar el valor original y normalizar variantes inequívocas a `country_iso2` (ES/España/Espanya/Spain → ES; Portugal/PT → PT…), manteniendo desconocidos como nulos, sin inferir país por moneda. Eliminarlo en cleaned fue una simplificación reversible del MVP (raw lo conserva), no una demostración de irrelevancia. El score actual sigue sin usar país; una correlación con sus propias notas no demostraría valor frente al organizador. Antes de incluirlo, revisar cobertura/sesgo y validar su aportación por grupos cuando exista referencia adecuada. No se modifica ahora S01 ni se regenera el pipeline: se priorizan cobertura/estabilidad del score y demo.
- S02: fuera `label/service` de productos bancarios/deuda (metadatos técnicos redundantes para esta v1).
- S03: fuera `balances.available` (100% nulo). El resto de columnas dudosas se conserva.
- S04: fuera `debt_schedule_config.amortization_type` (constante).

## 6. Decisiones D: estado vigente y cambios

**«Aplicada v1» significa política implementada, no confirmación de Embat ni verdad económica definitiva.** Todos los flags se conservan en cleaned. Las cifras son de la última ejecución completa.

### Transacciones

| ID | Estado y decisión implementada |
|---|---|
| D01 · extremos | Aplicada v1: `is_extreme_amount`, 491 filas, umbral absoluto >100.000.000 **unidades nominales**, no EUR convertidos. Excluir de flujos. En contexto de reconstrucción, un extremo posterior al cierre invalida el tramo; no se borra para cuadrar artificialmente un saldo |
| D02 · relativos | **Revisada y aplicada:** 253 → **433** flags. Antes era ×20 p99 de toda la historia de la empresa, con fuga temporal y mezcla de monedas. Ahora: ×20 p99 de los **6 meses completos anteriores**, empresa-moneda, booked, FX=1, no extremos; mínimo 100 filas. Sin historia suficiente no se marca por esta regla. Excluir de flujos |
| D03 · resincronización | Aplicada v1: 30.119 flags. Mismo criterio anterior: ≥50% de filas pertenecen a duplicados en empresa-mes y ≥20 filas; marcar repeticiones tras la primera. Excluir de flujos. Sigue siendo heurístico |
| D04 · propios | **Revisada y aplicada:** 63.642 → **55.444** flags. Espejos +X/−X del mismo día, moneda conocida igual, cuentas distintas, booked, FX=1 y sin D03. Emparejamiento uno a uno por orden; conservador, puede omitir parejas reales. Fuera de flujos operativos; dentro del saldo de cada cuenta |
| D05 · intragrupo | **Revisada y aplicada:** 90.418 → **85.902** flags. Misma moneda, grupo y día, **empresas distintas**, sin reutilizar pares D04. Fuera del operativo tanto por empresa como por grupo: es financiación/tesorería interna, no ventas externas. Se informa aparte; dentro del saldo de cuenta |
| D06 · producto desconocido | 1.313 flags. **Cambia la recomendación anterior:** no incluir en importes sin saber moneda ni cuenta. Sí contar como cobertura perdida; fuera de reconstrucción |
| D07 · moneda/FX | Pendiente de Embat. Provisional: no conversión; solo FX=1 para importes bancarios. Ratios tampoco son invariantes si antes se mezclan monedas. Ver FE02 |
| D08 · bloques de negocio | Aplicado el mapeo explícito de FE03. `uncategorized` no se convierte en ingreso operativo. No se recategoriza texto libre; solo se recupera un token inequívoco de contraparte para contexto |
| D09 · conciliación | Aplicada: `accounting_status` no es feature del score. No se confunde conciliación contable con booked/pending bancario |
| D19 · codificación | Aplicada: no inventar caracteres perdidos `�`. Búsqueda de eventos ASCII; no reparar textos sin origen recuperable |

Los porcentajes exploratorios antiguos sobre sumas brutas de importes no son importes consolidados en euros: había monedas mezcladas. Se conservan las muestras/notebooks como evidencia del problema, no como magnitudes monetarias del producto.

### Facturas

| ID | Estado y decisión implementada |
|---|---|
| D10 · duplicados | **Revisada y aplicada:** 18.534 → **18.439** flags. La clave incorpora moneda además de empresa, contraparte, tipo, fechas, importe y concepto. Excluir duplicados marcados de las métricas. No mezclar USD/EUR idénticos |
| D11 · documentos | 75.900 ambiguos marcados. **V1 más conservadora que la propuesta anterior:** solo `invoice`. `invoiceGroup` podría duplicar facturas individuales; `note/refund` necesitan saber si son abonos de AR/AP. No sumar por signo sin esa semántica. Pregunta abierta a Embat |
| D12 · plazos | Aplicada: 20.412 anómalos. Cuentan en emisión, no vencimientos/aging/retrasos. Plazo inválido si falta fecha, es negativo o supera 365 días |
| D13 · pagos futuros | **Corregida:** 18.237 → **19.476** flags. Después del día de extracción, no extracción + 1 día. Cualquier hora del propio día de extracción es válida para el flag. Abiertas hasta su fecha indicada; no generan estadísticas de pagos realizados en meses anteriores |
| D14 · stale pending | 3.068 flags conservados como auditoría de extracción. **No** convertirlos en un estado overdue histórico: se reconstruye vencimiento en cada cierre |
| D20 · overdue | Aplicada: nunca usar status final. Ratios de vencidas se reconstruyen; niveles absolutos y sus medias móviles son descriptivos, fuera de `model_features`. Se seleccionan cambios, pendientes, volatilidad y z-score contra historia propia |
| D22 · pago anterior a emisión | **Nueva:** `is_payment_before_issuance`, **19.068** filas. Se conserva la fecha (puede ser anticipo), pero no se calcula DSO/DPO/retraso con ella. Según su fecha, la factura puede estar ya liquidada al emitirse |

### Saldos, FX y cobertura

| ID | Estado y decisión implementada |
|---|---|
| D15 · columnas de saldo | Aplicada: `countable/liquidity/granted` de balances permanecen pero no se usan; no mezclar significados bancarios distintos |
| D16 · huecos | Aplicada: calendario fijo; importes bancarios NaN sin movimientos utilizables; flags de mes fino, historia y falta de datos. Elegibilidad = 6 meses consecutivos utilizables + ≥5 movimientos utilizables actuales + cobertura de filiales observadas igual a 1 |
| D17 · desaparición | Pregunta abierta. Se conserva la cola con NaN y meses desde última observación; ni cese ni ceros. No usar el último mes global como predictor |
| D18 · unidad | Pregunta abierta. Hay features y score por empresa y grupo-moneda; no existe aún un score único de grupo multimoneda ni conversión FX |
| D21 · deuda final | Aplicada: `outstanding/granted/liquidity` solo como contexto a extracción. Deuda pagada/intereses observados sí son features mensuales. No se repite el saldo final en toda la historia; no se proyecta el cuadro de amortización |
| D23 · FX inválido | **Nueva:** `has_invalid_exchange_rate`: **77 transacciones y 3.311 facturas** con tasa nula, no finita o ≤0. No imputar. Excluir del importe bancario; factura en su moneda explícita puede aportar nominal sin conversión |
| D24 · saldo sin producto | **Nueva:** `balances.is_unknown_product`: **29** filas. Conservar, pero no agregar sin moneda ni reconstruir cuenta desconocida |

## 7. Contrato de feature engineering

### FE01 · Tiempo, ausencia y cobertura

24 cierres completos: **2024-09 a 2026-08**. `month` se etiqueta con el primer día, pero representa hechos hasta el cierre. Se genera el calendario completo para que shift(3) sean tres meses naturales; nunca pegar meses separados por huecos. Septiembre de 2026 solo se utiliza al anclar el contexto de saldos, no como mes mensual completo.

Los conteos sin registros son 0; importes/ratios sin datos son NaN. Si hay movimientos válidos pero ninguno operativo, el operativo puede ser 0. Si todos fueron excluidos por calidad, no fabricar un 0. No imputar features ni scores neutrales. `is_training_eligible` no garantiza etiqueta futura ni todas las monedas cubiertas.

Cobertura: cuentas activas y nuevas observadas, fracción de filas anteriores a conexión, meses desde última transacción, filas usables/observadas, empresas del grupo usables/esperadas y moneda declarada/total. Son contexto de calidad, no predictores por defecto. Se usa `created_at` como diagnóstico, sin afirmar disponibilidad en tiempo real de histórico importado antes de la conexión.

### FE02 · Moneda y agregación

Moneda de transacción = moneda conocida de su producto solo cuando FX=1. Panel primario = moneda de `companies`; los importes **no** representan toda la empresa cuando existen otras monedas. Los paneles auxiliares permiten analizarlas sin mezclarlas. Las facturas se conservan en su `currency`; no se usan tasas dudosas para convertir a moneda contable.

Grupos: agregar filas/obligaciones por moneda y recalcular ratios/medianas antes de calcular dinámica; **no** promediar ratios o percentiles de filiales. Cobertura esperada = filiales observadas hasta t en esa moneda, no tamaño futuro final del grupo. Los universos auxiliares pueden añadir monedas nuevas; sus filas anteriores son vacías, no un alta histórica.

### FE03 · Flujos de caja y operación

Filtro base: booked, FX=1, producto conocido, sin D01/D02/D03/D06. Mapeo por signo y categoría:

| Métrica | Definición |
|---|---|
| `tx_cash_inflow/outflow` | Entradas/salidas utilizables de cualquier categoría, incluyendo tesorería; no se llaman ventas |
| `tx_inflow` | Positivos `collection`, `bulk_collection`, `pos_settlement`, `cash_settlement(s)`, `payment_refund`, `tax_refund`; sin D04/D05 |
| `tx_outflow` | Absoluto de negativos `payment`, `bulk_payment`, `utility`, `salary`, `social_security`, `tax`, `collection_refund`; sin D04/D05 |
| `tx_fixed_cost` | Negativos salary/social_security/tax/utility; proxy de gasto recurrente, no contabilidad de costes fijos |
| `debt_principal_paid`, `debt_interest_paid` | Negativos debt_repayment/interest_charge; excluir D05, **conservar la pata negativa D04**: liquidar deuda entre productos propios no elimina el servicio de deuda |
| `tx_fees_paid` | Negativos fee, sin D04/D05 |

Transferencias, inversión, retiradas de efectivo/TPV y sin categoría no se imputan como ventas/gasto operativo. El neto operativo = entrada − salida. Se conservan importes de sin categoría/internos/intragrupo como contexto.

Ratios: margen neto/(entrada+salida), entrada/salida, entrada/gasto recurrente, servicio de deuda/intereses/comisiones sobre entrada. Denominador ausente o ≤0 → NaN, no infinito. No son ratios contables de balance.

`tx_lfl_inflow_growth` compara entradas de **las mismas cuentas con datos en t y t−1**; una nueva cuenta no se interpreta automáticamente como crecimiento. No garantiza que la sincronización de esas cuentas sea completa.

### FE04 · Facturas históricas aproximadas

Solo `invoice` no duplicadas. Nominal y dirección AR/AP; emitido/recibido en mes de emisión. Antes de observar fuente estándar: NaN. Después puede haber emisión 0 sin facturas nuevas, **bajo la hipótesis explícita de continuidad del ERP**; no verificable sin logs. Si solo hay documentos excluidos, no se fabrican ceros.

Al cierre t se consideran solo emisiones anteriores a t+1. Abiertas = sin fecha real de pago o con pago en/después de t+1. `paid` con fecha anulada es liquidación desconocida: excluirla del stock, informar su conteo. Se aproxima pendiente por nominal completo hasta pago: **no existe histórico de pagos parciales**. No usar `pending_amount`, `status == overdue` ni D14 como features históricas.

DSO/DPO realizado = mediana de **pago − emisión**, acotado 0–365; retraso = **pago − vencimiento**, acotado −60–365, mediana/p90/proporción tardía. Se agregan **en mes de pago**, no en mes de emisión. Excluir pagos futuros/anteriores a emisión; para retrasos también vencimientos anómalos. Este DSO/DPO realizado no es una estimación contable sobre toda la cartera: hay sesgo hacia facturas que sí se pagan.

Aging: nominal abierto, vencido y vencido >90 días. Vencer el propio día de cierre no cuenta como días de retraso. Ratio vencido = vencido/abierto con vencimiento válido; se informa cobertura de vencimientos. Obligaciones próximas 30/60/90 días: solo facturas ya emitidas y abiertas, nunca facturas futuras. También ratio de próximos 30 días sobre emitido/recibido actual, con NaN si denominador 0.

### FE05 · Nivel, dinámica y estacionalidad

Bases: entradas, salidas, neto, margen, carga de deuda/intereses, emitido/recibido, DSO/DPO y vencido AR/AP.

- `_ma3/6`, `_std3/6`: media/desviación poblacional de 3/6 meses naturales, incluido t; ventana completa requerida.
- `_slope3/6`: pendiente OLS por mes, ventana completa.
- `_delta1/3/6`: t − t−k, sin rellenar huecos.
- Importes: cambios divididos por absoluto del valor previo (`_change*_scaled`) y pendiente dividida por absoluto de media de ventana (`_slope*_scaled`).
- `_zscore_prior6`: contra t−6..t−1, **sin t**, mínimo 3 observaciones válidas dentro de esa ventana; sin desviación positiva → NaN.
- `_yoy_change`: cambio relativo contra t−12; sin referencias futuras. Mes del año como covariable estacional.
- Volatilidad std3/std6 y número de meses con neto negativo en seis meses completos.

No se estima curva estacional ni percentiles usando toda la muestra. No se aprenden imputadores, winsorizadores o escaladores en esta capa: ajustar solo en train, con split por grupo. Los 126 candidatos son una base inicial, **no una selección validada predictivamente**.

### FE06 · Liquidez y deuda separadas

Cuentas `checking`: `saldo(cierre) = saldo_foto − movimientos posteriores hasta el día de la foto`. Se mantiene D04/D05; no se sustituye por cashflow operativo. Se incluyen movimientos del 1 de septiembre al reconstruir agosto por la hipótesis de foto **al cierre del día**. Para las 16 fotos anteriores al 1 de septiembre se respeta su fecha, sin extrapolar hacia adelante.

Fuera pending y duplicados de sincronización. Tramos posteriores con extremos/outliers, FX ambiguo, duplicados o estados no booked → no fiables, saldo NaN. Sin snapshot, antes de observar cuenta o con foto anterior al cierre → NaN. Una cuenta sin flags aún puede tener movimientos omitidos: **la integridad bancaria no está demostrada**.

Caja agregada solo cuando todas las cuentas corrientes conocidas a ese cierre en esa moneda son reconstruibles. Runway = caja/salidas operativas medias 3m, no burn neto ni gasto total. Cobertura AP = caja/vencimientos conocidos 30d, exigiendo cobertura de fechas. Todo esto está en contexto retrospectivo, fuera de predictores históricos.

Deuda final: invertir signo de outstanding/granted para deuda positiva, utilización solo si concedido >0; signos inesperados marcados. No inferir saldo 0 en empresas sin deuda reportada ni repetir snapshot 24 meses. No usar balances.available (eliminada) ni proyectar las 87 configuraciones de amortización como si fueran historia conocida.

### FE07 · Contrapartes y eventos reservados

Concentración HHI de cobros operativos identificados + cobertura del importe conocido; ID explícito o un único token `COUNTERPARTY_n` del texto. IDs locales a cada empresa; no se infiere contagio entre clientes. HHI de facturas también descriptivo. **Fuera de la allowlist**, no un score sobre las contrapartes.

Eventos booked no duplicados de sincronización: EMBARGO, IMPAGADO, APLAZAMIENTO, DESCUBIERTO/EXCEDIDO y DEMORA. Solo conteos reservados: texto coincidente no demuestra un impago ni define una etiqueta. Mes sin booked observable → NaN. Si se usan para targets/regla de evidencia, no reutilizar esas señales como predictors del mismo horizonte.

### FE08 · Límites temporales y validación

Los tests de prefijo e inserción de registros futuros evitan anticipación accidental **en las transformaciones de cleaned**. No recuperan timestamps de ingestión, revisiones ERP ni eventos eliminados por estados finales. T02 y F02 ya dependen del snapshot; tampoco hay pago parcial histórico. No prometer un backtest de disponibilidad real a partir de estas pruebas.

Validación automática: hashes, claves/calendario, conteos y signos coherentes, proporciones en [0,1], vencido ≤ abierto, ausencia de infinitos y snapshots fuera del panel. Se prueba publicación/rollback, conservación de ficheros ajenos, determinismo en fixtures y rechazo de outputs manipulados. La regeneración real hasta 2026-02 pasó para empresa, empresa-moneda y grupo-moneda.

## 8. Qué se cambió frente a los markdowns anteriores

- CSV/DuckDB/Polars → lectura de cleaned con pandas/numpy existentes.
- Septiembre de 2026 mensual → **agosto como último mes completo**.
- Ceros universales en calendario → missingness explícita.
- Sumar todo importe positivo → flujos operativos explícitos, moneda separada y cobertura.
- Outlier con historia completa → referencia de meses anteriores por moneda.
- Supuesto «ratio de empresa independiente de FX» → rechazado si se mezclan monedas antes de dividir.
- DSO/DPO como retraso contra vencimiento → separar plazo realizado desde emisión y retraso.
- `pending/overdue/pending_amount` finales en meses pasados → reconstrucción aproximada a cierre.
- Deuda final constante / saldo inicial 0 → snapshots y reconstrucción fuera del panel de entrenamiento.
- Percentiles de toda la muestra → aplazar transformaciones aprendidas a train.
- Concentración como riesgo de red → contexto local descriptivo.
- Supresión de alertas con t+1 / anticipación contra caída del propio score → no válida para evaluación causal; diseño futuro debe usar regla independiente.

`docs/feature-engineering.md` y `docs/validation.md` reflejan la implementación. `docs/README.md` y README raíz tienen comandos actuales. Los otros diseños llevan aviso explícito de estado. `CLAUDE.md` local incorpora notas de continuidad para próximas sesiones; las decisiones compartibles están todas aquí.

## 9. Siguiente trabajo, en orden

1. Revisar scores, ejemplos y abstenciones de §10. El índice existe; no es necesario fabricar un target para producir esta primera entrega.
2. Confirmar formato/unidad/escala del envío y recibir feedback del organizador. Sin sus resultados no hay MAE, correlación ni acierto oficial que reportar.
3. Investigar cobertura baja, saltos de nivel, dependencia de componentes opcionales y moneda incompleta. Comparar variantes predefinidas con un holdout fijo, no ajustar para que la distribución parezca bonita.
4. En paralelo, cerrar el alcance de producto de §11 y desplegar cartera + ficha + solicitud/revisión. Backend/API solo si hace falta persistencia multiusuario; una demo estática con estado local declarado sirve para el primer recorrido.
5. Si después se quiere un modelo supervisado de eventos, cerrar M02, censura, split temporal/purga y SHAP. Ese modelo no aprendería automáticamente a imitar el score oculto. Medir anticipación contra una regla independiente antes de prometer 3/6 meses.

## 10. Primer score ejecutable — 19-09-2026

### SC01 · Qué se ha decidido y qué NO se ha aprendido

A petición del usuario, primer intento de score comparable conceptualmente a la salud financiera evaluada por los organizadores, aunque sus resultados no están disponibles. **`financial_baseline_v1` es un índice explícito, no un GBM ni una probabilidad.** Usa pocas señales financieras defendibles y una referencia robusta. No entrenar un modelo sobre nuestra propia fórmula y venderlo como aprendizaje de su resultado oculto.

Implementación en `src/xray/score/`: nivel y tendencia se desarrollaron en paralelo, con auditoría independiente e integración/tests. No hay nuevas dependencias ni cambios adicionales en cleaned. La única ampliación de features es FE09.

### FE09 · Soporte exacto del retraso de facturas

Se añaden `inv_ar_delay_count` e `inv_ap_delay_count`: número de facturas pagadas en el mes con vencimiento válido, exactamente las que forman la mediana de retraso. `inv_*_paid_count` incluye pagos con vencimiento anómalo y **no era un denominador válido** para ese propósito. Se mantienen todos los importes y features anteriores; los paneles pasan de 250/244/243 a **252/246/245 columnas**. Siguen siendo 126 candidatos del catálogo: estos dos campos son calidad, no salud.

### SC02 · Nivel financiero 0–100

Pesos nominales: operación 45%, servicio de deuda 25%, retraso AR 15%, retraso AP 15%. Se renormalizan solo entre componentes disponibles, nunca se interpreta ausencia de ERP como puntualidad. `level_coverage` y `component_mask` muestran qué sostiene el resultado; no son confianza estadística.

Anclas propuestas con interpolación lineal y saturación:

| Señal | Valor → nota |
|---|---|
| Margen de flujos `(entrada−salida)/(entrada+salida)` | −1→0; −0,25→20; 0→55; 0,10→75; 0,25→90; ≥0,50→100 |
| Servicio observado/entradas | 0→100; 0,05→90; 0,15→70; 0,30→40; 0,50→15; ≥1→0 |
| Retraso AR/AP realizado, días pago−vencimiento | ≤0→100; 7→85; 15→65; 30→40; 60→15; ≥90→0 |

Margen/servicio usan media3 solo si hay tres meses naturales con calidad suficiente; si no, valor actual. AR/AP usan valor actual y ≥5 retrasos válidos según FE09. Sin conteo exacto, el pipeline desactiva el bloque; no usa una media3 de retrasos sin soporte de ventana verificado.

**Caso límite corregido:** entradas cero y principal/intereses conocidos con suma positiva → componente de servicio nota0, con su peso. Explicación `debt_service_without_inflow=1`, no un ratio inventado/infinito. Entradas cero y servicio cero/desconocido → componente ausente. Servicio observado cero no prueba ausencia de deuda; tampoco el margen de flujos es margen contable.

### SC03 · Referencia para empresas nuevas y holdout

- 200 grupos de referencia / 50 holdout, elegidos por orden hash SHA-256 con semilla 20260918. Todas las filiales de un grupo van juntas. Universo del split fijado antes de evaluar; no cambiarlo entre variantes.
- Para cada mes t, ajustar solo con grupos de referencia y los 12 meses anteriores, excluyendo t. Cada grupo pesa igual, cada empresa dentro de grupo igual y sus observaciones igual.
- q10/q90 de cada señal, recortada al dominio de sus anclas, definen una interpolación empírica 0–100 orientada a salud. Mezcla **70% anclas + 30% referencia** únicamente con ≥100 observaciones válidas, ≥20 grupos conocidos y dispersión positiva; antes, solo anclas.
- El JSON guarda el calendario de referencias, parámetros, soportes y contrato de columnas núcleo/opcionales. `predict` no ajusta cuantiles con las empresas nuevas. Una columna bancaria núcleo ausente es error de esquema, no componente opcional; ERP ausente sí se permite y se señala.
- Las referencias cambian mensualmente según información anterior, de modo que el nivel puede variar algo por su escala. La tendencia se calcula con cambios financieros, no por diferencias de ese nivel normalizado. No comparar variantes cambiando a la vez el universo de referencia.

**Holdout no equivale a accuracy:** solo podemos verificar cobertura, distribución y mecánica de transferencia. No tenemos notas oficiales, PD, LGD ni pérdidas realizadas.

### SC04 · Mejora/deterioro y score final

Momentum: `50 + 50*tanh(orientación*cambio/escala)` por señal, media ponderada entre señales disponibles:

| Cambio | Peso | Escala | Mejora |
|---|---:|---:|---|
| Margen t−t−3 | 25% | 0,10 | Sube |
| Servicio/entradas t−t−3 | 25% | 0,10 | Baja |
| Retraso AR t−t−3 | 12,5% | 10 días | Baja |
| Retraso AP t−t−3 | 12,5% | 10 días | Baja |
| Media3 de crecimiento de entradas en cuentas comunes | 25% | 0,05 | Sube |

Necesita cuatro meses consecutivos con soporte para deltas; para facturas, ≥5 retrasos válidos en cada mes. Crecimiento comparable exige tres tasas válidas y sus meses previos. Meses con menos de cinco movimientos utilizables o rechazados por calidad interrumpen soporte y persistencia. No hay interpolación de huecos ni t+1.

- `improving`: momentum ≥60 confirmado dos meses, con señal común que sostenga el signo.
- `deteriorating`: ≤40 con la misma confirmación.
- `watch`: señal inicial o señales contrapuestas; no forzar estable.
- `stable`: dos meses neutrales con señal común y sin direcciones significativas enfrentadas.
- `insufficient_history`: tendencia no calculable. `direction` conserva up/down/flat/unknown; `trend_months` positivo/negativo indica persistencia de mejora/deterioro.

**Score = clip(nivel + 0,20 × (momentum−50), 0, 100)**: ajuste máximo ±10 puntos. Si falta momentum, score=nivel con estado provisional; momentum permanece NaN, no se finge neutralidad. `stability` es un diagnóstico de regularidad de cambios, no otro sumando: una caída sostenida puede ser muy regular.

### SC05 · Calidad, abstención y explicación

Mínimos actuales: ≥5 transacciones utilizables; ≥80% de filas bancarias utilizables; ≥10% del importe utilizable identificado como operativo; cobertura de filiales observadas en esa moneda =1; operación disponible y peso observado ≥0,4. Son umbrales de evidencia elegidos técnicamente, no calibrados contra el organizador.

Si fallan → `not_scored`, score nulo y motivo. Si hay nivel pero poca historia (<6 meses), tendencia desconocida, componentes opcionales ausentes o moneda parcial → `provisional`, sin castigo financiero por falta de datos. `scored` indica soporte completo según estos criterios, **no aprobación crediticia ni calidad predictiva demostrada**.

Las contribuciones suman exactamente el score: términos del nivel + términos centrados del momentum + ajuste de recorte. Son explicaciones analíticas, no SHAP. Máscara de componentes y `delta_requires_review` avisan de cambios de cobertura/cuentas; **no son detectores exhaustivos de todos los saltos**. `delta_vs_prev` puede mezclar cambios financieros, fuentes disponibles y normalización, por eso no sustituye a momentum.

CSV de último cierre: conserva entidades/monedas observadas aunque les falte la fila del mes final, sin arrastrar el score anterior. `current_month_present`, `last_scored_month`, `is_stale` y `staleness_status` distinguen actual, obsoleto y nunca puntuado. No puede inventariar IDs que nunca aparecieron en la entrada; el universo esperado del test se deberá contrastar con su maestro.

### SC06 · Archivos y uso

Directorio: **`data/processed/scores/`**. Se han ejecutado empresa y grupo-moneda; el código también admite empresa-moneda.

- `company_monthly_scores.parquet`: historia completa, incluidos meses sin score.
- `company_latest_scores.csv`: export legible del último cierre, con motivos y cobertura.
- `company_score_explanations.parquet`: desglose numérico completo.
- `company_score_examples.json`: ejemplos ilustrativos del holdout, no una muestra representativa.
- `_company_score_reference.json`: referencia reutilizable para nuevas empresas.
- `_company_score_report.json`: distribución, cobertura, cohortes y límites; acuerdo con organizador/accuracy/lead time = null.
- `_company_score_manifest.json`: hashes, parámetros, código y versiones.

Los archivos de grupo llevan prefijo `group_currency` y no suman monedas distintas. **No hay todavía score único para un grupo multimoneda ni submission oficial aceptada.** Publicación con staging/backups; hashes detectan corrupción accidental, pero no autentican datos frente a alguien capaz de reescribir también el manifiesto. En inferencia se preservan exactamente los bytes de la referencia utilizada y se comprueba su hash.

```bash
python -X utf8 scripts/03_compute_scores.py fit
python -X utf8 scripts/04_validate_scores.py --check-prefix 2026-02-01
python -X utf8 scripts/03_compute_scores.py fit --panel group_currency
python -X utf8 scripts/04_validate_scores.py --panel group_currency --check-prefix 2026-02-01
```

Nuevas empresas, tras generar sus features en una raíz separada:

```bash
python -X utf8 scripts/03_compute_scores.py predict --features-dir data/hidden/processed --reference data/processed/scores/_company_score_reference.json
```

`data/hidden/processed` es una ruta de ejemplo, no datos recibidos. En predict, configuración congelada y misma versión de código/dependencias; aportar historia completa, no una fila final aislada. No usar fit sobre el conjunto oculto. El CSV es un candidato genérico: confirmar unidad, escala, fecha, columnas y tratamiento de abstenciones antes de enviarlo.

### SC07 · Resultados del primer intento y límites visibles

Agosto de 2026, panel primario:

| Resultado | Cantidad |
|---|---:|
| Empresas presentes en salida | 1.286 |
| Con score numérico | 876 (68,1%) |
| De ellas, provisionales | 726 |
| Con soporte completo (`scored`) | 150 |
| Sin score por evidencia insuficiente | 410 |
| Mejora confirmada | 167 |
| Deterioro confirmado | 63 |
| Estable confirmado | 14 |
| En observación / señales no concluyentes | 502 |
| Con score pero sin momentum suficiente | 130 |

Las cinco filas de trayectoria suman las 876 puntuadas; las 410 sin score no se convierten en neutrales. La mediana del score es **68,41**, p25 **47,84**, p75 **86,08**. Hay 114 scores ≤1 o ≥99. **No hemos ajustado para ocultar esta saturación.**

Holdout: 257 empresas, **189 puntuadas** en agosto; mediana 72,10 frente a 67,17 en referencia. No son métricas de acierto. Historia completa: 15.782 filas empresa-mes puntuadas de 30.864. Grupo-moneda: 3.587 filas puntuadas de 15.600; en agosto 187 parejas de 650. No confundir ese denominador con número de grupos.

**Debilidad a mejorar:** mediana del cambio mensual absoluto 8,63 puntos entre las empresas puntuadas en ambos meses; existen saltos de hasta 100. Cambian componentes/fuentes y hay volatilidad real o de cobertura. Este baseline distingue nivel y dirección, pero todavía **no demuestra la estabilidad de producto que queremos**. No suavizarlo a ciegas ni presentar estos saltos como eventos económicos confirmados.

Ejemplos ilustrativos de holdout en agosto, con scores parecidos y trayectorias opuestas:

| Empresa | Score | Nivel | Momentum | Trayectoria |
|---|---:|---:|---:|---|
| COMP_0006 · EUR | 61,35 | 52,78 | 92,85 | Mejorando; provisional |
| COMP_0019 · EUR | 60,13 | 66,76 | 16,85 | Deteriorándose; provisional |

No son empresas con etiqueta conocida de éxito/fracaso: ilustran cómo lee el índice sus señales. La comparación con el score del organizador sigue pendiente.

## 11. Producto: decisiones que siguen abiertas

Para no depender de leer otro documento, los pendientes comerciales de `nueva-proposicion.md` son:

1. Aprobar foco **precalificación + expediente de circulante**, no financiación automática/preaprobada.
2. Confirmar comprador/interlocutor real de Embat, piloto y licencia B2B; financiador como socio que aprueba/presta, no socio contratado ficticio.
3. Fijar política orientativa: nivel + momentum separados **o** score compuesto; no volver a multiplicar por momentum sin justificar doble conteo. Topes por empresa/grupo y moneda, revisión humana; no confundir límite sugerido con exposición/pérdida real.
4. Cerrar demo P0 de dos vistas: cartera/revisión y ficha/solicitud; preparar expediente descargable, enviar a revisión demo y guardar motivo/estado. Navegación por cualquier entidad puntuable y estado no evaluable visible.
5. Repartir responsables de motor, producto, front y pitch. El front puede avanzar en paralelo con fixtures rotuladas; no esperar a un GBM.
6. Mantener LLM, pricing detallado, marketplace y contrafactuales complejos detrás de la entrega mínima. El simulador no promete causalidad ni aprobación.
7. Comprobar URL en incógnito/otro dispositivo y todos los botones del recorrido. Vídeo de respaldo no sustituye una demo navegable. Backend opcional mientras la persistencia local y el cambio de rol sean explícitamente de demo.

Esta v1 no bloquea futuras políticas: modificar la regla, añadir el cambio a este registro, regenerar y repetir tests/validación. No borrar raw ni hacer cambios silenciosos de significado en columnas existentes.
