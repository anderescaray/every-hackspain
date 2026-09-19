# Documentación técnica — X-Ray · Embat

**Empieza por [decisiones.md](./decisiones.md): basta para saber qué está hecho, qué cambió y qué debes decidir.** Los demás documentos amplían el contrato técnico o conservan propuestas de pasos futuros.

## Estado real

| Capa | Estado | Referencia |
|---|---|---|
| Limpieza reproducible | Implementada y revisada; flags, validación, hashes y publicación con respaldo | `src/xray/clean/`, [decisiones.md](./decisiones.md) |
| Features mensuales | Implementadas: empresa, empresa-moneda y grupo-moneda; nivel, dinámica y calidad | `src/xray/features/`, [feature-engineering.md](./feature-engineering.md) |
| Contexto retrospectivo | Saldos reconstruidos, cobertura de liquidez y deuda final, separados del modelo | [feature-engineering.md](./feature-engineering.md) |
| Validación de features | Tests, hashes, checks de contrato e invariancia de prefijo | [validation.md](./validation.md) |
| Leaderboard y predicción supervisada | Sin resultados oficiales ni acuerdo medido; pendiente formato/feedback. No bloquea el baseline | [decisiones.md](./decisiones.md) |
| Score y explicación | Baseline 0–100 implementado: nivel, momentum, trayectoria, referencia congelada y contribuciones aditivas. No GBM/SHAP ni probabilidades | [scoring.md](./scoring.md), [explainability.md](./explainability.md) |
| Alertas, API y demo | Diseños pendientes, sin despliegue ni métricas comprobadas | [alerts-and-monitoring.md](./alerts-and-monitoring.md), [product-and-demo.md](./product-and-demo.md) |

## Ejecutar lo implementado

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit
python -X utf8 scripts/04_validate_scores.py
python -m pytest -q
```

`-X utf8` evita problemas de consola Windows con los mensajes del log. No hace falta instalar nuevas dependencias si se usa el entorno existente (pandas/numpy/pyarrow/pytest). `XRAY_DATA_DIR` permite otra raíz de datos.

La validación extendida es:

```bash
python -X utf8 scripts/02_validate_features.py --check-prefix 2026-02-01
```

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
    _feature_catalog.json
    _feature_quality.json
    _feature_manifest.json
    scores/
        company_monthly_scores.parquet
        company_latest_scores.csv
        company_score_explanations.parquet
        company_score_examples.json
        _company_score_reference.json
        _company_score_report.json
        _company_score_manifest.json
        group_currency_...          equivalentes por grupo-moneda
```

Los snapshots/contextos y eventos reservados **no** están en la lista de predictores. Las versiones anteriores se conservan en `.history/` dentro de la capa; no eliminarlas sin revisar si se necesita volver a ellas. Los datos y derivados siguen ignorados por git.

## Continuación

1. Revisar casos, cobertura y saltos del primer score; no interpretar el holdout como acierto frente a etiquetas que no tenemos.
2. Confirmar unidad/formato de entrega y obtener feedback del leaderboard; no hace falta esperar un script para usar el baseline.
3. En paralelo, construir la demo de cartera + ficha + solicitud/revisión para Embat, con deterioro **y** mejora.
4. Si se quiere predicción supervisada de eventos, definir targets/censura y validación independiente antes de GBM/SHAP. No entrenar contra nuestra propia fórmula para simular acuerdo con el organizador.
5. Aplicar el score a nuevas empresas con `predict --reference` y el JSON congelado; no recalibrar con el test oculto.

El último mes completo es **agosto de 2026**. No sustituir missingness por 0 ni convertir el contexto retrospectivo en predictores históricos sin una decisión nueva documentada.
