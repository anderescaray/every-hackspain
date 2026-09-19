# Documentación técnica — X-Ray · Embat

**[decisiones.md](./decisiones.md) es el registro central.** §13 contiene el score V2 suavizado (qué se hizo, resultados, qué no mejora y pendientes); §12 la auditoría que lo motivó; §10 V1 y §11 producto. Para retomar el proyecto con otro agente: leer §13, después [scoring-v2.md](./scoring-v2.md) y el informe `data/processed/evaluation/score_comparison.md` (generado localmente). [continuar-score-v2.md](./continuar-score-v2.md) fue el relevo previo a V2; sus tareas de estabilidad y comparador están ejecutadas, las de liquidez y fallback no.

## Estado real

| Capa | Estado | Referencia |
|---|---|---|
| Limpieza reproducible | Implementada y revisada; flags, validación, hashes y publicación con respaldo. Anotaciones semánticas D25–D30/F07 (pólizas operativas, SCF, repos, pasarela, eventos de estrés, fecha prevista ERP) | `src/xray/clean/`, [decisiones.md](./decisiones.md) §14, [hallazgos-datos.md](./hallazgos-datos.md) |
| Features mensuales | Implementadas: empresa, empresa-moneda y grupo-moneda; nivel, dinámica y calidad | `src/xray/features/`, [feature-engineering.md](./feature-engineering.md) |
| Contexto retrospectivo | Saldos reconstruidos, cobertura de liquidez y deuda final, separados del modelo | [feature-engineering.md](./feature-engineering.md) |
| Validación de features | Tests, hashes, checks de contrato e invariancia de prefijo | [validation.md](./validation.md) |
| Score V1 (control) | `financial_baseline_v1`: nivel, momentum, referencia y contribuciones. Ruidoso (mediana de cambio mensual 8,8 puntos); conservado como control en `scores/` | [scoring.md](./scoring.md), [explainability.md](./explainability.md) |
| **Score V2 (candidato)** | `financial_smoothed_v2`: nivel de flujos agregados 6m, momentum trimestre/trimestre estandarizado por volatilidad propia, confirmación bache/tendencia, episodios, explicación aditiva exacta. Mediana de cambio mensual 3,3; extremos a la mitad; 922 empresas puntuadas en agosto | [scoring-v2.md](./scoring-v2.md), decisiones §13 |
| Comparador V1/V2 | Estabilidad, proxies de estrés (texto y caja negativa), riesgo por etiqueta, anticipación con regla independiente, sensibilidad. Ninguna versión discrimina los proxies; V2 gana en estabilidad sin perder | [validation.md](./validation.md), `src/xray/evaluation/` |
| Leaderboard y predicción supervisada | Sin resultados oficiales ni acuerdo medido; pendiente formato/feedback | [decisiones.md](./decisiones.md) |
| Alertas, API y demo | Diseños pendientes, sin despliegue ni métricas comprobadas | [alerts-and-monitoring.md](./alerts-and-monitoring.md), [product-and-demo.md](./product-and-demo.md) |

## Ejecutar lo implementado

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit                 # V1 control -> data/processed/scores/
python -X utf8 scripts/04_validate_scores.py
python -X utf8 scripts/05_compute_scores_v2.py fit              # V2 -> data/processed/scores_v2/
python -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python -X utf8 scripts/07_compare_scores.py                     # -> data/processed/evaluation/
python -m pytest -q -p no:asyncio                               # 233 tests (-W error si no hay pytest-asyncio global)
```

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
```

Snapshots/contextos y eventos reservados **no** están en la lista de predictores de ninguna versión. Las versiones anteriores se conservan en `.history/` dentro de cada capa; no eliminarlas sin revisar si se necesita volver a ellas. Los datos y derivados siguen ignorados por git.

## Continuación

1. Producto y demo sobre V2: cartera con `trajectory`/`episode`, ficha con contribuciones y relato «nivel 6m · trimestre reciente frente a anterior · mes actual». Ver decisiones §11 y §13 (SC13).
2. Confirmar unidad/formato/escala del envío con Embat; `scores_v2/company_latest_scores.csv` es candidato, no submission.
3. Liquidez como dimensión del nivel y fallback de exportación siguen pendientes (decisiones §12 V2-01/V2-03, §13 SC13).
4. No restaurar país ni añadir `nueva-proposicion.md` a commits. No hacer commit/push sin petición.

El último mes completo es **agosto de 2026**. No sustituir missingness por 0 ni convertir el contexto retrospectivo en predictores históricos sin una decisión nueva documentada.
