# Brief: backend FastAPI para servir el score (para implementar en paralelo)

Instrucciones autosuficientes para otro agente. No requiere conocer la conversación previa.
Estado del repo verificado el 19-09-2026 (commit `40c30da`).

## 0. Principio rector: la API sirve, no calcula

El score (`financial_smoothed_v2`, `src/xray/score_v2/`) es **batch**: nivel de 6 meses, referencia
ajustada sobre grupos y meses anteriores, manifiestos con hashes y test de prefijo. La API **no
reimplementa nada de eso**: lee los artefactos que ya genera `scripts/08_build_product.py` en
`data/processed/product/` y los devuelve. Único cómputo en caliente permitido: `whatif` (función
pura sobre una empresa, aún no existe; no bloquea). El recálculo completo se lanza como job
(`POST /import`) ejecutando los scripts existentes con `XRAY_DATA_DIR` apuntando a otra carpeta.

Consecuencia: cuando el equipo de datos mejore features/score y regenere artefactos, la API no cambia.

## 1. Artefactos de entrada (ya existen; no modificarlos)

Generados por, en orden:

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/05_compute_scores_v2.py fit
python -X utf8 scripts/08_build_product.py
```

Salida en `data/processed/product/` (gitignored; pedir la carpeta al equipo o regenerar, ~5 min):

| Fichero | Contenido | Uso en la API |
|---|---|---|
| `portfolio.json` | `{"latest_month": "2026-08-01T00:00:00", "companies": [ {...}, ... ]}` — una fila por empresa (1.286), moneda principal, último mes | `GET /portfolio` |
| `companies/{company_id}.json` | `{company_id, group_id, latest_month, currencies: {EUR: {timeline: [24 filas], why_changed: {month, terms: [...]}, confidence: {...}}}}` | `GET /companies/{id}` |
| `groups/{group_id}.json` | `{group_id, n_companies, companies: [filas de portfolio]}` (250) | `GET /groups/{id}` |
| `score_changes.parquet`, `confidence.parquet` | detalle por entidad-moneda-mes | opcional (evidencia paginada) |
| `_product_manifest.json` | `created_at`, `latest_month`, `inputs_sha256`, `code.git_commit`, `code.source_sha256` | `GET /health` y cabecera de versión |

Campos de una fila de portfolio (exactos):
`company_id, group_id, currency, currencies, month, score, level, momentum, stability, trajectory,
episode, score_status, score_reason, delta_vs_prev, confidence, confidence_band, main_signal,
main_signal_delta`.

Campos de cada punto del `timeline`:
`month, score, level, momentum, stability, trajectory, episode, score_status, score_reason,
delta_vs_prev, level_operations, level_debt, level_collections, level_payments, confidence,
confidence_band`.

Valores enumerados observados: `score_status ∈ {scored, provisional, not_scored}`;
`trajectory` incluye `insufficient_history, stable, emerging_improvement, ...`; `episode` incluye
`none, not_sustained_by_current_month, ...`. **No** hardcodear la lista: pasar el string tal cual.
`score` puede ser `null` (no puntuada); nunca sustituir por 0 ni 50.

Complementario en `data/processed/scores_v2/`: `company_latest_scores.csv` (candidato a entrega
al leaderboard, no submission oficial), `_company_score_reference.json` (referencia congelada para
`predict`).

## 2. Contrato de la API

Base: `backend/` en la raíz del repo. FastAPI + uvicorn. **Sin base de datos**: filesystem + JSON.
Raíz de datos configurable con la variable `XRAY_DATA_DIR` (misma que usa `src/xray/paths.py`);
por defecto `<repo>/data`. Los artefactos se cargan en memoria al arrancar y se recargan si
cambia el `sha256` de `_product_manifest.json` (o con `POST /reload`, protegido por token simple).

| Método | Ruta | Respuesta | Notas |
|---|---|---|---|
| GET | `/health` | `{status, latest_month, method: "financial_smoothed_v2", manifest_created_at, git_commit, n_companies}` | leer del manifiesto |
| GET | `/portfolio` | `{latest_month, total, items: [...]}` | filtros query: `trajectory`, `score_status`, `group_id`, `min_score`, `max_score`, `confidence_band`; orden `sort=score|delta_vs_prev|confidence`, `order=asc|desc`; paginación `limit` (≤500, def. 100), `offset` |
| GET | `/companies/{company_id}` | el JSON del fichero, más `meta: {method, manifest_sha256}` | 404 si no existe |
| GET | `/companies/{company_id}/timeline?currency=EUR` | solo `timeline` de esa moneda | 400 si la moneda no está en `currencies` |
| GET | `/companies/{company_id}/why?currency=EUR` | `why_changed` de esa moneda | idem |
| GET | `/groups/{group_id}` | JSON del fichero | 404 |
| GET | `/alerts?severity=&type=&limit=` | `{items: []}` hasta que exista `alerts.json`; si existe, servirlo con filtros | no bloquear la demo por esto |
| GET | `/export/latest.csv` | `scores_v2/company_latest_scores.csv` tal cual | `Content-Type: text/csv` |
| POST | `/import` | `{job_id, status: "queued"}` | ver §4; puede entregarse después |
| GET | `/import/{job_id}` | `{job_id, status, started_at, finished_at, log_tail, artifacts_dir}` | |
| POST | `/reload` | `{reloaded: true, manifest_sha256}` | cabecera `X-Admin-Token` |

Reglas de respuesta:
- Fechas como ISO 8601 (ya vienen así). `NaN` nunca sale: los ficheros ya usan `null`.
- Cada respuesta lleva cabecera `X-Xray-Manifest: <sha256 de _product_manifest.json>` para poder
  auditar qué versión del score se estaba mostrando.
- CORS abierto para `localhost:3000` y el dominio del front (variable `CORS_ORIGINS`).
- Errores: `{detail: "..."}` estándar de FastAPI; 404 para ids desconocidos, 400 para query inválida,
  503 si los artefactos no están cargados (con mensaje que diga qué script ejecutar).

## 3. Estructura de código

```
backend/
  pyproject.toml            fastapi, uvicorn[standard], pydantic>=2 (pandas/pyarrow ya están en el repo)
  app/
    main.py                 create_app(), CORS, routers, startup load
    config.py               XRAY_DATA_DIR, CORS_ORIGINS, ADMIN_TOKEN, PRODUCT_DIR = data/processed/product
    store.py                carga y cachea portfolio/companies/groups/manifest; reload(); lookup por id
    schemas.py              modelos Pydantic (Portfolio, PortfolioItem, CompanyDetail, TimelinePoint, Health, ImportJob)
    routers/
      health.py  portfolio.py  companies.py  groups.py  alerts.py  export.py  imports.py
    jobs.py                 cola simple en memoria + subprocess para /import
  tests/
    conftest.py             fixture: carpeta temporal con 3 empresas / 2 grupos escritos a mano con el esquema de §1
    test_portfolio.py  test_companies.py  test_health.py  test_import.py
  README.md                 cómo arrancar, variables, ejemplos curl
```

Instalar dependencias con el gestor de paquetes (`pip install -e backend` o `uv add`), **no** editando
`pyproject.toml` a mano; versiones publicadas hace ≥7 días. No añadir dependencias al `pyproject.toml`
raíz del pipeline. No modificar nada bajo `src/xray/` ni `scripts/` salvo un bug bloqueante, y en
ese caso avisar.

Los modelos Pydantic deben admitir campos extra (`model_config = ConfigDict(extra="allow")`): el
equipo de datos añadirá al portfolio/timeline campos como `coverage_state`,
`categorized_amount_share`, `recent_events`, `loc_utilization` sin avisar a la API.

## 4. `POST /import` (job de recálculo; entregar en último lugar)

Cuerpo: multipart con los CSV originales (mismos nombres que `data/raw/`: `companies.csv`,
`transactions.csv`, ...). Flujo:

1. Guardar en `data/uploads/{job_id}/raw/`.
2. Lanzar subproceso con `env XRAY_DATA_DIR=data/uploads/{job_id}` ejecutando en orden:
   `scripts/00_clean_data.py`, `scripts/01_build_monthly_features.py`,
   `scripts/05_compute_scores_v2.py predict --reference data/processed/scores_v2/_company_score_reference.json`,
   `scripts/08_build_product.py`.
   Usar `predict` con la referencia congelada del dataset principal: **no** volver a hacer `fit`
   con empresas nuevas (es el contrato para el test oculto).
3. Guardar `stdout/stderr` en `data/uploads/{job_id}/log.txt`; estado `queued|running|done|failed`.
4. Al terminar, el job **no** sustituye los artefactos principales: expone su carpeta y
   `GET /portfolio?dataset={job_id}` (y equivalentes) permiten consultarlos. Un solo job a la vez.

Si el tiempo aprieta, este endpoint se sustituye por documentación de cómo hacerlo a mano.

## 5. Tests mínimos (pytest, ejecutar con `python -m pytest -q -p no:asyncio backend/tests`)

- `/health` devuelve `latest_month` y `git_commit` del manifiesto de la fixture.
- `/portfolio` filtra por `trajectory`, ordena por `score` desc con `null` al final, pagina.
- `/companies/{id}` devuelve el JSON íntegro y 404 en id inexistente; `timeline?currency=XXX` → 400.
- `null` se preserva (una empresa `not_scored` de la fixture debe salir con `score: null`).
- `X-Xray-Manifest` presente y cambia tras `POST /reload` con manifiesto distinto.
- `/import` con un job simulado (monkeypatch del subproceso) pasa por `queued → done`.

## 6. Definición de hecho

- `uvicorn app.main:app --app-dir backend` arranca con los artefactos reales y responde en <100 ms a
  `/portfolio` y `/companies/{id}`.
- README con comandos y 5 ejemplos `curl`.
- Ningún cambio en `src/xray/`, `scripts/`, `data/processed/`.
- Commits solo de `backend/`; no hacer push sin petición.

## 7. Contexto para decisiones (leer si hay dudas)

- `docs/roadmap-tecnico-mvp.md` §1 y §3.1: arquitectura y rutas originales (este brief las concreta).
- `docs/decisiones.md` §13: qué significa cada campo del score V2; §14 y `docs/hallazgos-datos.md`:
  cambios de datos en curso que añadirán campos.
- `src/xray/product/bundle.py`: cómo se construyen exactamente los JSON.
- Convenciones del repo: español en docs/comentarios, código compacto, sin dependencias nuevas
  en el pipeline, sin imputar (nunca 0 ni 50 por falta de datos), publicación atómica con manifiesto.
