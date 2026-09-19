# Documentación técnica — X-Ray · Embat

**Empieza por [ESTADO-ACTUAL.md](./ESTADO-ACTUAL.md)** (arquitectura vigente, cifras, comandos, pendientes). **[decisiones.md](./decisiones.md) es el registro central.** §13 contiene el score V2 suavizado (qué se hizo, resultados, qué no mejora y pendientes); §12 la auditoría que lo motivó; §10 V1 y §11 producto. Para retomar el proyecto con otro agente: leer §13, después [scoring-v2.md](./scoring-v2.md) y el informe `data/processed/evaluation/score_comparison.md` (generado localmente). [continuar-score-v2.md](./continuar-score-v2.md) fue el relevo previo a V2; sus tareas de estabilidad y comparador están ejecutadas, las de liquidez y fallback no.

## Estado real

| Capa | Estado | Referencia |
|---|---|---|
| Limpieza reproducible | Implementada y revisada; flags, validación, hashes y publicación con respaldo. Anotaciones semánticas D25–D30/F07 (pólizas operativas, SCF, repos, pasarela, eventos de estrés, fecha prevista ERP) | `src/xray/clean/`, [decisiones.md](./decisiones.md) §14, [hallazgos-datos.md](./hallazgos-datos.md) |
| Features mensuales | Implementadas: empresa, empresa-moneda y grupo-moneda; nivel, dinámica y calidad | `src/xray/features/`, [feature-engineering.md](./feature-engineering.md) |
| **Categorías AI (D31)** | Artefacto estático generado una vez con TypeSafe Jev para el 39 % de importe sin categoría; opt-in vía `--ai-categories`. A/B: 1.024 empresa-mes recuperan el filtro operativo, +55 empresas puntuadas en agosto | [jev-categorias.md](./jev-categorias.md), decisiones §15 |
| Contexto retrospectivo | Saldos reconstruidos, cobertura de liquidez y deuda final, separados del modelo | [feature-engineering.md](./feature-engineering.md) |
| Validación de features | Tests, hashes, checks de contrato e invariancia de prefijo | [validation.md](./validation.md) |
| Score V1 (control) | `financial_baseline_v1`: nivel, momentum, referencia y contribuciones. Ruidoso (mediana de cambio mensual 8,8 puntos); conservado como control en `scores/` | [scoring.md](./scoring.md), [explainability.md](./explainability.md) |
| **Score V2 (canónico, decisiones §21)** | `financial_smoothed_v2`: nivel de flujos agregados 6m, momentum trimestre/trimestre estandarizado por volatilidad propia, confirmación bache/tendencia, episodios, explicación aditiva exacta. Mediana de cambio mensual 3,3; extremos a la mitad; 922 empresas puntuadas en agosto | [scoring-v2.md](./scoring-v2.md), decisiones §13 |
| Comparador V1/V2 | Estabilidad, proxies de estrés (texto y caja negativa), riesgo por etiqueta, anticipación con regla independiente, sensibilidad. Ninguna versión discrimina los proxies; V2 gana en estabilidad sin perder | [validation.md](./validation.md), `src/xray/evaluation/` |
| Leaderboard y predicción supervisada | Sin resultados oficiales ni acuerdo medido; pendiente formato/feedback | [decisiones.md](./decisiones.md) |
| **Advisor: plan de grupo + sensibilidad de empresa** | `treasury_advisor_v1`: escenarios mecánicos sobre la función de nivel exacta de V2. Plan de grupo (asunción de servicio de deuda D1, financiación de pago a proveedores P; objetivo cóncavo por tramos; greedy determinista con certificado) y sensibilidad por empresa (pendiente por palanca, siguiente nudo, cuánto para cambiar de tramo). Narrativa por plantillas con validador de anclaje; LLM opcional no conectado. Agosto 2026: 19 grupos con plan / 160 sin palancas / 71 unipersonales; 949 empresas con sensibilidad; 0 fallos de anclaje | [group-optimization.md](./group-optimization.md), [roadmap-group-advisor.md](./roadmap-group-advisor.md), decisiones §20, `src/xray/group_advisor/` |
| Frontend (Next.js) | Portfolio `/`, ficha de empresa y grupo con datos reales vía `09_export_frontend.py`; simulador con 81 escenarios precalculados (`10_build_whatif.py`). Sin despliegue público | `frontend/`, [frontend-data-contract.md](./frontend-data-contract.md), decisiones §19 |
| Pulse Four Pillars | Experimento (`xray.pulse`); su ledger `xray.ledger` sí es canónico y alimenta features y Cash Truth | decisiones §21 |
| Alertas, API y demo | Alertas: solo diseño. API FastAPI existe pero el frontend no la usa. Sin despliegue | [alerts-and-monitoring.md](./alerts-and-monitoring.md), [product-and-demo.md](./product-and-demo.md) |

## Ejecutar lo implementado

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py             # D31 por defecto; --no-ai-categories para solo banco
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit                 # V1 control -> data/processed/scores/
python -X utf8 scripts/04_validate_scores.py
python -X utf8 scripts/05_compute_scores_v2.py fit              # V2 -> data/processed/scores_v2/
python -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python -X utf8 scripts/07_compare_scores.py                     # -> data/processed/evaluation/
python -X utf8 scripts/08_treasury_advisor.py                   # planes de grupo + sensibilidad -> data/processed/advisor/
python -X utf8 scripts/08_treasury_advisor.py --group GROUP_0067    # o --company COMP_0007: imprime la narrativa sin publicar
python -X utf8 scripts/08_build_product.py                      # -> data/processed/product/
python -X utf8 scripts/10_build_whatif.py                       # -> product/whatif_scenarios.parquet (~8 min, opcional)
python -X utf8 scripts/09_export_frontend.py                    # -> frontend/public/generated/ (contrato del frontend, V2)
# Experimento Pulse (no canónico): PYTHONPATH=src python -m xray.pulse ... y scripts/09b_export_frontend_pulse.py --run-dir ...
python -W error -m pytest -q                                    # suite completa
```

`08` exige que `scores_v2/` se haya calculado sobre las features actuales (comprueba hashes); tras regenerar features, ejecutar `03`/`05` (también `--panel group_currency`) antes.

Entorno con uv (`.python-version` = 3.14): `uv sync --extra dev --group notebooks` y después `uv run python -X utf8 scripts/...`, `uv run python -W error -m pytest -q`. Para ejecutar un notebook sin abrirlo: `cd notebooks && uv run jupyter nbconvert --to notebook --execute --inplace 01_exploracion_datos.ipynb` (≈35 s); para trabajar con él, `uv run jupyter lab`.

`-X utf8` evita problemas de consola Windows con los mensajes del log. No hace falta instalar nuevas dependencias (pandas/numpy/pyarrow/pytest). `XRAY_DATA_DIR` permite otra raíz de datos. Ambos scores admiten `--panel group_currency` y `predict --reference ...` para entidades nuevas sin recalibrar.

## Flujo actual

```text
data/raw/                        originales inmutables
    |
    | 00_clean_data.py
    v
data/cleaned/                    8 tablas Parquet + log + manifiesto
    |
    | 01_build_monthly_features.py
    v
data/processed/
    company_monthly_features.parquet
    company_currency_monthly_features.parquet
    group_currency_monthly_features.parquet
    stress_events_reserved.parquet
    reconstructed_liquidity_context.parquet
    company_currency_liquidity_context.parquet
    debt_snapshot_context.parquet
    _feature_catalog.json / _feature_quality.json / _feature_manifest.json
    scores/                      V1 control (03_compute_scores.py)
    scores_v2/                   V2 candidato (05_compute_scores_v2.py): mismos ficheros + episode, z, diagnósticos
    evaluation/                  score_comparison.json / .md (07_compare_scores.py)
    advisor/                     08_treasury_advisor.py: group_plans/{id}.json|.md, company_sensitivity/{id}.json|.md,
                                 advisor_steps / advisor_groups / sensitivity_levers .parquet, _advisor_report.json, _advisor_manifest.json
```

Snapshots/contextos y eventos reservados **no** están en la lista de predictores de ninguna versión. Las versiones anteriores se conservan en `.history/` dentro de cada capa; no eliminarlas sin revisar si se necesita volver a ellas. Los datos y derivados siguen ignorados por git.

## Continuación

1. Producto y demo sobre V2 **y el advisor**: cartera con `trajectory`/`episode`, ficha con contribuciones, relato «nivel 6m · trimestre reciente frente a anterior · mes actual» y bloque «Qué mueve tu nivel» (`company_sensitivity/`); vista de grupo con el plan (`group_plans/`) solo si el grupo tiene ≥2 filiales puntuadas. Ver decisiones §11, §13 (SC13) y §20, y [group-optimization.md](./group-optimization.md) §13.
2. Confirmar unidad/formato/escala del envío con Embat; `scores_v2/company_latest_scores.csv` es candidato, no submission.
3. Liquidez como dimensión del nivel y fallback de exportación siguen pendientes (decisiones §12 V2-01/V2-03, §13 SC13).
4. No restaurar país ni añadir `nueva-proposicion.md` a commits. No hacer commit/push sin petición.

El último mes completo es **agosto de 2026**. No sustituir missingness por 0 ni convertir el contexto retrospectivo en predictores históricos sin una decisión nueva documentada.
