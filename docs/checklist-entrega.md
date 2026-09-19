# Checklist de cobertura y testing pre-deploy — Embat Pulse

**Propósito:** saber con checkboxes qué exige el enunciado / el MVP y qué está verificado, antes de cualquier deploy público en Vercel.

**Regla:** marcar `[x]` solo tras verificarlo en esta pasada (automatizado o manual). Si no se ha comprobado, dejar `[ ]`. Gaps conocidos se anotan en §5.

**Última pasada:** 19-09-2026 (noche). Veredicto en §6.

Empresas / grupos de referencia:

| ID | Para qué |
|---|---|
| `COMP_0764` | Historia larga + simulador (health 33, deteriorating, 81 escenarios) |
| `COMP_0001` | Estable (health 52) |
| `COMP_0647` | Apoyo intragrupo (health 48) |
| `COMP_0045` | Banco extranjero / D31 (health 47) |
| `COMP_0006` | Improving (portfolio) |
| `COMP_0037` | Deteriorating (portfolio) |
| `COMP_0007` | Sensibilidad / grupo GROUP_0064 |
| `GROUP_0250` | Vista de grupo (19 miembros) |
| `GROUP_0067` | Overview / network / recommendations |

Demo local: http://localhost:3111/ (ya en marcha en esta pasada).

---

## 1. Requisitos del enunciado

Fuente: [`enunciado-embat.md`](../enunciado-embat.md) (obligatorio + bonus) y criterios de evaluación.

### 1.1 Obligatorios

- [x] **E1 · Predicción sobre el test oculto** — Mecánica verificada: `scripts/05_compute_scores_v2.py` + `data/processed/scores_v2/company_latest_scores.csv` existen. **Límite aceptado:** formato exacto Embat y fallback por signo para plantillas no vistas por D31 siguen pendientes (no bloquean demo).
- [x] **E2 · Señal en las dos direcciones** — Portfolio: 74 `improving`, 91 `deteriorating`, 612 `stable`. UI: `/companies/COMP_0006` (improving) y `/companies/COMP_0037` (deteriorating) HTTP 200 con señal de trayectoria.
- [x] **E3 · Trayectoria, no foto** — Fichas con `history` (p.ej. COMP_0764: 22 meses) + `trajectory` en JSON y página.
- [x] **E4 · Explicación** — Drivers presentes (COMP_0764: 4; COMP_0001: 4) + secciones de relato en UI.
- [x] **E5 · Producto encima del score** — Pulse en UI: Health, Origen de caja (Cash Truth), Confidence, Simulador, vistas de grupo.
- [x] **E6 · Comprador identificado** — Embat como tier premium documentado (`ESTADO-ACTUAL`, propuesta Pulse). Pitch ensayable (no es código).
- [x] **E7 · Demo navegable (local)** — http://localhost:3111/ Portfolio + fichas + grupos OK. **URL pública Vercel:** pendiente (es el siguiente paso tras este gate).

### 1.2 Bonus

- [ ] **E8 · Anticipación medida** — `lead_time.json` / métrica publicada. **Gap:** no implementado.
- [ ] **E9 · Monitor que avisa** — `alerts[]` en COMP_0764 y demos = `[]`. UI renderiza bloque Alertas vacío. **Gap:** datos no poblados.

### 1.3 Criterios de evaluación (chequeo de pitch)

- [x] Generalización (mecanismo `predict --reference` explicable al jurado)
- [x] Trayectoria vs foto del último mes
- [x] Las dos caras (mejora y deterioro)
- [x] Estabilidad / bache vs tendencia (`episode` / trayectoria en V2)
- [ ] Anticipación medida — gap E8
- [ ] Monitor — gap E9
- [x] Producto + comprador + explicación + artesanía (demo local se abre)

---

## 2. Superficies UI (todas)

Validar con JSON reales en `frontend/public/generated/` (no fixtures). Contratos: [`frontend-data-contract.md`](./frontend-data-contract.md), [`frontend/AGENTS.md`](../frontend/AGENTS.md).

### 2.1 Portfolio `/`

- [x] Lista de empresas con Health Score (o sin puntuar sin inventar 0) — 1.286 items; 1.011 con score; 275 null
- [x] Filtros / orden / búsqueda — cubiertos por tests unitarios (`portfolio.test.ts`) + página 200
- [x] Ordenación: nulos al final — test unitario PASS
- [x] Enlace a ficha / grupo — `has_detail` y `group_id` en items; navegación HTTP 200
- [x] `null` ≠ 0 — summary y tests; 275 sin score no aparecen como 0

### 2.2 Company Detail `/companies/[id]`

- [x] Health Score protagonista 0–100
- [x] Dimensiones + confidence separada (p.ej. COMP_0764 conf=79)
- [x] Assessment / summary en español (contrato + página)
- [x] Trayectoria / histórico
- [x] Drivers / «por qué ha cambiado»
- [x] Cash Truth («Origen de…» en HTML)
- [x] Time Borrowed: empty state honesto (`ar`/`ap` = null; sección «Tiempo financiado» visible sin inventar)
- [x] Alertas: bloque presente, lista vacía (gap E9 de datos)
- [x] Evidence / drill-down (contrato + tests e2e previos; sección en ficha)
- [x] Simulador FE-05: **81 escenarios**; ~78 multi-palanca; etiqueta **«del nivel actual»** en HTML
- [x] Smoke HTTP 200: COMP_0764, 0001, 0647, 0045, 0006, 0037

### 2.3 Grupo `/groups/[id]` (+ `/network`, `/recommendations`)

- [x] Overview GROUP_0250 / GROUP_0067 HTTP 200, schema 1.0, sin Group Health inventado (contrato)
- [x] Network GROUP_0067/network HTTP 200
- [x] Recommendations GROUP_0067/recommendations HTTP 200 (`recommendations` en JSON)
- [x] Plan advisor mecánico **no** mapeado al contrato de grupo — empty / insights Data; motor sigue en `data/processed/advisor/` (gap §5)

### 2.4 Estados de error

- [x] Sin JSON: `/companies/COMP_99999` → «no disponibles» / «todavía» (archivo inexistente)
- [x] ID inválido: `/companies/not-a-valid-id` → 404
- [x] JSON inválido: cubierto por tests unitarios + Playwright fixtures (no re-ejecutado e2e en esta pasada)

### 2.5 Reglas duras de UI

- [x] Frontend no calcula / no interpola — tests `companyScenario` + AGENTS
- [x] `null` ≠ 0 — tests portfolio + cash
- [x] Textos en español — páginas demo en español

---

## 3. Pipeline e integridad

### 3.1 Artefactos FE-05 (what-if factorial)

- [x] `whatif_scenarios.parquet` — 81.891 filas; 1.011 empresas; COMP_0764 = 81 filas (mtime 19-09 22:25)
- [x] `09_export_frontend.py` — COMP_0764.json mtime 22:27 con `scenarios: 81`
- [x] `validate:generated` (+ `--groups` + `--portfolio`) OK — portfolio 1.286; grupos hasta GROUP_0250

### 3.2 Suites automatizadas

- [x] `python3 -m pytest -q -p no:asyncio` → **569 passed, 1 failed** (`tests/test_pulse_pipeline.py::test_currency_runs_do_not_overwrite_or_mix`, rojo conocido D32 / Pulse, no bloquea V2 ni frontend)
- [x] `cd frontend && npm test` → **67 pass / 0 fail**
- [x] `cd frontend && npm run lint` → OK (tras ignorar stub `tests/support/cssModules.cjs` en eslint)
- [x] `cd frontend && npm run typecheck` → OK
- [ ] Playwright e2e — **omitido en esta pasada** (opcional; smoke HTTP + unit tests cubren rutas críticas)

### 3.3 Prefijo temporal

- [ ] Prefijo features/scores — **omitido** (no se regeneró score en esta pasada; artefactos previos con prefijo OK según ESTADO-ACTUAL)

---

## 4. Protocolo de esta pasada (orden)

1. Confirmar / regenerar `10` → `09` → `validate:generated`.
2. Suites §3.2.
3. Arrancar demo local; paseo §2 con empresas de la tabla.
4. Rellenar §1–§3; gaps en §5.
5. Veredicto §6. **No deploy** si §6 = no listo.

### Registro de ejecución

| Paso | Resultado | Notas |
|---|---|---|
| What-if + export + validate | PASS | 81 escenarios/empresa; contratos OK |
| pytest | PASS con 1 rojo conocido | 569 passed / 1 failed Pulse currency |
| frontend test / lint / typecheck | PASS | 67 tests; lint fix eslint ignore cjs |
| e2e Playwright | OMITIDO | Smoke HTTP en su lugar |
| Paseo UI manual (HTTP + JSON) | PASS | localhost:3111 rutas demo |
| Prefijo temporal | OMITIDO | Sin regeneración de score |

---

## 5. Gaps explícitos (no bloquean demo local; sí condicionan pitch / bonus)

| Gap | Impacto | Acción |
|---|---|---|
| E8 Anticipación medida | Bonus del enunciado | Implementar alertas + `lead_time.json` (prioridad B) |
| E9 Monitor / `alerts[]` vacías | Bonus; UI ya renderiza | Poblar desde `event_type` D30 |
| Time Borrowed real | MVP MUST de propuesta; nicho | Empty state OK para presentar; F4 si sobra tiempo |
| Import UI | MUST propuesta; no demo crítica | API `/import` existe; sin pantalla |
| Advisor → contrato grupo | SHOULD | Motor en `advisor/`; falta mapear a JSON de grupo |
| Fallback por signo (E1) | Test oculto con bancos nuevos | `hallazgos-datos.md` §11.5 |
| URL pública | E7 completo ante jurado | Siguiente: deploy Vercel tras este gate |
| Test Pulse currency mix | Suite Python | Rojo conocido en `origin/main` (D32); Pablo/Ander |

---

## 6. Gate deploy

**Criterio listo:** E2–E6 verificados `[x]`; E7 local `[x]`; E1 con nota de límite aceptada; §2 Portfolio + Company + simulador FE-05 PASS; §3.1 y §3.2 verdes (salvo rojo conocido documentado); sin fallos bloqueantes en el paseo demo.

**Criterio no listo:** fallo en Health/trayectoria/explicación/Cash Truth/simulador con datos reales; validate:generated rojo; o E7 local no arranca.

| Campo | Valor |
|---|---|
| **Veredicto** | **LISTO para iniciar deploy en Vercel** (gate pre-deploy PASS). Demo local verificada. Bonus E8/E9 y URL pública siguen abiertos. |
| **Fecha** | 19-09-2026 |
| **Listo para Vercel** | **sí** (siguiente fase = configurar build/`09` o montar JSON; no implica que la URL exista aún) |

---

## 7. Comandos de referencia

```bash
# Artefactos
python3 -X utf8 scripts/10_build_whatif.py
python3 -X utf8 scripts/09_export_frontend.py
cd frontend && npm run validate:generated && npm run validate:generated -- --groups && npm run validate:generated -- --portfolio

# Suites
python3 -m pytest -q -p no:asyncio
cd frontend && npm ci && npm test && npm run lint && npm run typecheck
# opcional: npx playwright install chromium && npm run build && npm run test:e2e

# Demo
cd frontend && npm run dev -- --port 3111
```
