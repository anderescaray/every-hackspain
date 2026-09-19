# Estado actual del proyecto — punto de entrada para cualquier agente

**Fecha:** 19-09-2026, noche. **Rama:** `main` (`987c5c3` + cambios locales del what-if factorial pendientes de commit, ver §5).
Léelo entero antes de tocar nada: hoy han trabajado cuatro personas en paralelo sobre `main` y la mitad del tiempo se ha ido en reconciliar.

**Pre-deploy:** checklist rellenado en [`checklist-entrega.md`](./checklist-entrega.md) — gate **LISTO para iniciar deploy Vercel** (demo local verificada; E8/E9 y URL pública pendientes).

## 1. Qué es el producto

**Embat Pulse**: early warning y explicación de tesorería para CFOs y para Embat sobre su cartera (reto HackSpain X-Ray, `enunciado-embat.md`). Responde cinco preguntas: cómo está la empresa (Health Score), hacia dónde va (trayectoria, bache vs tendencia), por qué cambia (contribuciones exactas), de dónde viene su caja (Cash Truth) y qué pasaría bajo otras condiciones (simulador). Comprador: Embat como tier premium; usuario: CFO/tesorero.

## 2. Arquitectura vigente (decisión §21 de `decisiones.md`)

```
data/raw/*.csv
  │ 00 clean (xray.clean: flags D03–D30, D38 centinelas, F01–F07; nunca borra filas dudosas;
  │           sin cortes por tamaño: D01/D02 retiradas por D32)
  ▼
data/cleaned/*.parquet
  │ 01 features (xray.features; clasificación de movimientos = ledger canónico xray.ledger.classify;
  │              categorías AI D31 por defecto; coverage_state FE10; FX a EUR tipo fijo D32;
  │              primer mes parcial D33; fechas de pago de relleno = retraso no medible D39)
  ▼
data/processed/*_monthly_features.parquet
  │ 05 score V2 fit  (xray.score_v2 = financial_smoothed_v2: nivel 6m + momentum normalizado por
  │                   volatilidad propia + ajuste estacional + referencia congelada; también --panel group_currency)
  ▼
data/processed/scores_v2/
  │ 08 product (xray.product: change_narrative, confidence, cash_truth, bundle)
  │ 10 what-if (xray.product.whatif: 81 escenarios/empresa re-puntuados con la referencia congelada)
  ▼
data/processed/product/
  │ 09 export (xray.product.frontend_export → contrato JSON del frontend)
  ▼
frontend/public/generated/{portfolio.json, companies/*.json, groups/*.json}   (gitignored)
  │
  ▼  Next.js (frontend/): "/" Portfolio · /companies/[id] · /groups/[id]{,/network,/recommendations}
```

**Motor canónico del score: V2.** El motor alternativo **PulseFourPillars** (`xray.pulse`, de Pablo) se conserva como experimento con su propio exportador (`src/xray/product/pulse_frontend_export.py`, `scripts/09b_export_frontend_pulse.py`); **no alimenta el frontend**. Motivo medido: 16 empresas con Health frente a 977–1.011 con V2, 1 mes de historia frente a 24 (tabla en §21). Su **ledger** sí es canónico y ya alimenta features y Cash Truth.

El backend FastAPI (`backend/`, solo lectura sobre `product/`) existe pero el frontend no lo usa: lee JSON estáticos. Ver `brief-backend-api.md`.

## 3. Cifras reales del último run (agosto 2026)

- 1.286 empresas, 250 grupos, 24 meses (2024-09 → 2026-08).
- V2: **1.011 puntuadas** (284 `scored`, 727 `provisional`, tras D39), 275 `not_scored`. Prefijo 2026-02 invariante en features y scores. D39 bajó a las 107 empresas con fechas de pago de relleno (mediana −2,5 en agosto) y apenas movió al resto.
- Exportación: 1.161 fichas de empresa (125 sin ningún score no se exportan; la UI dice "no disponible"), 250 grupos, portfolio de 1.286, escenarios para las 1.011 puntuadas.
- Tests: **566 Python pasan** + **67 frontend**; lint y typecheck limpios. Único rojo conocido: `tests/test_pulse_pipeline.py::test_currency_runs_do_not_overwrite_or_mix` — falla igual en `origin/main` desde el D32 de Ander; es de Pablo/Ander. En Windows (entorno uv, pandas 3.0.6) además: los tests de publicación de Pulse (`fcntl` no existe en Windows; symlinks sin privilegios) y `tests/test_frontend_export.py::test_evidence_refs_resolve_and_absent_blocks_are_explicit` (una descripción vacía se exporta como `"nan"` en vez de `"Sin concepto"`; falla igual en `origin/main`).

## 4. Comandos

```bash
# Suites
python3 -m pytest -q -p no:asyncio                 # -p no:asyncio evita un plugin global de la máquina de Camilo
cd frontend && npm ci && npm test && npm run lint && npm run typecheck

# Pipeline completo (~45 min; el what-if son ~30 de ellos)
python3 -X utf8 scripts/00_clean_data.py
python3 -X utf8 scripts/01_build_monthly_features.py             # D31 por defecto; --no-ai-categories para solo banco
python3 -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
python3 -X utf8 scripts/05_compute_scores_v2.py fit
python3 -X utf8 scripts/05_compute_scores_v2.py fit --panel group_currency   # lo exige el advisor de Ander
python3 -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python3 -X utf8 scripts/08_build_product.py
python3 -X utf8 scripts/10_build_whatif.py                       # opcional; sin él el simulador dice "sin escenarios"
python3 -X utf8 scripts/09_export_frontend.py

# Validar los JSON con el contrato del frontend
cd frontend && npm run validate:generated && npm run validate:generated -- --groups && npm run validate:generated -- --portfolio

# Demo local
cd frontend && npm run dev -- --port 3111      # http://localhost:3111/
```

Empresas útiles para la demo: `COMP_0764` (historia larga, simulador), `COMP_0001` (estable), `COMP_0647` (apoyo intragrupo dominante), `COMP_0045` (banco extranjero corregido por D31), `GROUP_0250`.

## 5. Trabajo en curso / sin commitear en la máquina de Camilo

- **What-if factorial (FE-05)**: `whatif.py` pasa de 21 escenarios «una palanca cada vez» a **81** (3 posiciones por palanca) para que cualquier combinación de sliders tenga resultado; `frontend_export._simulation` desglosa combinaciones; etiqueta «del apoyo actual» → «del nivel actual» en `WhatIfSection.tsx`. Tests verdes. `scripts/10_build_whatif.py` estaba ejecutándose (~30 min) y después hay que correr `09` y validar. Cambios staged, pendiente commit + push.

## 6. Pendiente por prioridad

**A · Para poder presentar**
1. Despliegue público (Vercel): el build debe ejecutar `09` o montar `COMPANY_ANALYSIS_DIR` / `GROUP_ANALYSIS_DIR` / `PORTFOLIO_ANALYSIS_FILE`. `public/` es público: solo agregados anonimizados (ya lo son).
2. Congelar `main` para la demo; todo por PR con suite verde y regeneración.
3. Formato del leaderboard con Embat; `scores_v2/company_latest_scores.csv` es candidato. `predict --reference` ya existe para el test oculto; **falta el fallback por signo** para bancos cuyas plantillas no vio D31 (`hallazgos-datos.md` §11.5).

**B · Bonus del enunciado**
4. Alertas + `lead_time.json` medido contra eventos discretos (`event_type` D30: cuota impagada, embargo…). Rellenan `alerts[]` de la ficha y una columna en Portfolio sin tocar componentes.
5. `coverage_state` dentro del momentum de V2 (deltas solo entre meses `ok`), más allá del `provisional` actual.

**C · Si sobra tiempo**
6. Time Borrowed AP (alerta de nicho), relaciones/recomendaciones de grupo (el advisor de Ander, `xray.group_advisor`, ya produce planes; falta mapearlos al contrato de grupo), `account_flows` en Cash Truth, Import UI.

**Pendiente de la revisión de EDA (cambian puntuaciones; para el rediseño del score):** F · amortizaciones anticipadas (14,8% del servicio de deuda, 68 empresas) y depósitos a plazo fuera del servicio de deuda; B2 · cuentas sin movimientos y saldo 0 como caja fiable (+245 empresas con caja para el advisor); I3 · señal de facturas vencidas recientes (el retraso de las pagadas no ve lo que no se cobra); recuperar la fecha real de pago casando factura y banco (D39 opción B). Detalle en `decisiones.md` D32–D40.

**Deuda técnica**: `stress_events` duplica `event_type`; fusionar los `Noul` de D31 en `event_type`; D26–D28 aún no excluyen `tx_cash_*`; la pasarela (D29) ya sale del servicio de deuda en el ledger (regla CT02: 5.012 movimientos Stripe/network pasan a operativos); Confidence y umbral 0,7 sin calibrar; `dimensions` del contrato 2.0 no admite `null` (exportamos neutro + `provisional`; Pablo lo resolvió en su 3.0, portarlo requiere tocar componentes de Álvaro).

## 7. Mapa de documentos

| Documento | Para qué |
|---|---|
| **`checklist-entrega.md`** | **Checklist pre-deploy:** enunciado E1–E9, UI, pipeline, paseo demo y gate Vercel. Rellenar antes de desplegar |
| `decisiones.md` | Registro central. §1–§9 datos y limpieza; §10 V1; §13 V2; §14 anotaciones D25–D30; FE10 cobertura; §15 D31 Jev; §16 producto/API; §17 encaje D25–D31; §18 D31 default; §19 frontend (FE-01…FE-05); §20 advisor de grupo (Ander); **§21 motor canónico V2 + ledger** |
| `hallazgos-datos.md` | Análisis de datos que justifica todo lo anterior (onboarding, ruido blanco, estacionalidad, taxonomía 2025-01, 39 % sin categoría, pólizas, overdue como higiene ERP) |
| `roadmap-tecnico-mvp.md` | Estado consolidado y plan A/B/C |
| `frontend-data-contract.md` | Contrato JSON 2.0 (empresa) / 1.0 (grupo) que consume el frontend; `frontend/types/portfolio.ts` para la cartera |
| `frontend/AGENTS.md` | Reglas del frontend (Álvaro): no calcular, `null` ≠ 0, fixtures aisladas, cómo probar |
| `scoring-v2.md`, `feature-engineering.md`, `validation.md` | Detalle técnico de V2, features y validación |
| `jev-categorias.md` | D31: categorías AI, cómo se generó el artefacto, qué no hacer |
| `group-optimization.md` | Advisor de grupo de Ander |
| `pulse-four-pillars-v1-implementation.md`, `pulse-frontend-integration.md` | Motor Pulse (experimento) |
| `brief-backend-api.md` | API FastAPI (no usada por el frontend) |

## 8. Reglas que nadie debe romper

- Nunca imputar: sin dato → `null`, nunca 0 ni 50. El frontend no calcula.
- Nada mira el futuro: cada valor en el mes t usa solo datos ≤ t; los tests de prefijo (`--check-prefix`) lo comprueban. Si añades una feature, añade su test de prefijo.
- `data/raw` es inmutable; `cleaned` marca, `features` decide.
- Referencia V2 congelada: para empresas nuevas `predict --reference`, jamás `fit` con ellas.
- Categoría de refund por **signo**, no por nombre (taxonomía del banco cambia en 2025-01).
- No commitear JSON generados ni datos; no push sin suite verde.
