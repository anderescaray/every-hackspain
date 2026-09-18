# Scoring — HackSpain X-Ray · Embat

Documentación de la capa que convierte features mensuales en un **score de salud financiera 0–100** por empresa y mes.

## Entrada y salida

```
Entrada:  data/processed/company_monthly_features.parquet
Salida:   data/processed/company_monthly_scores.parquet
          data/processed/leaderboard_submission.csv   (para test oculto)
```

Cada fila de salida: `company_id × month` con score descompuesto en tres componentes.

---

## Objetivo del score

El enunciado pide capturar **trayectoria**, no solo la foto del último mes. El ejemplo Northbrook (45→65) vs Velasco (82→68) muestra dos empresas con nivel similar en M24 pero riesgos opuestos.

El score debe responder:

| Pregunta | Componente |
|---|---|
| ¿Cómo está hoy? | **Nivel** |
| ¿Hacia dónde va? | **Momentum** |
| ¿Es un bache o una caída real? | **Estabilidad** |

---

## Arquitectura del score

```
company_monthly_features.parquet
        │
        ├─► Nivel (40%)      ── liquidez, cobros, operaciones, apalancamiento
        ├─► Momentum (40%)   ── deltas, pendientes, cambio de régimen
        └─► Estabilidad (20%) ── volatilidad, persistencia de señales negativas
        │
        ▼
   score = 0.4×nivel + 0.4×momentum + 0.2×estabilidad
        │
        ▼
   escala 0–100 (clamp + round)
```

Los pesos `0.4 / 0.4 / 0.2` son el punto de partida; ajustar con el leaderboard y validación interna.

---

## Componente 1: Nivel

Foto de salud en el mes `t`. Usa features **normalizadas a percentil** (0–1) por mes, tal como se define en [feature-engineering.md](./feature-engineering.md).

### Sub-scores de nivel

| Sub-score | Features (percentil) | Peso | Lógica |
|---|---|---:|---|
| `level_liquidity` | `liquidity_score_raw`, `cash_runway_months`, `cash_balance` | 0.30 | Más liquidez → mejor |
| `level_operations` | `operational_score_raw`, `tx_net_cashflow_ma3`, `inv_issued_amount_ma3` | 0.25 | Cashflow y facturación sanos → mejor |
| `level_collection` | `collection_score_raw`, `inv_dso_median`, `inv_overdue_ratio` | 0.25 | DSO bajo, morosidad baja → mejor |
| `level_leverage` | `leverage_score_raw`, `debt_utilization`, `debt_interest_to_inflow_ratio` | 0.20 | Menos apalancamiento → mejor (invertir signo) |

### Cálculo

```python
level_liquidity   = weighted_mean([pct(liquidity_score_raw), pct(cash_runway_months), pct(cash_balance)])
level_operations  = weighted_mean([pct(operational_score_raw), pct(tx_net_cashflow_ma3), pct(inv_issued_amount_ma3)])
level_collection  = weighted_mean([pct(collection_score_raw), 1 - pct(inv_dso_median), 1 - pct(inv_overdue_ratio)])
level_leverage    = weighted_mean([1 - pct(leverage_score_raw), 1 - pct(debt_utilization), 1 - pct(debt_interest_to_inflow_ratio)])

level = (
    0.30 * level_liquidity +
    0.25 * level_operations +
    0.25 * level_collection +
    0.20 * level_leverage
)  # resultado en [0, 1]
```

---

## Componente 2: Momentum

Captura la **dirección del movimiento**. Es lo que diferencia a Northbrook (mejorando) de Velasco (empeorando) cuando el nivel en M24 es similar.

### Sub-scores de momentum

| Sub-score | Features | Peso | Lógica |
|---|---|---:|---|
| `mom_cashflow` | `tx_net_cashflow_delta3`, `tx_net_cashflow_slope6` | 0.30 | Pendiente positiva → mejorando |
| `mom_invoicing` | `inv_issued_amount_delta3`, `inv_dso_delta3` | 0.25 | Más facturación, DSO bajando → mejorando |
| `mom_debt` | `debt_interest_paid_ma3` delta, `debt_utilization` delta | 0.20 | Menos presión de deuda → mejorando |
| `mom_level` | `level(t) - level(t-3)` | 0.25 | El propio nivel ya sube/baja |

### Normalización de deltas

Los deltas en unidades crudas no son comparables entre empresas. Convertir a percentil cross-sectional por mes antes de combinar:

```python
mom_cashflow = weighted_mean([
    pct(tx_net_cashflow_delta3),
    pct(tx_net_cashflow_slope6),
])
mom_invoicing = weighted_mean([
    pct(inv_issued_amount_delta3),
    1 - pct(inv_dso_delta3),   # DSO subiendo es malo
])
mom_debt = weighted_mean([
    1 - pct(debt_interest_paid_ma3 - debt_interest_paid_ma3.shift(3)),
    1 - pct(debt_utilization - debt_utilization.shift(3)),
])
mom_level = pct(level - level.shift(3))

momentum = (
    0.30 * mom_cashflow +
    0.25 * mom_invoicing +
    0.20 * mom_debt +
    0.25 * mom_level
)  # [0, 1]
```

### Detección de las dos direcciones

| Condición | Clasificación | Score momentum |
|---|---|---|
| `momentum > 0.65` | Mejorando con fuerza | Alto |
| `0.45 ≤ momentum ≤ 0.65` | Estable | Medio |
| `momentum < 0.45` | Deteriorando | Bajo |

Un detector de quiebras puro solo captura la cola inferior; este diseño reconoce **mejora excepcional** con la misma lógica.

---

## Componente 3: Estabilidad

Distingue un **bache puntual** de un **deterioro estructural**.

| Sub-score | Features | Peso | Lógica |
|---|---|---:|---|
| `stab_volatility` | `tx_volatility_ratio`, `tx_net_cashflow_std3` | 0.40 | Volatilidad baja → más estable |
| `stab_persistence` | meses consecutivos con `inv_overdue_ratio` alto | 0.30 | Morosidad persistente → inestable |
| `stab_recovery` | cashflow mes actual vs media 3m anterior | 0.30 | Recuperación tras caída → estable |

```python
stab_volatility  = weighted_mean([1 - pct(tx_volatility_ratio), 1 - pct(tx_net_cashflow_std3)])
stab_persistence = 1 - pct(consecutive_months_overdue_above_median)
stab_recovery    = pct(tx_net_cashflow - tx_net_cashflow_ma3.shift(1))  # positivo si recupera

stability = (
    0.40 * stab_volatility +
    0.30 * stab_persistence +
    0.30 * stab_recovery
)  # [0, 1]
```

### Regla bache vs caída

```
SI caída de cashflow > 1 std EN un mes
   Y cashflow del mes siguiente > 80% de la media pre-caída
ENTONCES → bache (no penalizar estabilidad)
SINO SI caída persiste 2+ meses
ENTONCES → deterioro estructural (penalizar estabilidad)
```

---

## Score final

```python
score_raw = 0.4 * level + 0.4 * momentum + 0.2 * stability
score     = round(clamp(score_raw * 100, 0, 100))
delta     = score(t) - score(t - 1)
```

### Campos de salida

| Campo | Tipo | Descripción |
|---|---|---|
| `company_id` | string | Clave |
| `group_id` | string | Para validación y vista de holding |
| `month` | date | YYYY-MM-01 |
| `score` | int | 0–100 |
| `level` | float | Componente nivel [0, 1] |
| `momentum` | float | Componente momentum [0, 1] |
| `stability` | float | Componente estabilidad [0, 1] |
| `delta_vs_prev` | int | Cambio vs mes anterior |
| `trajectory` | string | `improving` / `stable` / `deteriorating` / `recovering` |

### Clasificación de trayectoria

```python
if momentum > 0.60 and delta_vs_prev > 0:
    trajectory = "improving"
elif momentum < 0.40 and delta_vs_prev < 0:
    trajectory = "deteriorating"
elif delta_vs_prev > 0 and momentum < 0.50:
    trajectory = "recovering"   # nivel aún bajo pero girando
else:
    trajectory = "stable"
```

---

## Entrega al leaderboard

El script de scoring de los organizadores espera predicciones sobre empresas del **test oculto** (60–80 empresas no vistas). El pipeline debe:

1. Cargar CSV de empresas a puntuar (formato que den los organizadores)
2. Ejecutar feature engineering + scoring sobre esas empresas
3. Exportar el score de **M24** (o el mes que indiquen)

```csv
company_id,score
COMP_XXXX,68
COMP_YYYY,72
...
```

Script: `scripts/06_export_leaderboard.py`

---

## Iteración de pesos

| Parámetro | Rango a probar | Señal de ajuste |
|---|---|---|
| Peso nivel / momentum / estabilidad | 0.3–0.5 / 0.3–0.5 / 0.1–0.3 | Leaderboard + proxy interno |
| Ventana momentum | 3m vs 6m | Anticipación en backtest |
| Umbral trayectoria | ±0.05 sobre 0.40/0.60 | Balance mejora vs deterioro |

No overfittear a empresas concretas. Validar siempre con group k-fold ([validation.md](./validation.md)).

---

## Script de referencia

```
scripts/
  02_compute_scores.py       # scoring principal
  06_export_leaderboard.py   # CSV para test oculto
```

Dependencias: lee `company_monthly_features.parquet`, escribe `company_monthly_scores.parquet`.

---

## Próximo paso

Con scores calculados, generar explicaciones por empresa/mes → [explainability.md](./explainability.md).
