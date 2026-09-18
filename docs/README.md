# Documentación técnica — HackSpain X-Ray · Embat

Guía de implementación del reto de salud financiera: desde datos crudos hasta producto demo-able.

## Flujo del sistema

```
data/raw/  CSV originales (9 ficheros)
      │
      ▼
[0] Limpieza ─────────────► data/cleaned/*.parquet   (ver decisiones.md)
      │
      ▼
[1] Feature Engineering ──► company_monthly_features.parquet
      │
      ▼
[2] Scoring ──────────────► company_monthly_scores.parquet
      │
      ├──► [3] Explicabilidad ──► company_explanations.json
      ├──► [4] Alertas ──────────► alerts.json
      ├──► [5] Validación ───────► métricas internas + CSV leaderboard
      │
      ▼
[6] Producto + Demo ──────► API + frontend desplegado
```

## Documentos

| # | Documento | Qué cubre |
|---|---|---|
| 0 | [decisiones.md](./decisiones.md) | Reglas de limpieza aplicadas y decisiones de datos pendientes |
| 1 | [feature-engineering.md](./feature-engineering.md) | ETL, features mensuales por empresa, normalización |
| 2 | [scoring.md](./scoring.md) | Score 0–100: nivel, momentum, estabilidad |
| 3 | [explainability.md](./explainability.md) | Drivers, descomposición, timeline de cambios |
| 4 | [alerts-and-monitoring.md](./alerts-and-monitoring.md) | Monitor proactivo, anticipación, bache vs caída |
| 5 | [validation.md](./validation.md) | Group k-fold, backtest, métricas proxy, leaderboard |
| 6 | [product-and-demo.md](./product-and-demo.md) | Embat Pulse, API, frontend, despliegue, pitch |

## Artefactos generados

```
data/cleaned/                        # capa limpia (una tabla por parquet)
data/processed/
  company_monthly_features.parquet   # ~30.864 filas
  company_monthly_scores.parquet     # ~30.864 filas
  company_explanations.json          # explicaciones por empresa/mes
  alerts.json                        # feed de alertas
  leaderboard_submission.csv         # entrega al script de scoring

backend/                             # FastAPI
frontend/                            # Next.js demo
scripts/
  00_clean_data.py                   # hecho: data/raw -> data/cleaned
  01_build_monthly_features.py
  02_compute_scores.py
  03_generate_explanations.py
  04_generate_alerts.py
  05_validate.py
  06_export_leaderboard.py
```

## Requisitos del enunciado → documento

| Requisito | Documento |
|---|---|
| Predicción test oculto (leaderboard) | [scoring.md](./scoring.md), [validation.md](./validation.md) |
| Señal en las dos direcciones | [scoring.md](./scoring.md) (componente momentum) |
| Trayectoria, no foto | [scoring.md](./scoring.md), [feature-engineering.md](./feature-engineering.md) |
| Explicación | [explainability.md](./explainability.md) |
| Producto encima del score | [product-and-demo.md](./product-and-demo.md) |
| Comprador identificado | [product-and-demo.md](./product-and-demo.md) |
| Demo navegable | [product-and-demo.md](./product-and-demo.md) |
| Anticipación medida (bonus) | [alerts-and-monitoring.md](./alerts-and-monitoring.md) |
| Monitor que avisa (bonus) | [alerts-and-monitoring.md](./alerts-and-monitoring.md) |

## Orden de implementación (hackathon)

| Fase | Tiempo est. | Entregable |
|---|---|---|
| Feature engineering | 3–4 h | `company_monthly_features.parquet` |
| Scoring v1 | 2–3 h | `company_monthly_scores.parquet` + CSV leaderboard |
| Explicabilidad | 1–2 h | `company_explanations.json` |
| Alertas | 1–2 h | `alerts.json` |
| Validación + iteración | 1–2 h | métricas + ajuste de pesos |
| API + demo web | 4–5 h | URL desplegada |
| Pitch | 1 h | presentación 5 min |
