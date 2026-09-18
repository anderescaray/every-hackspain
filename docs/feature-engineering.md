# Feature Engineering — HackSpain X-Ray · Embat

Documentación del pipeline de transformación de datos crudos en señales mensuales por empresa. Este documento es la base del motor de score de salud financiera.

## Objetivo

Convertir los 9 ficheros CSV en un **panel mensual** con granularidad `company_id × month`, donde cada fila resume el comportamiento financiero de una empresa en un mes concreto del periodo **2024-09 → 2026-09** (24 meses).

```
Entrada:  ~3,5M filas (transacciones + facturas + productos)
Salida:   ~30.864 filas (1.286 empresas × 24 meses)
Formato:  Parquet (`data/processed/company_monthly_features.parquet`)
```

El score se construye **encima** de este panel, no directamente sobre los CSV.

---

## Principios de diseño

| Principio | Por qué |
|---|---|
| **Agregar antes de modelar** | 2,6M transacciones no caben en memoria de forma iterativa; DuckDB/Polars agregan una sola vez |
| **Granularidad mensual** | El enunciado pide score mes a mes y medir anticipación |
| **Señales de trayectoria** | Rolling windows (3m, 6m), deltas y pendientes capturan mejora/deterioro |
| **Separar bache de caída** | Volatilidad y persistencia del cashflow distinguen un mes malo de un deterioro estructural |
| **Sin leakage de grupo** | Features por `company_id`; validación cruzada por `group_id` |
| **Interpretabilidad** | Cada feature tiene nombre de negocio claro para alimentar explicaciones |

---

## Arquitectura del pipeline

```
groups.csv ──────────────────────────────┐
companies.csv ───────────────────────────┤
banking_products.csv ────────────────────┤
debt_products.csv ───────────────────────┼──► DuckDB / Polars ──► Parquet
debt_schedule_config.csv ────────────────┤         │
transactions.csv ────────────────────────┤         ▼
invoices.csv ────────────────────────────┤   company_monthly_features.parquet
balances.csv ────────────────────────────┘
```

### Stack recomendado

- **DuckDB** — SQL sobre CSV sin cargar todo en RAM
- **Polars** — alternativa para transforms en Python
- **Parquet** — formato de salida cacheable y rápido de releer

### Script de referencia (estructura)

```
scripts/
  01_build_monthly_features.py   # ETL principal
  02_validate_features.py        # checks de calidad
data/
  processed/
    company_monthly_features.parquet
```

---

## Claves y joins

| Clave | Uso |
|---|---|
| `company_id` | Primary key del panel; cruza todos los ficheros |
| `group_id` | Solo para validación y vista agregada de holding (no como feature directa) |
| `product_id` | Join transacciones/balances ↔ productos bancarios/deuda |
| `month` | `YYYY-MM-01` derivado de `date` / `issuance_date` |

### Calendario de meses

Generar los 24 meses explícitamente y hacer **cross join** con todas las empresas para garantizar filas con ceros donde no hay actividad (mes sin transacciones ≠ mes sano).

```sql
-- Pseudocódigo: esqueleto del panel
SELECT c.company_id, m.month
FROM companies c
CROSS JOIN months m   -- 24 filas fijas
```

---

## Features por fuente de datos

### 1. Transacciones (`transactions.csv`)

**Fuente principal de cashflow operativo.** ~2,6M filas.

#### Agregaciones base (por `company_id`, `month`)

| Feature | Fórmula | Interpretación |
|---|---|---|
| `tx_count` | COUNT(*) | Volumen de actividad bancaria |
| `tx_inflow` | SUM(amount) WHERE amount > 0 | Entradas de caja |
| `tx_outflow` | ABS(SUM(amount)) WHERE amount < 0 | Salidas de caja |
| `tx_net_cashflow` | SUM(amount) | Cashflow neto del mes |
| `tx_inflow_outflow_ratio` | tx_inflow / NULLIF(tx_outflow, 0) | Capacidad de cubrir salidas |
| `tx_avg_amount` | AVG(ABS(amount)) | Ticket medio de movimiento |
| `tx_counterparty_count` | COUNT(DISTINCT counterparty_id) | Diversificación de contrapartes |
| `tx_counterparty_hhi` | SUM(share_i²) por contraparte | Concentración de riesgo (Herfindahl) |

#### Features por categoría (ratio sobre total de movimientos)

Categorías relevantes del dataset:

| Categoría | Feature derivada | Señal |
|---|---|---|
| `collection` | `tx_pct_collection` | Capacidad de cobro |
| `payment` | `tx_pct_payment` | Ritmo de pago a terceros |
| `tax` | `tx_pct_tax` | Carga fiscal / posibles retrasos |
| `fee` | `tx_pct_fee` | Coste bancario |
| `interest_charge` | `tx_pct_interest` | Carga financiera explícita |
| `transfer` | `tx_pct_transfer` | Movimientos internos |
| `utility` | `tx_pct_utility` | Gasto operativo recurrente |

#### Features de trayectoria (rolling, calculadas post-agregación)

| Feature | Ventana | Interpretación |
|---|---|---|
| `tx_net_cashflow_ma3` | 3 meses | Tendencia reciente de caja |
| `tx_net_cashflow_ma6` | 6 meses | Tendencia media plazo |
| `tx_net_cashflow_std3` | 3 meses | Volatilidad reciente |
| `tx_net_cashflow_std6` | 6 meses | Volatilidad estructural |
| `tx_net_cashflow_delta1` | t − t-1 | Cambio mes a mes |
| `tx_net_cashflow_delta3` | t − t-3 | Cambio trimestral |
| `tx_net_cashflow_slope6` | regresión 6m | Pendiente de cashflow |
| `tx_volatility_ratio` | std3 / std6 | Ratio > 1 → inestabilidad creciente |

#### Proxy de saldo de caja (reconstruido)

`balances.csv` solo tiene snapshot a 2026-09-01. Para meses anteriores:

```
cash_balance(t) = cash_balance(t-1) + tx_net_cashflow(t)
```

Inicializar en 0 o usar el balance final retrocediendo desde M24. Generar:

| Feature | Interpretación |
|---|---|
| `cash_balance` | Saldo estimado de cuentas corrientes |
| `cash_balance_delta1` | Variación mensual de liquidez |
| `cash_runway_months` | cash_balance / ABS(tx_outflow_ma3) | Meses de caja al ritmo actual |

---

### 2. Facturas (`invoices.csv`)

**Fuente principal de comportamiento de cobro y pago.** ~898k filas.

#### Convención de signos

| Signo de `amount` | Tipo | Uso |
|---|---|---|
| Positivo | Factura emitida (cobro) | DSO, facturación, morosidad de clientes |
| Negativo | Factura recibida (pago) | DPO, disciplina de pago a proveedores |

#### Agregaciones base (por `company_id`, `month` de `issuance_date`)

| Feature | Fórmula | Interpretación |
|---|---|---|
| `inv_issued_count` | COUNT WHERE amount > 0 | Volumen de facturación |
| `inv_issued_amount` | SUM(amount) WHERE amount > 0 | Facturación total |
| `inv_received_count` | COUNT WHERE amount < 0 | Volumen de compras facturadas |
| `inv_received_amount` | ABS(SUM(amount)) WHERE amount < 0 | Compras facturadas |
| `inv_pending_ratio` | COUNT(status IN pending,overdue) / COUNT(*) | % facturas sin cerrar |
| `inv_overdue_ratio` | COUNT(status = overdue) / COUNT(*) | Morosidad |
| `inv_cancel_ratio` | COUNT(status = cancel) / COUNT(*) | Anulaciones / fricción |

#### DSO y DPO (días)

Calcular por factura individual y agregar a mediana mensual (más robusto que media ante outliers):

```
delay_days = payment_date − due_date
```

| Feature | Filtro | Interpretación |
|---|---|---|
| `inv_dso_median` | amount > 0, status = paid | Días de retraso en cobros (positivo = tarde) |
| `inv_dpo_median` | amount < 0, status = paid | Días de retraso en pagos |
| `inv_dso_p90` | amount > 0 | Cola de morosidad en cobros |
| `inv_early_payment_ratio` | delay_days < 0 | % pagos/cobros anticipados |

#### Features de trayectoria

| Feature | Interpretación |
|---|---|
| `inv_issued_amount_ma3` | Tendencia de facturación |
| `inv_issued_amount_delta3` | Crecimiento/decrecimiento trimestral |
| `inv_dso_delta3` | Empeoramiento/mejora en cobros |
| `inv_dpo_delta3` | Cambio en disciplina de pago |
| `inv_overdue_ratio_ma3` | Morosidad persistente vs puntual |

---

### 3. Deuda (`debt_products.csv` + `debt_schedule_config.csv`)

**Fuente de apalancamiento y coste de financiación.** ~2.239 productos de deuda.

> Nota: `outstanding` y `granted` en `debt_products.csv` son valores al momento de extracción (M24). Para meses anteriores, aproximar con transacciones de categoría `interest_charge` y movimientos de productos de deuda, o tratar como feature de nivel constante con delta solo en M24.

#### Features de nivel (por `company_id`, constantes o M24)

| Feature | Fórmula | Interpretación |
|---|---|---|
| `debt_total_outstanding` | SUM(outstanding) | Deuda total pendiente |
| `debt_total_granted` | SUM(granted) | Líneas concedidas |
| `debt_utilization` | outstanding / NULLIF(granted, 0) | Uso de financiación |
| `debt_product_count` | COUNT(DISTINCT product_id) | Complejidad de estructura de deuda |
| `debt_has_factoring` | BOOL type = factoring | Uso de anticipo de facturas |
| `debt_has_confirming` | BOOL type = confirming | Programa de pagos a proveedores |
| `debt_has_loc` | BOOL type = lineofcredit | Línea de crédito disponible |
| `debt_loc_liquidity` | SUM(liquidity) WHERE type = lineofcredit | Colchón de liquidez disponible |

#### Features de coste (desde transacciones, mensuales)

| Feature | Filtro | Interpretación |
|---|---|---|
| `debt_interest_paid` | category = interest_charge | Carga de intereses del mes |
| `debt_interest_paid_ma3` | rolling 3m | Tendencia del coste financiero |
| `debt_interest_to_inflow_ratio` | interest / tx_inflow | Peso del coste de deuda sobre entradas |

#### Features de schedule (`debt_schedule_config.csv`)

| Feature | Interpretación |
|---|---|
| `debt_avg_interest_rate` | Tipo medio ponderado por outstanding |
| `debt_has_variable_rate` | Exposición a subida de tipos |
| `debt_next_payment_days` | Días hasta próximo vencimiento (desde fecha del mes) |

---

### 4. Balances (`balances.csv`)

**Snapshot final a 2026-09-01.** Una fila por producto (~8.000 filas).

Usar principalmente para **validar** el saldo reconstruido desde transacciones y como feature de M24:

| Feature | Interpretación |
|---|---|
| `balance_total` | SUM(balance) por empresa |
| `balance_available` | SUM(available) — liquidez usable |
| `balance_checking_ratio` | % en cuentas corrientes vs inversión/ahorro |

No usar como feature histórica directa (solo un punto temporal).

---

### 5. Metadatos de empresa (`companies.csv` + `groups.csv`)

Features estáticas (no cambian mes a mes, pero enriquecen el panel):

| Feature | Fuente | Uso |
|---|---|---|
| `group_id` | companies | Validación cruzada |
| `group_size` | groups.n_companies_in_sample | Contexto de holding |
| `company_currency` | companies | Normalización futura si multi-moneda |
| `company_tenure_months` | created_at → month | Antigüedad en plataforma |
| `company_erp` | companies / groups | Segmentación (no para score directo) |

---

## Features compuestas (post-proceso)

Calculadas después de unir todas las fuentes, antes del score:

| Feature | Componentes | Interpretación |
|---|---|---|
| `liquidity_score_raw` | cash_balance, balance_available, debt_loc_liquidity | Capacidad de aguantar shocks |
| `operational_score_raw` | tx_net_cashflow_ma3, inv_issued_amount_ma3 | Salud operativa |
| `collection_score_raw` | inv_dso_median, inv_overdue_ratio | Calidad de cobros |
| `leverage_score_raw` | debt_utilization, debt_interest_to_inflow_ratio | Presión financiera |
| `stability_score_raw` | tx_volatility_ratio, inv_overdue_ratio_ma3 | Bache vs deterioro |

Estas `*_raw` se normalizan a percentil cross-sectional por mes antes de alimentar el score final.

---

## Normalización

Para que el score sea comparable entre empresas y meses:

```
feature_pct(t) = PERCENT_RANK(feature(t)) OVER (PARTITION BY month)
```

- Resultado en [0, 1] por mes
- Robusto ante outliers (común en cashflow de pymes)
- Permite explicar: "DSO en percentil 85 este mes"

Alternativa para producción: z-score con winsorización al p1/p99.

---

## Esquema de salida

```yaml
# company_monthly_features.parquet
company_id:       string    # COMP_XXXX
group_id:         string    # GROUP_XXXX
month:            date      # YYYY-MM-01
# --- cashflow (transactions) ---
tx_count:         int
tx_inflow:        float
tx_outflow:       float
tx_net_cashflow:  float
tx_net_cashflow_ma3: float
tx_net_cashflow_ma6: float
tx_net_cashflow_std3: float
tx_net_cashflow_slope6: float
tx_volatility_ratio: float
cash_balance:     float
cash_runway_months: float
# --- invoices ---
inv_issued_amount: float
inv_dso_median:   float
inv_dpo_median:   float
inv_overdue_ratio: float
inv_dso_delta3:   float
# --- debt ---
debt_total_outstanding: float
debt_utilization: float
debt_interest_paid: float
debt_interest_to_inflow_ratio: float
# --- composite raw ---
liquidity_score_raw: float
operational_score_raw: float
collection_score_raw: float
leverage_score_raw: float
stability_score_raw: float
```

Total estimado: **~45–55 columnas** por fila.

---

## Validación de calidad

Ejecutar tras cada build del pipeline:

| Check | Condición esperada |
|---|---|
| Completitud del panel | 1.286 × 24 = 30.864 filas |
| Sin duplicados | UNIQUE(company_id, month) |
| Rango temporal | month BETWEEN 2024-09-01 AND 2026-09-01 |
| Nulls críticos | tx_net_cashflow NOT NULL (puede ser 0) |
| Consistencia de saldo | cash_balance(M24) ≈ balance_total ± 10% |
| Outliers | Ningún feature > p99.9 sin revisar |

```python
# Ejemplo de validación rápida
assert len(df) == 1286 * 24
assert df.duplicated(["company_id", "month"]).sum() == 0
assert df["tx_net_cashflow"].isna().sum() == 0
```

---

## Consideraciones de rendimiento

| Operación | Tiempo estimado | Notas |
|---|---|---|
| Agregación transacciones (DuckDB) | ~30–60 s | Leer CSV directamente |
| Agregación facturas (DuckDB) | ~20–40 s | Índice por company_id + month |
| Rolling features (Polars) | ~5 s | Sobre panel ya agregado |
| Escritura Parquet | < 1 s | ~30k filas |
| **Total pipeline** | **~2 min** | Re-ejecutable en cada iteración |

Guardar Parquet evita reprocessar 3,5M filas en cada cambio del score.

---

## Orden de implementación

1. Esqueleto del panel (`company_id × month`)
2. Agregaciones de transacciones (cashflow base)
3. Rolling windows y proxy de saldo
4. Agregaciones de facturas (DSO/DPO/morosidad)
5. Features de deuda (nivel + intereses desde transacciones)
6. Features compuestas y normalización
7. Validación y export a Parquet

---

## Próximo documento

Una vez generado `company_monthly_features.parquet`, el siguiente paso es documentar la **capa de scoring** (`docs/scoring.md`): cómo convertir estas features en el score 0–100 con componentes de nivel, momentum y estabilidad.
