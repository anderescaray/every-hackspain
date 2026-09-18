# Documentación técnica — X-Ray · Embat

**Empieza por [decisiones.md](./decisiones.md): basta para saber qué está hecho, qué cambió y qué debes decidir.** Los demás documentos amplían el contrato técnico o conservan propuestas de pasos futuros.

## Estado real

| Capa | Estado | Referencia |
|---|---|---|
| Limpieza reproducible | Implementada y revisada; flags, validación, hashes y publicación con respaldo | `src/xray/clean/`, [decisiones.md](./decisiones.md) |
| Features mensuales | Implementadas: empresa, empresa-moneda y grupo-moneda; nivel, dinámica y calidad | `src/xray/features/`, [feature-engineering.md](./feature-engineering.md) |
| Contexto retrospectivo | Saldos reconstruidos, cobertura de liquidez y deuda final, separados del modelo | [feature-engineering.md](./feature-engineering.md) |
| Validación de features | Tests, hashes, checks de contrato e invariancia de prefijo | [validation.md](./validation.md) |
| Targets y leaderboard | Pendiente de script oficial y definición de eventos | [decisiones.md](./decisiones.md) |
| Scoring y SHAP | Pendiente; el documento de scoring conserva un baseline propuesto, no un modelo entrenado | [scoring.md](./scoring.md), [explainability.md](./explainability.md) |
| Alertas, API y demo | Diseños pendientes, sin despliegue ni métricas comprobadas | [alerts-and-monitoring.md](./alerts-and-monitoring.md), [product-and-demo.md](./product-and-demo.md) |

## Ejecutar lo implementado

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
python -X utf8 scripts/02_validate_features.py
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
```

Los snapshots/contextos y eventos reservados **no** están en la lista de predictores. Las versiones anteriores se conservan en `.history/` dentro de la capa; no eliminarlas sin revisar si se necesita volver a ellas. Los datos y derivados siguen ignorados por git.

## Continuación

1. Confirmar contrato del leaderboard y semántica de FX/estados con Embat.
2. Definir targets 3/6 meses y censura, usando las columnas reservadas sin circularidad.
3. Entrenar GBM por grupos, con nivel y momentum separados, SHAP y transformaciones aprendidas solo en train.
4. Medir generalización y anticipación con una regla independiente.
5. Construir una demo desplegada para Embat/financiador que muestre deterioro **y** mejora.

El último mes completo es **agosto de 2026**. No sustituir missingness por 0 ni convertir el contexto retrospectivo en predictores históricos sin una decisión nueva documentada.
