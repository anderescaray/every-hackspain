# Explicabilidad — HackSpain X-Ray · Embat

> **Estado: diseño pendiente, no hay explicaciones ni scores generados.** Ver [decisiones.md](./decisiones.md) para lo implementado. Los JSON, impactos y meses de anticipación siguientes son ejemplos, no resultados. El último mes completo es agosto de 2026. Para el GBM acordado se requiere SHAP; un giro de momentum frente a una caída del propio score no es una medición independiente de anticipación.

Documentación de la futura capa que explica **por qué** una empresa tiene un score concreto y **qué lo movió** respecto al mes anterior.

## Entrada y salida

```
Entrada:  company_monthly_features.parquet
          company_monthly_scores.parquet
Salida:   data/processed/company_explanations.json
```

El enunciado exige que nadie compre una caja negra. Con el score compuesto (nivel + momentum + estabilidad) la explicación es **nativa**, sin necesidad de SHAP.

---

## Qué debe explicar el sistema

| Pregunta | Respuesta esperada |
|---|---|
| ¿Por qué este score? | Descomposición en componentes con peso |
| ¿Qué cambió desde el mes pasado? | Top drivers con impacto en puntos |
| ¿Hacia dónde va? | Clasificación de trayectoria + timeline |
| ¿Cuándo empezó a cambiar? | Mes de inflexión del momentum (anticipación) |

---

## Estructura de una explicación

```json
{
  "company_id": "COMP_0218",
  "month": "2026-09",
  "score": 68,
  "delta_vs_prev": -3,
  "trajectory": "deteriorating",
  "summary": "Score 68 (−3 vs ago). Momentum negativo 4 meses. DSO subió 12 días.",
  "decomposition": {
    "level":     {"value": 0.72, "points": 29, "weight": 0.4},
    "momentum":  {"value": 0.38, "points": 15, "weight": 0.4},
    "stability": {"value": 0.85, "points": 17, "weight": 0.2}
  },
  "drivers": [
    {
      "signal": "DSO (días de cobro)",
      "metric": "inv_dso_median",
      "previous": 28,
      "current": 40,
      "change": "+12 días",
      "direction": "worse",
      "impact_points": -4,
      "component": "level_collection"
    },
    {
      "signal": "Cashflow neto",
      "metric": "tx_net_cashflow",
      "previous": 45000,
      "current": 34500,
      "change": "-23%",
      "direction": "worse",
      "impact_points": -3,
      "component": "mom_cashflow"
    },
    {
      "signal": "Morosidad",
      "metric": "inv_overdue_ratio",
      "previous": 0.05,
      "current": 0.11,
      "change": "+6 pp",
      "direction": "worse",
      "impact_points": -2,
      "component": "level_collection"
    }
  ],
  "inflection": {
    "momentum_turned": "2026-05",
    "months_before_level_drop": 3,
    "description": "El momentum giró a negativo en mayo; el nivel no cayó hasta agosto."
  }
}
```

---

## Descomposición del score

Traducir cada componente [0, 1] a puntos sobre 100 según su peso:

```python
def component_points(value: float, weight: float) -> int:
    return round(value * weight * 100)

# Ejemplo: level=0.72, weight=0.4 → 29 puntos
```

### Texto automático de descomposición

Plantilla:

```
Score {score} = Nivel {level_pts} + Momentum {mom_pts} + Estabilidad {stab_pts}
```

Ejemplo:

> Score 68 = Nivel 29 + Momentum 15 + Estabilidad 17

Si el usuario pregunta por una empresa con nivel alto pero score medio:

> "Velasco saca 68 porque su momentum (15 pts) arrastra el score pese a un nivel aún razonable (29 pts)."

---

## Cálculo de drivers (top 3)

Para cada mes `t`, comparar features clave entre `t` y `t-1`. Atribuir impacto proporcional al cambio en el sub-score del componente afectado.

### Features candidatas a driver

| Feature | Etiqueta humana | Componente |
|---|---|---|
| `inv_dso_median` | DSO (días de cobro) | level_collection |
| `inv_overdue_ratio` | Morosidad | level_collection |
| `tx_net_cashflow` | Cashflow neto | mom_cashflow |
| `tx_net_cashflow_delta3` | Tendencia de caja (3m) | mom_cashflow |
| `cash_balance` | Saldo de caja | level_liquidity |
| `cash_runway_months` | Meses de caja | level_liquidity |
| `debt_utilization` | Uso de financiación | level_leverage |
| `debt_interest_to_inflow_ratio` | Carga financiera | level_leverage |
| `inv_issued_amount_ma3` | Facturación (3m) | level_operations |
| `tx_volatility_ratio` | Volatilidad de caja | stability |

### Algoritmo de impacto

```python
# 1. Calcular delta de cada sub-score entre t y t-1
delta_sub = sub_score(t) - sub_score(t - 1)

# 2. Para cada feature del sub-score, estimar contribución
#    contrib = delta_sub * (peso_feature * delta_feature_normalizado)

# 3. Ordenar por |impact| descendente, tomar top 3
drivers = sorted(impacts, key=lambda d: abs(d.impact_points), reverse=True)[:3]
```

### Formato de cambio legible

| Tipo de feature | Formato |
|---|---|
| Ratio / percentil | `+6 pp` o `−8%` |
| Días (DSO/DPO) | `+12 días` |
| Importes | `−23%` (siempre relativo, no absoluto) |
| Conteos | `+15 transacciones` |

Usar siempre **dirección de negocio** (`better` / `worse`), no solo signo matemático.

---

## Detección de inflexión (anticipación)

Medir cuántos meses **antes** el sistema vio venir el cambio:

```python
# Mes en que momentum cruza 0.50 hacia abajo (de mejorando a empeorando)
momentum_turn = first_month_where(momentum < 0.45, after=momentum > 0.55)

# Mes en que el score cae más de 5 puntos
level_drop = first_month_where(delta_vs_prev < -5)

months_before = months_between(momentum_turn, level_drop)
```

Incluir en la explicación de M24 para empresas con deterioro:

> "El sistema detectó el giro en M20, **3 meses antes** de que el score cayera de forma visible."

Esto alimenta el **bonus de anticipación** del enunciado.

---

## Timeline para la demo

Por empresa, preparar serie de 24 meses para gráficos:

```json
{
  "company_id": "COMP_0218",
  "timeline": [
    {"month": "2024-09", "score": 45, "level": 0.42, "momentum": 0.48, "stability": 0.70},
    {"month": "2024-10", "score": 47, "level": 0.43, "momentum": 0.52, "stability": 0.72},
    "...",
    {"month": "2026-09", "score": 68, "level": 0.72, "momentum": 0.38, "stability": 0.85}
  ],
  "annotations": [
    {"month": "2026-05", "type": "momentum_turn", "label": "Momentum gira a negativo"},
    {"month": "2026-08", "type": "score_drop", "label": "Score cae 5 pts"}
  ]
}
```

---

## Resúmenes automáticos (NLG simple)

Plantillas por trayectoria — sin LLM obligatorio para el MVP:

| Trayectoria | Plantilla |
|---|---|
| `improving` | "Score {score} (+{delta} vs mes anterior). Tendencia positiva en {top_driver}." |
| `deteriorating` | "Score {score} ({delta} vs mes anterior). Momentum negativo {n} meses. {top_driver} empeoró." |
| `recovering` | "Score {score} (+{delta}). Aún por debajo de la media, pero {top_driver} mejora." |
| `stable` | "Score {score} (sin cambio relevante). Señales estables en caja y cobros." |

Opcional: enriquecer con LLM en la demo para recomendaciones ([product-and-demo.md](./product-and-demo.md)).

---

## API de explicaciones

Endpoints que consume el frontend:

```
GET /companies/{company_id}/explanation?month=2026-09
GET /companies/{company_id}/timeline
GET /companies/{company_id}/drivers?month=2026-09
```

Respuesta: JSON con la estructura definida arriba. Precomputar en batch; no calcular en tiempo real en la demo.

---

## Script de referencia

```
scripts/
  03_generate_explanations.py
```

---

## Próximo paso

Convertir cambios significativos en alertas proactivas → [alerts-and-monitoring.md](./alerts-and-monitoring.md).
