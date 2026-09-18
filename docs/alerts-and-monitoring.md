# Alertas y monitorización — HackSpain X-Ray · Embat

Documentación del sistema proactivo que **levanta la mano** cuando una empresa cambia de verdad, sin que nadie pregunte.

## Entrada y salida

```
Entrada:  company_monthly_scores.parquet
          company_monthly_features.parquet
          company_explanations.json
Salida:   data/processed/alerts.json
```

Bonus del enunciado: monitor que avisa + anticipación medida en meses.

---

## Objetivo

| Problema | Solución |
|---|---|
| Un mes malo de caja ≠ deterioro | Reglas de confirmación antes de alertar |
| Score estable en M24 oculta trayectoria | Alertar por momentum, no solo por nivel |
| Usuario no revisa el dashboard a diario | Feed de alertas ordenado por severidad |
| Jurado pide anticipación | Registrar mes de detección vs mes de impacto visible |

---

## Tipos de alerta

| Tipo | Código | Disparador | Severidad |
|---|---|---|---|
| Caída de score | `SCORE_DROP` | `delta_vs_prev ≤ −5` | Alta |
| Momentum negativo sostenido | `MOMENTUM_DECLINE` | `momentum < 0.40` durante 2+ meses | Media |
| Cambio de régimen | `REGIME_CHANGE` | momentum cruza 0.50 (mejorando → empeorando) | Alta |
| Morosidad creciente | `OVERDUE_SPIKE` | `inv_overdue_ratio` sube > 5 pp en 3m | Media |
| Presión de deuda | `DEBT_PRESSURE` | `debt_utilization > 0.85` o intereses/inflow > umbral | Media |
| Liquidez crítica | `LIQUIDITY_WARNING` | `cash_runway_months < 2` | Alta |
| Recuperación | `RECOVERY` | `trajectory = recovering` y `delta_vs_prev ≥ +3` | Info (positiva) |
| Mejora excepcional | `STRONG_IMPROVEMENT` | `momentum > 0.65` y `delta_vs_prev ≥ +5` | Info (positiva) |

---

## Reglas de confirmación (bache vs caída)

Antes de emitir alertas negativas, aplicar filtros:

### Filtro 1: Persistencia

```
SCORE_DROP solo si:
  - delta_vs_prev ≤ −5
  Y (delta_vs_prev(t-1) < 0 OR momentum < 0.45)
```

Un único mes malo sin continuidad → **no alertar** (clasificar como `BOUNCE`, sin entrada en feed).

### Filtro 2: Recuperación de cashflow

```
SI tx_net_cashflow(t) cae > 1 std
   Y tx_net_cashflow(t+1) > 0.8 × media(tx_net_cashflow t-3..t-1)
ENTONCES suprimir SCORE_DROP en t
```

### Filtro 3: Estacionalidad

Si la caída ocurre en el mismo mes que en años anteriores (patrón estacional en el dataset), reducir severidad de `SCORE_DROP` a baja o suprimir. Implementación mínima: comparar con media del mismo mes en los 24 meses disponibles por empresa.

---

## Estructura de una alerta

```json
{
  "alert_id": "ALERT_202609_COMP0218_001",
  "company_id": "COMP_0218",
  "group_id": "GROUP_0113",
  "month": "2026-09",
  "type": "REGIME_CHANGE",
  "severity": "high",
  "title": "Cambio de régimen detectado",
  "message": "El momentum lleva 4 meses negativo. DSO subió 12 días desde junio.",
  "score": 68,
  "delta_vs_prev": -3,
  "trajectory": "deteriorating",
  "drivers": [
    {"signal": "DSO", "change": "+12 días", "impact_points": -4}
  ],
  "anticipation": {
    "detected_at": "2026-05",
    "visible_impact_at": "2026-08",
    "months_ahead": 3
  },
  "recommended_actions": [
    "Revisar cartera de clientes con mayor retraso de pago",
    "Activar recordatorios de cobro automáticos"
  ],
  "acknowledged": false,
  "created_at": "2026-09-01T00:00:00Z"
}
```

---

## Feed de alertas

`alerts.json` es un array ordenado por:

1. `severity` (high → medium → info)
2. `month` descendente
3. `|delta_vs_prev|` descendente

```json
{
  "generated_at": "2026-09-18T12:00:00Z",
  "total_alerts": 47,
  "by_severity": {"high": 12, "medium": 28, "info": 7},
  "alerts": [ "..."]
}
```

### Vista monitor (demo)

Pantalla dedicada que muestra:

- Alertas de las últimas 4 semanas (últimos meses del dataset)
- Filtro por severidad y tipo
- Badge en lista de empresas cuando hay alerta activa sin ack

---

## Métricas de anticipación

Calcular a nivel global para el pitch:

| Métrica | Fórmula | Objetivo |
|---|---|---|
| **Lead time medio** | AVG(`months_ahead`) en alertas `REGIME_CHANGE` | > 2 meses |
| **Tasa de falsos positivos** | Alertas suprimidas por filtro / total candidatas | < 30% |
| **Cobertura de deterioro** | % empresas con `trajectory=deteriorating` que tuvieron alerta previa | > 70% |
| **Balance direccional** | Alertas `STRONG_IMPROVEMENT` / alertas negativas | ~0.2–0.3 |

Script de agregación en `scripts/05_validate.py` (sección alertas).

---

## Recomendaciones automáticas

Reglas simples mapeadas a tipo de alerta (sin LLM en MVP):

| Tipo alerta | Acción recomendada |
|---|---|
| `OVERDUE_SPIKE` | Revisar clientes con mayor DSO; activar cobros |
| `DEBT_PRESSURE` | Evaluar refinanciación o amortización anticipada |
| `LIQUIDITY_WARNING` | Retrasar pagos no críticos; usar línea de crédito |
| `MOMENTUM_DECLINE` | Revisión de costes y previsión de caja 13 semanas |
| `STRONG_IMPROVEMENT` | Ventana para negociar mejor condiciones con banco |

Estas recomendaciones alimentan el módulo **Embat Pulse** ([product-and-demo.md](./product-and-demo.md)).

---

## Monitor proactivo (comportamiento en demo)

En producción real: cron mensual tras cierre de datos. En la demo:

1. Precomputar alertas para M22–M24
2. Simular "nuevas alertas" con timestamp reciente
3. Mostrar notificación en UI: *"3 empresas requieren atención este mes"*

Opcional: endpoint `GET /alerts/recent?limit=10` que devuelve las más severas.

---

## API de alertas

```
GET  /alerts                    # feed completo, paginado
GET  /alerts/recent             # últimas N alertas
GET  /companies/{id}/alerts     # alertas de una empresa
POST /alerts/{id}/acknowledge   # marcar como vista (demo)
```

---

## Script de referencia

```
scripts/
  04_generate_alerts.py
```

---

## Próximo paso

Validar calidad del score y alertas antes de iterar → [validation.md](./validation.md).
