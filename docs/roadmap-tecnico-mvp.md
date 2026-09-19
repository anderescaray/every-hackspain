# Roadmap técnico — Embat Pulse MVP

> **Estado 19-09-2026 (noche):** F0, F1, F2 y backend hechos y en `origin/main`; pendientes F3 (alertas + lead time), F4 (Time Borrowed), F5 (what-if), F6 (import UI/deploy) y el frontend. Decisiones tomadas en `decisiones.md` §16.

> Traduce `embat_pulse_mvp_propuesta_final.md` a módulos de código, partiendo de lo que **ya existe** en `src/xray/`. Cada bloque dice: qué hay, qué falta, dónde va, contrato de entrada/salida, tests mínimos y orden. Cifras de cobertura medidas el 19-09-2026 sobre `data/cleaned/` (ver §0).

---

## Estado consolidado y plan (19-09-2026, noche) — ver también `ESTADO-ACTUAL.md`

**Producto:** Embat Pulse — early warning y explicación de tesorería. Responde: cómo está la empresa (Health), hacia dónde va (Momentum/trayectoria, bache vs tendencia), por qué cambia (contribuciones exactas), de dónde viene la caja (Cash Truth) y quién financia a quién (Time Borrowed). Comprador: Embat como tier premium sobre su cartera; usuario: CFO/tesorero.

### Capas y estado

| Capa | Estado | Referencia |
|---|---|---|
| Datos: clean + features | Hecho. Anotaciones D25–D30, `coverage_state` FE10, categorías AI D31 (**default del CLI desde este cierre**) | decisiones §14, FE10, §15, §17 |
| Pulse Score V2 (**canónico**, decisiones §21) | Hecho. Nivel 6m, momentum normalizado por volatilidad propia, episodio bache/tendencia, ajuste estacional del crecimiento, `provisional` por cobertura | `scoring-v2.md`, decisiones §13 |
| Explicación + Confidence | Hecho (F1) | decisiones §16 PR-03/04 |
| Cash Truth + dependencia de apoyo | Hecho (F2) | decisiones §16 PR-05/06 |
| API FastAPI (solo lectura, `/import` con referencia congelada) | Hecho | `brief-backend-api.md`, `backend/` |
| Frontend | Portfolio `/` + Company Detail + Grupo, con datos reales vía `scripts/09_export_frontend.py` y simulador con 81 escenarios (decisiones §19 FE-01…FE-05). Falta despliegue | `frontend/`, `frontend-data-contract.md` |
| Alertas + lead time (bonus del enunciado) | Solo diseño | `alerts-and-monitoring.md` |
| Time Borrowed | Medido, no implementado (nicho: 4 empresas AR, 130 AP) | `patron-tiempo-prestado.md` |
| What-if, despliegue público | No existen | — |

### Contra los requisitos del enunciado

| Requisito | Estado |
|---|---|
| Predicción sobre test oculto | Mecánica lista (`predict --reference`, `/import`). Falta formato del leaderboard y fallback por signo para plantillas no vistas |
| Dos direcciones · trayectoria · explicación | Cumplidos (V2 + change_narrative) |
| Producto encima + comprador | Cash Truth, Confidence, API; Embat |
| Demo navegable | En local sí (`npm run dev`); **sin URL pública** |
| Anticipación medida (bonus) | No: hay anclas discretas (`event_type`) pero falta `lead_time.json` |
| Monitor que avisa (bonus) | No |

### Plan por bloques

**A · Imprescindible para presentar**
1. ~~Integrar Company Detail~~ ~~Portfolio~~ (hechos, §19 FE-01/FE-03) · desplegar con los JSON exportados (Vercel + `COMPANY_ANALYSIS_DIR` o build que ejecute `09`).
2. D31 default + reajuste de la referencia V2 + regeneración `processed`/`scores_v2`/`product` (decisiones §18).
3. Fallback por signo residual + `categorized_amount_share` (test oculto con bancos sin plantilla conocida).

**B · Diferencial**
4. Alertas (F3) sobre `event_type` + Noul + `support_dependency_ratio` + cambio de trayectoria; `lead_time.json` medido contra eventos discretos. Cubre los dos bonus.
5. `coverage_state` en el momentum de V2 (deltas solo entre meses `ok`).

**C · Si queda tiempo**
6. Time Borrowed AP como alerta de nicho; what-if; Import UI.

**Deuda técnica conocida:** `stress_events` duplica `event_type`; D26–D28 aún no excluyen `tx_cash_*`; D29 no excluye pasarela de `interest_charge`; Confidence y umbral 0,7 sin calibrar.

---

## 0. Inventario: propuesta vs. código

| Pieza del MVP (MUST) | Estado | Dónde está / dónde irá |
|---|---|---|
| Cleaning + Features | **Hecho** | `xray.clean`, `xray.features` → `data/cleaned/`, `data/processed/*.parquet` |
| Pulse Score / Health / Momentum / Stability | **Hecho (V2)** | `xray.score_v2` → `data/processed/scores_v2/company_monthly_scores.parquet` (`score`, `level`, `momentum`, `stability`, `trajectory`, `episode`, `score_status`, `score_reason`, `delta_vs_prev`) |
| Explanations (contribuciones exactas) | **Hecho** | `scores_v2/company_score_explanations.parquet` (`layer`, `feature`, `value`, `feature_score`, `effective_weight`, `final_contribution`, `definition`) |
| Confidence | **Parcial** | Existen `level_coverage`, `component_mask`, `score_status`, `has_sufficient_history`, `has_partial_currency_coverage`. Falta un campo único 0–100 con desglose |
| "Why is Pulse changing" (deltas mes a mes) | **No existe** | Nuevo `xray.product.change_narrative` |
| Cash Truth | **Cimientos** | Flags `is_internal_transfer` (D04), `is_intragroup` (D05) en `cleaned/transactions.parquet`; agregados mensuales `tx_internal_amount`, `tx_intragroup_amount`, `tx_uncategorized_amount`, `tx_inflow/outflow`, `tx_debt_*`. Falta el artefacto por empresa-mes con buckets y el flag de dependencia |
| Time Borrowed | **No existe** | Solo hay retraso D (`inv_ar/ap_delay_median`) a nivel empresa-mes. Falta L, A y la comparación por relación (`company_id`, `counterparty_id`) |
| Alerts | **Solo diseño** | `docs/alerts-and-monitoring.md`. Nuevo `xray.product.alerts` |
| What-if | **No existe** | Nuevo `xray.product.whatif`, reutilizando `score_v2.score_panel` con referencia congelada |
| Evidence drill-down | **No existe** | Índices `company_id → transaction_id[] / operation_id[]` por bucket y por relación |
| Import CSV (pantalla 0) | **Parcial** | Pipeline por scripts; falta job asíncrono + `XRAY_DATA_DIR` por upload |
| Portfolio / Company Detail (UI) | **No existe** | `backend/` (FastAPI) + `frontend/` (Next.js) |
| Vista grupo (SHOULD) | **Cimientos** | Panel `group_currency` ya se puntúa; `tx_intragroup_amount` con signo por empresa da emisor/receptor |

Cobertura medida (base para decidir qué se enseña):

- Apoyo intragrupo D05: 949 empresas con algún movimiento, **540 con ≥5% de su importe**; 477 receptoras netas / 469 emisoras netas.
- Circulación propia D04: 637 empresas, 275 con ≥5%.
- Sin categoría (`uncategorized`): **35% del importe total**, mediana 12% por empresa. Es el bucket mayor: se muestra como "incierto".
- Facturas: 785 de 1.286 empresas. Relaciones comparables (≥10 facturas pagadas, ≥6 meses, plazo real): AR 2.069 en 264 empresas; AP 4.184 en 418 empresas. Caso "puntualidad mejora pero tiempo-a-caja empeora": 6 relaciones / 4 empresas (AR); inverso AP: 27 / 21. Proveedores acortando ventana ≥15 d: 324 relaciones / 130 empresas.

Conclusión de alcance: **Cash Truth es señal de cobertura amplia; Time Borrowed es alerta de nicho**. El orden de implementación de la propuesta (Cash Truth antes que Time Borrowed) queda validado.

---

## 1. Arquitectura objetivo

```
data/raw/*.csv
   │  xray.clean                        (existe)
   ▼
data/cleaned/*.parquet
   │  xray.features                     (existe)
   ▼
data/processed/*_monthly_features.parquet
   │  xray.score_v2                     (existe)
   ▼
data/processed/scores_v2/*
   │
   │  xray.product  ← NUEVO paquete, solo lee capas anteriores, nunca las modifica
   │    cash_truth.py        → product/cash_truth.parquet          (empresa-moneda-mes × bucket)
   │    time_borrowed.py     → product/time_borrowed.parquet       (empresa × contraparte × ventana)
   │    change_narrative.py  → product/score_changes.parquet       (empresa-mes: top-k deltas de contribución)
   │    confidence.py        → product/confidence.parquet          (empresa-mes: 0–100 + desglose)
   │    alerts.py            → product/alerts.parquet + alerts.json
   │    evidence.py          → product/evidence/*.parquet          (índices id → filas fuente)
   │    whatif.py            → sin artefacto; función pura usada por el backend
   │    bundle.py            → product/portfolio.json, product/companies/{id}.json (lo que sirve el backend)
   ▼
backend/   FastAPI, sirve JSON precomputado + POST /whatif + POST /import (job)
frontend/  Next.js; Portfolio · Company Detail · Alerts · Group (lite) · Import
```

Reglas que heredan de `xray` y se aplican a `xray.product`:

1. **Sin futuro**: cualquier valor en el mes `t` se calcula solo con datos `≤ t`. Test de prefijo obligatorio (recalcular con datos hasta `2026-02-01` reproduce exactamente las filas anteriores), igual que `06_validate_scores_v2.py --check-prefix`.
2. **Sin imputar**: cobertura insuficiente → `NaN` + motivo, nunca 0 ni 50.
3. **Publicación atómica**: usar `xray.artifacts.publish_bundle` + manifiesto con hashes de entrada, como hace `score_v2.pipeline.run`.
4. **El LLM no calcula**: el frontend renderiza JSON; el texto narrativo se genera por plantillas en Python (LLM opcional, después).
5. **V1 no se toca**; el producto consume V2 (`METHOD = financial_smoothed_v2`).

---

## 2. Módulos nuevos — contrato y algoritmo

### 2.1 `xray/product/cash_truth.py`

**Entrada**: `cleaned/transactions.parquet` (`status == booked`, flags D04/D05, `category`, `amount`, `currency`, `date`, `transaction_id`), `cleaned/companies.parquet` (`group_id`).

**Buckets** (orden de prioridad; un movimiento cae en el primero que cumpla):

| Bucket | Regla |
|---|---|
| `own_circulation` | `is_internal_transfer` |
| `group_support` | `is_intragroup` |
| `financing_investment` | `category ∈ {debt_repayment, interest_charge, investment_deployment, investment_return}` |
| `operations` | `category ∈ INFLOW ∪ OUTFLOW` de `features/transactions.py` (misma lista, importarla, no duplicarla) |
| `unpaired_transfer` | `category == transfer` sin espejo |
| `uncertain` | `category == uncategorized` o resto |

**Salida** `product/cash_truth.parquet`, clave `(company_id, currency, month, bucket)`: `amount_in`, `amount_out`, `amount_abs`, `n_tx`, `share_abs` (sobre el total abs del mes). Más una tabla resumen por empresa-moneda-mes con:

- `group_support_net` = entradas − salidas intragrupo (positivo = receptora).
- `support_dependency_ratio` = `group_support_net_in / (operations_in + group_support_net_in)` sobre ventana 6 m (mín. 3 meses con calidad; usar `month_quality_ok` del panel de features). `NaN` si no hay soporte.
- `support_dependency_trend` = ratio ventana reciente − ventana anterior (mismo esquema trimestre vs trimestre de V2).
- `uncertain_share_6m`: para Confidence.

**Evidence**: `product/evidence/cash_truth_tx.parquet` con `(company_id, month, bucket, transaction_id)`; el backend pagina por ahí.

**Tests**: (a) espejo D04 no cuenta como operación ni como apoyo; (b) un par intragrupo suma +X en receptora y −X en emisora, neto de grupo 0; (c) prefijo temporal; (d) suma de `share_abs` por mes = 1.

### 2.2 `xray/product/time_borrowed.py`

**Entrada**: `cleaned/invoices.parquet` con filtros: `document_type == invoice`, `~is_ambiguous_document`, `~is_possible_duplicate`, `~has_anomalous_term`, y para A/D además `status == paid`, `payment_date` no nulo, `~is_payment_before_issuance`, `~is_future_payment`. (F04 ya anula `payment_date` en no pagadas: no hay que repetirlo.)

**Relojes por factura**: `L = due − issuance`, `A = payment − issuance`, `D = payment − due` (días).

**Ventanas por relación** `(company_id, counterparty_id, direction)`: dos ventanas móviles de 6 meses por `issuance_date` (reciente vs anterior), evaluadas cada mes `t`. Condición de comparabilidad: ≥5 facturas pagadas en **cada** ventana y `L > 0` en ≥50% de ellas (si no, la relación es "al contado" y L no significa plazo). Estadístico: mediana ponderada por importe.

**Salida** `product/time_borrowed.parquet`, clave `(company_id, counterparty_id, direction, month)`: `L_prev, L_recent, A_prev, A_recent, D_prev, D_recent, dL, dA, dD, n_prev, n_recent, amount_recent, comparable (bool)`, y `pattern`:

| `pattern` | Regla (AR) | Regla (AP, espejo) |
|---|---|---|
| `terms_extended_time_to_cash_up` | `dL ≥ 15 ∧ dA ≥ 10` | — |
| `punctuality_masks_slower_cash` | `dD ≤ −5 ∧ dA ≥ 10` | `dD ≥ 5 ∧ dA ≤ −10` |
| `supplier_window_compressed` | — | `dL ≤ −15` |
| `supplier_window_extended` | — | `dL ≥ 15` |
| `none` | resto | resto |

Agregado empresa-mes (para Company Detail y Confidence): `ar_time_to_cash_recent`, `ar_time_to_cash_prev`, `ap_payment_window_recent/prev`, ponderados por importe sobre relaciones comparables; `n_comparable_ar`, `n_comparable_ap`.

**Evidence**: `product/evidence/time_borrowed_inv.parquet` con `(company_id, counterparty_id, month, window, operation_id)`.

**Tests**: (a) el ejemplo del documento (62→102 plazo, 20→0 retraso) produce `punctuality_masks_slower_cash`; (b) relación al contado (L=0) no es comparable; (c) facturas no pagadas no entran en A/D; (d) prefijo temporal.

### 2.3 `xray/product/change_narrative.py` — "Why is Pulse changing"

**Entrada**: `scores_v2/company_monthly_scores.parquet` + `company_score_explanations.parquet`.

**Algoritmo**: para cada empresa-mes con score y mes natural anterior con score, join de contribuciones por `(layer, feature)`; `delta_contribution = final_contribution_t − final_contribution_{t−1}`. Separar tres causas por término, como pide `explainability.md`:

- `value_effect`: cambio del valor financiero con peso constante (`Δfeature_score × w_{t−1}`).
- `weight_effect`: cambio de peso efectivo/disponibilidad (`feature_score_t × Δw`); si el término aparece o desaparece va íntegro aquí y se marca `component_set_changed`.
- `reference_effect`: residuo cuando `reference_effective_from` cambia.

**Salida** `product/score_changes.parquet`: `(company_id, currency, month, rank, feature, layer, delta_contribution, value_effect, weight_effect, value_prev, value_now, sentence)`. `sentence` por plantilla, p. ej. `"Generación operativa: margen 6m 0,08 → 0,03 (−6 puntos)"`. Top-3 por `|delta_contribution|`; el resto agregado en `other`.

**Tests**: suma de deltas = `delta_vs_prev` (tolerancia numérica); un término que aparece de la nada va a `weight_effect`.

### 2.4 `xray/product/confidence.py`

**Salida** `product/confidence.parquet`, empresa-moneda-mes: `confidence` 0–100 y desglose. Media ponderada de sub-puntuaciones, cada una 0–100, todas ya disponibles:

| Sub-score | Fuente | Peso |
|---|---|---:|
| Historia | `level_months` / 6, `has_sufficient_history` | 25 |
| Cobertura del score | `level_coverage`, `component_mask` | 25 |
| Calidad del mes | `month_quality_ok`, `tx_all_currency_count` | 15 |
| Certeza de caja | `1 − uncertain_share_6m` (Cash Truth) | 20 |
| ERP / relaciones | ERP presente, `n_comparable_ar + n_comparable_ap` | 15 |

Regla de UI: `confidence < 40` → mostrar score como "provisional" y ocultar dirección. Documentar que **no es probabilidad de acierto**.

### 2.5 `xray/product/alerts.py`

**Entrada**: scores V2, `cash_truth`, `time_borrowed`, `score_changes`, `confidence`.

**Tipos MVP** (subconjunto de `alerts-and-monitoring.md` adaptado a V2, que ya trae la confirmación bache/tendencia):

| Código | Disparador (todo en `t`, sin mirar `t+1`) | Severidad |
|---|---|---|
| `TREND_DETERIORATION` | `episode == trend_deterioration` y primer mes con esa etiqueta (o cada 3 meses si persiste) | high |
| `TREND_IMPROVEMENT` | `episode == trend_improvement`, idem | info |
| `EMERGING_DETERIORATION` | `trajectory == emerging_deteriorating` dos meses seguidos | medium |
| `ONE_OFF_DIP` | `episode == one_off_dip` | low (no en feed principal; visible en ficha) |
| `SUPPORT_DEPENDENCY_UP` | `support_dependency_ratio ≥ 0,3 ∧ support_dependency_trend ≥ 0,1` | high |
| `CUSTOMER_TERMS_EXTENDED` | alguna relación AR `pattern ∈ {terms_extended_time_to_cash_up, punctuality_masks_slower_cash}` con `amount_recent` en el top-5 de clientes | medium |
| `SUPPLIER_WINDOW_COMPRESSED` | relaciones AP `supplier_window_compressed` que suman ≥20% del AP reciente | medium |
| `LOW_CONFIDENCE` | `confidence < 40` con score publicado | info |

Cada alerta lleva `drivers` (del `change_narrative`), `evidence_ref` (bucket/relación/ids) y `first_seen_month`. Deduplicación: una alerta abierta por `(company_id, type)`; se cierra cuando la condición deja de cumplirse.

**Salida**: `product/alerts.parquet` + `product/alerts.json` (esquema del doc de alertas).

**Anticipación medida (bonus, barato)**: reutilizar `xray.evaluation.compare` (ya calcula inicios de episodio y lead time contra proxies). Publicar en `product/lead_time.json` el histograma de meses entre `first_seen_month` de `TREND_/EMERGING_DETERIORATION` y el inicio de episodio del proxy, con la advertencia de SC11 (falsas alarmas ≈75%). No prometer "3 meses"; mostrar la distribución.

### 2.6 `xray/product/whatif.py`

**Enfoque**: no reimplementar el score. Tomar el panel de features de la empresa, aplicar el escenario a las columnas fuente de V2 en los meses de la ventana reciente, y llamar a `score_v2.score_panel(panel_modificado, referencia_congelada)`. Comparar `score`, `level`, `momentum`, contribuciones.

**Escenarios MVP** (mecánicos, sobre columnas existentes):

| Escenario | Columnas afectadas |
|---|---|
| `customer_terms_days: −15` | `inv_ar_delay_median` (y su conteo), `inv_dso_median` |
| `collections_days: −10` | idem |
| `supplier_window_days: +15` | `inv_ap_delay_median`, `inv_dpo_median` |
| `operating_inflow_pct: +5` | `tx_inflow`, `tx_net_cashflow`, derivados |
| `group_support_pct: −50` | no toca el score V2 (excluye intragrupo); solo recalcula `support_dependency_ratio` |

Salida: JSON `{baseline, scenario, delta, changed_terms[]}`. Texto fijo en UI: *"Resultado mecánico bajo este escenario; no es una predicción."*

**Tests**: escenario nulo reproduce el score exacto; escenario solo afecta a meses de la ventana; no puede modificar meses futuros.

### 2.7 `xray/product/bundle.py`

Compone lo que el backend sirve sin cómputo en caliente:

- `product/portfolio.json`: una fila por empresa (último mes con score): `score, level, momentum, stability, trajectory, episode, confidence, main_signal` (feature top-1 de `score_changes`), `n_alerts_open`, `group_id`, `has_erp`, `score_status`.
- `product/companies/{company_id}.json`: timeline 24 m (score/level/momentum/stability/episode), `score_changes` del último mes, `cash_truth` (últimos 6 m por bucket + dependency), `time_borrowed` (agregado + top relaciones), `alerts`, `confidence` desglosada.
- `product/groups/{group_id}.json`: filiales con score + `group_support_net` + score del panel `group_currency`.
- `product/demo_cases.json`: ids elegidos para la demo (ver §4).

Script de entrada: `scripts/08_build_product.py` (ejecuta 2.1–2.5 y 2.7, publica con manifiesto).

---

## 3. Backend y frontend

### 3.1 `backend/` (FastAPI)

| Método | Ruta | Fuente |
|---|---|---|
| GET | `/portfolio` | `portfolio.json` |
| GET | `/companies/{id}` | `companies/{id}.json` |
| GET | `/companies/{id}/evidence?kind=cash_truth&bucket=&month=` | `evidence/*.parquet` (paginado) |
| GET | `/companies/{id}/evidence?kind=time_borrowed&counterparty=` | idem |
| GET | `/groups/{id}` | `groups/{id}.json` |
| GET | `/alerts?severity=&type=&limit=` | `alerts.json` |
| POST | `/companies/{id}/whatif` | `whatif.simulate()` en caliente (una empresa, <1 s) |
| POST | `/import` | guarda CSV en `data/uploads/{job}/raw/`, lanza subproceso con `XRAY_DATA_DIR`; devuelve `job_id` |
| GET | `/import/{job_id}` | estado + log |
| GET | `/health` | — |

Sin base de datos: filesystem + JSON. `XRAY_DATA_DIR` ya permite apuntar a un dataset alternativo (`xray/paths.py`), así que Import reutiliza el pipeline tal cual.

### 3.2 `frontend/` (Next.js + Tailwind + Recharts)

Pantallas en orden de valor para la demo: **Company Detail → Portfolio → Alerts → Group → Import**. El front arranca con fixtures copiadas de `product/` para no bloquearse por el backend.

### 3.3 Despliegue

Frontend en Vercel; backend en Railway/Render con `data/processed/product/` empaquetado en la imagen (sin los CSV crudos; `product/` cabe en decenas de MB). Import en producción desactivado o limitado a un CSV pequeño de una empresa; la demo usa el dataset preprocesado.

---

## 4. Orden de implementación y paralelización

| Fase | Tareas | Depende de | Paralelizable con |
|---|---|---|---|
| **F0** ✅ | Pipeline reproducible con el fix de fechas (`io.py`); V2 calculado en `scores_v2/` | — | — |
| **F1** ✅ | 2.3 change_narrative · 2.4 confidence · 2.7 bundle · `scripts/08` (commit `40c30da`) | F0 | Front con fixtures (Company Detail, Portfolio) |
| **Backend** ✅ | `backend/` FastAPI según `brief-backend-api.md`, incl. `/import` (commit `366093f`) | F1 | — |
| **F2** ✅ | 2.1 cash_truth + evidence, integrado en bundle y portfolio (commit `5c91af7`) | F0 | F1 |
| **F3** | 2.5 alerts (tipos de score + `SUPPORT_DEPENDENCY_UP`) · lead_time.json | F1, F2 | Backend GET |
| **F4** | 2.2 time_borrowed + evidence + alertas AR/AP | F0 | F3 |
| **F5** | 2.6 whatif + `POST /whatif` | F1 | UI Alerts/Group |
| **F6** | Import job · despliegue · `demo_cases.json` · ensayo | todo | — |

Si el tiempo aprieta: **F4 se recorta a "solo agregado empresa-mes + 2 casos de demo"** y F6 Import se sustituye por "usar dataset precargado". F1–F3 son irrenunciables.

### Casos de demo candidatos (medidos)

- Apoyo intragrupo dominante: `COMP_0647` (1.246 movs, 95% del importe, receptora neta), `COMP_1225`, `COMP_0586`.
- Circulación propia alta: `COMP_0855` (56%), `COMP_1152`, `COMP_0957`.
- Time Borrowed AR ("puntualidad mejora, caja más lenta"): `COMP_1191` / `COUNTERPARTY_48964` (plazo 76→139, retraso 0→−90, tiempo a caja 30→52, 347 k€).
- Time Borrowed AP (ventana comprimida): `COMP_0149` / `COUNTERPARTY_106430` (60→30 días, 50 M€).
- Bache vs tendencia: elegir de `scores_v2/company_score_examples.json` (`one_off_dip` y `trend_deterioration` en agosto 2026).

Confirmar cada caso con score V2 publicado y `confidence ≥ 60` antes de fijarlo.

---

## 5. Definición de hecho

- `python -X utf8 scripts/08_build_product.py` genera `data/processed/product/` con manifiesto y pasa `--check-prefix 2026-02-01`.
- `pytest -q` verde con los tests nuevos de §2 (mínimo 2–4 por módulo).
- `uvicorn backend.main:app` responde en `/portfolio`, `/companies/{id}`, `/alerts`, `/whatif`.
- URL pública abre en incógnito y recorre los 4 momentos de la demo sin consola de errores.
- `docs/decisiones.md` con una entrada nueva (§14) que registre buckets de Cash Truth, umbrales de Time Borrowed y reglas de alerta como decisiones, con sus límites.

---

## 6. Riesgos técnicos concretos

| Riesgo | Mitigación |
|---|---|
| 31% de empresas sin score en el último mes (V2: 922/1.286 en agosto) | Portfolio muestra `not_scored` con motivo, nunca las oculta; Confidence lo hace visible |
| Bucket `uncertain` = 35% del importe | Mostrarlo siempre; la narrativa dice "no identificable con suficiente confianza" |
| Time Borrowed con 4 empresas en el caso estrella AR | Presentarlo como alerta de nicho; el lado AP (130 empresas) es el que se generaliza |
| What-if que toque columnas que V2 no usa | `whatif.py` valida contra la allowlist de señales de `ScoreV2Config`; escenario sin efecto devuelve `delta = 0` explícito |
| Import en vivo tarda minutos | Job asíncrono con estado; demo con dataset precargado |
| Fuga de futuro en ventanas móviles nuevas | Test de prefijo obligatorio en `cash_truth`, `time_borrowed`, `alerts` |
