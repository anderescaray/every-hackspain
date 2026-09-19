# PulseFourPillars V1 — implementación

Las secciones originales documentan la entrega V1.0 y sus comprobaciones históricas. La integración web posterior está en `pulse-frontend-integration.md`; el endurecimiento acotado de Debt V1.0.1 se describe al final. No se sustituyen los artefactos ni la configuración histórica V1.0.

## 1. Arquitectura

`CSV → cutoff previo a limpieza → clean_all → ledger canónico → monthly facts → Pulse features → cuatro pilares → JSON/Parquet inmutables`.

El batch vive en `xray.pulse.pipeline`; reutiliza I/O, validación y limpieza existentes. `financial_baseline_v1` y `financial_smoothed_v2` siguen independientes: Pulse no usa referencias estadísticas, Stouffer, neutralización ni renormalización. No se conectó el frontend ni se añadieron endpoints.

La clasificación compartida cambia deliberadamente las features transaccionales legacy. Las referencias V2 preexistentes **no validan esa nueva semántica** ni calibran Pulse; no se hizo refit V2 en esta tarea. El backend sigue sirviendo su producto legacy, no estos nuevos runs; su eventual migración/recalibración queda separada.

```bash
python scripts/09_compute_pulse.py --raw-dir data \
  --out-dir data/processed/pulse --as-of 2026-08-31 \
  --data-vintage 2026-09-01 --company-id COMP_1084
```

Sin `--company-id`, procesa el portfolio. La selección conserva otras empresas del grupo para detectar espejos; nunca mezcla monedas. `--previous-run` permite comparar una emisión almacenada, incluida una reexpresión del mismo `as_of`.

## 2. Cash Truth

`xray.ledger.classify` es la única interpretación económica, compartida por features legacy y Cash Truth de producto. Conserva importe/ID/fecha, clase/subclase, inclusión, regla/versiones/confianza, flags y linaje hasta el registro lógico del CSV. Préstamos y circulación identificada no son ingresos operativos. Principal, intereses y comisiones **verificadas** entran una sola vez en servicio financiero; fees ambiguas quedan `uncertain`. Filas no booked o excluidas por calidad siguen auditables, sin aportar caja.

Las categorías Jev preexistentes son evidencia **opcional y congelada**, nunca una llamada AI. Pulse exige `--ai-categories <parquet>` explícito y conserva una copia/hash. El umbral se pasa con `--ai-min-confidence`; clasificación/version/config-hash y hash de evidencia distinguen metodología de información. El bundle legacy verifica el mismo cache/umbral, código canónico, fuentes cleaned y outputs de features. Manifiestos pre-canónicos o cualquier inconsistencia exigen regenerar features/product; no hay fallback silencioso.

## 3. Monthly facts

Unidad: empresa × moneda × mes. Los hechos incluyen I/O/N, principal/interés/fees/S, financiación externa, circulación, inversión, incertidumbre, conteos y cobertura. `N=I−O`; `S=principal+interest+verified_financing_fees`. Desgloses adicionales permiten reconciliar con caja elegible del ledger. No convierten calendarios sin observación en cero; la cobertura explícita puede acreditar inactividad.

## 4. Fórmulas exactas

Ventana: últimos **seis meses naturales completos**. `as_of` dentro de un mes no incorpora ese mes parcial. Sin epsilon ni redondeo antes del resultado:

| Pilar | Feature y transformación |
|---|---|
| Generation | `g=ΣN/ΣO`; `clip(50+200g,0,100)` |
| Momentum | `β=median((N_b−N_a)/(b−a), a<b)`; `m=3β/mean(O)`; `clip(50+200m,0,100)` |
| Resilience | `d=Σmax(−N,0)/ΣO`; `clip(100−400d,0,100)` |
| Debt & Obligations | `s=ΣS/ΣI`; interpolación lineal `(0,100),(.10,50),(.30,0)` y clipping |
| Health | `.40G+.15M+.25R+.20D`, sólo con cuatro pilares válidos |

Momentum es **nowcast**, no forecast. Frecuencia/episodios/materialidad/recovery/worst month son diagnósticos, no ponderaciones adicionales. Los pesos son política inicial **no calibrada científicamente**. Health describe treasury/cash health y early warning: no PD, rating ni AUC.

## 5. Debt semantics

Nombre técnico: `observed_debt_service_pressure`. Mide servicio observado respecto de entradas operativas, no leverage, solvencia, inventario contractual ni obligaciones futuras. Estados `verified`, `partial`, `unknown`; sin evidencia suficiente o denominador válido, score `null`. No identificar pagos NO equivale a ausencia de deuda ni a D100. Principal/interés son desgloses, nunca scores sumados.

## 6. JSON y persistencia

Contratos dataclass: `LedgerTransaction`, `MonthlyFacts`, `CashTruthResult`, `PulseScoreResult`. El resultado incluye features raw/normalizadas, numerador/denominador/anclas/fórmula/ventana, pesos/contribuciones, evidencia, confianza, sensibilidad y linaje. El frontend recibe todo: **no debe recalcular**.

```text
<out>/latest.json                       # puntero atómico + hash del manifiesto
<out>/runs/pulse-<content-hash>/
  manifest.json                        # hashes de TODOS los descendientes
  config.json, classification_config.json
  source_snapshot/*.parquet, cleaned/*.parquet, cleaning_log.csv
  ledger.parquet, monthly_facts.parquet
  pulse_features.parquet, pulse_scores.parquet, portfolio.json
  companies/<company>/<currency>/{cash_truth,score}.json
  comparisons/previous_month/...       # comparación reconstruida y auditable
  classification_evidence/...          # sólo con cache explícito
```

El directorio completo se publica mediante rename y luego se sustituye `latest.json`; un fallo no expone archivos mezclados. Reejecución idéntica es idempotente; modificación o conflicto de run se rechaza. Hashes recursivos incluyen JSON anidados y detalles. `portfolio` es ligero; `alert_count=0` porque no se agregó un motor separado de alertas (flags y críticos sí se entregan).

Versiones explícitas: schema, cleaning, classification, facts, config, score. Config JSON empaquetado y registro SHA vinculan metodología a `score_version`: cambiar pesos/anclas/fórmulas/policies requiere registrar una nueva versión. `code_version` hashea fuentes de ejecución, no HEAD/docs/timestamps; dependencias también quedan registradas.

## 7. Critical movements

Preselección determinista y acotada, seguida de exclusión individual y recálculo incremental de facts/pilares. Se informan deltas, cambio de signo del mes y motivo; una transferencia enorme puede ser irrelevante, mientras un cobro menor puede cambiar déficit/diagnóstico. No se confunde tamaño con impacto. Si la exclusión elimina identificación de Debt, Health delta queda null, no se inventa.

**Demo real COMP_1084, EUR, 2026-08-31:** G=0, M=57.43435, R=0, D=null (`unknown`), Health=null; peso conocido=.8, límites `[8.61515,28.61515]`. Hay seis meses observados, pero clasificación sólo del 50.0034% del importe y ningún servicio financiero identificado. La robustez queda `indeterminate`: **no inventamos un Health completo**. La fixture sintética de tests es distinta de esta ejecución real.

El movimiento `0dc9ebb65a7e4949a412aa203a366e80`, −40.299,48 EUR del 2026-03-05, cambia Momentum **−4.79651 puntos** al excluirlo: el neto de marzo pasa de −883.789,51 a −843.490,03 EUR y reduce la mejora relativa posterior. G/R están saturados en cero, sin cambio; Health delta es null. Es crítico por alterar materialmente el diagnóstico de trayectoria, no por estar entre los importes mayores ni por un efecto causal supuesto.

Run local: `data/processed/pulse/runs/pulse-6a524f63ef2c548edb8e6be7a631567804a64ad6d3f79bc5d789cbba992236c8/`: 59.618 filas del ledger, incluidos pares del grupo necesarios para clasificar; 378 filas facts; un score; 29 archivos auditados recursivamente. Artefactos ignorados por Git.

## 8. Change attribution

Separa hechos I/O/N/S, cambios de evidencia/cobertura/perímetro/cache y cambios de metodología/configuración. No etiqueta como deterioro económico un salto no comparable. Por defecto reconstruye el mes anterior desde el mismo vintage con cutoff **antes de limpiar** y persiste esos detalles; alternativamente valida el run anterior indicado.

## 9. Robustness y confidence

Supuestos deterministas versionados: uncertain material, exclusión de movimientos influyentes y perímetro comparable. Rango probado incluye baseline cuando es identificable; escenarios no identificables no justifican afirmar robustez alta. No es un confidence interval.

Confidence describe history/classification coverage, uncertain amount share, consistencia de perímetro/moneda y evidencia de deuda; **no modifica Health**.

## 10. Tests y validación

Tests unitarios cubren invariantes económicos, monotonía, escala, tres trayectorias, missing, exactitud de contribuciones, críticos, atribución, sensibilidad y configuración versionada. Integración cubre raw→JSON, COMP_1084 sintético, monedas separadas, cutoff anterior a pending/booked matching, determinismo byte-a-byte entre destinos, hash recursivo, tampering, conflictos y fallo de publicación atómica.

Validación del **2026-09-19**, Python 3.14 / pandas 3.0.6 / NumPy 2.5.3 / PyArrow 25.0.1:

- `python -m pytest tests -q`: **347 tests + 15 subtests pasan**; un warning esperado del CSV con fecha inválida.
- `(cd backend && python -m pytest -q)`: **12 pasan**; dos deprecations de dependencias Starlette.
- Ruff `--isolated --select E4,E7,E9,F`: módulos cambiados/nuevos y tests de la implementación pasan.
- Mypy `--follow-imports=skip --ignore-missing-imports`: **21 módulos Python pasan**. El repositorio no tenía configuración propia de lint/type checks Python; no se afirma type-check estricto de pandas sin stubs.
- `python -m build --outdir /tmp/pulse-package-dist-final`: sdist y wheel correctos, ambos configs incluidos.
- Demo real repetida: mismo run ID y **todos los archivos/hashes idénticos**; manifiesto recursivo verificado. Ocho SHA256 raw coinciden con el baseline anterior a implementar; `git diff --check` limpio.

El entorno aislado usado es `/tmp/pulse_four_pillars_venv/bin/python`. El frontend permanece sin cambios; no se ejecutó su build porque no es gate de este batch Python.

## 11. Cobertura, missing e historia

Si falta un pilar: `status=partial`, Health null, pesos originales, `known_weight`, `missing_components`; `health_min=Σ contribuciones conocidas`, `health_max=health_min+100×peso faltante`. Son **límites de identificación**, no intervalos estadísticos.

`as_of` económico se distingue de `data_vintage/knowledge_cutoff`. Los CSV no conservan estados conocidos-en-cada-fecha: la salida se identifica como `retrospective_restatement`, no emisión histórica reconstruida fielmente. `created_at` significa onboarding/conexión, NO apertura; no se eliminan por ello transacciones históricas legítimas. Snapshots de invoices/deuda no entran en fórmulas V1.

## 12. Archivos

Nuevos: `src/xray/ledger/*`, `src/xray/pulse/*` y configs, `scripts/09_compute_pulse.py`, `tests/test_ledger.py`, `tests/test_pulse_engine.py`, `tests/test_pulse_pipeline.py`, este documento.

Modificados: `src/xray/artifacts.py`, `features/__init__.py` (provenance), `features/transactions.py`, `features/ai_categories.py` (compatibilidad), `product/cash_truth.py`, `product/bundle.py`, tests legacy afectados y `pyproject.toml` (config empaquetada). Se añadieron también tests de revisión independiente de motor/publicación. CSV raw y componentes frontend no se modifican.

## 13. Commit local

La implementación se entrega en un commit convencional local, sin push ni atribución AI. Para localizar el SHA que incorpora este documento, sin introducir una referencia autorreferencial inválida:

```bash
git log --diff-filter=A --format='%h %s' -- docs/pulse-four-pillars-v1-implementation.md
```

## 14. Debt V1.0.1: identificación acotada, no ausencia supuesta

El patch mantiene **sin cambios** G/M/R, pesos, anclas, seis meses completos, denominadores, FX y clasificación económica `cash-truth-v1`. Se registra una configuración nueva; seleccionar la anterior conserva la política estricta V1.0. Los hechos añaden `monthly-facts-v1.1` y la evaluación separada `debt-uncertainty-v1`.

- Cada salida incierta elegible conserva ID/linaje y añade `debt_uncertainty_status`, regla, referencias a evidencia y versión. Una fee bancaria genérica puede ser `debt_possible`; transferencias, retiradas de efectivo y demás evidencia insuficiente quedan `debt_unresolved`. **Ninguna regla actual acredita `debt_impossible`**: un canal no prueba el uso económico final.
- Los hechos publican importes `debt_possible_uncertain_outflows`, `debt_impossible_uncertain_outflows`, `debt_unresolved_uncertain_outflows` y `potentially_financial_uncertain_outflows = possible + unresolved`. Son desgloses adicionales, no nueva caja ni doble cómputo en S. Los meses ausentes siguen siendo nulos; las exclusiones y problemas de moneda permanecen independientes.
- Se conservan principal/intereses/fees verificadas/servicio identificado aun cuando falta historia, junto con meses observados/requeridos. Un subtotal observado no se presenta como seis meses completos.
- Sólo con historia y denominadores válidos, servicio identificado positivo, moneda inequívoca y **sin salidas excluidas**, se forma `S_min = S_identificado`, `S_max = S_min + potencialmente_financiero`. La misma transformación Debt produce `[D_min,D_max]`. Anchura ≤5 puntos permite el punto medio explícitamente `bounded`; una anchura mayor mantiene Debt/Health puntuales nulos, conservando el intervalo.
- Sin servicio identificado, `service_absence_verified=false`: no hay D100 ni certificación automática de ausencia. Tampoco se acotan artificialmente las salidas excluidas o de moneda incierta.
- La salida distingue `complete_verified`, `complete_bounded`, `partial` e `insufficient_evidence`; incluye `identified_score`, `score_range`, anchura, estimador, desglose de servicio y límites. Health conserva contribuciones exactas y pesos fijos. Los rangos son de **identificación**, no intervalos de confianza estadísticos ni calibración científica.
- `identified_range` de Health propaga exclusivamente el intervalo Debt **manteniendo G/M/R y los demás hechos fijos**. No representa toda la incertidumbre de clasificación. Cambios numéricos de servicio/rango no se confunden con cambios estructurales de evidencia en la atribución temporal.

Se autorizaron únicamente pruebas focalizadas de este cambio y comprobaciones estáticas rápidas, no una nueva ejecución de las suites generales históricas de la sección 10. Ledger: `tests/test_debt_uncertainty.py` y `tests/test_ledger.py`, **24 pasan**; motor **55 pasan**, más **una integración determinista**; exporter **20 pasan** y contratos frontend **24 pasan**. Ruff, comprobación de tipos acotada y build rápido frontend pasan. La materialización y comparación final se registran en `pulse-frontend-integration.md`.

Límite previo fuera del pipeline canónico: `score_company` acepta DataFrames internos, no entradas de una API pública. Antes de exponer esa interfaz a fuentes no confiables hay que endurecer la presencia de conteos de moneda y la no negatividad de exclusiones. El productor mensual actual sí emite esos campos y magnitudes no negativas; no se relajaron sus gates ni se amplió esta tarea a ingestión externa.
