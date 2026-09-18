# Feature engineering implementado — X-Ray

La referencia de **estado, decisiones, cifras verificadas y pendientes** es [decisiones.md](./decisiones.md). Este documento describe el contrato técnico de la v1; sustituye al diseño anterior basado en CSV, DuckDB/Polars, ceros para meses ausentes y snapshots históricos constantes.

## Ejecución y código

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -m pytest -q
```

Validación adicional sobre datos completos:

```bash
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
```

Usa pandas, numpy y pyarrow, sin dependencias nuevas. Entrada exclusivamente `xray.io.read_cleaned(...)`. Lógica importable en `src/xray/features/`; los scripts son puntos de entrada. `FeatureConfig` controla inicio, fin, extracción, mínimo de historia y mes fino. CLI: `--cleaned-dir`, `--out-dir`, `--start-month`, `--end-month`, `--extraction-date`. La fecha de extracción de la limpieza sigue definida en `xray.paths.EXTRACTION_DATE`; no cambiar solo la de features para un dataset nuevo sin adaptar también la limpieza.

## Artefactos en `data/processed/`

| Artefacto | Clave / propósito |
|---|---|
| `company_monthly_features.parquet` | Empresa × mes, importes solo en su moneda declarada; 1.286 × 24 filas en este dataset |
| `company_currency_monthly_features.parquet` | Empresa × moneda × mes; todas las monedas observadas hasta el corte más la declarada |
| `group_currency_monthly_features.parquet` | Grupo × moneda × mes; recalcula sumas, ratios, medianas y dinámicas, no promedia ratios de filiales |
| `stress_events_reserved.parquet` | Empresa × mes; conteos de eventos bancarios reservados, no targets ni features |
| `reconstructed_liquidity_context.parquet` | Cuenta corriente × mes; saldo reconstruido y flags de fiabilidad, retrospectivo |
| `company_currency_liquidity_context.parquet` | Caja reconstruida, cobertura, runway y cobertura de vencimientos; retrospectivo |
| `debt_snapshot_context.parquet` | Producto de deuda a extracción; saldo, concedido y utilización, sin inventar historia |
| `_feature_catalog.json` | Lista explícita `model_features`, tipos y rol de cada columna |
| `_feature_quality.json` | Filas, cobertura, elegibilidad, meses finos y fracción de nulos |
| `_feature_manifest.json` | Parámetros, hashes de inputs, código y outputs, versiones y manifiesto de limpieza |

Los paneles auxiliares pueden añadir una moneda cuando esta aparece por primera vez en la ventana. Las filas anteriores correspondientes son vacías: no significan una moneda conectada históricamente. El panel primario tiene un calendario fijo por empresa.

Publicación: staging, copias anteriores en `.history/`, sustitución atómica **por fichero**, manifiesto al final y rollback ante excepciones. No se eliminan outputs de otros pasos (scores, alertas...). `.pipeline.lock` evita publicaciones concurrentes. No hay garantía ACID multiarchivo ni lectores concurrentes: los consumidores deben verificar hashes y no leer durante publicación.

## 1. Calendario y cobertura

- Meses completos: **2024-09 → 2026-08**, ambos inclusive. `month` es el primer día, pero la fila utiliza hechos hasta el cierre de ese mes. Septiembre de 2026 no es un mes mensual completo.
- Un mes sin movimientos no prueba actividad cero. Los conteos observados son 0; los importes bancarios son `NaN`. Se conserva también la cola tras la última transacción, sin clasificarla como cese.
- `tx_count`, `tx_usable_count`, `tx_usable_row_share`, cuentas activas/nuevas, meses desde último movimiento, cobertura de filiales y fracción de filas anteriores a conexión son diagnósticos.
- `is_training_eligible`: seis meses naturales consecutivos con al menos un movimiento utilizable; al menos cinco utilizables en el mes actual; cobertura de las filiales observadas hasta ese momento igual a 1. No equivale a etiqueta disponible ni a moneda completa.
- `has_partial_currency_coverage` avisa de filas en otras monedas, sin producto conocido o con FX ambiguo. Las shares son **por filas**, no una cobertura económica en euros.
- No se usa `last_transaction_date` global ni la futura fecha de desconexión como predictor.

## 2. Monedas y transacciones

No hay tipos de cambio fiables para consolidar. No se multiplican ni dividen importes por `exchange_rate`. Tampoco es válido dividir sumas de monedas mezcladas y llamarlo ratio independiente de moneda.

Transacciones utilizables: `booked`, moneda de producto conocida, `exchange_rate == 1`, sin `is_extreme_amount`, `is_relative_outlier`, `is_sync_duplicate` ni `is_unknown_product`. El flag de outlier relativo ya es causal en `cleaned`.

| Bloque | Categorías / fórmula |
|---|---|
| `tx_cash_inflow/outflow` | Entradas/salidas utilizables de cualquier categoría; incluyen tesorería. No se llaman ventas |
| `tx_inflow` | Positivos `collection`, `bulk_collection`, `pos_settlement`, `cash_settlement(s)`, `payment_refund`, `tax_refund`; sin traspasos ni intragrupo |
| `tx_outflow` | Absoluto de negativos `payment`, `bulk_payment`, `utility`, `salary`, `social_security`, `tax`, `collection_refund`; sin traspasos ni intragrupo |
| `tx_fixed_cost` | Subconjunto negativo `salary`, `social_security`, `tax`, `utility`; proxy de gasto recurrente, no costes fijos contables |
| `debt_principal_paid`, `debt_interest_paid` | Negativos de `debt_repayment` / `interest_charge`; fuera intragrupo, pero se conserva la pata negativa de liquidaciones entre productos propios |
| `tx_fees_paid` | Negativos `fee`, sin espejos ni intragrupo |
| Importes sin categoría / internos / intragrupo | Contexto de cobertura, separado del operativo |

`transfer`, retiradas de efectivo/TPV e inversión no son por sí mismos ventas o gastos operativos. No se recategoriza texto libre. Los refunds se tratan como flujos de caja operativos, no como ventas contables.

Ratios: margen `(inflow-outflow)/(inflow+outflow)`, cobertura `inflow/outflow`, `inflow/fixed_cost`, servicio de deuda/intereses/comisiones sobre inflow. Denominador nulo o no positivo → `NaN`, nunca infinito ni un cero inventado.

`tx_lfl_inflow_growth`: crecimiento de entradas operativas usando únicamente las cuentas con movimientos utilizables tanto en t como en t−1. Ayuda a separar onboarding de crecimiento, sin garantizar continuidad de sincronización.

Concentración: HHI de cobros entre contrapartes conocidas, con cobertura del importe identificado. Se usa el ID explícito o un único token `COUNTERPARTY_n` del concepto; no se enlazan empresas ni se infiere una red. **Solo contexto descriptivo**, fuera de `model_features`.

## 3. Facturas a cada cierre

V1 utiliza solo `document_type == invoice`, sin duplicados marcados. `invoiceGroup` se reserva hasta saber si duplica facturas individuales; `note/refund` no se pueden asignar a abonos AR/AP solo por signo. `paymentDocument/deposit/other/cheque` quedan fuera.

El importe se mantiene en `currency`, sin FX. Tasas inválidas no impiden usar el nominal de una factura cuya moneda está explícita; sí impiden cualquier conversión.

Para cierre de mes t:

- Emitida antes del primer instante de t+1: pertenece al universo conocido.
- Abierta: no tiene fecha real de pago, o esta es igual/posterior al primer instante de t+1.
- `paid` con fecha anulada por inválida: estado de liquidación desconocido; no se inventa abierta/cerrada. Se informa `inv_unknown_settlement_count`.
- Abierta vencida: vencimiento anterior al día de cierre; vencer el propio día no son días de retraso. Ratios de vencidas usan importes abiertos **con vencimiento válido**, con columna de cobertura.
- Vencimientos próximos 30/60/90 días: solo de facturas ya emitidas y abiertas en t. No se mira qué nuevas facturas aparecerán después.
- `pending_amount` y estado final de conciliación no se usan para reconstruir importes pendientes parciales. Se aproxima con el nominal completo hasta el pago: no hay histórico de pagos parciales.

| Señal | Cálculo |
|---|---|
| Emitido / recibido | Importe absoluto y conteo en el mes de emisión, AR/AP separados |
| DSO / DPO realizado | Mediana de `payment_date - issuance_date`, observada **en el mes del pago**, acotada a 0–365 días |
| Retraso | `payment_date - due_date`, separado de DSO/DPO, acotado a −60–365; mediana, p90 y proporción tardía |
| Aging | Abierto, vencido y vencido más de 90 días, por AR/AP |
| Presión próxima | Vencimientos conocidos 30/60/90 días; ratio 30d/emitido o recibido del mes |

Plazos anómalos cuentan para facturación, no aging/retrasos. Pagos anteriores a emisión quedan fuera de DSO/DPO; pueden ser anticipos y, según su fecha, estar ya liquidados. Pagos futuros no contribuyen a estadísticas realizadas. No se usa `status == overdue` ni `is_stale_pending` como señal histórica.

Antes de la primera factura → `NaN`. Tras observar facturas estándar se permite 0 en emisión de meses sin nuevas facturas, bajo el supuesto explícito de continuidad del ERP, **no verificable** sin logs de sincronización. Si solo hay documentos excluidos, no se fabrica facturación cero.

El nivel absoluto de vencidas y sus medias móviles se mantienen para descripción, pero no entran en `model_features`: se seleccionan cambios y anomalías respecto a la propia historia para reducir el efecto de higiene ERP.

## 4. Dinámica y estacionalidad

Sobre 12 señales base: entradas, salidas y neto operativos, margen, carga de deuda/intereses, emitido/recibido, DSO/DPO y ratios vencidos AR/AP.

| Sufijo | Definición |
|---|---|
| `_ma3/6`, `_std3/6` | Media y desviación poblacional de los últimos 3/6 meses, incluido t; exige ventana completa |
| `_slope3/6` | Pendiente OLS por mes natural, con todos los meses observados |
| `_delta1/3/6` | x(t) − x(t−k), sin ffill |
| `_change1/3/6_scaled` | Delta / absoluto del valor en t−k, para importes |
| `_slope3/6_scaled` | Pendiente / absoluto de la media de la ventana, para importes |
| `_zscore_prior6` | Contra media/desviación de t−6..t−1, mínimo 3 observaciones, **excluyendo t** |
| `_yoy_change` | Cambio relativo frente a t−12; sin comparar contra meses futuros del mismo año |

La pendiente y las medias usan calendario continuo; no se pegan febrero y abril como si fueran contiguos. Un denominador 0 deja la señal normalizada en `NaN`. El z-score permite 3 observaciones válidas dentro de los 6 meses anteriores; no exige las 6.

Persistencia: número de meses de neto operativo negativo en seis meses completos. Volatilidad: std3/std6. Estacionalidad: mes del año + cambio interanual; no se estima una curva estacional con toda la muestra.

No se entrenan percentiles, escaladores, imputadores ni winsorizadores cross-sectional en esta capa. Eso se ajustará **solo con train y por fold de grupo**.

## 5. Liquidez y deuda: contexto, no predictores históricos

Reconstrucción únicamente de cuentas `checking`:

`saldo(cierre) = foto(cuenta) − suma(movimientos posteriores al cierre hasta el día de la foto)`.

Se asume que la foto corresponde al **cierre del día indicado**; incluye por tanto movimientos de septiembre de 2026 al reconstruir agosto. Es una hipótesis pendiente de confirmar. Se usa la fecha real de cada foto: hay saldos anteriores al 1 de septiembre. No se extrapola una foto anterior al cierre.

Mantiene transferencias propias e intragrupo (son reales para el saldo de cada cuenta), excluye pending y duplicados de sincronización. Si el tramo de reconstrucción contiene extremos/outliers, FX ambiguo, duplicados o estados no booked, se marca no fiable y el valor pasa a `NaN`. Tampoco se reconstruye antes de observar la cuenta o sin snapshot. **Ausencia de flags no demuestra integridad del libro**: movimientos omitidos no son detectables.

La caja agregada se ofrece solo si todas las cuentas corrientes conocidas a ese cierre en esa moneda son reconstruibles. Se generan runway y caja/vencimientos AP como contexto, nunca dentro del panel de entrenamiento. El runway divide por salidas **operativas** medias de 3 meses, no burn neto ni gasto total.

Deuda: signo invertido para mostrar deuda positiva; utilización pendiente/concedido solo con concedido positivo; signos inesperados marcados. Se mantiene exclusivamente la fecha de extracción, no se repite 24 veces. No se proyecta el cuadro de amortización: solo hay 87 filas y sus condiciones son una foto.

## 6. Uso por el siguiente paso

1. Ejecutar validación y leer `_feature_catalog.json`.
2. Seleccionar exactamente `model_features`; **no** usar `select_dtypes(number)` sobre todas las columnas.
3. Aplicar elegibilidad y evaluar sensibilidad a moneda incompleta, onboarding y cobertura ERP. Una fila no elegible puede mostrarse como datos insuficientes; no se le asigna un score neutral por defecto.
4. Definir el target y su horizonte antes de entrenar. Censurar filas sin futuro observable; no completar etiquetas con cero.
5. Separar grupos completos entre train/val/test. Identificadores, ERP y datos de cobertura no son señales económicas por defecto.
6. Si una feature termina formando parte de la regla de target, retirarla de sus predictores conforme a la definición acordada.

**Límite de causalidad:** los tests verifican operaciones temporales sobre la capa cleaned, no pueden recuperar disponibilidad histórica de registros, revisiones de ERP, cancelaciones ya eliminadas ni snapshots de estados que el dataset no contiene. No presentar esto como una prueba de anticipación real.
