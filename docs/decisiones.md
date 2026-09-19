# Decisiones del proyecto: datos, score y producto

**Estado al 19-09-2026 (noche): motor canónico del frontend = V2 (`financial_smoothed_v2`) sobre el ledger canónico; Pulse Four Pillars conservado como experimento; frontend con Portfolio, ficha, grupo y simulador con escenarios precalculados; 1.011 empresas puntuadas en agosto. Punto de entrada para cualquier agente: [ESTADO-ACTUAL.md](./ESTADO-ACTUAL.md).** Para el detalle: §21 (motor canónico y cifras), §19 (frontend FE-01…FE-05), §18 (D31 default), §14/FE10 (anotaciones y cobertura), §13 (V2), §20 (advisor de grupo, Ander), §15 (D31, categorías AI). Lo anterior a §13 es histórico. La lógica ejecutable está en `src/xray/`; los notebooks conservan la evidencia exploratoria, no son otra implementación del pipeline.

## 1. Resumen: qué tienes ya

- `data/raw/` intacto: **los hashes SHA-256 de los 8 CSV coinciden con los existentes antes de esta revisión**.
- Limpieza regenerada: **2.554.288 transacciones** y **876.756 facturas**; no se han añadido eliminaciones de filas a las reglas originales. El 19-09 (noche) se añadieron anotaciones semánticas D25–D30 y F07 (§6, §14) sin tocar filas.
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
| 5 · FE06 / V2-01 | ¿La foto de saldos es apertura o cierre del día? ¿Está completo el libro? | V1 mantiene contexto separado y supuesto cierre del día. V2 propone investigar caja fiable normalizada con auditoría temporal, aún sin implementar | Validar inclusión de liquidez, cohortes comparables y límites de reconstrucción |
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

- **S01 · Decisión confirmada por el usuario tras la revisión: mantener eliminado `companies.country` por simplicidad y prioridad del producto. No restaurarlo ni abrir un estudio de país en V2.** Auditoría: 1.056 nulos de 1.286 empresas (82,1%); 230 con país, 170 variantes de España, cobertura en 62 grupos. Se propuso conservar/normalizar a ISO, pero el usuario decidió no priorizarlo: esa restauración ya no es una tarea pendiente. Raw conserva la información. El porcentaje de nulos no demuestra irrelevancia universal; esta es una decisión de alcance del MVP. El score continúa sin país.
- S02: fuera `label/service` de productos bancarios/deuda (metadatos técnicos redundantes para esta v1).
- S03: fuera `balances.available` (100% nulo). El resto de columnas dudosas se conserva.
- S04: fuera `debt_schedule_config.amortization_type` (constante).

## 6. Decisiones D: estado vigente y cambios

**«Aplicada v1» significa política implementada, no confirmación de Embat ni verdad económica definitiva.** Todos los flags se conservan en cleaned. Las cifras son de la última ejecución completa.

### Transacciones

| ID | Estado y decisión implementada |
|---|---|
| D01 · extremos | **Retirada por D32 (aplicada 2026-09-19).** Antes: `is_extreme_amount`, 491 filas con umbral absoluto >100.000.000 **en moneda local**, excluidas de los flujos. Error: 478 de las 491 estaban en COP/AOA/VND/CLP/XOF/ARS (mediana ≈70.000 € equivalentes) y en las 15 empresas afectadas se quitaba el 67% del importe de cobros operativos. La cifra "38% del importe entrante" sumaba divisas distintas y no es válida. La columna ya no existe en cleaned |
| D02 · relativos | **Retirada por decisión del usuario (2026-09-19, D32).** Antes: `is_relative_outlier`, >20× p99 de los 6 meses anteriores por empresa-moneda (~430 filas), excluidas de los flujos y marcaban la reconstrucción de saldo como no fiable. Ahora no existe: ninguna fila se aparta por ser grande |
| D03 · resincronización | Aplicada v1: 30.119 flags. Mismo criterio anterior: ≥50% de filas pertenecen a duplicados en empresa-mes y ≥20 filas; marcar repeticiones tras la primera. Excluir de flujos. Sigue siendo heurístico |
| D04 · propios | **Revisada y aplicada:** 63.642 → **55.444** flags. Espejos +X/−X del mismo día, moneda conocida igual, cuentas distintas, booked, FX=1 y sin D03. Emparejamiento uno a uno por orden; conservador, puede omitir parejas reales. Fuera de flujos operativos; dentro del saldo de cada cuenta |
| D05 · intragrupo | **Revisada y aplicada:** 90.418 → **85.902** flags. Misma moneda, grupo y día, **empresas distintas**, sin reutilizar pares D04. Fuera del operativo tanto por empresa como por grupo: es financiación/tesorería interna, no ventas externas. Se informa aparte; dentro del saldo de cuenta |
| D06 · producto desconocido | 1.313 flags. **Cambia la recomendación anterior:** no incluir en importes sin saber moneda ni cuenta. Sí contar como cobertura perdida; fuera de reconstrucción |
| D07 · moneda/FX | **Resuelta por D32 (aplicada).** Antes: no convertir y solo FX=1 en los importes bancarios; el panel principal solo contaba las cuentas en la moneda declarada |
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
| D23 · FX inválido | `has_invalid_exchange_rate`: **77 transacciones y 3.311 facturas** con tasa nula, no finita o ≤0. **Desde D32 es solo informativo**: `exchange_rate` no se usa para convertir ni para excluir |
| D24 · saldo sin producto | **Nueva:** `balances.is_unknown_product`: **29** filas. Conservar, pero no agregar sin moneda ni reconstruir cuenta desconocida |
| D32 · importes en EUR, sin corte por tamaño | **Decidida por el usuario y aplicada el 2026-09-19.** (1) No se elimina ni se excluye ningún movimiento por su importe absoluto: si existe, se conserva (desaparece D01). (2) Todos los importes pasan a EUR con **un tipo fijo por moneda** (`src/xray/fx.py`): BCE a 2026-09-18 para 29 monedas, open.er-api.com a 2026-09-19 para 13 y paridad oficial para BAM y XOF; cubre las 44 monedas del dataset y una moneda desconocida da NaN (nunca se supone EUR). La conversión se hace **en features, no en cleaned**: cleaned conserva importes en moneda original con `product_currency`/`currency`. Transacciones por moneda del producto, facturas por `currency`, saldos y deuda por moneda del producto; saldo y movimientos con el mismo tipo, así la reconstrucción hacia atrás cuadra. `exchange_rate` no se usa (en unas monedas va contra EUR, como DKK 7,47; en otras parece ir contra USD, como HKD 7,83). **Cambios:** sin `is_extreme_amount` ni `is_relative_outlier` (D02 también retirada: ninguna fila se aparta por su tamaño, ni absoluto ni relativo); D04/D05 ya no exigen FX=1 (el emparejamiento sigue siendo en la misma moneda original); `eligible` = booked, importe convertible y sin D03/D06; los tres paneles salen con `currency = EUR` (empresa y grupo consolidan todas sus cuentas y facturas); el panel de empresa añade `declared_currency` y `tx_primary_currency_row_share` (solo contexto); `has_partial_currency_coverage` = hay movimientos sin moneda conocida; desaparece `tx_ambiguous_fx_count`; `debt_snapshot_context` en EUR con `source_currency`. **Resultado:** +96.624 movimientos usables (3,9%) en 270 empresas. V2: 949 empresas puntuadas en agosto (antes 922), mediana/p95 de |Δ| mensual 3,26/17,6 (antes 3,31/17,9). V1: 898 en agosto, mediana 8,8. Prefijo 2026-02 correcto en features, V1 y V2. **Aproximación reconocida:** sin variación del cambio en la ventana (en ARS es grande). **Futuro:** tipos diarios por moneda aplicados en la fecha de cada movimiento. Tras convertir, solo 13 movimientos superan 100 M€ (7 empresas): disposición y amortización de préstamo, reparto intragrupo y 4 centinelas `999.999.999` "MANUAL QUITAR RETENCION" (COMP_0604), casi todos `uncategorized` o intragrupo. `group_advisor/fx.py` ya usa `xray.fx.FX_TO_EUR`; `product/cash_truth.py` (remoto) también convierte a EUR y ya no filtra FX=1, para que su `currency` case con la de los scores. **Integración con el remoto (19-09, tarde):** el stash/pull chocó con estos cambios; resuelto conservando ambos lados y renumerando esta decisión de D25 a D32 (el remoto ya usa D25–D31) |
| D33 · primer mes parcial | **Decidida por el usuario y aplicada el 2026-09-19.** Las empresas que entran a mitad de ventana empiezan a mitad de mes (primer movimiento: mediana día 14) y ese mes tiene ~60% de la actividad normal (mediana de cobros por mes desde el primero: 4, 8, 9, 8, 9); el mes siguiente ya es normal. Si entra en las ventanas genera un crecimiento falso de ~+60%. Regla: `onboarding_months` de FE10 pasa de **2 a 1** (sustituye al onboarding de 2 meses, no hay dos mecanismos) y, en ese mes, `is_partial_first_month` anula los importes bancarios (`PARTIAL_MONTH_COLUMNS`) antes de ventanas y ratios; los conteos se conservan. **Excepción:** si el mes es el primero de la extracción (`DATA_START` = 2024-09-01) está completo (primer movimiento el día 1–3) y no se anula. Resultado: 865 meses parciales (antes de la excepción eran 1.273, 408 de ellos completos). V2: 948 empresas puntuadas en agosto, mediana/p95 de |Δ| 3,22/17,7. `created_at` no marca el inicio: el primer movimiento cae de mediana 54 días antes del alta; la historia empieza en el primer movimiento |
| D34 · `erp` | **Decidida por el usuario el 2026-09-19.** No es feature del score: es metadato de integración. `erp` nulo ≈ ERP no conectado: 463 de 541 empresas sin ERP no tienen facturas, y 707 de 745 con ERP sí. Se usa solo como contexto de cobertura ("sin ERP conectado: score solo con bancos"). `groups.erp` es el mismo dato con otra nomenclatura (`businessOne` frente a "SAP Business One"). Pendiente: comprobar en el paso de facturas si la fecha de pago de relleno depende del ERP |
| D35 · cuentas bancarias | **Decidida por el usuario el 2026-09-19.** (1) Nº de cuentas, nº de bancos y `bank_name` **no son features**: miden cobertura de integración con Embat, no salud (igual que D34). (2) Se valida el tratamiento de flujos: `checking` concentra el 95,6% de los movimientos; tarjeta, TPV y póliza cuentan; la liquidación de tarjeta en `checking` viene como `pos_withdrawal` (2.108 de ~2.500), fuera de las salidas operativas, así que el gasto no se duplica (residuo de ~80 líneas `payment`). (3) Para el paso de saldos quedan: la póliza usada como cuenta operativa (8,1% de los cobros operativos en `lineofcredit`; D25 del remoto), las 201 cuentas de inversión sin movimientos (~192 M€ de saldo) y las 174 corrientes sin movimientos con saldo distinto de cero (~16 M€). El alta y la baja de cuentas durante la ventana (1.459 cuentas empiezan más de 60 días después de la primera de su empresa; 1.016 terminan antes de 2026-06) es cobertura, tratada por `account_change` de FE10 |
| D36 · deuda registrada | **Decidida por el usuario el 2026-09-19.** (A) La deuda del score sale **solo de los flujos bancarios** (servicio de deuda del libro de caja); `debt_products` es contexto. El registro está incompleto: ~100 empresas pagan cuotas recurrentes (≥6 meses) de préstamos no conectados (p. ej. Santander Consumer). La cifra inicial de 388 "empresas con deuda sin registro" estaba inflada: 150 solo tenían `interest_charge`, casi siempre comisiones de pasarela o de cuenta, y muchas de las otras eran pagos sueltos. (B) **Prohibido** usar `created_at` de deuda como señal de nueva financiación (85% dentro de la ventana: es la fecha de conexión). (C) El uso (dispuesto / concedido) solo en productos rotativos (`is_revolving`: póliza, confirming, factoring; uso mediano de la póliza 16%, p90 100%); en préstamos, hipotecas, leasing y avales queda NaN. (D) `debt_snapshot_context` toma lo dispuesto, lo concedido y el disponible de `balances` (fechado a 2026-09-01) y usa `debt_products` como respaldo (`outstanding_source`); coinciden en ~71% y difieren ~2% del concedido en el resto. Sigue siendo contexto a extracción, no predictor (D21). (E) La historia del uso de la póliza (reconstrucción hacia atrás: el 46% de 205 pólizas da valores imposibles) se decide en el paso de saldos. (F) Las comisiones de pasarela ya salen del servicio de deuda en el libro de caja del remoto (CT02: 5.012 movimientos Stripe/network → operativos); la revisión del resto de lo que entra en servicio de deuda está pendiente de decisión |
| D37 · cuadros de amortización | **Decidida por el usuario el 2026-09-19. Solo documentación: no cambia código ni resultados** (`debt_schedule_config` solo la usa la limpieza; ningún score, feature, advisor, producto ni frontend la consume). 87 cuadros de 40 empresas (3%). (A) No es feature del score. (B) **Es una foto desactualizada**: en 81 de 87 la `next_payment_date` es anterior a la extracción (mediana entre esas: 155 días antes) y el pendiente es ~9% mayor que el de `debt_products`. Una "próxima cuota" pasada **no es impago**. (C) Uso previsto solo como contexto de producto para esas 40 empresas: coste de la deuda (tipo mediano 3%, rango 0–11%; 29 a tipo variable), avisando de la fecha del cuadro. `annual_interest_rate_or_spread` va en tanto por uno (0,03 = 3%). (D) No se casan cuotas teóricas con el banco: la cuota (sistema francés) aparece repetida (≥3 meses) en su cuenta de cargo solo en 18 de 87, mientras que 68 de esas cuentas muestran `debt_repayment` mensual. El servicio de deuda se mide en el banco |
| D38 · saldos centinela y liquidez disponible | **Decidida por el usuario el 2026-09-19.** (B1) **Marcar, no borrar:** `balances.is_sentinel_balance` para saldos de cuenta bancaria ≥100 M€ que no se explican por la actividad de su cuenta (más de 1.000× su mayor movimiento, o formados por ajustes técnicos). Marca 4 cuentas: COMP_1068 (+99.999.990.000 € con movimientos de pocos euros), COMP_0420 (dos cuentas a −999.999.999) y COMP_0604 (~1.000 M€ de ajustes "QUITAR RETENCION"). Los saldos grandes de préstamos (p. ej. 300 M€ de COMP_0415) no se marcan: son deuda real. `transactions.is_technical_placeholder` marca los ajustes de exactamente ±999.999.999 (COMP_0538, COMP_0604): **siguen en los flujos (D32)**, pero invalidan la caja reconstruida de los cierres anteriores. Solo `features/context.py` lee saldos, así que es el único punto que aplica la marca; advisor y validación reciben la caja ya corregida. Efecto: 6 meses-empresa dejan de tener caja de ±1.000 M€ y la validación pierde un falso "caja negativa" (COMP_0420); no cambian el score, la web ni el advisor de agosto. (B3) Nuevo contexto `liquidity_snapshot_context`: caja en cuentas (corriente, ahorro, wallet, TPV, plataformas de gasto; sin tarjetas, cuyo saldo es deuda) + inversión + disponible de pólizas, en EUR y sin centinelas. Columnas nuevas que nada consume todavía: base para la ficha, el advisor o un score futuro. (B4) La historia del uso de la póliza no se reconstruye (46% de 205 pólizas da valores imposibles). (B2, pendiente) Dar por fiables las cuentas sin movimientos con saldo 0 (245 empresas sin caja en agosto solo por ellas) cambia resultados del advisor: no aplicada |
| D39 · fechas de pago de relleno | **Decidida por el usuario el 2026-09-19. Cambia el score V2.** Algunos ERP ponen el vencimiento como fecha de pago al marcar una factura como pagada: 155 casos empresa-dirección con ≥95% de pagos exactamente al vencimiento (66 AR, 89 AP), 67 de 84 empresas en Business Central (mediana de exactas 82%, frente a 9–20% en Sage 200 o NetSuite). Pruebas de que no es real: depende del ERP; en cobros serían clientes pagando siempre el día exacto; casando factura y banco por importe, el banco confirma la fecha del ERP solo en el 32% de sus facturas (60% en el resto) y el 44% se pagó tarde según el banco (0% según el ERP); el doble de pagos con fecha posterior a la extracción (5,5% frente a 2,9%). Tratamiento (opción A): en `features/invoices.py`, si el historial de la entidad y dirección hasta el mes tiene ≥30 pagos con vencimiento válido y ≥95% exactos, `inv_{ar,ap}_delay_median/_p90/late_paid_ratio` quedan NaN ese mes y `inv_{ar,ap}_payment_date_filler` = True. V2 ya trata un retraso vacío como dimensión ausente (reparte el peso), sin lógica nueva. Regla causal (solo pasado) con test de invariancia de prefijo. Antes, en agosto, 105 empresas con score tenían una señal de retraso de relleno (nota media 99 frente a 79). Mejora futura (B/C): recuperar la fecha real casando factura y banco (hoy ~34% de sus facturas) |
| D40 · facturas abiertas y DSO | **Solo documentación, no cambia resultados.** (I2) `facturas_abiertas()` del notebook solo con `invoice` y sin canceladas. Retraso (pago − vencimiento) no es DSO/DPO (pago − emisión o *countback*); V2 usa el retraso. Limitación de supervivencia: el retraso solo ve facturas pagadas; en las empresas con más AR vencida reciente sin cobrar (~30%) el retraso de las cobradas es ~2,5 días. Una señal de "vencidas recientes" (últimos 90 días, contra la historia propia) queda para el rediseño del score. (I4) De las 193.750 facturas abiertas a extracción, el 44% venció hace >6 meses y el 26% hace >1 año, con tasas de abiertas iguales en 2024 y 2025 (~21%): higiene del ERP, no impago; no se usan en valor absoluto (D20) |
| D41 · estrés propio y anticipación medida | **Decidida por el usuario el 2026-09-19. No cambia puntuaciones** (0 diferencias en V2). (A) `event_type` (D30) gana el tipo `embargo_tercero`, con prioridad sobre `embargo`: ingresos en Hacienda de lo retenido a un empleado o proveedor ("DOC. DE INGRESOS ASOCIADOS EMBARGOS"), retenciones de nómina y transferencias al juzgado. Son 331 movimientos en 47 empresas; quedan 315 embargos propios en 129 ("EMBARGO COMUNICADO", "EJECUCION EMBARGO", "EMBARGOS AEAT"…). (B) `src/xray/evaluation/lead_time.py` + `scripts/11_lead_time.py` → `data/processed/evaluation/lead_time.{json,md}` y `lead_time_events.parquet`. Reglas fijadas antes de ver resultados: evento = primer estrés propio (cuota impagada, embargo propio, aplazamiento, descubierto, recargo de apremio, demora) tras 6 meses observados sin estrés; señal = primera etiqueta V2 `emerging_deterioration`/`deteriorating` en los 6 meses previos (umbral fijo de V2); evaluable con ≥3 meses de score previos; falsa alarma = inicio de racha de alarma sin estrés propio en los 6 meses siguientes (solo alarmas con 6 meses de futuro observado). **Resultado:** 153 inicios (142 evaluables, 11 censurados); detectados 45 (32%); antelación mediana 3 meses (p25–p75: 2–5); 78% de falsas alarmas; evento tras alarma 22% frente al 18% de base (×1,2): **señal débil, no se maquilla**. Las empresas con estrés propio ya puntúan 3–5 puntos menos que el resto seis meses antes (estudio de eventos): el score las ve más débiles como nivel, no como caída que se acelera. Las 123 empresas que dejan de tener datos casi nunca tienen estrés propio antes de irse (2–4% frente al 16% de las activas): 53 cortan de golpe (baja en Embat), 52 se apagan (cobros al 5%; cese o cambio de banco), 15 intermedias, 3 sin historia; no se usan como evento de validación (circular: se definen con los mismos flujos que usa el score) |

### Anotaciones semánticas (19-09, `src/xray/clean/annotations.py`; evidencia en `docs/hallazgos-datos.md`)

Solo marcan; ninguna feature las consume todavía (paso siguiente: máscara de cobertura y fallback por signo en features).

| ID | Columna(s) | Estado y decisión implementada |
|---|---|---|
| D25 · tipo de producto | `product_kind` (banking/debt/nulo), `product_type` | **183.417** movimientos ocurren sobre productos de deuda (181.917 en `lineofcredit`, 312 pólizas, 170 empresas): pólizas usadas como cuenta operativa. Reconstruir su saldo/utilización igual que checking; no tratarlas como producto desconocido |
| D26 · SCF | `is_scf_adjustment` | **18.208** filas (`SCF-AJUS.SALDO`, 42 empresas, ~1.400 M abs): ajustes de confirming. Financiación, fuera del flujo operativo y del fallback por signo |
| D27 · repos | `is_repo_pair` | **5.530** filas `PR.A`/`VT.A` con sumas espejo: colocación de tesorería. Fuera del operativo |
| D28 · efectivo | `is_cash_disposal` | **3.803** filas `DISP.ENTREG.EFECT.` sin categoría: retirada de efectivo, no gasto identificado |
| D29 · pasarela | `gateway_kind`, `is_gateway_cost` | **13.009** filas `[fecha] tipo` (charge/payment/payout/refund/stripe_fee/network_cost/adjustment). Los **5.020** costes de pasarela venían como `interest_charge` antes de 2025-01 y como sin categoría después: excluirlos del servicio de deuda |
| D30 · eventos | `event_type` | **15.676** filas: impagado_cliente 7.887, recibo_devuelto 5.433 (refund negativo **por signo**, robusto al cambio de taxonomía de 2025-01), aplazamiento 902, embargo 646, cuota_impagada 365, descubierto 283, demora 111, reclamacion 30, recargo_apremio 19. Prioridad al primero que casa. `SANCION` excluido a propósito: "SANCIONES Y MULTAS" son multas de tráfico en tarjeta (3.638 filas de una flota) |
| F07 · fecha prevista | `invoices.expected_payment_date` | **219.366** facturas no pagadas conservan la fecha de relleno como previsión del ERP, separada de `payment_date` (real). Nunca se usa como pago realizado |

Ruptura de taxonomía conocida (2025-01): `payment_refund`/`collection_refund` invierten signo y `interest_charge` deja de incluir costes de pasarela. Ninguna feature debe depender del **nombre** de categoría de refund; usar signo + D29.

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

`docs/feature-engineering.md` y `docs/validation.md` reflejan la implementación. El `README.md` raíz (único README) tiene comandos y estado actuales. Los otros diseños llevan aviso explícito de estado. `CLAUDE.md` local incorpora notas de continuidad para próximas sesiones; las decisiones compartibles están todas aquí.

## 9. Siguiente trabajo, en orden

1. Conservar V1 como control (`a1af735`, datos/modelos actuales con manifiestos) y reproducir la auditoría de §12 / `docs/validation.md`. No sobrescribir el control al experimentar.
2. Implementar un comparador reproducible con proxy interno normalizado por exposición, split por grupo/tiempo y control de tamaño. No entrenar contra una etiqueta inventada para imitar al organizador.
3. Comparar V1, caja sola, V1 estabilizado y una V2 con liquidez + dinámica corregida; evaluar el fallback aparte. Ver variantes, restricciones y entregables en §12.
4. Confirmar formato/unidad/escala del envío y semántica de saldos con Embat. No hay canal conectado y no se ha enviado la pregunta de §12; no bloquear el experimento por esperar un script.
5. En paralelo, cerrar alcance de producto (§11) y avanzar cartera + ficha + solicitud/revisión. API solo si hace falta persistencia multiusuario; no invertir el resto del hackathon únicamente en el score.
6. Elegir cambios por evidencia comparativa y declarar sus límites. Si más adelante se entrena un modelo supervisado, cerrar target/censura y explicabilidad; no presentar los proxies internos como notas oficiales ni prometer anticipación no medida.

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

## 12. Auditoría posterior y relevo hacia V2 — 19-09-2026

**Prioridad vigente para el siguiente agente.** Lo que sigue distingue resultados reproducidos, hipótesis y trabajo propuesto. La auditoría fue de solo lectura; todavía no se ha corregido el algoritmo, incorporado liquidez, definido un proxy normalizado persistente ni implementado fallback. Los 167 tests comprueban mecánica de V1, **no suficiencia financiera o predictiva**. El siguiente paso es comparar variantes, no declarar V1 terminado como producto.

### RV01 · Evidencia reproducida de V1, toda la historia

Fuentes locales: `company_monthly_features.parquet`, `scores/company_monthly_scores.parquet`, `company_currency_liquidity_context.parquet`, `stress_events_reserved.parquet`; todos en `data/processed/`. Baseline consolidado en commit `a1af735`; manifiesto de scores generado el `2026-09-19T06:53:33+00:00`. El manifiesto conserva el HEAD anterior a ese commit porque se generó antes de commitear: los hashes de fuentes permiten comprobar el código utilizado. Protocolo y fragmento reproducible en `docs/validation.md`.

| Medida | Toda la ventana 2024-09–2026-08 |
|---|---:|
| Empresa-mes con score / total | 15.782 / 30.864 |
| Sin score | 15.082 (48,87%) |
| Sin score anteriores a la primera observación bancaria | 8.634 |
| Sin score restantes | 6.448 |
| Mediana / p75 / p95 de cambio mensual absoluto | 8,77 / 17,94 / 44,26 puntos |
| Scores exactamente 0 o 100 | 1.617 |
| Scores ≤1 o ≥99 | 1.972 |
| `improving` / `deteriorating` | 2.373 / 766 |
| `watch` / `stable` / `insufficient_history` entre puntuadas | 7.537 / 201 / 4.905 |
| Mediana de cambio absoluto con cambio de componentes | 17,40 (2.541 pares) |
| Mediana sin cambio de componentes | 7,74 (11.105 pares) |

No confundir estas cifras con §10, que describe principalmente **agosto**: allí el cambio absoluto mediano era 8,63. Tampoco llamar 1.972 «exactamente saturados»: son valores dentro de un punto del extremo. Los 8.634 meses previos al primer dato no deben convertirse en historia financiera inventada para mejorar artificialmente cobertura. El problema de entrega más inmediato son las **410 empresas sin score en agosto (31,88%)**.

### RV02 · Prueba exploratoria frente a eventos futuros, sin normalizar tamaño

Etiqueta exploratoria: al menos una coincidencia de EMBARGO, IMPAGADO, APLAZAMIENTO, DESCUBIERTO/EXCEDIDO o DEMORA en t+1..t+h. Se suman las columnas `stress_*` de la tabla reservada para determinar presencia; el evento del mes t no se incluye. Exigir que los h meses futuros tengan registro bancario observable en esa tabla; NaN futuro implica censura, no ausencia de evento. Esto no garantiza integridad del libro ni que una mención textual sea estrés propio.

Se utiliza el holdout de V1 y, **dentro de cada horizonte**, exactamente las mismas filas con score y runway disponibles para comparar tres riesgos: `-score`, `-cash_runway_months_retrospective` y `log1p(tx_all_currency_count)`.

| Horizonte | Filas / grupos | Positivos | AUC menor score | AUC menor runway | AUC mayor actividad |
|---|---:|---:|---:|---:|---:|
| 3 meses | 1.398 / 36 | 170 | 0,5261 | 0,6811 | 0,6650 |
| 6 meses | 973 / 25 | 161 | 0,5185 | 0,6273 | 0,5961 |

**Interpretación limitada:** V1 muestra poca señal frente a este proxy bruto. Caja parece más útil, pero solo contar transacciones se aproxima mucho a su AUC: tamaño/actividad puede explicar parte del resultado. No hay intervalos de confianza, ajustes por exposición, episodios incidentes ni validación de semántica del texto. Las ventanas se solapan y las filas no son independientes por empresa/grupo. No es comparación con la nota del organizador ni lead time medido. Los JSON de V1 siguen con métricas oficiales nulas; estas AUC proceden de una auditoría puntual, no de un evaluador persistente ya implementado.

El holdout de 50 grupos **ya se ha mirado**, también para esta comparación. No presentarlo después como un test completamente intacto. Ajustar variantes dentro de los grupos de desarrollo y declarar cualquier reutilización del holdout; no cambiar semilla para buscar un resultado favorable. Una nueva evaluación final debe reservarse antes de ajustar y quedar identificada por grupos/fechas.

### RV03 · Causas que debe investigar/corregir la siguiente versión

1. **Sesgo alcista mecánico del crecimiento.** `features/transactions.py` calcula `(entrada_actual−entrada_previa)/entrada_previa` en cuentas comunes y `score/trajectory.py` promedia tres tasas simples. `100 → 200 → 100 → 100` da media **+16,67%**, aunque crecimiento total sea 0; la media de cambios logarítmicos da 0. Probar crecimiento compuesto/logarítmico con tratamiento explícito de ceros, o variación simétrica acotada. No forzar 50/50 entre mejora y deterioro: corregir la asimetría, no maquillar la distribución.
2. **Peso efectivo y disponibilidad.** El margen tiene peso nominal 45%, pero puede pesar **100%** si solo él está disponible. Los cambios de componentes y sus pesos renormalizados pueden mover el nivel sin una mejora financiera equivalente. Medir por separado valor, disponibilidad, normalizador y transición media3→valor mensual.
3. **Suavizado frágil.** Hoy se usa media3 cuando hay soporte; al perderlo se vuelve al dato mensual. Un pago grande o el cambio de ventana puede generar saltos. Comparar agregados de flujos 3/6 meses, ratios de agregados, medianas y/o EWMA causal; no elegir parámetros únicamente para que el gráfico resulte suave.
4. **`watch` agrupa cosas diferentes.** Primer indicio, señales contrapuestas y agregados neutrales con alguna señal individual activa acaban ahí. Separar motivos: señal no confirmada, conflicto, estable con incertidumbre y soporte insuficiente. No llamar estable a lo desconocido ni confirmar un bache con t+1.
5. **Normalización cambiante.** Aun congelado para inferencia, el JSON de V1 contiene distintas referencias mensuales. Medir cuánto del cambio de nivel procede de ellas. Preservar escala comparable y no confundir crecimiento del universo/onboarding con mejora.

### V2-01 · Liquidez: candidato prioritario, inclusión aún NO aplicada

La exclusión absoluta de caja fue conservadora para el control V1; **no debe interpretarse como prohibición de investigarla en V2**. Una reconstrucción contable puede aproximar un saldo que existía en t y que en producción se observaría directamente. Pero la identidad solo es válida con libro/moneda/fecha coherentes; no basta argumentar que Embat dispone de saldos diarios.

Disponibilidad en el panel primario: caja reconstruida en **14.704 filas**; runway en **11.400**, de las que **2.260 carecen de score V1**. En agosto hay runway para 818 empresas; entre las 410 sin score, **286 tienen caja y 149 runway**. Estas cifras no demuestran fiabilidad histórica completa ni autorizan imputar el resto como caja cero.

Probar caja normalizada por salidas operativas y, como variante explícita, por salidas recurrentes incluyendo servicio de deuda, evitando doble conteo. El runway actual divide solo por `tx_outflow_ma3`: no es burn neto, gasto total ni meses de supervivencia garantizados. Mantener caja negativa como información, controlar ceros del denominador y evaluar nivel robusto/evolución por moneda.

**Salvaguardas obligatorias:**

- Respetar `is_reconstruction_unreliable` y cobertura de cuentas; no reutilizar valores que ya están invalidados.
- Auditar fecha real de snapshot y supuesto apertura/cierre, transferencias conservadas para saldo, libro incompleto y huecos. Flag falso no prueba integridad.
- El flag actual examina transacciones **posteriores a t** (`features/context.py`). Su disponibilidad es retrospectiva: no usar el flag ni su patrón de missingness como predictor de estrés ni presentar una selección retrospectiva como información conocida entonces.
- Comparar con/sin caja sobre una **cohorte común** y reportar cobertura ampliada aparte. La V2 debe distinguir reconstrucción retrospectiva de saldos realmente observados en producción.
- Versionar la lista de señales de V2; no meter contexto de liquidez silenciosamente en la allowlist/modelo V1. Deuda final estática y eventos reservados no quedan autorizados por esta revisión.
- Test contable útil: añadir un movimiento futuro y ajustar coherentemente la foto final no debe alterar el saldo anterior. Cambiar arbitrariamente la foto sin ajustar el libro sí cambia la historia inferida: no confundir esta revisión de datos con una prueba causal válida. Mantener pruebas de no futuro para flujos, rolling, normalización y decisiones de alerta.

### V2-02 · Estabilidad y dirección

Probar señales de nivel suavizadas de 3–6 meses y reducir dependencia de un único margen mensual. Comparar horizonte corto/largo y medir el retraso de reacción: seis meses de media pueden retrasar más de un mes; el ejemplo 45→65 del enunciado **no es una restricción numérica de volatilidad**.

Corregir el crecimiento asimétrico, estabilizar pesos cuando falta una fuente y separar señal de salud de cambios de cobertura. Si se introducen priors por componente, estos se ajustan solo con referencia/pasado; no convertir la pérdida de información en una recuperación aparente. Mantener nivel y momentum explicables y las dos direcciones simétricas. No disimular ruido recortando todas las notas a una banda estrecha.

### V2-03 · Cobertura de entrega y fallback

El usuario necesita poder entregar un número por entidad. Proponer dos salidas diferenciadas: **score sustentado por observaciones** (puede estar ausente) y **score de exportación con fallback** (finito cuando el contrato lo requiera).

Jerarquía a implementar/evaluar: dimensiones fiables actuales → último estado fiable con antigüedad/decaimiento explícitos → prior de referencia. No inventar cero actividad ni una nota saludable. El prior es una estimación de último recurso, no un dato observado ni una etiqueta del organizador.

Incluir `score_source`, confianza **de datos** o grado de evidencia, última observación y aviso de prior puro/obsolescencia; no llamarlo probabilidad calibrada de acierto. La trayectoria requiere observaciones comparables: **ir hacia el prior por perder datos no significa mejorar**. Preservar huecos antes del onboarding en el historial; completar un export exigido no obliga a pintar una historia ficticia. Aún no hay fallback en el código V1: conserva NaN.

### V2-04 · HHI y unidad

**HHI permanece descriptivo por ahora**, no factor prioritario del score. HHI bancario disponible en 11.606 filas: cobertura identificada mediana **51,35%**, p25 **11,20%**, p75 **98,83%**; solo **4.442** filas tienen ≥80% del importe identificado. No confundir HHI entre contrapartes conocidas con concentración total ni asignar todo lo desconocido a un cliente ficticio.

HHI de facturas AR disponible en **9.753** filas, de las que **9.750** tienen ≥80% de nominal identificado; los tres cuartiles de cobertura son 100%. Se midió con `invoice` AR no duplicadas, emisión hasta agosto y moneda declarada de la empresa. El porcentaje de identificación **no demuestra cobertura completa del ERP**.

Mejora propuesta: top1/top3 y HHI en ventanas de 3–6 meses, con tamaño de muestra, moneda, fuente y porcentaje desconocido. Separar concentración de **facturación** de concentración de **cobros**. No hay red de contagio ni score de las contrapartes.

Unidad de trabajo propuesta: empresa como motor y grupo derivado recalculando magnitudes/ratios, no promediando sin más scores. No sumar divisas. La unidad oficial y el formato siguen pendientes; el código actual soporta empresa y grupo-moneda, no un rating único multimoneda.

### V2-05 · Proxy interno y experimento concreto, pendiente de implementar

**No hay un target oficial visible.** La idea de que la nota oculta refleja una «salud latente» del generador es una hipótesis razonable, **no un hecho comprobado**. El proxy sirve para comparar variantes, no para entrenar a ciegas ni reemplazar la verdad del organizador.

Antes de ajustar pesos, fijar definición, exposición, cohortes y horizontes:

- Contar operaciones/episodios de estrés deduplicados y definir qué menciones significan estrés propio. Evitar sumar varios términos de la misma operación como sucesos independientes.
- Normalizar por exposición adecuada: movimientos booked no duplicados con texto observable, en el mismo universo de empresa/ventana que el numerador. `tx_all_currency_count` solo fue un baseline aproximado de actividad, no ese denominador exacto.
- Para muestras pequeñas, comparar tasas con suavizado hacia un prior estimado en referencia; futuros sin observación suficiente se censuran. Tasas futuras son resultados de evaluación, nunca features disponibles en t.
- **Dividir por N y volver a etiquetar «tasa >0» no corrige el sesgo de presencia de eventos.** Evaluar tasas/residuos normalizados, estratos de tamaño y referencias de actividad/persistencia, con umbrales elegidos en desarrollo.
- Split por grupo y tiempo, purga de horizontes solapados y agregación/incertidumbre a nivel de grupo. No presentar miles de ventanas repetidas como muestras independientes. No reaprender referencia, imputadores o percentiles con el test oculto.

Variantes acotadas, predefinidas y versionadas:

| Variante | Pregunta |
|---|---|
| A · V1 congelado | Control reproducible, sin cambiarlo mientras se compara |
| B · Solo liquidez fiable normalizada | ¿Cuánta señal aporta la dimensión simple? |
| C · V1 estabilizado y crecimiento corregido, sin liquidez | ¿Cuánto mejora quitar ruido y asimetría? |
| D · Liquidez + las señales estabilizadas de C | ¿Aporta combinación incremental sobre caja sola y C? |
| E · Fallback de exportación sobre la variante elegida | ¿Qué cobertura añade y qué incertidumbre/error introduce? Evaluación separada |

Comparar A–D en las mismas filas observables; añadir una evaluación del universo ampliado y E por separado, sin fingir una mejora al cambiar la muestra. Baselines mínimos: actividad/tamaño y persistencia/no cambio, además de caja sola. Informar proxy 3/6 meses, cobertura, falsos avisos si hay definición suficiente, cambios de score, saturación, persistencia, transiciones y retraso de reacción. No seleccionar solo por AUC ni por suavidad: un score constante puede parecer estable y no servir.

**Entregable del siguiente agente:** comparador ejecutable con configuración y manifiestos; informe A–E con denominadores y límites; candidato V2 con nivel/momentum/confianza/origen, explicaciones actualizadas y exportación; tests de causalidad donde proceda, monedas, crecimiento cerrado sin falsa mejora, fallbacks sin falsa recuperación y sensibilidad a cobertura. Guardar variantes fuera de los artefactos V1 y registrar qué se adopta/rechaza. Si no hay mejora defendible, decirlo.

### RV04 · Contacto con Embat y estado de trabajo

No hay canal MCP/mensajería conectado en esta sesión. **No se ha contactado con Embat ni recibido respuesta.** Pregunta preparada para que el usuario la traslade:

> ¿La unidad evaluada es company_id o group_id? ¿Score final por entidad o serie mensual? ¿Fecha de corte, escala/sentido, columnas, métrica y tratamiento de pocas observaciones? ¿Se evalúa nivel, trayectoria o ambos? Para liquidez: ¿los saldos están reconciliados con todos los movimientos y son de apertura o cierre del día?

La falta de respuesta no bloquea el comparador ni justifica inventar el contrato oficial. No pedir scores ocultos como requisito para trabajar, ni afirmar una integración/contacto inexistente.

**Relevo:** base publicada `a1af735`, rama `ander/clean-pipeline`. `data/` y resultados viven solo localmente y están ignorados; `CLAUDE.md` está excluido localmente de git. `nueva-proposicion.md` debe seguir fuera de commits por petición del usuario; su resumen necesario está en §11. Esta auditoría/plan se documenta después del commit; no asumir que un clon remoto ya tiene estos cambios sin comprobarlo. V2 se implementó después (§13). No resetear cambios ajenos ni publicar código/commits sin petición.

Esta v1 no bloquea futuras políticas: modificar la regla, añadir el cambio a este registro, regenerar y repetir tests/validación. No borrar raw ni hacer cambios silenciosos de significado en columnas existentes.

## 13. Score V2 suavizado — 19-09-2026 (tarde)

**Petición del usuario:** un score más suavizado, que distinga un mes malo de una tendencia mala, que diga si la empresa está en buen momento o decayendo y que todo sea explicable. Implementado como versión nueva `financial_smoothed_v2` en `src/xray/score_v2/`, rama `ander/score-v2`; **V1 no se ha modificado** (único cambio en `src/xray/score/report.py`: `example_cases` acepta una lista opcional de etiquetas, comportamiento por defecto idéntico). Método completo en `docs/scoring-v2.md`; protocolo de comparación en `docs/validation.md`.

### SC08 · Diagnóstico previo que motiva el diseño

Reproducida la auditoría de §12 sobre los artefactos V1 actuales (mediana/p75/p95 de |Δ| 8,77/17,94/44,26; 1.617 extremos exactos; trayectorias 7.537 watch / 2.373 improving / 766 deteriorating). Medido además, sobre `company_monthly_features`: la desviación típica del margen operativo **mensual** dentro de una misma empresa, en ventanas de seis meses, tiene mediana **0,29** (empresas pequeñas 0,44; grandes 0,20). La diferencia trimestre-a-trimestre del margen agregado tiene IQR ±0,17 y el signo de la desviación del mes actual respecto al nivel de seis meses persiste al mes siguiente solo el 53% de las veces (ruido). Con escalas fijas de 0,10 como las de V1, el ruido mensual satura el momentum: por eso V1 saltaba y etiquetaba mejora/deterioro casi al azar. Cualquier V2 debía normalizar los cambios por la volatilidad propia de cada empresa.

### SC09 · Decisiones de diseño adoptadas

| ID | Decisión | Motivo / alternativa descartada |
|---|---|---|
| V2-L1 | Nivel = ratios de **flujos agregados en seis meses** (mín. 3 meses con calidad), mismas anclas y misma mezcla 70/30 que V1, `reference_months=24` | Agregar antes de dividir evita que un mes minúsculo arrastre el nivel; la referencia expansiva elimina el ruido de normalización mensual (RV03.5). Media de ratios y EWMA descartadas por menos explicables y menos robustas a meses pequeños |
| V2-L2 | Retrasos AR/AP = media de medianas mensuales ponderada por número de pagos, mín. 5 pagos en la ventana | No existe la mediana agrupada en features; la ponderación por soporte es la aproximación más fiel disponible |
| V2-M1 | Momentum = trimestre reciente − trimestre anterior sobre los mismos agregados | Explicable en una frase; sustituye a delta3 de valores mensuales |
| V2-M2 | Crecimiento de entradas = suma de log(1+g) en tres meses, g recortado a −1 y log a ±1,5 | Corrige RV03.1 (ciclo 100→200→100→100 = 0, test dedicado) |
| V2-M3 | Cada cambio se divide por σ mensual propia medida en los 12 meses **anteriores al trimestre reciente** (mín. 4, con suelos 0,05/0,02/3 días/0,05) y ajustada a la ventana (√(2/3), √3) | Con σ incluyendo el trimestre reciente, una ruptura grande inflaba su propia σ y se anulaba (comprobado: escalón de 0,20 no confirmado, escalón de 0,16 sí). Con σ previa, a mayor ruptura mayor z (test) |
| V2-M4 | Agregación por **Z de Stouffer** `Σwz/√Σw²`, pesos margen 0,35 · crecimiento 0,25 · deuda 0,20 · AR 0,10 · AP 0,10; `momentum = 50+50·tanh(z̄/2)` | La media ponderada de tanh diluía una ruptura clara de una sola dimensión (margen z=−2,7 quedaba «stable»); con Stouffer el agregado es N(0,1) bajo ruido con cualquier subconjunto de fuentes, así que el umbral no depende de tener ERP |
| V2-M5 | Dirección si `|z̄| ≥ 1,5`; confirmación con dos meses seguidos **y** mes actual del mismo lado de su nivel (`current_month_support_z`); histéresis 0,75 para mantener una dirección confirmada | Es la regla que separa bache de tendencia sin mirar t+1. Umbral 1,0 daba 26% de etiquetas direccionales y 1,5 un 21% de |z̄|>1,5 frente al 13% esperado bajo ruido; la sensibilidad 1,0/1,5/2,0 está en el comparador |
| V2-M6 | Momentum solo si las señales disponibles suman ≥50% del peso nominal; si no, NaN y `insufficient_history` (no se rellena con 50) | Evitar «estable» sostenido por una única señal |
| V2-E1 | `episode`: `trend_*`, `one_off_dip/spike` (|desviación mensual| ≥ 2σ sin tendencia confirmada), `not_sustained_by_current_month`, `none` | Hace explícita la respuesta a «bache o caída». Un umbral absoluto de 0,20 marcaba el 44% de los meses como atípicos; 2σ propia marca el 8,9% |
| V2-Q1 | Mes actual fino (1–4 movimientos) se puntúa con la ventana como `provisional` / `thin_current_month`; sin movimientos → `not_scored`; ventana < 3 meses → `insufficient_window_history` | Más cobertura legítima en agosto (922 frente a 876) sin imputar |
| V2-X1 | Explicación aditiva exacta; contribuciones de momentum `k(z̄)·wᵢzᵢ/‖w‖` con factor de saturación común; columna nueva `standardized_value` | Suma validada automáticamente; cada término conserva el signo de su señal |
| V2-X2 | Salida en `data/processed/scores_v2/`; el pipeline rechaza escribir sobre `scores/` | V1 conservado como control |

Se conservan de V1: umbrales de calidad mensual, split 200/50 por `group_id` con semilla 20260918 (holdout ya inspeccionado, declarado en el JSON), anclas, fit/predict con referencia congelada, publicación con staging/backup/manifiesto, exclusión de saldos, deuda final, eventos reservados, HHI y país.

### SC10 · Resultados (panel empresa, toda la historia y agosto 2026)

| Métrica | V1 | V2 |
|---|---:|---:|
| Filas puntuadas | 15.782 | 14.084 |
| Mediana / p75 / p95 de cambio mensual absoluto | 8,77 / 17,94 / 44,26 | **3,31 / 7,26 / 17,87** |
| Cambios > 10 puntos | 20,0% | **6,5%** |
| Scores exactamente 0/100 · a ≤1/≥99 | 1.617 · 1.972 | **716 · 953** |
| Cambio de etiqueta mes a mes | 32,5% | **25,8%** |
| Puntuadas en agosto | 876 (150 scored / 726 provisional) | **922** (285 / 637) |
| Trayectorias (toda la historia) | 7.537 watch · 2.373 imp. · 766 det. · 201 stable · 4.905 s/hist. | 6.443 stable · 635 emerging imp. · 790 emerging det. · 163 improving · 321 deteriorating · 155 mixed · 5.577 s/hist. |
| Agosto | 502 watch · 167 imp. · 63 det. · 14 stable · 130 s/hist. | 554 stable · 53 em. imp. · 68 em. det. · **15 improving · 19 deteriorating** · 10 mixed · 203 s/hist. |

Filas comunes 13.198 (solo V1 2.584: los dos primeros meses de cada empresa; solo V2 886: meses actuales finos): |Δ| mediana 8,64 → 3,46; Spearman entre scores 0,79. Episodios en agosto: 36 `one_off_dip`, 24 `one_off_spike`, 22 `not_sustained_by_current_month`, 19 `trend_deterioration`, 15 `trend_improvement`. Grupo-moneda: 192 parejas puntuadas en agosto (V1: 187). Validación de prefijo hasta 2026-02 correcta en ambos paneles: regenerar con datos hasta febrero reproduce exactamente los scores históricos.

Momentum publicado en 8.507 filas; |z̄| > 1,5 en el 21,4% (13% esperado bajo ruido puro): hay señal por encima del ruido, pero la mayor parte de los meses son, correctamente, `stable`. Deterioros confirmados (321) doblan a mejoras confirmadas (163); no se ha forzado simetría.

### SC11 · Lo que V2 NO mejora (comparador `scripts/07_compare_scores.py`, informe en `data/processed/evaluation/`)

Protocolo fijado en código antes de mirar resultados; partición de desarrollo (200 grupos), holdout aparte y etiquetado como ya inspeccionado; mismas filas para todas las señales; bootstrap de 200 remuestreos por grupo completo; detalle en `docs/validation.md`.

- **Proxy de texto de estrés futuro** (EMBARGO/IMPAGADO/…, t+1..t+h, censurando futuros no observados): AUC V1 0,509/0,510 y V2 0,517/0,522 a 3/6 meses (8.233 y 6.234 filas comunes); IC95 de V2−V1 [−0,008, +0,027] y [−0,009, +0,032]. **Ninguna de las dos discrimina.** La actividad bancaria sola da AUC 0,71 en la dirección «más movimientos → más menciones»: el proxy mide sobre todo exposición; dentro de terciles de actividad ambos scores quedan en 0,54–0,55. Spearman con la tasa de eventos por movimiento ≈0,02–0,04.
- **Proxy de caja reconstruida negativa futura** (independiente del score; runway < 1 se descartó como evento porque ocurre en el 51% de las filas, caja < 0 en el 7,5%): AUC V1 0,50–0,56 y V2 0,49–0,54 según horizonte y partición; IC95 incluyen 0. La persistencia de la caja actual da 0,86–0,93: la caja predice caja, pero no es feature de ninguna versión (D de §12 sigue pendiente).
- **Riesgo relativo por etiqueta a 6 meses (desarrollo):** V2 `deteriorating` 0,246 frente a `stable` 0,232 (RR 1,06); `improving` 0,266 (RR 1,15, en la dirección equivocada); V1 `deteriorating` RR 1,18. `one_off_dip` tiene la tasa más baja (0,176). Las etiquetas no predicen estas menciones.
- **Anticipación con regla independiente** (inicio de episodio tras seis meses limpios; señal en los seis meses previos): texto, 180 inicios: V1 confirmado detecta 26% con lead mediano 3 meses; V2 confirmado 11% con lead 2,5; V2 emerging-o-confirmado 27% con lead 3. Falsas alarmas a seis meses ≈75% para todos con tasa base 20%. Caja negativa, 55 inicios: V1 16%, V2 confirmado 4%, V2 emerging 18%; falsas alarmas 87–90% con tasa base 14%. Mejora: 141 recuperaciones (seis meses limpios tras evento); V1 improving detecta 43%, V2 confirmado 4%, V2 emerging 21%.
- **Sensibilidad al umbral:** con `direction_z` 1,0/1,5/2,0 las cuotas de `deteriorating` son 6,6%/3,8%/2,2% y sus falsas alarmas 76%/75%/74%: el umbral cambia cuántas veces se avisa, no la calidad del aviso frente a este proxy.

**Conclusión honesta:** V2 cumple lo pedido (estabilidad ×2,6 en la mediana de cambio, extremos a menos de la mitad, etiquetas que separan bache de tendencia con regla explícita, cobertura mayor en agosto, explicación exacta) **sin perder** discriminación frente a los proxies (diferencias dentro del ruido). No se puede afirmar que anticipe eventos de estrés: los proxies disponibles apenas se relacionan con la dinámica de flujos operativos de ninguna de las dos versiones, y el texto sintético es sobre todo exposición. Se adopta V2 como candidato de entrega por estabilidad y explicabilidad, con V1 como control; la calibración contra la nota del organizador sigue siendo el único juez que falta.

### SC12 · Reproducir

```bash
python -X utf8 scripts/05_compute_scores_v2.py fit
python -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python -X utf8 scripts/05_compute_scores_v2.py fit --panel group_currency
python -X utf8 scripts/06_validate_scores_v2.py --panel group_currency --check-prefix 2026-02-01
python -X utf8 scripts/07_compare_scores.py
python -W error -m pytest -q          # 201 tests: 167 V1 + 26 V2 + 8 comparador
```

Tests V2 (`tests/test_score_v2.py`): ciclo de entradas sin mejora ficticia, agregación de flujos frente a media de ratios, calendario natural sin puentear huecos, meses de baja calidad fuera de la ventana, no-futuro, bache nunca confirmado como tendencia (y `not_sustained_by_current_month`), escalón confirmado en ≤3 meses con score monótono y `stable` al estabilizarse en el nuevo régimen, mejora simétrica con histéresis, ruptura mayor → z mayor, empresa estable sin dirección, momentum 50 en serie constante, referencia serializable y grupos disjuntos, prefijo/mutación futura, referencia congelada e independencia del batch, descomposición exacta, primeros dos meses sin score, mes fino provisional, mes sin movimientos no puntuado, desaparición del ERP sin salto (>7 puntos) y desvanecimiento en la ventana, ERP ausente permitido pero no sano, error de esquema por columna núcleo, mediana de retraso sin conteo rechazada, deuda sin entradas → nota 0, snapshots/texto no consumidos, orden de entrada, configuración incoherente rechazada. Tests del comparador (`tests/test_evaluation_compare.py`): AUC, Spearman, censura y normalización del proxy, inicios/recuperaciones, caja negativa futura, lead time, bootstrap reproducible, métricas de estabilidad.

### SC13 · Pendientes tras V2

1. Producto/demo sobre V2: cartera con `trajectory`/`episode`, ficha con la tabla de contribuciones y el relato «nivel 6m · trimestre reciente frente a anterior · mes actual». Sin desplegar aún.
2. Contrato del leaderboard (D18/M01) sin cambios: confirmar unidad, escala y formato; `company_latest_scores.csv` de V2 es candidato, no submission.
3. Liquidez como dimensión (variante D) y fallback de exportación (E) siguen sin implementar; la caja actual predice caja futura (AUC 0,86–0,93) y podría aportar una dimensión de nivel si se resuelve la auditoría de fiabilidad retrospectiva de §12.
4. El rebote simétrico del momentum tres meses después de un mes atípico está documentado (`atypical_months_in_window`), no suavizado.
5. Ninguna cifra de este apartado equivale a acuerdo con el score oculto ni a anticipación financiera demostrada; los proxies son texto sintético y caja reconstruida.

## 14. Anotaciones semánticas en cleaned — 19-09-2026 (noche)

**Petición del usuario:** entender los datos con detalle, identificar patrones no evidentes para el motor de scoring e implementarlos uno a uno. La evidencia completa está en `docs/hallazgos-datos.md` (onboarding/desconexión, ruido blanco mensual, estacionalidad, ruptura de taxonomía en 2025-01, 39 % del importe sin categoría, pólizas operativas, deuda no declarada, `overdue` como higiene ERP). Este apartado documenta el **primer paso implementado**: marcas en la capa cleaned. No cambia ninguna feature ni ningún score.

### SC14 · Qué se ha hecho

- Nuevo módulo `src/xray/clean/annotations.py` (D25–D30), llamado al final de `clean_transactions`. Solo añade columnas; **no quita filas ni recategoriza**: 2.554.288 transacciones y 876.756 facturas, como antes.
- `clean_all` pasa ahora a `clean_transactions` la tabla de productos con `type` y `kind` (banking/debt). Si faltan, `product_kind`/`product_type` quedan nulos (compatibilidad con tests y tablas antiguas).
- `clean_invoices`: nueva columna `expected_payment_date` (F07) con la fecha de relleno que F04 anula; `payment_date` sigue siendo solo pago real.
- `CleaningLog` admite la acción `annotate` para columnas no booleanas.
- Tests nuevos en `tests/test_clean_annotations.py` (6): tipo de producto y compatibilidad, bloques SCF/repo/efectivo, pasarela, prioridad de eventos y signo, fecha prevista. **225 tests pasan** (`python -m pytest -q -p no:asyncio`; `-W error` falla en el entorno del usuario por el plugin global `pytest-asyncio`, no por el proyecto).
- `data/cleaned` regenerado (44 s). Conteos por regla en `_cleaning_log.csv` y en la tabla de §6 «Anotaciones semánticas».

### SC15 · Por qué estas marcas y no otras

| Marca | Problema que resuelve | Cómo se verificó |
|---|---|---|
| D25 `product_kind/type` | 170 empresas operan (cobros, nóminas, impuestos) desde 312 pólizas de crédito; la reconstrucción de caja solo mira `checking` y D06 las trataba como desconocidas | 183.417 movimientos, 181.917 en `lineofcredit`; `liquidity = balance − granted` en `balances` |
| D26–D28 SCF, repos, efectivo | Son el grueso identificable del 39 % de importe sin categoría; no son ingreso ni gasto operativo y contaminarían cualquier fallback por signo | Plantillas de texto sobre 635k filas sin categoría; sumas espejo PR.A/VT.A idénticas (2,22e8) |
| D29 pasarela | `interest_charge` incluía costes de Stripe antes de 2025-01 y después pasaron a `-`: ruptura del servicio de deuda para ~150 empresas | Mismas 528 empresas activas antes/después; plantilla `[fecha] tipo` casa 13.009 filas en 17 empresas |
| D30 `event_type` | Los eventos de estrés son el único ancla discreta e independiente para medir anticipación; el conteo previo (`stress_events`) no distinguía cuota impagada propia de recibo devuelto de cliente ni era robusto al cambio de signo de los refunds | Revisión manual de plantillas por evento; `SANCION` retirado tras detectar 3.638 multas de tráfico de una flota |
| F07 fecha prevista | El 96 % de las facturas `overdue` tienen `payment_date == due_date`: es la previsión del ERP, útil como calendario de vencimientos, nunca como pago | Distribución de edad de overdue sin decaimiento por antigüedad |

Descartado en esta capa y aplazado a features: mes dormido / cuenta cerrada / cambio de cuentas (son propiedades del calendario mensual, no de la fila) y el ajuste estacional.

### SC16 · Qué no ha cambiado

- Reglas T/F/D01–D24 idénticas; mismos hashes de raw; mismas filas eliminadas.
- Ninguna feature consume aún D25–D30 ni F07. `stress_events` sigue usando sus propios patrones hasta que se migre a `event_type`.
- Ningún score (V1, V2) cambia con esta regeneración de cleaned.

### SC17 · Siguiente paso acordado

`coverage_state` empresa-mes en features (**hecho, FE10 abajo**), ajuste estacional explícito y fallback por signo excluyendo D04/D05/D26/D27; después utilización de póliza, servicio de deuda desde transacciones (con D29 excluido) y colas de retraso en facturas. Ver `docs/hallazgos-datos.md` §11 para el orden y la justificación.

### FE10 · Estado de cobertura por entidad-moneda-mes (`src/xray/features/coverage.py`)

Motivo: las trayectorias más extremas del panel eran altas de cuentas y desconexiones, no cambios de negocio (`hallazgos-datos.md` §1). Se etiqueta cada fila de los tres paneles con `coverage_state`, calculado **solo con datos ≤ mes**; el test de prefijo hasta 2026-02 sigue pasando.

| Estado | Regla | Filas panel primario | Agosto 2026 |
|---|---|---:|---:|
| `no_data` | `tx_count == 0` | 10.163 | 152 |
| `pre_activity` | solo cuentas dormidas y aún sin actividad real observada | 511 | 11 |
| `dormant` | solo cuentas dormidas tras haber tenido actividad real (pausa o desconexión: no se distingue sin mirar el futuro) | 848 | 62 |
| `onboarding` | primeros `onboarding_months=2` meses desde la primera actividad real | 2.417 | 1 |
| `account_change` | entran/salen cuentas activas que pesan ≥ `account_change_min_share=0,10` del volumen del mes en que estaban activas | 1.982 | 86 |
| `ok` | comparable con el mes anterior | 14.943 | 974 |

Cuenta dormida en el mes = ≤ `dormant_max_transactions=3` movimientos utilizables **y** < `dormant_max_amount=2.000` unidades nominales (comisiones de 12/30/182/250). El umbral de importe es nominal por moneda; revisar si se puntúan monedas con escala muy distinta. Sin materialidad, `account_change` marcaba 4.739 filas porque tarjetas secundarias parpadean entre dormida y activa; con ella, 1.982.

Columnas nuevas: `coverage_state`, `is_coverage_comparable`, `tx_active_accounts_real`, `tx_dormant_accounts`, `tx_new_active_accounts`, `tx_dropped_active_accounts`, `tx_account_change_share`, `months_since_first_activity`. Son calidad/cobertura: **fuera de `model_features`** (siguen siendo 126). Validación añadida: estados dentro del contrato, `no_data` ⇔ `tx_count == 0`, ningún `ok` sin cuenta activa real. `_feature_quality.json` publica el recuento por estado.

Casos verificados sobre datos reales: COMP_0794 (alta en 26-02) pasa `pre_activity → onboarding → account_change → ok`; COMP_0612 (desconexión) termina en `dormant`/`no_data`; COMP_1109 marca `no_data` en el hueco y `account_change` al reaparecer. De las 12.583 filas `is_training_eligible`, 1.334 son `account_change` y 34 dormidas/onboarding: hoy entran al score y no deberían alimentar el momentum.

**Uso previsto (pendiente, capa score):** momentum y deltas solo entre meses `ok` consecutivos; `onboarding`/`account_change` → nivel sin trayectoria; `dormant` → no puntuar ni arrastrar el score anterior. Tests: `tests/test_coverage_state.py` (8).

## 15. Categorías AI para movimientos sin categoría (TypeSafe Jev) — 19-09-2026

**Petición del usuario:** evaluar dónde aporta valor real el modelo Jev de TypeSafe (decisiones tipadas con probabilidad y confianza, sin generación de texto) e integrarlo **una sola vez**, sin dependencia de API en el pipeline. Evidencia previa en §14/`hallazgos-datos.md` §5: el 24,9 % de las filas y el **38,8 % del importe** están sin categoría, con importe sin categoría ≈ 0,95× el importe operativo identificado, concentrado en banca no española (HSBC/ING/Revolut 76–85 %).

### D31 · Qué se ha hecho

- **Pasada única** con `scripts/experimental/jev_categorize_all.py` (experimental, fuera del pipeline): 145.818 plantillas de texto (`upper`, `COUNTERPARTY_n→CP`, `[TOKEN]→T`, dígitos→`#`, sin puntuación), una llamada por plantilla+signo con `state = {narrativa, dirección, importe típico}`. 140.818 plantillas sin categoría (todas, sobre booked y |importe| ≤ 1e8) + 5.000 más frecuentes con categoría del banco como control. 144.166 llamadas, 80 min, ~30 req/s; **198 plantillas (0,14 %) sin respuesta** por agotarse los créditos. Preguntas: `Choice` en 12 bloques económicos (con opción `unknown` obligatoria), dos `Noul` de estrés (recibo devuelto por impago; descubierto/embargo/recargo).
- **Artefacto estático versionado:** `resources/jev_categories/template_categories.parquet` (11 MB) + `_manifest.json` (preguntas, mapeos, hashes, conteos). Respuestas crudas (99 MB) solo en `data/enriched/`, gitignored.
- **Integración como política en features, no en cleaned** (A03): `src/xray/features/ai_categories.py`; `FeatureConfig(ai_categories_path, ai_min_confidence=0.7)`; CLI `--ai-categories`, `--ai-min-confidence`. Solo rellena filas `category == "uncategorized"`; **la categoría del banco nunca se sobreescribe**. Conserva `category_bank`, `category_source` (bank/ai/none) y `category_ai_confidence`. Nuevos importes diagnósticos `tx_ai_categorized_amount`, `tx_ai_nonoperating_amount`. El manifiesto de features registra `ai_categories_sha256`.
- Mapeo bloque→categoría FE03: `operating_inflow→collection`, `supplier_payment→payment`, `utility/salary/social_security/tax` idénticos (tax con signo positivo → `tax_refund`), `bank_fee→fee`, `internal_transfer/cash/bank_adjustment→ai_nonoperating` (fuera de flujos operativos). **`interest_or_debt` y `unknown` no se usan**: el bloque de deuda tuvo acuerdo débil con el banco en el control. Veto en código: bloque operativo incoherente con el signo → `unknown` (3.089 plantillas, 42.031 filas).
- Tests: `tests/test_ai_categories.py` (5). **233 tests pasan.** Sin flag, ninguna feature ni score cambia.

### D31 · Evidencia

Control (5.000 plantillas con categoría de banco, a nivel de bloque grueso FE03 `op_in/op_out/debt/fee/nonop`): acuerdo **78 %** sin umbral, **85 %** con conf ≥ 0,7 (cobertura 48 %), **87 %** con conf ≥ 0,85; ponderado por filas 86–88 %. Cruces `op_in↔op_out`: 42 filas de 460k. Revisión manual: una parte visible de los desacuerdos son errores del banco (`PRIMEVIDEO.ES`=utility, `FACEBK ads`=fee, `CLARET LOAN`=tax, `TRANSF INTERNA`=tax), así que el acuerdo es un suelo, no la accuracy. Fuga principal: banco `payment`/`collection` → Jev `nonop` (transferencias a contrapartes; ambiguo), que es conservadora.

Sin categoría (613k filas): confianza mediana 0,71. Con conf ≥ 0,7 se clasifica el **39 % de filas / 34 % del importe**; operativo recuperado **29 % / 30 %**; no operativo identificado 8 % / 4 %. Techo: el 4,4 % de filas y **13 % del importe** es texto totalmente redactado (`([X] NONREF)…`) marcado `unknown` con alta confianza; irrecuperable por cualquier método.

A/B sobre el pipeline completo (misma cleaned, `data/processed` vs `data/processed_ai`):

| Medida | Base | Con D31 |
|---|---:|---:|
| `tx_inflow` / `tx_outflow` totales | — | +6,4 % / +11,8 % |
| Importe sin categoría | 6,39e10 | 5,07e10 (−20,6 %) |
| Empresa-mes (≥5 mov.) que fallan «≥10 % operativo» | 2.188 | **1.164** (1.024 recuperados, 0 nuevos fallos; 239 empresas) |
| Share operativo mediano | 0,557 | 0,630 |
| Volatilidad intra-empresa del margen (std mensual, mediana) | 0,419 | 0,401 (baja en 313 empresas, sube en 132) |
| Score V2 agosto 2026: puntuadas / `not_scored` | 922 / 364 | **977 / 309** |
| Score V2 toda la historia: filas puntuadas | 14.084 | 14.932 (+848, 179 empresas; 0 perdidas) |
| Δ score en filas puntuadas en ambas | — | mediana 0,78, p90 7,1; >10 pts en 7,2 % |
| Mediana por empresa del Δ mensual del score | 3,18 | 3,27 |

Los cambios grandes revisados son correcciones, no artefactos: COMP_1101 (score 1 → 64: cobros «CT INGENIEROS» 302k sin categoría daban margen −1), COMP_0045 (100 → 48: banco holandés, todas las salidas `SEPA Overboeking` sin categoría daban margen +1), COMP_0556 (30 → 91: «Amount received» de banco UK sin categoría daban entradas 0).

### D31 · Límites y pendientes

- Umbral 0,7 **propuesto, no calibrado**: elegido por el codo del control (85 %) y la cobertura; comparar 0,6/0,85 con el mismo holdout antes de cerrarlo.
- Acuerdo medido contra la categoría del banco, que tiene errores; no hay etiqueta oro ni resultados del organizador.
- `interest_or_debt` sin usar: el servicio de deuda sigue dependiendo de `debt_repayment/interest_charge` del banco (con la ruptura D29). Los dos `Noul` de estrés están en el artefacto (129 plantillas / 10.307 filas de recibo devuelto ≥0,7; 409 / 3.960 de descubierto/embargo) pero **ninguna feature los consume** todavía; candidatos a complementar D30 `event_type`.
- El artefacto cubre solo plantillas vistas en este dataset: un dataset nuevo con textos distintos requiere otra pasada (créditos) o quedará `uncategorized` como hoy.
- Decidir si D31 pasa a ser el default del pipeline (`01_build_monthly_features.py --ai-categories resources/jev_categories/template_categories.parquet`) y regenerar `processed`/`scores_v2` con él.

## 16. Capa de producto y API — 19-09-2026 (noche)

Implementado sobre V2 sin recalcular ningún score. Código en `src/xray/product/` y `backend/`; plan completo en [roadmap-tecnico-mvp.md](./roadmap-tecnico-mvp.md); contrato de la API en [brief-backend-api.md](./brief-backend-api.md). Todo lo de esta sección está en `origin/main`.

### PR01 · Lo que existe y cómo se reproduce

```bash
python -X utf8 scripts/05_compute_scores_v2.py fit      # scores_v2/
python -X utf8 scripts/08_build_product.py              # data/processed/product/  (~1 min)
uvicorn app.main:app --app-dir backend --port 8000      # API de solo lectura
python -m pytest -q tests                               # pipeline + producto
python -m pytest -q -p no:asyncio backend/tests         # API
```

`data/processed/product/`: `portfolio.json` (1.286 filas, moneda principal, último mes), `companies/{id}.json` (timeline 24 m, «por qué ha cambiado», confidence, cash truth, por moneda), `groups/{id}.json`, `score_changes.parquet`, `confidence.parquet`, `cash_truth_monthly.parquet`, `cash_truth_summary.parquet`, `evidence/cash_truth_tx.parquet`, `_product_manifest.json` (hashes de entradas/salidas y commit).

### PR02 · Decisiones

| ID | Decisión | Motivo |
|---|---|---|
| PR-01 | **La API sirve, no calcula.** FastAPI lee los JSON precomputados y se recarga sola cuando cambia el sha256 del manifiesto; cada respuesta lleva `X-Xray-Manifest` | Cuando datos/score cambian, la API no cambia; se audita qué versión se enseñó |
| PR-02 | `POST /import` ejecuta `00 → 01 → 05 predict --reference <congelada> → 08` en subproceso con `XRAY_DATA_DIR` aislado por job; se consulta con `?dataset=job_id` y **no** sustituye el dataset principal | Mismo contrato que el test oculto: nunca `fit` con empresas nuevas |
| PR-03 | «Por qué ha cambiado» = delta de la contribución exacta de cada término entre meses naturales consecutivos, separado en **efecto valor** (Δ nota × peso anterior) y **efecto peso** (aparición/desaparición/renormalización). La suma reproduce `delta_vs_prev` (validado en las 67.392 filas) | Responde al requisito obligatorio del enunciado con la aritmética del score, sin narrativa inventada. `reference_changed` marca que parte del efecto valor puede venir de la referencia expansiva; no se aísla todavía |
| PR-04 | **Confidence** 0–100 = media ponderada de historia (25), componentes disponibles (25), calidad del mes (15), tendencia calculable (15) y caja identificada (20); tope 70 con cobertura parcial de moneda; 0 sin movimientos. Se declara «no es probabilidad de acierto» | Compone campos que V2 ya publica; los pesos son propuesta de UI, no calibración |
| PR-05 | **Cash Truth**: un bucket por movimiento elegible (mismo criterio de elegibilidad que features), por prioridad `own_circulation (D04) → group_support (D05) → financing_investment → operations (INFLOW∪OUTFLOW) → unpaired_transfer → uncertain`. Lo no identificado se publica como `uncertain`, nunca se reparte | No inventar clasificación. Reutiliza los espejos de limpieza en vez de contrapartes (que no se comparten entre empresas) |
| PR-06 | `support_dependency_ratio = apoyo_recibido_6m / (entradas_operativas_6m + apoyo_recibido_6m)`, ventana hacia atrás, mínimo 3 meses activos; tendencia = trimestre reciente − anterior; rol `net_receiver/net_provider/balanced`. Test de prefijo | Señal de «Internal Support Dependency» de la propuesta, sin mirar t+1 |
| PR-07 | Las dimensiones «dependencia de apoyo» y «resiliencia» de la propuesta **no entran en el score**; viven en Cash Truth y Confidence | El score V2 tiene cuatro componentes; no prometer en pantalla lo que el número no contiene |
| PR-08 | Time Borrowed, alertas, what-if y frontend siguen pendientes (F3–F6 del roadmap). `/alerts` devuelve lista vacía hasta que exista `alerts.json` | Priorizar por cobertura medida (PR03) |

### PR03 · Cobertura medida que justifica el orden

- Cash Truth: reparto del importe elegible — operación 33 %, circulación propia 18 %, incierto 18 %, traspasos sin emparejar 16 %, apoyo intragrupo 13 %, financiación 1 %. En agosto 2026 el ratio de dependencia existe para 1.152 empresas; **307 ≥ 30 %**, 143 con tendencia ≥ +10 pp. Caso de demo: `COMP_0647` (apoyo 77,5 % del movimiento, operación saca 22 M€ y mete 1,1 M€).
- Time Borrowed (medido sobre `cleaned/invoices`, aún sin implementar): relaciones comparables (≥10 facturas pagadas, ≥6 meses, plazo real) AR 2.069 en 264 empresas, AP 4.184 en 418. El patrón «puntualidad mejora pero tiempo a caja empeora» aparece en **6 relaciones / 4 empresas** (`COMP_1191`/`COUNTERPARTY_48964`); proveedores acortando ventana ≥15 d: 324 relaciones / 130 empresas. Es alerta de nicho, no señal universal.
- Contrapartes: 0 `counterparty_id` de facturas compartidos entre empresas → no hay red de contagio posible con estos datos.

### PR04 · Correcciones de datos

- `io.read_raw`: cinco fechas de facturas con años 3025–7025 desbordan `datetime64[ns]`; con pandas 2.2 `parse_dates` dejaba la columna como texto y la limpieza fallaba antes de llegar a F05. Ahora se fuerzan a `NaT` y F05 las trata. Fixture de `tests/test_clean.py` alineado.

### PR05 · Límites

- Cash Truth clasifica por reglas de limpieza y categoría del banco; el bucket `uncertain` (18 %) es información, no error. Las categorías AI (§15) no se usan aún en los buckets.
- Confidence no está calibrada contra ningún resultado; ordena evidencia, no acierto.
- No hay anticipación medida publicada (`lead_time.json` pendiente en F3) ni despliegue público: la API corre en local.

## 17. Encaje D25–D30 / FE10 / V2 estacional con D31 — 19-09-2026 (noche)

Revisión cruzada tras leer `docs/jev-categorias.md`. Lo implementado en §14/FE10 (anotaciones, cobertura, estacionalidad en V2, commit `fcb2bb3`) y D31 (§15, commit `c32901f`) son complementarios; ninguna pieza requiere cambios en la otra. Tabla de solapes y decisiones propuestas, pendientes de acuerdo del equipo.

### SC18 · Solapes verificados

| Pieza mía | Pieza D31 | Relación | Decisión propuesta |
|---|---|---|---|
| D26–D28 `is_scf_adjustment`, `is_repo_pair`, `is_cash_disposal` | Jev clasifica los mismos textos como `bank_adjustment`/`internal_transfer`/`cash` → `ai_nonoperating` | Redundantes y coherentes; el flag es exacto por plantilla | Excluir de `tx_cash_*` **por flag**; D31 cubre el resto |
| D29 `is_gateway_cost` | Jev manda `[fecha] stripe_fee/network_cost` a `fee` | Complementarios: D31 recompone `tx_fees_paid` desde 2025-01; D29 permite **excluirlos** de `interest_charge` antes de 2025-01, que D31 no toca | Servicio de deuda = `interest_charge & ~is_gateway_cost` |
| D30 `event_type` (regex + signo) | `noul_unpaid_return` (10.307 filas ≥0,7), `noul_overdraft_or_seizure` (3.960) | Los Noul distinguen «devolución de fianza/error» de «recibo devuelto por impago», que el regex no separa; son multilingües | Fusionar en `event_type` con prioridad regex exacto D30 > Noul ≥0,7; publicar `event_source` |
| FE10 `coverage_state` | — | Independiente: D31 no altera `tx_count`/`tx_usable_count`; sí sube `tx_operating_amount_share` (0,557 → 0,630) | Ninguna |
| Fallback por signo (`hallazgos` §11.5, no implementado) | D31 resuelve el 29 % de filas / 30 % del importe sin categoría con categoría real | D31 es mejor donde hay plantilla; el fallback sigue haciendo falta para el **13 % del importe totalmente redactado** y para **plantillas no vistas del test oculto** (créditos agotados) | Implementar fallback solo sobre filas que sigan `uncategorized` tras D31, excluyendo D04/D05/D26/D27; publicar `categorized_amount_share` |
| Referencia congelada V2 (cuantiles + factores estacionales) | Features con D31 desplazan `tx_inflow/outflow` (+6,4 % / +11,8 %) | Mezclar referencia base con features D31 mueve el nivel | Si D31 pasa a default, **reajustar la referencia** en el mismo cambio y regenerar `processed`/`scores_v2` |

### SC19 · Riesgos que D31 no elimina

1. Test oculto con bancos extranjeros: sin plantilla conocida, el caso COMP_0045 (score 100 por salidas invisibles) se repetiría; solo el fallback por signo lo evita.
2. El 85 % de acuerdo es contra la categoría del banco, no accuracy; `interest_or_debt` sigue sin usarse (acuerdo 4/10).
3. Estacionalidad: los factores de V2 se estiman sobre `tx_lfl_inflow_growth`; con D31 el crecimiento incluye más flujo operativo y los factores deben reestimarse (automático en `fit`).

### SC20 · Orden propuesto

1. D31 a default + reajuste de referencia V2 + regeneración (un solo commit coordinado).
2. Fallback por signo residual con `categorized_amount_share`.
3. Fusión Noul → `event_type`; migrar `stress_events` a `event_type`.
4. Exclusión D26–D28 por flag y D29 en servicio de deuda.
5. Consumo de `coverage_state` en momentum de V2 más allá del `provisional` actual (deltas solo entre meses `ok` consecutivos).

## 18. D31 como default, referencia V2 reajustada y regeneración — 19-09-2026 (cierre)

Primer punto del bloque A del plan (`roadmap-tecnico-mvp.md`, «Estado consolidado»). Un solo cambio coordinado para que `processed`, `scores_v2` y `product` sean coherentes entre sí y con la referencia congelada.

### SC21 · Qué se ha hecho

- `scripts/01_build_monthly_features.py` usa por defecto `resources/jev_categories/template_categories.parquet` (`xray.paths.AI_CATEGORIES_PATH`); `--no-ai-categories` recupera el comportamiento anterior y `--ai-categories RUTA` permite otro artefacto. Si el artefacto no existe, falla con mensaje explícito en lugar de degradar en silencio. `FeatureConfig.ai_categories_path` sigue siendo `None` por defecto en la API de Python: `build_features` sin argumentos no cambia y los tests no dependen del artefacto.
- Regenerados en orden: features (prefijo 2026-02 OK), `scores_v2 fit` (referencia reajustada sobre features D31, prefijo OK), `08_build_product`. El manifiesto de features registra `ai_categories_sha256 = 448d70d1…`.

### SC22 · Resultado sobre datos reales

| Medida | Antes (base) | Ahora (D31 + FE10 + estacional) |
|---|---:|---:|
| Agosto 2026 puntuadas / `not_scored` | 922 / 364 | **977 / 309** (281 `scored`, 696 `provisional`) |
| Filas puntuadas, toda la historia | 14.084 | **14.932** |
| Motivos `provisional` en agosto | — | optional_components_missing 409, trend_unavailable 125, thin_current_month 72, partial_currency 51, **coverage_account_change 27**, short_history 12 |
| Filas `coverage_onboarding` / `coverage_account_change` en la historia | — | 357 |
| Trayectoria agosto | — | stable 620, emerging_deterioration 66, emerging_improvement 61, deteriorating 19, improving 17, mixed 12, insufficient 491 |
| Mediana de |Δ score mensual| | 3,18 | 3,05 |

Factores estacionales del crecimiento vigentes en agosto 2026 (log-crecimiento, mediana centrada, ≥50 filas por mes del año): **ago −0,29**, ene −0,16, nov −0,11, dic +0,11, jul +0,06, resto |·|<0,07. Coinciden con la exploración (`hallazgos-datos.md` §3). En agosto de 2026 el ajuste suma +0,22 al crecimiento trimestral mediano: sin él, la caída estacional de agosto se leería como deterioro de entradas.

### SC23 · Límites

- La referencia congelada ahora presupone features con D31; `predict` sobre un dataset nuevo debe ejecutarse con el mismo artefacto (o con `--no-ai-categories` **y** una referencia ajustada sin D31). Plantillas no vistas quedan `uncategorized`: sigue pendiente el fallback por signo (A.3).
- El manifiesto guarda la ruta absoluta del artefacto; el hash es lo que identifica la versión.
- Las cifras de agosto no son acierto frente al organizador; miden cobertura y estabilidad.

## 19. Integración del frontend: exportador al contrato JSON — 19-09-2026 (noche)

El frontend mergeado (`7822f35`, `frontend/`) **no consume la API ni `product/companies/{id}.json`**: lee ficheros estáticos `frontend/public/generated/{companies,groups}/<id>.json` con su propio contrato Zod (`docs/frontend-data-contract.md`: empresa `2.0`, grupo `1.0`). Se decide **no tocar el frontend** y añadir un exportador en la capa de producto (bloque A.1 del roadmap).

### FE-01 · Qué se ha hecho

- `src/xray/product/frontend_export.py` + `scripts/09_export_frontend.py`: traduce `product/` al contrato con escritura atómica; **no recalcula**. Resultado real: **1.018 empresas** (268 sin ningún score no se exportan: la UI muestra «no disponible») y **250 grupos**, todos válidos con `npm run validate:generated` (y `-- --groups`). `/companies/COMP_0647` y `/groups/GROUP_0250` renderizan con datos reales. Tests: `tests/test_frontend_export.py` (7).
- Mapeo: `health_score = round(score)`; `history` = meses con score (el último coincide con el actual, `as_of` = fin de mes); `trajectory` colapsa las 7 etiquetas V2 a 3 (`emerging_*` → su dirección; `mixed_signals`/`insufficient_history` → `stable`); `drivers` = términos de «por qué ha cambiado» con `component → dimensión`; `cash_truth` = 6 buckets → 4 categorías (`unpaired_transfer` y `financing_investment` → `uncertain`, neto `null`), `own_account_circulation` = pata de entrada de D04 contada una vez; `evidence` = hasta 10 movimientos por empresa (2 por bucket, luego por importe) con `total_count` real. `time_borrowed` `null`, `alerts []`, `scenarios []` con metodología que explica la ausencia. Textos en español por plantilla.
- **Dimensiones (decisión provisional a revisar con el autor del frontend):** el contrato exige cuatro números 0–100 y V2 puede no tener `momentum` o cobros/pagos. `cash_generation = level_operations`, `debt = level_debt`, `resilience = media(level_collections, level_payments)`, `momentum = momentum`; una dimensión ausente se exporta con el valor del propio `health_score` (no altera la media) y `health_score_model.provisional = true`. Pesos exportados: los efectivos de V2 traducidos a cuatro dimensiones (momentum 0,20 · cash_generation 0,36 · resilience 0,24 · debt 0,20; `0,8×0,45`, `0,8×0,25`, `0,8×0,30`). Propuesta al frontend: admitir `null` en `dimensions` para no exportar neutros.
- Grupo mínimo válido: miembros con score/dimensiones/rol (`support_role` de Cash Truth → provider/receiver/both), `internal_received/provided` y `cash_generation_net` de la ventana 6m; liquidez/deuda/obligaciones `null` con explicación; `relations`, `recommendations`, `insights` vacíos; `limitations` explícitas.

### FE-02 · Límites y siguientes pasos

- El frontend no tiene **Portfolio**: la demo arranca en una URL de empresa. Pedir al autor una ruta `/` que lea un `portfolio.json` (podemos exportarlo al contrato que defina).
- `public/` es público y los JSON están gitignored: en despliegue hay que ejecutar `09_export_frontend.py` en el build o montar `COMPANY_ANALYSIS_DIR`/`GROUP_ANALYSIS_DIR`.
- Cuando existan alertas (bloque B), Time Borrowed y escenarios, se rellenan los campos ya previstos sin cambiar componentes. `account_flows` (cuentas y transferencias con dos tramos) queda pendiente: requiere enlazar los pares D04/D05 a filas de evidencia.
- Orden de ejecución completo: `00 → 01 → 05 fit → 08 → 09`, y después `npm run validate:generated` desde `frontend/`.

### FE-03 · Portfolio v1 (19-09, noche)

El frontend no tenía ruta raíz. Se añade **`/`** con la cartera («¿qué empresas necesitan atención?»): KPIs (empresas, con score, atención alta, deteriorándose, mejorando, dependientes de apoyo), filtros por trayectoria / atención / estado / grupo / búsqueda, ordenación (atención, Health Score, Δ mes, cobertura, dependencia, id) con nulos siempre al final, paginación de 100 y enlaces a ficha y grupo. Formulario GET: funciona sin JavaScript y conserva la URL como estado.

- Contrato nuevo `frontend/types/portfolio.ts` (`schema_version 1.0`; una fila por empresa: `health_score` entero nullable, `trajectory` 3 valores + `trajectory_stage` confirmed/emerging, `confidence`, `score_status`, `status_reason` en español, `main_signal` e impacto, `support_dependency_ratio`, `attention`, `has_detail`). Lectura en `services/portfolioData.ts` (`PORTFOLIO_ANALYSIS_FILE` opcional); `npm run validate:generated -- --portfolio`. Tests `tests/portfolio.test.ts` (5).
- Exportación en `frontend_export.portfolio_export`: **1.286 filas** (218 atención alta, 162 media; 85 deteriorándose, 78 mejorando, 491 sin trayectoria). `attention`: alta = deterioro confirmado o dependencia ≥ 50 %; media = deterioro emergente, dependencia ≥ 30 % o score < 35; baja el resto. Es una prioridad de revisión, no una probabilidad.
- Las empresas sin ficha (`has_detail = false`, 268 sin ningún score) aparecen en la tabla con su motivo pero sin enlace.

> Sección numerada §14 en local; renumerada a §18 al integrar las §14–§17 del remoto y a §20 al integrar sus §18–§19 (19-09-2026).

## 20. Optimización de grupo — `group_treasury_advisor_v1` (19-09-2026, planificación)

**Estado: especificado y aprobado, no implementado.** Spec en `docs/group-optimization.md`; ejecución por paquetes de trabajo paralelizables en `docs/roadmap-group-advisor.md`. Los agentes que implementen cada WP registran aquí sus desviaciones y resultados con IDs `GA-xx`.

### GA-00 · Decisiones tomadas con el usuario

| Decisión | Elegido | Descartado y por qué |
|---|---|---|
| Objetivo de grupo | Utilidad cóncava lineal a tramos `U(L)` con pendientes 3/2/1 en <40 / 40–70 / ≥70, `G = Σ ω_i U(L_i) / (2,1·Σ ω_i)` en 0–100, `ω_i` iguales | Max-min lexicográfico (ignora la segunda peor filial); consolidado grupo-moneda (ponderado por flujo, la filial grande domina y las transferencias no lo mueven) |
| Palancas | **D1** asunción del servicio de deuda de la filial débil por la fuerte; **P** financiación para pagar AP en plazo, solo si la receptora está restringida por liquidez | **D2** cancelación anticipada: V2 mide servicio observado y el pico de principal penaliza seis meses aunque ahorre intereses. **A** aceleración de cobros: coste no observable. Margen: estructural, no es tesorería |
| Horizonte | Efecto en k=1 (próximo cierre) y k=6 (régimen); optimización en k=6; momentum no simulado | Solo régimen (oculta la transición); serie k=1..6 (más supuestos) |
| Narrativa | Plantillas deterministas + Q&A cerrado primero; LLM opcional después con validador de anclaje y fallback | LLM desde el inicio (sin proveedor decidido; el producto no puede depender de él) |
| Encaje de producto | «Escenario mecánico bajo supuestos explícitos» (What-if, propuesta §11); actualizar §12/§18 de `embat_pulse_mvp_propuesta_final.md` en WP5 | Solo diagnóstico sin importes (menos útil); prescriptivo pleno (fiscalidad/covenants no observables) |
| Estructura de producto | **Dos apartados, un motor**: ficha de empresa (score + «qué mueve tu nivel») siempre; vista de grupo (plan coordinado) solo si ≥2 filiales puntuadas; enlaces cruzados (papel de la filial en el plan). La vista de empresa es sensibilidad, la de grupo son acciones coordinadas; no compiten | Solo grupo cuando hay grupo (la unidad del score es la empresa; 71 grupos unipersonales); solo empresa (pierde la tesis de grupo) |
| FX | **Tabla fija `fx_rates_to_eur` solo en el advisor y solo para importes** (caja del donante, necesidades, totales en moneda de reporte; palancas cruzadas de moneda con supuesto `fx_fixed_rate` visible). Las señales de V2 son ratios dentro de una moneda y no necesitan FX. `transactions.exchange_rate` **no se usa**: es ambiguo (USD con rate 1 y ≠1, EUR con rate ≠1, máx 6.500; solo 4% de filas) | Convertir en features/V2 ahora (cambia el candidato del leaderboard, la política de 201 tests y reabre D07); mantener D07 estricta también en importes (pierde 42 grupos multimoneda). Variante opcional posterior: panel `company_consolidated` a tipo fijo como artefacto separado para medir cobertura (299 empresas multimoneda) |
| Sensibilidad de empresa | **Palancas de tesorería y de negocio, etiquetadas**: `ap_on_time`, `ar_faster`, `debt_service_cut` (tesorería) y `cut_outflow`, `raise_inflow` (negocio, solo sensibilidad, nunca recomendación). Por palanca: pendiente actual (derivada por diferencia finita sobre `score_level`), distancia al siguiente nudo de las anclas, y cuánto hace falta para cambiar de tramo (bisección, función monótona). Dos normalizaciones: por 1% de cambio relativo y por 10.000 de equivalente de caja | Solo tesorería (deja el 45% del nivel sin sensibilidad visible) |
| Motor común | Perturbaciones **primitivas** sobre la fila de señales de ventana (`inflow_scale`, `outflow_scale`, `debt_service_scale`, `debt_service_add`, `ap_delay_scale`, `ar_delay_scale`); D1, P y las palancas de empresa son composiciones. Un solo motor para los dos ámbitos | Motores separados por ámbito (duplican anclas y casos límite) |

### GA-00b · Hechos comprobados que motivan el módulo (agosto 2026, V2, solo lectura)

157 grupos con ≥2 filiales puntuadas; dispersión intra-grupo mediana 36,6 puntos; 47 grupos con una filial <40 y otra >70. Caja reconstruida fiable en 1.176 de 2.047 pares empresa-moneda (runway en 822). Componentes deuda/pagos/cobros disponibles en 931/587/461 empresas. 42 grupos con más de una moneda declarada. El score grupo-moneda correlaciona 0,84 con la media ponderada por flujo de sus filiales. Ejemplo `GROUP_0064` EUR: niveles 100 / 57 / 38, consolidado 51.

Monedas (cleaned): 90,2% de filas de transacciones en EUR (USD 3,8%, GBP 1,7%); `exchange_rate ≠ 1` en el 4,0% de filas y ambiguo por moneda; 1.149 de 1.286 empresas declaradas en EUR; 299 empresas con alguna cuenta en moneda distinta a la declarada.

### GA-00c · Principios que no se negocian en la implementación

- Una transferencia intragrupo no mueve ningún componente de V2 (D05); solo lo que la receptora hace con la caja. El donante pierde caja, no nivel (mientras liquidez no sea dimensión de V2).
- D1 no cambia el servicio externo del grupo: redistribuye. Se dice.
- Los escenarios se valoran con `xray.score_v2.level.score_level` y la referencia congelada del mes: la función exacta de V2, no una aproximación.
- Sin caja fiable no hay palanca; sin nivel no hay filial optimizable; grupos unipersonales y sin palancas se reportan con motivos y cuentan en la cobertura.
- Greedy determinista con certificado hasta pares; sin garantía de óptimo global.
- Todo número de la narrativa debe existir en el JSON del plan (validador), también para las plantillas.
- FX fijo solo para importes y siempre con original y tipo aplicado; nunca `transactions.exchange_rate`; las señales no se convierten.
- Las palancas de negocio (`cut_outflow`, `raise_inflow`) se muestran como sensibilidad con «todo lo demás igual», nunca como recomendación.
- No se toca `score_v2/`, `scores/` ni el contrato del leaderboard.

### GA-01 · Invariantes del estado (WP1, `src/xray/group_advisor/{config,fx,state}.py`, 19-09-2026)

**Se cumplen todos.** Sobre el panel real, con `window_outflow_sum` y `window_debt_service_sum` recalculadas por `state.window_sums` y las señales de `build_signals`: agosto 2026, 922 filas optimizables → `op_margin_w = (I−O)/(I+O)` en 922/922 comprobables y `debt_service_w = S/I` en 906/906 comprobables (`I > 0` y `d` finito; las 16 restantes tienen `d` NaN por `I = 0`), indicador `debt_without_inflow_w = (I = 0 ∧ S > 0)` en 922/922; sobre las 1.286 filas de agosto 944/944 y 927/927; sobre los 30.864 meses del panel 14.240/14.240 y 13.991/13.991 (tolerancia relativa 1e-6, sin ninguna diferencia). Los niveles del estado son los de `scores_v2` (leídos, no recalculados) y `score_level` sobre la fila de señales del estado con la referencia vigente los reproduce con diferencia 0,0 en las filas optimizables. `GROUP_0064` en 2026-08-01: 12 filiales en el panel, 3 optimizables (`COMP_0007` 57,23 amber, `COMP_0222` 100 green, `COMP_0738` 38,09 red), consolidado EUR 51,19. `load_inputs` tarda ≈31 s (26 s son `build_signals`, que no se toca); `iter_group_states` sobre los 250 grupos ≈3 s.

Decisiones de implementación de WP1 donde la spec dejaba margen:

| Punto | Elegido | Motivo |
|---|---|---|
| Máscaras de `O` y `S` | Las mismas que `_flow_aggregates` de V2: mes con calidad **y** `tx_inflow`/`tx_outflow` observados; `S` exige además principal e intereses observados en todos los meses de la ventana y queda NaN si no (como `debt_service_w`); ambas NaN si la ventana no llega a `level_min_months` (como `level_inflow_sum`) | Que `derive(fila)` reproduzca exactamente las señales V2; en datos reales las máscaras coinciden con «meses con calidad» (deuda nunca NaN donde hay flujos) |
| Filiales sin nivel | Entran en `subsidiaries` con `optimizable=False`, `tramo="none"` y su `score_reason`; no se filtran | La spec §5.3 exige listarlas con motivo; los grupos unipersonales o sin filial optimizable se detectan desde el estado |
| Aviso de invariantes | `logging.warning`, no `warnings.warn` | La suite corre con `-W error`; un aviso de datos no debe convertirse en excepción |
| Consistencia scores/features | `load_inputs` exige que `_company_score_manifest.json.input.feature_sha256` sea el hash actual de las features | Un estado con niveles de una versión y señales de otra sería incoherente en silencio |
| `evidence` | Nueve campos fijos (`EVIDENCE_FIELDS`: caja, runway, AP vencido/30/60, AR abierto, `S`, `O`, `I`); `monthly_debt_service` no se duplica porque es `S/H` | Ids deterministas `ev_0001…` por `company_id` y campo; solo valores observados |
| `convert` misma moneda | Devuelve `(importe, 1.0)` sin consultar la tabla; moneda ausente o tabla `None` → `MissingFXRateError(ValueError)` con `.currency` | Lo intra-moneda nunca depende de FX (spec §7); WP3 mapea la excepción a `fx_rate_unavailable` |
| `AdvisorConfig` | Además de §11: `levers ⊆ {D1, P}`, `subsidiary_weighting ∈ {equal, size}`, `tramo_bounds` con exactamente dos cortes (`red/amber/green`), `sensitivity_r_max` con las cinco palancas y `r_max > 0`, `month` primer día de mes; `reporting_currency` solo se exige en la tabla si hay tabla | Validaciones conservadoras; el contrato fija tres tramos |
| Tabla FX | `fx.DEFAULT_FX_TO_EUR`: 39 monedas (`companies.currency ∪ banking_products.currency` de cleaned), valores **aproximados** (`FX_SOURCE="approximate"`, `FX_ASOF="2026-09-01"`): USD 1,10, GBP 0,85, CHF 0,94, JPY 165, MXN 20,5, BRL 6,2, ARS 1.300, CLP 1.030, COP 4.500, PEN 4,0, DKK 7,46, BAM 1,95583, XOF 655,957, AOA 1.000, GHS 12… | Sin acceso a tipos de referencia a 2026-09-01; tabla de trabajo a sustituir antes de usar importes convertidos en producción; `AdvisorConfig.fx_rates_to_eur` sigue siendo `None` por defecto |
| Fixture `make_group_state` | Si una fila no trae `level`, lo calcula con `score_level` sobre sus señales y la referencia (anclas puras por defecto) aplicando la regla V2 de nivel nulo sin operaciones o cobertura < 0,4; `cash_reliable` verdadero por defecto cuando se pasa caja | Estados sintéticos coherentes con el motor para WP3/WP7 sin repetir la lógica |

### GA-02 · Motor contrafactual (WP2, `src/xray/group_advisor/counterfactual.py`, 19-09-2026)

Implementado según la spec §4 con `score_level` de V2 como única función de nivel. Comprobado: `level_from_signals` sobre las filas de `build_signals` de agosto 2026 reproduce `scores_v2.level` y los cuatro componentes con diferencia máxima **0,0** en 24 empresas reales (las 20 primeras por `company_id` con nivel, más las 4 con `has_uncovered_debt_service`; 15 con 4 componentes, 2 con 3, 7 con 2; una en CAD). Suite: 35 tests propios, 236 en total con `-W error`.

Decisiones tomadas donde la spec dejaba margen (ninguna cambia las fórmulas de §4):

| Punto | Elegido | Motivo |
|---|---|---|
| Señal base NaN | La primitiva la deja NaN y `derive` da NaN en la derivada (indicador `False`); `debt_service_add` sobre `S` NaN devuelve `S` NaN, no `k·Δ` | No inventar servicio de deuda en una ventana donde no se observó (regla 8). Un tercio de las filas del panel tiene `debt_principal_paid` NaN |
| Denominadores | `op_margin_w` NaN si `I+O ≤ 0`; `debt_service_w` NaN si `I ≤ 0` (no solo `== 0`) | Misma regla que `_ratio` de `signals.py` (`denominator > 0`) |
| `debt_service_add` con `S_k < 0` | `ValueError`; un residuo negativo de redondeo (`|S_k| ≤ 1e-9·max(1, |S|)`) se toma como 0 | Evita un error espurio al liberar exactamente toda la cuota (`Δ = −S/k`) |
| Rangos de `apply_d1` | `0 ≤ φ ≤ 1` y `monthly_service_b_in_donor_ccy ≥ 0` finito | Fracciones fuera de [0,1] no son una asunción de deuda; φ = 0 es identidad |
| `level_from_signals` | Solo lee las cinco columnas que consume `score_level`; si a una fila le faltan las derivadas la pasa por `derive`; filas ya derivadas se usan tal cual | Permite alimentar filas directas de `build_signals` (WP1) y filas de primitivas sin duplicar cálculo |
| `evaluate_action` | Puntúa solo donante y receptora (no todo `rows`); en `P` la señal del donante se informa antes = después (`ap_delay_w`) | `score_level` es fila a fila; el resto del grupo no cambia |
| Validación de `k` | Entero (`int`/`np.integer`, no `bool`) con `1 ≤ k ≤ horizon`; `horizon` entero ≥ 1 | Evita mezclas fraccionarias de meses que la spec no define |
| Test de datos reales | Restringe el panel a las empresas elegidas antes de `build_signals` (≈1 s en vez de ≈26 s) | Las señales son por empresa-moneda sobre su propio calendario: el subconjunto no altera el resultado |

### GA-03 · Narrativa y anclaje (WP4, 19-09-2026)

**Hecho:** `src/xray/group_advisor/{narrative,grounding,qa,llm}.py`, cinco fixtures en `tests/fixtures/advisor_*.json` (esquemas §8.1/§8.2 exactos, cifras calculadas con las anclas reales de V1/V2 y la utilidad `U` de §5.3) y `tests/test_group_advisor_narrative.py` (51 tests). Los cinco renders (`markdown` y `text`) y las nueve intenciones de Q&A pasan `validate_grounding`. Solo stdlib; no depende de otros módulos del paquete.

**Desviaciones y decisiones (todas conservadoras: nunca se calcula un número que no esté en el JSON, salvo `fracción × 100`):**

| Punto | Decisión | Motivo |
|---|---|---|
| Frase D1 `{monthly}` | Cuota mensual **completa** de la receptora (`baseline.subsidiaries[b].signals.monthly_debt_service`), no `fraction × cuota` | El producto no está en el JSON; la frase ya dice «{fraction} de las cuotas» |
| Frase P `{coverage}` | `fraction` (φ, fracción de `ap.gap`) con el calificador «de la necesidad de AP vencido y próximo no cubierta por caja»; se añade la evolución del retraso AP desde `effects` | ψ = x/(V+D30) no figura en el esquema §8.1 |
| Frase `cut_outflow` `({amount} al mes)` | «(hasta {quantity_after} al mes)» | La reducción mensual no está en el JSON; sí `quantity_after` (mensual) y `cash_equivalent` (ventana) |
| Caja comprometida total en el Resumen | Se lista **por donante** (`cash_committed_by_donor`), con equivalente en moneda de reporte si difiere | §8.1 no tiene campo total; sumar en la plantilla violaría el anclaje. Si WP3 añade un total al esquema, actualizar fixtures y Resumen |
| Lista blanca `ALWAYS_ALLOWED = {1, 6, 10000, 100, 40, 70}` | Aceptados siempre | 1 y 6: `k` reportados y «por 1 %»; 10.000: normalización fija de eficiencia y ranking por caja; 100: escala del nivel y «100 %»; 40 y 70: fronteras de tramo. La sensibilidad no serializa `config`, así que no se puede depender de que estén en el JSON |
| Comparación numérica | `round(a,1) == round(b,1)` **o** `abs(a−b) ≤ 0,05`; porcentajes también como `valor/100` a 3 decimales; se admite `fracción × 100` para valores del JSON en [−1, 1] | Evita el doble redondeo cuando la plantilla muestra 2–4 decimales (0,4499 → «0,45» → 0,5 ≠ 0,4) |
| Fixture de sensibilidad | `rel_change_needed` de `cut_outflow` = 0,297 y de `raise_inflow` = 0,396 (no ~0,08) | Con `level_operations < 40` (condición de §6.2.7 para emitir `structural_note`) y las anclas reales, llegar a 70 exige un cambio mayor. Se priorizó la coherencia anclas/nota sobre la cifra orientativa del roadmap |
| Claves no ejemplificadas en la spec | `diagnosis.unexplained_ap_delays[*] = {company_id, ap_delay_w, reconstructed_cash, ap_need, note}`; en pasos P, `effects.*.donor.signal_before/after` = `ap_delay_w` del donante antes = después (GA-02), `null` si no lo tiene (caso del fixture); `levers_evaluated[*].donor_capacity = null` si la caja del donante no es fiable | La spec muestra `[]` o no cubre el caso; WP3 debe reproducir estas claves o acordar otras |
| Semántica de `level_before` en pasos sucesivos | Estado tras el paso anterior **en el mismo k** (k=1 y k=6 tienen antes/después propios); la narrativa muestra cada horizonte con su par | Coherente con el greedy secuencial; evita «49,3 → 39,6» engañosos |
| Cambio de tramo en el Resumen | Categoría derivada del `level_after` del último paso y `config.tramo_bounds` (40/70 por defecto) | Es una etiqueta, no un número; los niveles citados están en el JSON |
| Q&A `how_to_reach_tramo` | Lee también `levers[*].lever/available/current/unit` además de `to_next_tramo` | Para nombrar la palanca y dar la magnitud con su unidad |
| `render_*` para `status` sin plan/sensibilidad | Plan: «Resumen» (plantilla por estado, motivos por filial desde `levers_evaluated` + `diagnosis`) + «Cobertura de datos» + «Supuestos y límites». Sensibilidad `not_scored`: «Dónde estás» + «Supuestos y límites» | Spec §9.1 «plantilla por `status`» |

**Límites conocidos del validador:** solo comprueba existencia numérica, no semántica (un «paso 3» pasa si el 3 existe en cualquier campo). Es lo que fija §9.3; la defensa real es la plantilla determinista por defecto y el LLM como paráfrasis opcional.

### GA-04 · Optimizador de grupo (WP3, `src/xray/group_advisor/{objective,optimizer,plan}.py`, 19-09-2026)

Cifras del dataset previo a D32; resultados vigentes en GA-06.

**Hecho:** `objective.py` (`utility`, `group_utility`, `subsidiary_weights`, `tramo`, `levels_by_tramo`), `optimizer.py` (`WorkingState`, `donor_buffer`, `is_liquidity_constrained`, `recipient_need`, `generate_candidates`, `optimize_group`, `certificate`) y `plan.py` (`build_plan`, `plan_to_json`) con el esquema exacto de `tests/fixtures/advisor_plan_{example,no_levers,single}.json` (test recursivo de claves y tipos en `tests/test_group_advisor_plan_schema.py`); `tests/test_group_advisor_optimizer.py` cubre los tests de la spec §12 «Objetivo y optimizador». Los 250 planes reales de agosto 2026 se construyen en ≈6 s (sin contar `load_inputs`), se renderizan con `render_plan` en `markdown` y `text` y los 500 renders pasan `validate_grounding`.

**Datos reales (agosto 2026):** 71 `single_subsidiary`, 160 `no_feasible_levers`, **19 `plan`** (25 pasos: 19 D1 y 6 P; fracciones 1,0 ×15, 0,5 ×4, 0,25 ×6; un par repartido en varios pasos). `ΔG` en régimen: mediana 2,6, mínimo 0,29, máximo 7,59; 5 pasos cambian de tramo a la receptora; caja comprometida total ≈3,33 M EUR. Certificado calculado en 12 planes, `greedy_gap > 0` en 3 (máximo 5,09 en `GROUP_0022`, donde el greedy reparte la necesidad en fracciones y el «greedy a 2 pasos» de la spec es inferior a un par de acciones completas). Motivos de infactibilidad por par más frecuentes (157 grupos con ≥2 optimizables): D1 `recipient_no_debt_service` 2.644, P `recipient_ap_component_unavailable` 2.571, D1 `donor_buffer` 1.932, P `recipient_no_ap_delay` 1.379, `donor_cash_unreliable` 1.238 por palanca, P `donor_buffer` 370, P `recipient_cash_unreliable` 250, P `recipient_not_liquidity_constrained` 192, `fx_rate_unavailable` 116 (P) / 74 (D1), `donor_no_inflow` 98, D1 `donor_level_floor` 62, `donor_outflow_unavailable` 8. **`GROUP_0064` es `no_feasible_levers`**, no el ejemplo ilustrativo de la spec §8.1: la necesidad D1 real de COMP_0007 es 1,77 M EUR (cuota 295.793/mes) frente a una capacidad de COMP_0222 de 338.196 EUR (ni φ = 0,25 cabe en el colchón), y COMP_0738 tiene `debt_service_w = 0` (deuda 100) y sin componente AP: su problema es el margen −0,80 (`structural_flags`).

Decisiones donde la spec o el roadmap dejaban margen:

| Punto | Elegido | Motivo |
|---|---|---|
| Evaluación de candidatos | Las mismas primitivas (`apply_d1`/`apply_p`) y `level_from_signals` que `evaluate_action`, pero **todas las filas perturbadas de un paso en una sola llamada por `k`**; el paso elegido se reevalúa con `evaluate_action` (referencia) y un test comprueba la igualdad en todos los candidatos | `evaluate_action` cuesta ≈9 ms (dos `score_level` de 2 filas); 22 filiales generan 3.696 candidatos por paso y el certificado enumera pares. Con lotes, los 250 grupos tardan ≈6 s |
| Filas de trabajo por `k` | `WorkingState.rows_by_k` / `levels_by_k` para cada `k` de `report_k` (siempre incluye `H`); `rows`/`levels` son las de `H`. Cada paso se aplica en todos los `k`; el efecto `k=1` del paso `n` parte del estado tras `n−1` pasos **en `k=1`** | Es la semántica del fixture de WP4 (`level_before` de k=1 y k=6 propios, GA-03) y permite `totals.k1` coherentes |
| Fracción `φ` y aditividad de D1 | `φ`, `fraction_used` y `need` son siempre fracciones de la necesidad **original** (`Σφ ≤ 1` = cubierta). Sobre la fila de trabajo se pasa a `apply_d1` la fracción relativa `φ_rel = φ·S_orig/S_k` y la cuota `S_k/H·fx`, de modo que la donante asume exactamente `φ·s_b` y la receptora libera lo mismo en cada `k` | Componer `debt_service_scale(−φ₁)` y `(−φ₂)` daría `S(1−φ₁)(1−φ₂)` y rompería la conservación del servicio externo del grupo (la donante añadiría `φ₂·s_b` y la receptora solo liberaría `φ₂(1−φ₁)·s_b`). P compone `ap_delay_scale` tal cual (multiplicativo, conservador; no hay primitiva aditiva para el retraso) |
| R5 (`L_a' ≥ L_a − δ`) | `L_a` es el nivel **del estado** (baseline), no el de trabajo: la caída acumulada del donante en todo el plan no supera δ | Evitar 5 puntos por paso durante 10 pasos |
| Requisitos del donante | `cash_reliable`, `O3` finito, `I > 0` para ambas palancas; `S` finito **solo para D1** | `debt_service_add` sobre `S` NaN no inventa servicio (GA-02) y el nivel del donante no reflejaría la cuota asumida; en P la donante no cambia de señales |
| Precedencia de motivos por par | donante (`donor_cash_unreliable` → `donor_outflow_unavailable` → `donor_no_inflow` → `donor_debt_service_unavailable`) → receptora (`recipient_no_debt_service`; P: `recipient_ap_component_unavailable` → `recipient_no_ap_delay` → `recipient_no_ap_need` → `recipient_cash_unreliable` → `recipient_not_liquidity_constrained` → `recipient_no_ap_need` si `gap = 0`) → R1 `fx_rate_unavailable` → R4 `fraction_cap` → R2 `donor_buffer` → tras evaluar, `donor_level_floor` / `donor_would_hit_zero_inflow_indicator`. `levers_evaluated` lista **todos** los pares ordenados `(palanca, donante, receptora)` entre optimizables | Igual que el fixture `no_levers` de WP4 (el motivo del donante manda). `recipient_no_ap_delay` es nuevo (paga en plazo o antes: nada que mejorar) |
| Fracciones y R2 | Rejilla efectiva `{min(φ, remanente)}` deduplicada; se evalúan todas las que caben en el colchón (R2 con las cuotas asumidas acumuladas); la mayor que cabe lleva `donor_buffer` si alguna mayor no cabía; `need_fully_covered` si `usado + φ ≥ 1`; `fraction_cap` si `φ = remanente < 1`; `donor_level_floor` si la caída del donante queda a < 0,5 puntos de δ | Nunca fracciones fuera de rejilla |
| Necesidad P | `gap = max(0, V + D30 − max(0, C))`; NaN (y `ap.gap = null`) sin caja fiable; `ψ = min(x_b/(V+D30), 1)` | «No identificable con suficiente confianza» (R3); con caja negativa el gap es todo el AP |
| `is_liquidity_constrained` | `True` si `C < V+D30` o `runway < 1`; `False` si alguna comprobación es posible y ninguna se cumple; `None` sin caja fiable ni runway (→ `recipient_cash_unreliable`) | Spec §5.1 |
| `x_report` | `reporting_currency` si hay tabla y tipo; si no, moneda del donante (también si la moneda del donante no está en la tabla en una acción intra-moneda) | Lo intra-moneda no depende de FX (§7) |
| Orden del greedy | `(−e, −ΔG, cruzada, x_report, donante, receptora, palanca, φ)` con `e` y `ΔG` redondeados a 1e-9 y `x_report` a 1e-6 | Empates exactos reproducibles (test USD 1,0) |
| `rejected_alternatives` | Lista plana con una entrada por `(palanca, donante, receptora)`: por paso las `rejected_alternatives_kept` siguientes (`lower_efficiency` / `below_min_gain` con `ΔG`, luego pares infactibles con su motivo); al parar, las mejores por debajo del mínimo (`below_min_gain`) o los pares bloqueados por el propio plan (`fraction_cap`, `donor_buffer`, `donor_level_floor`); los pares que acaban aplicándose pierden su registro anterior y, al parar, se registran primero con su motivo final | «Por qué no más» debe hablar del estado final del plan; la clave es `delta_utility_k{H}` (`k6`) |
| `certificate` | `checked` solo con ≥1 paso y `2 ≤ optimizables ≤ 6`; enumeración con las mismas reglas del greedy (R1–R5 acumuladas y `min_gain_utility` por acción) en `k=H`; `best_pair ≥ best_single`; `greedy_utility` = `G` tras 2 pasos (o todos si hay menos) o el baseline sin pasos; `greedy_gap` redondeado a 1e-6 | Fixtures de WP4 (`checked=false` sin plan, `greedy_utility` = baseline). Ojo: el gap incluye el efecto de repartir una necesidad en fracciones (definición literal de §5.4) |
| Pasos P: señal del donante | `effects.*.donor.signal_before/after = null` | La donante no cambia de señal en P; el render de WP4 etiqueta ese campo como «señal de deuda» y mostraría el retraso AP del donante. Difiere de la nota de GA-03 (que proponía `ap_delay_w` antes = después) |
| `status` | `single_subsidiary` si `coverage.subsidiaries == 1` (aunque no esté puntuada); `no_feasible_levers` sin pasos (incluye grupos sin filial optimizable, con `G = null`); `plan` con ≥1 paso. `stopped_because` ∈ {`no_feasible_candidates`, `no_candidate_above_min_gain`, `max_steps_reached`, `single_subsidiary`} | Roadmap WP3; `narrative.STOPPED_ES` usa `max_steps` (no `max_steps_reached`): pendiente de alinear en WP5 |
| `diagnosis` | `bottleneck.weakest_components` = componentes con nota < `tramo_bounds[0]` ordenados por nota; `structural_flags` si `level_operations < 40` con nota `margen 6m -0,30: no es palanca de tesoreria`; `unexplained_ap_delays` si paga tarde con caja fiable y sin restricción de liquidez (aunque `gap = 0`); `donor_candidates` = donantes elegibles con capacidad > 0; `recipient_candidates` = con deuda, o con AP tardío y necesidad (aunque no estén restringidas); ambas vacías si hay < 2 optimizables | Literales del fixture de WP4 (sin tildes) |
| `baseline.subsidiaries[*].liquidity` | `buffer` = `B_i` sin cuotas asumidas (también con caja no fiable); `excess_cash = max(0, C − B)` solo con caja fiable y colchón calculable | Igual que la sensibilidad (GA-05) |
| Evidencia por paso | Donante: `reconstructed_cash`, `runway_months`; receptora D1: `window_debt_service_sum`, `level_inflow_sum`; receptora P: `inv_ap_overdue_amount`, `inv_ap_due_30_amount`, `reconstructed_cash`, `runway_months` (solo ids existentes en `state.evidence`) | Ids relativos a donante y receptora |
| Serialización | `_jsonable`: tuplas → listas, numpy → nativos, NaN/inf → `null`, floats a 6 decimales, `-0.0` → `0.0`; `config` = `dataclasses.asdict` | «Nada de `numpy.float64`/`bool_` en el JSON» |

Pendiente para WP5: exportar en `__init__.py` `utility`, `group_utility`, `optimize_group`, `certificate`, `build_plan`, `plan_to_json`; añadir a `narrative.REASON_ES` `lower_efficiency`, `donor_debt_service_unavailable`, `recipient_no_ap_delay`, `recipient_level_unavailable`, `donor_would_hit_zero_inflow_indicator` y a `STOPPED_ES` `max_steps_reached` (hoy se muestran como código). Planes y renders reales de `GROUP_0064` (sin palancas), `GROUP_0022`, `GROUP_0067` y `GROUP_0013` (con pasos) en `data/processed/advisor_wip/` (carpeta temporal de revisión, no artefacto).

### GA-05 · Sensibilidad de empresa (WP7, `src/xray/group_advisor/sensitivity.py`, 19-09-2026)

Cifras del dataset previo a D32; resultados vigentes en GA-06.

**Hecho:** `company_sensitivity(state, company_id, config)`, `iter_company_sensitivities(inputs, month, config)` y `sensitivity_to_json`, con el esquema exacto de `tests/fixtures/advisor_sensitivity_{example,not_scored}.json` (test de esquema recursivo en `tests/test_group_advisor_sensitivity_schema.py`). Todo escenario se valora con `counterfactual.level_from_signals` (la función exacta de V2 con la referencia vigente). Sobre la fixture sintética de anclas puras la salida reproduce las cifras del fixture de WP4 (`cut_outflow`: 0,44 puntos por 1 %, nudo en 90.000, `r* = 0,2969`, 85.609,8 al mes). **Datos reales, agosto 2026 (1.286 empresas, 65 s):** 922 `sensitivity` / 364 `not_scored`; palancas disponibles `cut_outflow` 911, `raise_inflow` 906, `debt_service_cut` 456, `ap_on_time` 253, `ar_faster` 224; no disponibles: `ap_delay_already_zero` 248, `ar_delay_already_zero` 183, `no_debt_service_observed` 462, `ap_component_unavailable` 421, `ar_component_unavailable` 515, `no_operating_inflow` 16, `no_operating_outflow` 11, `debt_without_inflow_indicator` 4. Alcanzan el siguiente tramo por sí solas: `raise_inflow` 273, `cut_outflow` 255, `debt_service_cut` 89, `ar_faster` 24, `ap_on_time` 22 (`r*` mediana 0,33, p25 0,16, p75 0,52). `ap_on_time` factible con caja propia 28, requiere financiación 160, caja no fiable 65. Palanca top por 1 % en rojo: `cut_outflow` 64 / `raise_inflow` 41 / `ap_on_time` 7 / `ar_faster` 5. Rejilla monótona en las 5 palancas de las 922 empresas; los 922 renders pasan `validate_grounding`. `GROUP_0064`: COMP_0007 (57,2 ámbar) llega a verde con −25,9 % de salidas o +31,5 % de entradas, no con la cuota; COMP_0738 (38,1 rojo, margen −0,80) llega a 40 con −35,8 % de salidas o +55,8 % de entradas y lleva `structural_note`.

Decisiones donde la spec o el roadmap dejaban margen:

| Punto | Elegido | Motivo |
|---|---|---|
| Nudos de `raise_inflow` | Anclas del margen (`I* = O·(1+m*)/(1−m*)`) **y** del servicio de deuda (`I* = S/d*`, si `S > 0`), porque `d = S/I` también se mueve | `valid_until` debe ser un nudo real: con solo el margen la pendiente cambiaría antes de lo anunciado. Sobre la fixture de WP4 el nudo pasa de 121.767 (margen) a 108.000 (deuda) |
| Nudo alcanzado justo en `r_max` | `valid_until` = el nudo, `slope_after = None` | No hay dominio detrás para la diferencia finita (p. ej. retraso < 7 días → siguiente nudo 0 en `r = 1`); 274 casos de `debt_service_cut` con `d < 0,05` |
| `r` acotado al dominio de la primitiva | `r_cap = min(r_max, 1)` para las palancas de disminución; `r_max` para `raise_inflow` | `outflow_scale`/`debt_service_scale` exigen `α ≥ −1`; los retrasos `ψ ≤ 1` |
| Búsqueda de `r*` | Rondas de 16 puntos vectorizados (una llamada a `score_level` por ronda) hasta `hi − lo ≤ tol`; devuelve `hi` con `L(r*−tol) ≤ L(lo) < objetivo ≤ L(r*)` | Mismo invariante que la bisección con 4 llamadas en vez de 14; ≈70 ms por empresa |
| `debt_service_cut` con `I = 0` y `S > 0` | No disponible, motivo `debt_without_inflow_indicator` | Con el indicador activo `d` es NaN y la palanca solo actúa al anular `S` (el componente desaparece y el nivel se renormaliza): «alcanzable con −100 % de cuota» sería engañoso. 4 empresas |
| Retrasos fuera de `[valid_min, valid_max]` | No disponible (`*_component_unavailable`) | El componente no está en el nivel y aparecería a mitad de rejilla |
| `quantity` | Etiquetas del fixture de WP4 (`monthly_operating_outflow`, `monthly_operating_inflow`, `monthly_debt_service`, `ap_delay_w`, `ar_delay_w`); `unit` = código de moneda o `days` | Coherencia con el artefacto compartido; la narrativa usa `unit` para formatear |
| Colchón `B_i` y exceso | `B_i = max(κ·Σ términos de flujo presentes, Σ vencimientos presentes)`; `None` si no hay ningún término; `excess_cash` solo con caja fiable y colchón calculable | «Términos NaN se omiten» (R2); sin salidas ni vencimientos observados no se afirma exceso |
| `feasibility.note` | `alcanzable con caja propia` / `requiere financiacion` / `caja no fiable` (`unknown`) para `ap_on_time`; notas fijas para las demás | Vocabulario castellano sin tildes como el fixture; la narrativa ya traduce el veredicto |
| Redondeo | 6 decimales; si `|x| < 1e-3`, 6 cifras significativas | `level_per_unit` por unidad monetaria mensual es ~1e-6 en empresas grandes y se perdería |
| `assumptions` / `limitations` | Las del fixture más tres de §10 (caja reconstruida, no observables, nada contrastado) sin ids de palanca en el texto | El validador de anclaje exige que los ids citados existan en el JSON (en `not_scored` no hay palancas) |
| `iter_company_sensitivities` | Construye todos los estados del mes y ordena globalmente por `company_id` | Los grupos no particionan el orden de `company_id` |

Pendiente para WP5: `narrative.REASON_ES` no tiene etiqueta para `no_operating_outflow`, `no_operating_inflow`, `no_debt_service_observed`, `ap_delay_already_zero`, `ar_delay_already_zero` ni `debt_without_inflow_indicator` (se muestran como código); `__init__.py` sin exportar `company_sensitivity`, `iter_company_sensitivities`, `sensitivity_to_json`. Los JSON y renders reales de COMP_0007 y COMP_0738 están en `data/processed/advisor_wip/` (carpeta temporal de revisión, no artefacto). **Etiquetas resueltas en GA-07.**

### GA-06 · Pipeline y resultados sobre datos D32 (WP5a, `src/xray/group_advisor/pipeline.py`, `scripts/08_treasury_advisor.py`, 19-09-2026)

**Hecho:** `pipeline.run(features_dir, out_dir=None, config=None, month=None, verbose=True)` carga las entradas una sola vez, recorre los 250 grupos del mes (`iter_group_states`), construye y renderiza cada plan, calcula la sensibilidad de cada filial con `group_context` y `feasibility.covered_by_group_plan` rellenos, valida el anclaje de cada narrativa y publica en `data/processed/advisor/` los ficheros de la spec §8 (`group_plans/*.json|.md`, `company_sensitivity/*.json|.md`, `advisor_steps.parquet`, `advisor_groups.parquet`, `sensitivity_levers.parquet`, `_advisor_report.json`, `_advisor_manifest.json`). `run_from_states(states, inputs_sha256, config, out_dir, ...)` es el núcleo sin lectura de entradas (tests con estados sintéticos). `scripts/08_treasury_advisor.py` (`--features-dir`, `--out-dir`, `--month`, `--group GROUP_xxxx`, `--company COMP_xxxx`; los dos últimos imprimen la narrativa y no publican). `__init__.py` exporta `utility`, `group_utility`, `optimize_group`, `certificate`, `build_plan`, `plan_to_json`, `company_sensitivity`, `iter_company_sensitivities`, `sensitivity_to_json`, `render_plan`, `render_sensitivity`, `validate_grounding`, `answer`, `run`. `fx.default_fx_table()` devuelve ahora `xray.fx.FX_TO_EUR` (D32) con fallback a la tabla aproximada de WP1. Tests: `tests/test_group_advisor_pipeline.py` (15: 14 sintéticos + 1 sobre datos reales que republica en `data/processed/advisor`).

**Comando y tiempos:** `python -X utf8 scripts/08_treasury_advisor.py` → `data/processed/advisor/` en **2 min 19 s** (`load_inputs` 47,5 s; planes + sensibilidades 79,6 s; publicación < 1 s). `--group GROUP_0067` y `--company COMP_0007` ≈36 s cada uno (casi todo `load_inputs`). Salida: 500 ficheros en `group_plans/`, 2.572 en `company_sensitivity/`, tres parquet, informe y manifiesto (3.076 hashes de salida, hashes de las 7 entradas, `code_manifest` con el subconjunto `group_advisor`, `config`, tabla FX de 45 monedas con fuente y fecha, versiones). `scores/` y `scores_v2/` idénticos antes y después (sha256 de sus 140 ficheros). `data/processed/advisor_wip/` no se toca.

**Resultados (agosto 2026, D32, panel 100 % EUR):**

| Métrica | Valor |
|---|---|
| Grupos por `status` | **19 `plan` · 160 `no_feasible_levers` · 71 `single_subsidiary`** (250) |
| `no_feasible_levers` por nº de filiales optimizables | 0: 6 · 1: 14 · ≥2: 140 (159 grupos con ≥2 optimizables en total; 29 grupos sin ninguna filial puntuada) |
| `single_subsidiary` | 48 con la filial puntuada, 23 sin nivel |
| Motivos de infactibilidad por par (top 5) | `donor_cash_unreliable` 3.038 (1.519 por palanca) · `recipient_no_debt_service` 2.706 (D1) · `recipient_ap_component_unavailable` 2.549 (P) · `donor_buffer` 2.434 (D1 1.947 / P 487) · `recipient_no_ap_delay` 1.372 (P). Después: `recipient_cash_unreliable` 301, `recipient_not_liquidity_constrained` 189, `donor_no_inflow` 182, `recipient_no_ap_need` 89, `donor_level_floor` 72, `donor_outflow_unavailable` 16; `fx_rate_unavailable` 0 (todo EUR) |
| Planes y pasos | 19 planes, **25 pasos: 20 D1 + 5 P**; fracciones 1,0 ×15, 0,5 ×4, 0,25 ×5, 0,75 ×1; 17 planes de un paso, `GROUP_0022` y `GROUP_0067` con 4; restricción activa `need_fully_covered` 16, `donor_level_floor` 2, `donor_buffer` 1, ninguna 6 |
| ΔG por plan, k=6 | mediana **2,60** · p25 0,45 · p75 4,35 · mín 0,25 · máx 7,63 (`GROUP_0102`) |
| ΔG por plan, k=1 | mediana 0,06 · p25 0,05 · p75 0,15 · mín −0,02 · máx 0,33 |
| ΔG por paso, k=6 | mediana 0,80 · p25 0,39 · p75 3,56 · máx 7,09 |
| Filiales que cambian de tramo (k=6) | **5**, todas rojo → ámbar: COMP_1113 (`GROUP_0018`, 31,8 → 55,2), COMP_0986 (`GROUP_0044`, 30 → 40), COMP_1275 (`GROUP_0067`, 31 → 66,7), COMP_0071 (`GROUP_0102`, 30 → 55), COMP_0176 (`GROUP_0225`, 30 → 40) |
| Caja comprometida (EUR, moneda de reporte) | **3.335.755** en total: D1 812.129 · P 2.523.626 (2,45 M solo en `GROUP_0022`); mediana por plan 23.201 |
| Certificado | calculado en 11 planes (2–6 optimizables); `greedy_gap > 0` en **2**: `GROUP_0022` 5,08 y `GROUP_0067` 0,08 |
| `stopped_because` | `no_feasible_candidates` 128 · `no_candidate_above_min_gain` 51 · `single_subsidiary` 71 |
| Sensibilidad: empresas | 1.286 = **949 `sensitivity` + 337 `not_scored`**; 949 con ≥1 palanca disponible (100 % de las puntuadas) |
| Palancas disponibles | `cut_outflow` 937 · `raise_inflow` 936 · `debt_service_cut` 462 · `ap_on_time` 271 · `ar_faster` 238 (2.844 filas en `sensitivity_levers.parquet`) |
| No disponibles (motivo) | `ar_component_unavailable` 521 · `no_debt_service_observed` 483 · `ap_component_unavailable` 428 · `ap_delay_already_zero` 250 · `ar_delay_already_zero` 190 · `no_operating_inflow` 13 · `no_operating_outflow` 12 · `debt_without_inflow_indicator` 4 |
| Palanca top por 1 % según tramo | rojo (119): `cut_outflow` 63 · `raise_inflow` 45 · `ap_on_time` 6 · `ar_faster` 5 — ámbar (369): `raise_inflow` 197 · `cut_outflow` 156 · `ar_faster` 8 · `ap_on_time` 7 · `debt_service_cut` 1 — verde (461): `cut_outflow` 245 · `raise_inflow` 173 · `ap_on_time` 22 · `ar_faster` 15 · `debt_service_cut` 6 |
| Alcanzan el siguiente tramo por sí solas | **311 empresas** con ≥1 palanca; por palanca `raise_inflow` 292 · `cut_outflow` 277 · `debt_service_cut` 90 · `ar_faster` 28 · `ap_on_time` 27 |
| `r*` necesario (mediana · p25 · p75) | `cut_outflow` 0,26 · 0,12 · 0,39 — `raise_inflow` 0,30 · 0,14 · 0,57 — `debt_service_cut` 0,66 · 0,44 · 0,81 — `ap_on_time` 0,72 · 0,59 · 0,81 — `ar_faster` 0,66 · 0,44 · 0,83 |
| `ap_on_time`: factibilidad | con caja propia 27 · requiere financiación 165 · desconocida (caja no fiable o colchón no calculable) 79 · `covered_by_group_plan` 3 (COMP_0764 y COMP_0908 en `GROUP_0022`, COMP_1218 en `GROUP_0084`) |
| Papel en planes de grupo | 175 empresas en grupos con plan: 19 donantes, 23 receptoras, 0 `both`, 133 sin papel |
| Anclaje | **0 fallos** en 250 planes y 0 en 1.286 sensibilidades (`markdown`) |

Decisiones donde la spec o el roadmap dejaban margen:

| Punto | Elegido | Motivo |
|---|---|---|
| Configuración por defecto del pipeline | `pipeline.default_config()`: `AdvisorConfig` con `fx_rates_to_eur = xray.fx.FX_TO_EUR` (45 monedas) y `fx_source`/`fx_asof` de `xray.fx`; `run(config=None)` y el script la usan | §8 exige la tabla FX en el manifiesto; con el panel 100 % EUR el resultado es idéntico al de `fx_rates_to_eur=None` (ninguna acción cruzada, `fx_rate_unavailable` 0) |
| `fx.default_fx_table()` | `xray.fx.FX_TO_EUR` si `xray.fx` se importa con `FX_TO_EUR`, `FX_SOURCE` y `FX_ASOF`; si no, la tabla aproximada de WP1 (`APPROXIMATE_FX_TO_EUR`, `approximate`). El test de WP1 pasa a exigir fuente no vacía con fecha, `EUR == 1.0` y las 39 monedas del dataset | Una sola tabla FX en el proyecto (D32); los fixtures de WP4 siguen con `fx_source="approximate"` explícito |
| `group_context.role` | `donor` si solo dona, `recipient` si solo recibe, `both` si hace ambas cosas en pasos distintos (`narrative.ROLE_ES` lo contempla desde GA-07), `none` en el resto; `steps` = todos sus pasos ordenados | Roadmap WP5; en agosto 2026 no hay ningún `both` |
| `covered_by_group_plan` | Solo en `ap_on_time` disponible: `True` si un paso P tiene a la empresa como receptora, `False` si no; las demás palancas no llevan la clave; en `sensitivity_levers.parquet` la columna es `boolean` nullable (`<NA>` fuera de `ap_on_time`) | Esquema estable sin inventar factibilidad para palancas sin caja |
| `generated_at` | Un solo sello ISO UTC por lote, también en las sensibilidades (se sobreescribe el de `company_sensitivity`) | Reproducible byte a byte salvo el sello |
| `group_context` en `not_scored` | `has_group_plan` según el plan del grupo, `role = "none"`, `steps = []` | La empresa sin nivel no entra en el plan; la plantilla `not_scored` no renderiza «Papel en el grupo» |
| Publicación de carpetas | `publish_bundle` trabaja fichero a fichero (`shutil.copy2` + `os.replace`) y no admite carpetas ya existentes: `group_plans/` y `company_sensitivity/` se sustituyen enteras (la versión anterior pasa a `.history/<id>/`) y después `publish_bundle` publica los ficheros planos con el manifiesto al final. Staging `.staging-*` **dentro de `out_dir`** (mismo volumen; nada se escribe fuera) | `artifacts.py` no está entre los ficheros de WP5. Cada republicación deja dos carpetas en `.history/` (una por las carpetas, otra por los planos) |
| Comprobaciones antes de publicar | `out_dir` no puede solaparse con `scores/`, `scores_v2/`, las features, `cleaned/` ni `raw/` (`check_output_path`, también desde el script con `--out-dir`); las 7 entradas se rehashean y `features_dir/.pipeline.lock` no debe existir; `out_dir/.pipeline.lock` tampoco | Mismo protocolo que `score_v2.pipeline` |
| Informe | Además de lo pedido: `reasons_by_lever`, `tramo_changes` (lista), `available_by_lever`, `unavailable_reasons`, `reachable_by_lever`, `ap_on_time_feasibility`, `roles_in_group_plans`, `grounding_failed` (ids), `timings` (`load_inputs_s`, `compute_s`); distribuciones con `count`, `min`, `p25`, `median`, `p75`, `max`; ΔG por plan = totales − baseline | Cubre esta sección sin releer los JSON |
| Parquet | `month` como `datetime64[ns]`; `binding_constraints` unido por `\|`; columnas `*_k6` leen `k{horizon_months}` (H = 6 fijado por `level_window` de V2); `advisor_groups` incluye los 250 grupos (sin plan: `steps = 0`, `cash = 0`, totales = baseline, `greedy_gap` NaN) | Contrato del roadmap WP5 |

Observaciones y desviaciones:

- **ΔG en k=1 ligeramente negativo en 4 planes de un paso D1** (`GROUP_0044` −0,00003, `GROUP_0225` −0,001, `GROUP_0102` −0,008, `GROUP_0236` −0,02): al primer cierre el donante ya asume la cuota (su `debt_service_w` sube) mientras la receptora solo ha liberado 1/6 de la ventana; en régimen todos son positivos (≥ 0,25). El greedy optimiza en k=6 (GA-00) y la narrativa muestra ambos horizontes por paso. No se corrige: es la transición que la spec quiere hacer visible.
- **Importes minúsculos con efecto grande**: `GROUP_0044` (24,2 EUR, ΔG 2,86, 1.180 puntos de G por 10.000) y `GROUP_0225` (103,8 EUR, ΔG 3,56): la receptora tiene `level_inflow_sum = 0` con una cuota residual (`debt_without_inflow_w`, deuda 0); asumirla al 100 % elimina el componente y renormaliza el nivel (30 → 40). Es la mecánica de V2 (spec §2 y §4), no un error, pero el sentido de negocio es débil: una filial sin entradas operativas no mejora por 24 EUR. La narrativa muestra el importe y el aviso de componente eliminado; conviene decirlo en la demo.
- `GROUP_0064` sigue siendo `no_feasible_levers` (GA-04); `COMP_0007` (56,5 ámbar tras D32) llega a verde con −27,3 % de salidas o +34 % de entradas, no con la cuota.
- Cambios frente a GA-04/GA-05 (dataset previo a D32): empresas puntuadas 922 → 949; grupos con ≥2 optimizables 157 → 159; planes 19 → 19; pasos 25 → 25 (19 D1 + 6 P → 20 D1 + 5 P); ΔG k=6 mediana 2,6 → 2,6; caja comprometida ≈3,33 M → 3,34 M; `greedy_gap > 0` 3 → 2; `fx_rate_unavailable` 190 → 0; empresas que alcanzan el siguiente tramo por palanca 273/255/89/24/22 → 292/277/90/28/27 (`raise_inflow`/`cut_outflow`/`debt_service_cut`/`ar_faster`/`ap_on_time`).
- Los motivos de GA-07 (3.065 / 2.741 / 2.464…) cuentan pares **y** `rejected_alternatives`; los de esta sección solo `levers_evaluated` no factibles, de ahí la pequeña diferencia.

### GA-07 · Pulido de narrativa (WP5b, `src/xray/group_advisor/{narrative,qa}.py`, 19-09-2026)

**Hecho:** los renders reales de WP3/WP7 (`data/processed/advisor_wip/*.md`) mostraban códigos sin traducir, una frase del donante falsa en D1, «señal null → null» en pasos P y una lista «Palancas evaluadas no factibles» de 50–60 líneas por grupo. Cambios solo en `narrative.py`, `qa.py` (dos líneas) y `tests/test_group_advisor_narrative.py` (51 → 67 tests); los fixtures JSON no se tocan (los casos nuevos son `copy.deepcopy` de los fixtures con claves modificadas). Los pendientes de etiquetas de GA-04 y GA-05 quedan cerrados. Comprobación sobre datos reales de agosto 2026 (D32): 250 planes × {markdown, text} y 1.286 sensibilidades pasan `validate_grounding` (0 fallos); `GROUP_0067` pasa de 52 líneas de pares no factibles a 12 líneas agrupadas.

| Punto | Elegido | Motivo |
|---|---|---|
| Etiquetas | `REASON_ES` cubre los 18 `REASON_*` de `optimizer.py`, los 4 `BINDING_*` (en `CONSTRAINT_ES`; `need_fully_covered` también en `REASON_ES`), los 8 motivos de `lever_available` de `sensitivity.py` y los alias de los fixtures de WP4 (`no_debt_service`, `no_outflow`, `no_inflow`); `STOPPED_ES` añade `max_steps_reached` (conserva `max_steps`); `SCORE_REASON_ES` cubre los 10 `score_reason` de `xray.score_v2.core` (`ok` incluido) más `no_operating_flows`; `ROLE_ES["both"] = "donante y receptora"` | Un código sin etiqueta se mostraba en crudo (`no_debt_service_observed`, `no_usable_transactions`) |
| Test de cobertura de etiquetas | `engine_reason_codes()` lee el **código fuente** de `optimizer.py`/`plan.py` (`^(REASON|STOP|BINDING)_X = "..."`), de `sensitivity.py` (`LEVER_SPECS[*].unavailable_reason`, tuplas `False, "..."` y `f"{prefix}_..."` expandido a ap/ar) y de `score_v2/core.py` (`entry_reasons` y `reason.loc[...] = "..."`), y exige que todo lo hallado tenga etiqueta; una aserción de mínimos evita que el barrido quede vacío si cambia la forma de declarar los motivos | No existe `REASON_CODES` exportado y no se modifican esos módulos; si el motor cambia el patrón de declaración hay que actualizar las regex del test (documentado en su docstring) |
| Frase del donante | D1: «El donante asume servicio: su nivel pasa de {k6 antes} a {k6 después} (k=6); además compromete caja.» («se mantiene en {x}» si ambos formatean igual). P: «El donante no pierde nivel (la salida intragrupo no cuenta como operativa); pierde caja.» | La frase única de WP4 era falsa en D1 (el donante sí baja por la cuota asumida) |
| Señal del donante | Solo se imprime en D1 (`debt_service_w`); en P nunca, aunque el JSON trajera `ap_delay_w` antes = después (variante de GA-03) | En P el JSON real trae `null` (GA-04); etiquetarla «señal de deuda» sería incorrecto en cualquier caso |
| Pares no factibles agrupados | Clave `(palanca, lado, filial que bloquea, motivo)`: `donor_*` y `fx_rate_unavailable` → por donante con la lista de receptoras; `recipient_*`, `fraction_cap`, `need_fully_covered` → por receptora con la lista de donantes; otros → par a par. Orden: palanca según aparece, lado (donante, receptora, par), id, motivo. Formato: «D1 desde COMP_0216: {motivo} (capacidad 0 EUR) → receptoras: COMP_0407 (necesidad 5.762,7 EUR), …» / «P hacia COMP_0407: {motivo} (necesidad X) → donantes: COMP_0216, …» | 60 líneas por grupo de 6 filiales no se leían. Las «Alternativas rechazadas» (top-5 por paso) no cambian |
| Importes en los grupos | El importe propio de la filial que bloquea se cita una vez **solo si es único en el grupo** (`_unique`, redondeo a 6 decimales); la necesidad de cada receptora va entre paréntesis en los grupos por donante; la capacidad de los donantes **no** se cita en los grupos por receptora | Nunca se suma ni se elige un valor entre varios; la capacidad del donante no explica un motivo de la receptora |
| Grupos largos | Más de 8 contrapartes → las 8 primeras y «y otras», sin número | «y N más» y «N receptoras» serían números que no están en el JSON; no se amplía `ALWAYS_ALLOWED` |
| Papel en el grupo | `role` ∈ {`recipient`, `donor`, `both`, `none`} con `has_group_plan=True`: «En el plan de grupo G, esta filial recibe apoyo en el paso 1» / «actúa como donante en los pasos 1 y 2» / «actúa como donante y receptora en …» / «El grupo G tiene plan pero esta filial no participa en ningún paso»; sección oculta si `has_group_plan` es `False` o `None` | Frases cerradas en vez de «(papel: receptora; pasos: 1)». `pipeline.group_context` real nunca emite `both` (una filial que dona y recibe se etiqueta `recipient`) y `steps` es la unión de sus pasos como donante y receptora; la narrativa admite `both` igualmente |
| `covered_by_group_plan` | En `ap_on_time`: `True` → «cubierta por el plan de grupo (paso de financiación del pago a proveedores en plazo)»; `feasible_alone=False` y no cubierta → «requiere financiación externa o del grupo»; `feasible_alone=True` → «alcanzable con caja propia» (y «; cubierta por…» si además lo está); clave ausente → se tolera. El número de paso solo se cita si `feasibility` lo declara (`group_plan_steps`/`covered_by_steps`/`covered_by_step`/`group_plan_step`, claves opcionales que hoy el pipeline no escribe) | La letra «P» suelta es un id de palanca que no existe en el JSON de sensibilidad y el validador la rechazaría, por eso se escribe el nombre de la palanca. No se usa `group_context.steps` como número de paso: mezcla pasos D1/P y de donante/receptora y sería impreciso |
| Sin siguiente tramo | `next_tramo_target = null` (filial ya verde): «Ya está en el tramo más alto (verde); no hay siguiente tramo que alcanzar.» y se omiten las líneas «no alcanza n/d por sí sola»; igual en Q&A `how_to_reach_tramo` (único cambio en `qa.py`) | El render real de `COMP_1048` (nivel 88) decía «Ninguna palanca por sí sola alcanza n/d» tres veces. Hallado al revisar, no estaba en la lista de WP5b |
| Cobertura de datos | Una línea por filial sin nivel con `score_reason` traducido ya existía; solo faltaban las etiquetas. Resumen: «1 paso propuesto» / «N pasos propuestos» | `optimizable ≡ level no nulo` (`state.assemble_group_state`): no hay filiales con nivel y no optimizables |
| Fuera de alcance | No se muestra `score_reason` de las filiales puntuadas provisionales (`optional_components_missing` 373, `trend_unavailable` 135, `thin_current_month` 88, `short_history` 11 en agosto 2026) | No lo pedía WP5b y añadiría hasta una línea por filial; las etiquetas ya están en `SCORE_REASON_ES` si se quiere mostrar |

Códigos con etiqueta tras GA-07 — `REASON_ES`: `donor_cash_unreliable`, `donor_outflow_unavailable`, `donor_no_inflow`, `donor_debt_service_unavailable`, `donor_buffer`, `donor_level_floor`, `donor_would_hit_zero_inflow_indicator`, `recipient_no_debt_service`, `recipient_ap_component_unavailable`, `recipient_no_ap_delay`, `recipient_no_ap_need`, `recipient_cash_unreliable`, `recipient_not_liquidity_constrained`, `recipient_level_unavailable`, `fx_rate_unavailable`, `fraction_cap`, `need_fully_covered`, `lower_efficiency`, `below_min_gain`, `no_operating_outflow`, `no_operating_inflow`, `no_debt_service_observed`, `debt_without_inflow_indicator`, `ap_component_unavailable`, `ar_component_unavailable`, `ap_delay_already_zero`, `ar_delay_already_zero` (+ alias `no_debt_service`, `no_outflow`, `no_inflow`); `STOPPED_ES`: `no_candidate_above_min_gain`, `max_steps_reached`, `max_steps`, `no_feasible_candidates`, `single_subsidiary`; `CONSTRAINT_ES`: `need_fully_covered`, `donor_buffer`, `donor_level_floor`, `fraction_cap`; `SCORE_REASON_ES`: `ok`, `no_usable_transactions`, `incomplete_group_coverage`, `insufficient_window_history`, `insufficient_components`, `thin_current_month`, `short_history`, `trend_unavailable`, `optional_components_missing`, `partial_currency`, `no_operating_flows`.

Motivos observados en los datos reales de agosto 2026 (250 planes, pares + alternativas): `donor_cash_unreliable` 3.065, `recipient_no_debt_service` 2.741, `recipient_ap_component_unavailable` 2.551, `donor_buffer` 2.464, `recipient_no_ap_delay` 1.372, `recipient_cash_unreliable` 301, `recipient_not_liquidity_constrained` 191, `donor_no_inflow` 182, `below_min_gain` 175, `donor_level_floor` 135, `recipient_no_ap_need` 89, `fraction_cap` 23, `donor_outflow_unavailable` 16, `lower_efficiency` 9; `stopped_because`: `no_feasible_candidates` 128, `single_subsidiary` 71, `no_candidate_above_min_gain` 51 (`max_steps_reached` no aparece con `max_steps = 10`); ni `fx_rate_unavailable`, `donor_would_hit_zero_inflow_indicator`, `recipient_level_unavailable` ni `donor_debt_service_unavailable` aparecen en agosto con la configuración por defecto (sin tabla FX todo es intra-moneda). Sensibilidad: `ar_component_unavailable` 521, `no_debt_service_observed` 483, `ap_component_unavailable` 428, `ap_delay_already_zero` 250, `ar_delay_already_zero` 190, `no_operating_inflow` 13, `no_operating_outflow` 12, `debt_without_inflow_indicator` 4.

## 21. Motor canónico del frontend: V2 para el score, ledger de Pablo para Cash Truth — 19-09-2026 (noche)

### Contexto

Los commits `37d78fe` → `18582e3` añadieron un segundo motor (`xray.pulse`, «PulseFourPillars-v1.0», con ledger canónico `xray.ledger`) y conectaron el frontend **exclusivamente** a él, moviendo el exportador V2 a `legacy_frontend_export.py`. Se ejecutó el batch completo y la suite (que el commit de integración no había corrido: dos fallos, corregidos en `520e6b0`). Resultado real del snapshot Pulse frente a lo que el frontend enseñaba con V2 el mismo día:

| | V2 (`8ffe39d`) | Pulse (`18582e3`) |
|---|---:|---:|
| Empresas con Health Score en agosto 2026 | 977 | **16** (939 `partial` con Health `null`, 253 sin evidencia) |
| Meses en la trayectoria | hasta 24 | 1 |
| Escenarios del simulador | 21 por empresa | 0 |
| Empresas excluidas por moneda | 0 | 78 sin panel EUR |
| Referencia congelada / `predict` para el test oculto | sí | no |
| Cobertura FE10, estacionalidad, ruptura 2025-01 | sí | no |

La causa del 16 es una política del motor: Health solo si los cuatro pilares son válidos, y el pilar de deuda queda `unknown` sin servicio de deuda verificado (no identificar pagos ≠ no tener deuda). Defendible como principio; incompatible con «quién está sano» sobre una cartera. Ejemplo de divergencia: COMP_0764 → Pulse 65 (deuda 0) frente a V2 34.

### Decisión (SC24)

Repartir por capas en lugar de elegir un motor:

| Capa | Motor | Motivo |
|---|---|---|
| Health Score, trayectoria, momentum, explicación, leaderboard | **`financial_smoothed_v2`** | Cumple el enunciado hoy; probado (tests, prefijo, referencia congelada) |
| Clasificación de movimientos y Cash Truth | **Ledger de Pablo** (`xray.ledger.classify`) | Ya alimenta `features/transactions.py` y `product/cash_truth.py`; clasificación única y auditable con linaje |
| Frontend | Contrato 2.0 (empresa) / 1.0 (grupo, cartera) | Es el que Álvaro construyó y probó; recupera trayectoria, Portfolio con score y simulador |
| Pulse Four Pillars | Experimento conservado (`xray.pulse`, `product/pulse_frontend_export.py`, `scripts/09b_export_frontend_pulse.py`) | Reevaluar cuando tenga Health parcial renormalizado, histórico de 24 cierres y tests ejecutados |

Cambios en `camilo/v2-canonical`: `frontend_export.py` vuelve a ser el exportador V2 (con what-if FE-04); el de Pulse pasa a `pulse_frontend_export.py`; el frontend se restaura a `8ffe39d` (+ stub de CSS modules para los tests) y se retiran `services/pulseSnapshot.ts`, `types/pulse.ts` y fixtures Pulse; `docs/frontend-data-contract.md` vuelve a la versión 2.0. No se toca `xray.pulse`, `xray.ledger` ni sus tests: siguen en la suite.

**Efecto secundario ya asumido:** la referencia V2 se reajusta sobre las features del ledger (Pablo advertía que las referencias previas no validaban la nueva semántica). Cifras tras la regeneración en SC25.

### Pendiente con Pablo

- Su mejora de `dimensions` nullable en el contrato 3.0 es correcta y conviene portarla al 2.0 (hoy exportamos un neutro con `provisional`), pero requiere tocar componentes de Álvaro.
- Si Pulse llega a Health parcial (≥ 3 pilares) + 24 cierres, comparar ambos con `evaluation/compare.py` contra los eventos discretos `event_type` antes de volver a cambiar el canónico.

### SC25 · Regeneración V2 sobre las features del ledger + D32/D33/D36 (19-09, noche, tras rebase sobre `main`)

`00 → 01 (D31 default) → 05 fit (empresa y grupo-moneda) → 08 → 10 → 09` con `xray.ledger.classify` y los cambios de Ander (FX a EUR a tipo fijo D32, inicio de datos D33, deuda desde balances D36). Agosto 2026: **1.011 puntuadas** (329 `scored`, 682 `provisional`), 275 sin puntuar — antes 977/309; la conversión FX incorpora empresas que quedaban fuera por moneda parcial. Prefijo 2026-02 OK en features y scores. Exportación: 1.161 empresas con ficha (125 sin ningún score), 250 grupos, portfolio de 1.286, 1.011 con 21 escenarios; contratos válidos con `npm run validate:generated` (+ `--groups`, `--portfolio`). Suite: 566 Python pasan + 67 frontend, lint y typecheck limpios. Único fallo, `test_pulse_pipeline::test_currency_runs_do_not_overwrite_or_mix`, **falla igual en `origin/main`**: el D32 de Ander cambia el comportamiento de Pulse y el test de Pablo espera `None`; lo resuelven ellos.

### FE-04 / FE-05 · What-if precalculado para el simulador (19-09, noche)

El simulador del frontend solo selecciona escenarios precalculados por coincidencia exacta de los cuatro controles; exportábamos `scenarios: []`. `src/xray/product/whatif.py` + `scripts/10_build_whatif.py` → `product/whatif_scenarios.parquet`, que `09_export_frontend.py` vuelca en `simulation.scenarios`.

- **Método:** por empresa puntuada en el último mes, cada escenario modifica las features de los **últimos 6 meses** (cambio sostenido, no un mes aislado) y vuelve a puntuar con `score_v2.score_panel` y la **referencia congelada**: misma fórmula, sin recalibrar. La base reproduce el score publicado exactamente (si no, la empresa se descarta; 0 descartes).
- **Palancas** (claves fijadas por el contrato; etiquetas y semántica las define Data): `customer_term` = variación % de entradas operativas (recalcula margen y crecimiento like-for-like del primer mes de la ventana); `collection_delay` = días añadidos al retraso AR; `supplier_term` = días añadidos al retraso AP; `internal_support` = variación % de salidas operativas (baseline 100). Se reutilizan las claves del contrato con etiquetas honestas porque V2 no mide plazos concedidos ni apoyo intragrupo: simular eso daría siempre 0.
- **FE-05 — rejilla factorial:** la primera versión (21 escenarios «una palanca cada vez») dejaba «No disponible» en cuanto se movían dos controles. Ahora **81 escenarios** = 3 posiciones por palanca (% ∈ {−20, 0, +20}, días ∈ {0, 30, 60}), así **cualquier combinación de los sliders tiene resultado**. En combinaciones, `impacts` lista el efecto de cada palanca por separado y la explicación avisa de que no son aditivos. Coste: ~30 min por regeneración. La etiqueta fija «del apoyo actual» del componente pasa a «del nivel actual».
- **Resultados típicos:** COMP_0764: entradas −20 % → 34 → 23; salidas −20 % → +6. Retrasos AR/AP dan 0 en empresas sin facturas y el escenario lo explica. `example_id` = palanca sola de mayor efecto absoluto.
- **Límites:** sensibilidad del score, no predicción; pasos gruesos; un cambio sostenido de seis meses es una simplificación. Tests: `tests/test_product_whatif.py` (4), `tests/test_frontend_export.py`.
