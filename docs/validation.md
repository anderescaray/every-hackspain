# Validación — HackSpain X-Ray · Embat

Documentación de la estrategia para medir calidad del score **sin labels visibles**, generalizar al test oculto e iterar con el leaderboard.

## Contexto

- **Train visible:** ~1.286 empresas, 250 grupos, 24 meses
- **Test oculto:** 60–80 empresas que el sistema no ha visto
- **Evaluación:** leaderboard (acierto) + jurado (anticipación, producto, explicación)

No hay columna `target` en los CSV. La validación combina **proxies internos** y **feedback del script de scoring** de los organizadores.

---

## Principio clave: validar por grupo

Empresas del mismo `group_id` son filiales de un holding. **Nunca** mezclar filiales entre train y validation.

```python
from sklearn.model_selection import GroupKFold

gkf = GroupKFold(n_splits=5)
for train_idx, val_idx in gkf.split(X, groups=df["group_id"]):
    ...
```

| Split incorrecto | Split correcto |
|---|---|
| 80% empresas random | 80% **grupos** completos |
| Filial A en train, filial B en test del mismo holding | Todo el holding en train o en test |

---

## Métricas proxy (sin labels)

### 1. Anticipación del momentum

¿El momentum en `t` predice la dirección del nivel en `t+3`?

```python
future_level_delta = level(t+3) - level(t)
corr(momentum(t), future_level_delta)
```

| Resultado | Interpretación |
|---|---|
| > 0.4 | Buena señal anticipatoria |
| 0.2 – 0.4 | Aceptable; iterar pesos |
| < 0.2 | Momentum no aporta; revisar features |

### 2. Estabilidad temporal del score

Penalizar scores que saltan sin razón (ruido):

```python
score_volatility = df.groupby("company_id")["delta_vs_prev"].std().mean()
```

Objetivo: baja volatilidad mes a mes salvo en empresas con cambio real.

### 3. Separación bache vs tendencia

Identificar meses con caída puntual de cashflow seguidos de recuperación:

```python
# "Bache": caída en t, recuperación > 80% en t+1
# Penalizar si el score cae > 5 pts en t pero no en t+1 (falso deterioro)
false_alarm_rate = ...
```

Objetivo: `false_alarm_rate < 30%`

### 4. Balance direccional

El enunciado exige detectar **mejora** igual que **deterioro**:

```python
n_improving  = (trajectory == "improving").sum()
n_deteriorating = (trajectory == "deteriorating").sum()
ratio = n_improving / n_deteriorating
```

No buscar ratio 1:1 (más empresas estables en la realidad), pero evitar ratio < 0.1 (solo detector de quiebras).

### 5. Correlación nivel vs momentum en M24

Empresas con nivel alto y momentum bajo (caso Velasco) deben tener score **menor** que empresas con nivel similar y momentum alto:

```python
# En el cuartil superior de level(M24), correlación level vs score debe ser < correlación momentum vs score
```

---

## Backtest temporal

Simular predicción en el pasado usando solo datos hasta el mes `t`:

| Escenario | Train | Evaluar |
|---|---|---|
| Predicción 6m | Meses 1–18 | Score y trayectoria en 19–24 |
| Predicción 3m | Meses 1–21 | Score en 22–24 |

```python
# Para cada empresa, calcular score con datos hasta M18
score_m18 = compute_score(features[:M18])

# Comparar con score real M24
error = abs(score_m18_extrapolated - score_m24_actual)
```

Útil para ajustar pesos nivel/momentum/estabilidad antes del leaderboard.

---

## Validación de features

Ejecutar tras `01_build_monthly_features.py`:

| Check | Condición |
|---|---|
| Completitud | 1.286 × 24 = 30.864 filas |
| Unicidad | UNIQUE(company_id, month) |
| Nulls críticos | `tx_net_cashflow` sin nulls |
| Saldo M24 | `cash_balance` ≈ `balance_total` ± 10% |
| Outliers | Ninguna feature > p99.9 sin flag |

Script: `scripts/02_validate_features.py` (referenciado en feature-engineering.md).

---

## Validación del score

Ejecutar tras `02_compute_scores.py`:

| Check | Condición |
|---|---|
| Rango | `0 ≤ score ≤ 100` |
| Componentes | `0 ≤ level, momentum, stability ≤ 1` |
| Delta coherente | `delta_vs_prev = score(t) - score(t-1)` |
| Distribución | No > 80% empresas en rango 45–55 (score comprimido) |
| Varianza por mes | std(score) > 5 en cada mes |

---

## Validación de explicaciones

| Check | Condición |
|---|---|
| Drivers | Exactamente 1–3 drivers por empresa/mes |
| Impacto suma razonable | `sum(|impact_points|)` ≈ `|delta_vs_prev|` ± 2 |
| Inflexión | Presente en empresas con `trajectory = deteriorating` |

---

## Validación de alertas

| Check | Condición |
|---|---|
| Falsos positivos (bache) | Tasa < 30% tras filtros |
| Lead time medio | > 2 meses en `REGIME_CHANGE` |
| Cobertura | > 70% deterioros con alerta previa |
| Severidad | No > 50% alertas en severidad high (fatiga) |

---

## Iteración con el leaderboard

Flujo recomendado durante el hackathon:

```
1. Scoring v1 con pesos default (0.4/0.4/0.2)
2. Export CSV → script organizadores → métrica leaderboard
3. Ajustar pesos / umbrales / ventanas
4. Repetir hasta convergencia o límite de tiempo
```

### Qué ajustar según feedback

| Síntoma en leaderboard | Ajuste |
|---|---|
| Score muy comprimido (poca separación) | Aumentar peso momentum; revisar normalización |
| Buen ranking estático, malo en trayectoria | Subir peso momentum a 0.45–0.50 |
| Muchos falsos positivos en alertas | Endurecer filtros de persistencia |
| No detecta mejoras | Revisar sub-score `mom_invoicing` y `STRONG_IMPROVEMENT` |

**No** ajustar features o pesos usando empresas del test oculto directamente (no las tenéis). Usar group k-fold en train como proxy.

---

## Informe de validación (para pitch)

Generar un resumen de una página:

```markdown
## Validación interna

- Group 5-fold: correlación momentum→futuro = 0.42
- Lead time medio alertas: 2.8 meses
- Tasa falsos positivos (bache): 22%
- Leaderboard iteración 3: [métrica que den los organizadores]

Conclusión: el score anticipa cambios ~3 meses antes del impacto visible en nivel.
```

---

## Scripts de referencia

```
scripts/
  02_validate_features.py
  05_validate.py              # métricas proxy + alertas + informe
  06_export_leaderboard.py
```

---

## Próximo paso

Producto, API y demo navegable → [product-and-demo.md](./product-and-demo.md).
