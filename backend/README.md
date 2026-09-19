# Embat Pulse API (backend)

API FastAPI de **solo lectura** sobre los artefactos que genera `scripts/08_build_product.py` en
`data/processed/product/`. No recalcula ningún score: sirve JSON precomputado. Único cómputo en
caliente: el job de `POST /import`, que ejecuta los scripts del pipeline en un subproceso.

## Arrancar

```bash
# 1) artefactos (una vez, ~5 min con el dataset completo)
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/05_compute_scores_v2.py fit
python -X utf8 scripts/08_build_product.py

# 2) dependencias del backend
pip install -e "backend[dev]"

# 3) servidor
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Docs interactivas en `http://localhost:8000/docs`.

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `XRAY_DATA_DIR` | `<repo>/data` | Raíz de datos (misma que `src/xray/paths.py`); lee `processed/product/` y `processed/scores_v2/` |
| `CORS_ORIGINS` | `http://localhost:3000` | Orígenes permitidos, separados por coma |
| `ADMIN_TOKEN` | vacío (sin protección) | Cabecera `X-Admin-Token` para `POST /reload` |

Los artefactos se cargan al arrancar y se **recargan solos** cuando cambia el sha256 de
`_product_manifest.json` (p. ej. al regenerar con `08_build_product.py`). Cada respuesta lleva
`X-Xray-Manifest: <sha256>` para auditar qué versión del score se mostraba, y `X-Xray-Dataset`.

## Endpoints

| Método | Ruta | Notas |
|---|---|---|
| GET | `/health` | estado, `latest_month`, `git_commit` del manifiesto |
| GET | `/portfolio` | filtros `trajectory, episode, score_status, group_id, confidence_band, currency, min_score, max_score`; `sort=score|delta_vs_prev|confidence|level|momentum|company_id`, `order=asc|desc`; `limit` (≤500), `offset`. `null` siempre al final |
| GET | `/companies/{id}` | fichero íntegro + `meta` |
| GET | `/companies/{id}/timeline?currency=EUR` | 400 si la moneda no existe; sin `currency` usa la principal |
| GET | `/companies/{id}/why?currency=EUR` | top-3 «por qué ha cambiado» del último mes comparable |
| GET | `/groups/{id}` | filiales con su fila de portfolio |
| GET | `/alerts` | `{available: false, items: []}` hasta que exista `alerts.json` |
| GET | `/export/latest.csv` | `scores_v2/company_latest_scores.csv` |
| POST | `/reload` | fuerza recarga del dataset principal |
| POST | `/import` | multipart con los 8 CSV de `data/raw/`; devuelve `job_id` (202) |
| GET | `/import/{job_id}` | `queued | running | done | failed`, `log_tail`, `artifacts_dir` |

Todos los GET aceptan `?dataset=<job_id>` para consultar los artefactos de un job terminado en
lugar del dataset principal.

## Ejemplos

```bash
curl -s localhost:8000/health | jq
curl -s "localhost:8000/portfolio?trajectory=deteriorating&sort=delta_vs_prev&order=asc&limit=5" | jq '.items[] | {company_id, score, delta_vs_prev}'
curl -s localhost:8000/companies/COMP_1040/why | jq '.terms[].sentence'
curl -s "localhost:8000/companies/COMP_1040/timeline" | jq '.[-3:]'
curl -s localhost:8000/groups/GROUP_0147 | jq '{n_companies, n_scored}'
curl -s -o latest.csv localhost:8000/export/latest.csv
curl -s -X POST localhost:8000/import $(for f in groups companies banking_products debt_products debt_schedule_config balances invoices transactions; do echo -n "-F files=@data/raw/$f.csv "; done)
```

`POST /import` usa `05_compute_scores_v2.py predict --reference data/processed/scores_v2/_company_score_reference.json`
(referencia congelada del dataset principal, nunca `fit` con empresas nuevas) y deja su salida en
`data/uploads/{job_id}/processed/product/`. Un job a la vez; con el dataset completo tarda minutos.

## Tests

```bash
python -m pytest -q -p no:asyncio backend/tests
```

La fixture escribe 3 empresas / 2 grupos con el esquema real y simula el subproceso de import.
