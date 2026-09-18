# Decisiones de datos: limpieza y feature engineering

**Estado verificado al 18-09-2026: limpieza revisada + feature engineering v1 implementados, ejecutados y testeados.** Este documento es autosuficiente para saber qué está hecho, qué ha cambiado, cómo reproducirlo y qué falta decidir. La lógica ejecutable está en `src/xray/`; los notebooks conservan la evidencia exploratoria, no son otra implementación del pipeline.

## 1. Resumen: qué tienes ya

- `data/raw/` intacto: **los hashes SHA-256 de los 8 CSV coinciden con los existentes antes de esta revisión**.
- Limpieza regenerada: **2.554.288 transacciones** y **876.756 facturas**; no se han añadido eliminaciones de filas a las reglas originales.
- Panel primario: **30.864 filas × 250 columnas**, empresa × mes, septiembre de 2024–agosto de 2026. Contiene importes, ratios, dinámicas y diagnósticos; **no son 250 predictores**.
- Lista explícita de **126 candidatos de modelo**, sin IDs, fotos finales de deuda/saldos, niveles absolutos de vencidas ERP ni concentración descriptiva.
- Paneles auxiliares empresa-moneda y grupo-moneda, eventos reservados y contexto de liquidez/deuda separados.
- **35 tests pasando**, también con warnings tratados como errores; compilación de `src`, `scripts` y `tests` correcta.
- **Validación sobre datos completos y prueba de prefijo hasta febrero de 2026 correctas**: regenerar solo hasta ese mes da los mismos valores históricos para las mismas claves en los tres paneles.
- Manifiestos con hashes de inputs, outputs y código real, parámetros y versiones. Copias anteriores preservadas en `.history/`.

**No está hecho ni se presenta como hecho:** target, modelo/score, SHAP, submission, anticipación medida, alertas, API o demo. Falta el script del leaderboard. Las métricas y URLs ilustrativas de documentos antiguos no son resultados ni servicios comprobados; dichos documentos están marcados como diseños pendientes.

## 2. Lo que tienes que decidir o preguntar

No hace falta resolverlo para regenerar esta v1. Sí antes de cerrar el modelo, la consolidación económica o el pitch.

| Prioridad / ID | Pregunta pendiente | Decisión provisional implementada | Qué desbloquea |
|---|---|---|---|
| 1 · D18 / M01 | ¿Qué unidad, etiqueta, horizonte, métrica, desempate y formato exige el leaderboard? | Empresa × mes y grupo × moneda × mes. Sin target ni submission inventados | Entrenamiento y salida oficial. Si difiere del target de producto, dos cabezas sobre las mismas features |
| 2 · D07 | ¿En qué moneda viene `transactions.amount` cuando FX ≠ 1? ¿Cómo convertir y con qué fecha/tasa? | No convertir ni sumar monedas distintas. Excluir FX ≠ 1 y productos desconocidos de importes bancarios | Recuperar cobertura y consolidar grupos/empresas multimoneda |
| 3 · D17 | ¿Último movimiento significa cese, desconexión o baja de Embat? ¿Hay logs de cobertura bancaria/ERP? | Ausencia = dato no observado; no etiquetar cese/churn ni rellenar caja con 0 | Targets de actividad y censura; distinguir deterioro de pérdida de conexión |
| 4 · D11/D13/D22 | ¿Qué representan `paymentDocument`, `invoiceGroup`, `note/refund`, pagos futuros y pagos anteriores a emisión? | Solo facturas estándar; documentos ambiguos fuera; anticipos fuera de DSO/DPO; fechas futuras no son pagos realizados | Facturación neta correcta, abonos y más cobertura de comportamiento de pago |
| 5 · FE06 | ¿La foto de saldos es apertura o cierre del día? ¿Está completo el libro de movimientos? | Asumir cierre del día únicamente en contexto retrospectivo; no usarlo como predictor histórico | Validar liquidez y eventualmente una variante del modelo con saldos auditados |
| 6 · M02 | Si hay que definir target propio, ¿qué 2–3 eventos y reglas fijas se usarán a 3/6 meses? | Eventos textuales reservados en artefacto separado; ningún target construido | Modelo de producto, medición independiente de anticipación y falsas alarmas |

**Regla para el siguiente paso:** primero cerrar M01/M02 y las columnas reservadas para etiquetas. No aprender y evaluar la anticipación contra una caída del propio score. Nunca dividir filiales de un grupo entre train y validación.

## 3. Cómo reproducir y consumir

Desde la raíz del repositorio, con el entorno actual:

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -m pytest -q
```

Comprobaciones ampliadas, ya ejecutadas:

```bash
python -W error -m pytest -q
python -m compileall -q src scripts tests
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
```

`-X utf8` evita problemas con los caracteres del log en consola Windows. Entorno verificado: **Python 3.14.4, pandas 3.0.3, numpy 2.4.6, pyarrow 24.0.0**. No se han añadido dependencias. No se ha verificado esta implementación con pandas 2.x.

`XRAY_DATA_DIR` cambia la raíz de datos. Limpieza acepta `--raw-dir/--out-dir`; features acepta `--cleaned-dir/--out-dir`, `--start-month`, `--end-month`, `--extraction-date`. Para otro dataset no basta con cambiar esta última: la fecha de extracción de la limpieza también está en `xray.paths.EXTRACTION_DATE` y debe adaptarse coherentemente.

Código importable: `xray.features.build_features(tables, FeatureConfig(...))` para cálculo puro y `xray.features.run(...)` para lectura, validación y publicación. La entrada de features usa exclusivamente `xray.io.read_cleaned`, nunca CSV raw.

### Artefactos actuales en `data/processed/`

| Fichero Parquet | Filas × columnas | Uso |
|---|---:|---|
| `company_monthly_features` | 30.864 × 250 | Empresa × mes en su moneda declarada; panel primario |
| `company_currency_monthly_features` | 49.128 × 244 | Todas las monedas observadas hasta el corte, separadas, más la moneda declarada |
| `group_currency_monthly_features` | 15.600 × 243 | Consolidación de flujos por grupo **y moneda**, con ratios/medianas/dinámicas recalculados |
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

- S01: fuera `companies.country` (82% nulo y no normalizado).
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
| D18 · unidad | Pregunta abierta. Empresa-moneda y grupo-moneda disponibles; no existe aún un score consolidado por grupo ni conversión FX |
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

1. Obtener script/contrato oficial y cerrar M01; responder FX/documentos/fecha de snapshot con Embat.
2. Definir M02: 2–3 eventos, ventanas 3/6, regla independiente de evidencia, observación futura suficiente y censura. No etiquetar como negativas las filas del final sin futuro.
3. Seleccionar la allowlist, aplicar mínimos y estudiar sensibilidad a moneda incompleta, incorporación de cuentas, ERP incompleto y heurísticas D01–D05/D10. No afinar umbrales mirando el test oculto.
4. GBM por `group_id` + corte temporal/purga de horizontes, SHAP desde el primer modelo, nivel y momentum visibles y separados. Si hace falta, segunda cabeza de leaderboard.
5. Medir lead time con mediana/p25/p75, falsas alarmas, cobertura y censura frente a evento independiente; avisar de datos sintéticos y disponibilidad histórica incompleta.
6. API + demo navegable para Embat/financiador, con deterioro y mejora. No presentar los notebooks como producto desplegado.

Esta v1 no bloquea futuras políticas: modificar la regla, añadir el cambio a este registro, regenerar y repetir tests/validación. No borrar raw ni hacer cambios silenciosos de significado en columnas existentes.
