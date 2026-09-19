# Decisiones del proyecto: datos, score y producto

**Estado al 19-09-2026 (tarde): limpieza, features, score V1 (`a1af735`, control) y score V2 suavizado (`financial_smoothed_v2`, `src/xray/score_v2/`) implementados; comparador V1/V2 ejecutado.** Para continuar sin la conversación: leer primero §13 (V2: qué se hizo, resultados y qué no mejora), después §12 (auditoría que motivó V2), §10 (V1) y §11 (producto). Detalle metodológico de V2 en `docs/scoring-v2.md`. Este documento es autosuficiente para saber qué está hecho, qué ha cambiado, cómo reproducirlo y qué falta decidir. La lógica ejecutable está en `src/xray/`; los notebooks conservan la evidencia exploratoria, no son otra implementación del pipeline.

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
