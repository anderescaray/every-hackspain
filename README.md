# X-Ray · Embat — HackSpain 2026

Reto de Embat: construir un **score de salud financiera** (empresa × mes, con trayectoria, en las dos direcciones y explicable) sobre el rastro bancario y de facturas de 250 grupos empresariales, y un **producto vendible** encima. El enunciado oficial está en [`enunciado-embat.md`](enunciado-embat.md).

**Producto propuesto:** Embat Pulse, early warning y explicación de tesorería. Ver [`docs/embat_pulse_mvp_propuesta_final.md`](docs/embat_pulse_mvp_propuesta_final.md).

**Si retomas el proyecto con otro agente/modelo**, empieza por [`docs/decisiones.md`](docs/decisiones.md) §13 (score V2 suavizado: qué se hizo, resultados y qué no mejora), luego [`docs/scoring-v2.md`](docs/scoring-v2.md). El registro central sigue siendo `decisiones.md` (§10 V1, §11 producto, §12 auditoría, §13 V2). [`docs/continuar-score-v2.md`](docs/continuar-score-v2.md) es el relevo previo a V2, ya ejecutado en su mayor parte.

## Estado real

| Capa | Estado | Referencia |
|---|---|---|
| Limpieza reproducible | Implementada y revisada; flags, validación, hashes y publicación con respaldo | `src/xray/clean/`, [decisiones.md](docs/decisiones.md) |
| Features mensuales | Implementadas: empresa, empresa-moneda y grupo-moneda; nivel, dinámica y calidad | `src/xray/features/`, [feature-engineering.md](docs/feature-engineering.md) |
| Contexto retrospectivo | Saldos reconstruidos, cobertura de liquidez y deuda final, separados del modelo | [feature-engineering.md](docs/feature-engineering.md) |
| Validación de features | Tests, hashes, checks de contrato e invariancia de prefijo | [validation.md](docs/validation.md) |
| Leaderboard y predicción supervisada | Sin resultados oficiales ni acuerdo medido; pendiente formato/feedback. No bloquea el baseline | [decisiones.md](docs/decisiones.md) |
| Score V1 (control) | `financial_baseline_v1`: nivel, momentum, referencia y contribuciones. Ruidoso (mediana de cambio mensual 8,8 puntos); conservado en `data/processed/scores/` | [scoring.md](docs/scoring.md), [explainability.md](docs/explainability.md) |
| **Score V2 (candidato)** | `financial_smoothed_v2`: nivel de flujos agregados a 6 meses, momentum trimestre/trimestre estandarizado por la volatilidad propia de cada empresa, confirmación bache/tendencia con evidencia del mes actual, episodios (`one_off_dip`, `trend_deterioration`…), explicación aditiva exacta. Mediana de cambio mensual 3,3; extremos a la mitad; 922 empresas puntuadas en agosto. No discrimina proxies de estrés mejor que V1 (ninguna lo hace) | `src/xray/score_v2/`, [scoring-v2.md](docs/scoring-v2.md), decisiones §13 |
| Comparador V1/V2 | Estabilidad, proxies (texto de estrés, caja negativa), riesgo por etiqueta, anticipación con regla independiente, sensibilidad | `src/xray/evaluation/`, [validation.md](docs/validation.md) |
| **Advisor: plan de grupo + sensibilidad de empresa** | `treasury_advisor_v1` (`src/xray/group_advisor/`): escenarios mecánicos valorados con la función de nivel exacta de V2. Plan de grupo (D1: la filial fuerte asume el servicio de deuda de la débil; P: financia el pago a proveedores en plazo si la receptora está restringida por liquidez), objetivo cóncavo por tramos, greedy determinista con certificado, evidencia por paso. Sensibilidad por empresa: qué palanca mueve más el nivel, hasta dónde vale y cuánto hace falta para cambiar de tramo. Narrativa por plantillas con validador de anclaje (todo número del texto existe en el JSON); LLM opcional no conectado. Agosto 2026: 19 grupos con plan, 160 sin palancas, 71 unipersonales; 949 empresas con sensibilidad; 0 fallos de anclaje | [group-optimization.md](docs/group-optimization.md), [roadmap-group-advisor.md](docs/roadmap-group-advisor.md), decisiones §14 |
| Alertas, API y demo | Diseños pendientes, sin despliegue ni métricas comprobadas | [alerts-and-monitoring.md](docs/alerts-and-monitoring.md), [product-and-demo.md](docs/product-and-demo.md), [embat_pulse_mvp_propuesta_final.md](docs/embat_pulse_mvp_propuesta_final.md) |

Otros documentos: [patron-tiempo-prestado.md](docs/patron-tiempo-prestado.md) (crédito comercial: puntualidad frente a conversión de caja).

## Datos

Dataset sintético: **1.286 sociedades en 250 grupos**, 24 meses (2024-09-01 → 2026-09-01; el último mes completo es **agosto de 2026**). Está generado a partir de la distribución de datos reales de tesorería de pymes. Los IDs (`company_id`, `group_id`, `product_id`, `counterparty_id`) son estables entre ficheros.

`data_summary/` contiene muestras pequeñas de cada tabla (en git) y el diccionario [`data_dictionary.md`](data_summary/data_dictionary.md):

| Fichero | Filas muestra | Filas completas |
|---|---:|---:|
| `groups.csv` | 32 | 250 |
| `companies.csv` | 9 | 1.286 |
| `banking_products.csv` | 9 | 5.987 |
| `debt_products.csv` | 9 | 2.239 |
| `debt_schedule_config.csv` | 9 | 87 |
| `balances.csv` | 9 | 7.996 |
| `invoices.csv` | 12 | 897.894 |
| `transactions.csv` | 10 | 2.556.437 |

El dataset completo (~615 MB) **no está en git**: `transactions.csv` e `invoices.csv` superan el límite de 100 MB de GitHub y `data/` está en `.gitignore`. Pedidlo a la organización y copiad los CSV originales en `data/raw/`, que **nunca se modifican**.

## Estructura

```
every.hackspain/
├── data/                  ← solo local, ignorado por git
│   ├── raw/               ← CSV originales (inmutables)
│   ├── cleaned/           ← salida de la limpieza (parquet + log + manifiesto)
│   └── processed/         ← features, scores y artefactos del producto
├── data_summary/          ← muestras y diccionario (en git)
├── docs/                  ← documentación técnica, producto y decisiones.md
├── resources/             ← artefactos estáticos versionados (categorías Jev, D31)
├── notebooks/             ← exploración (01) y análisis de limpieza (02)
├── scripts/               ← puntos de entrada del pipeline (00_…, 01_…)
├── src/xray/              ← código del pipeline
└── tests/
```

## Ejecutar lo implementado

```bash
python -X utf8 scripts/00_clean_data.py
python -X utf8 scripts/01_build_monthly_features.py
# opcional (D31): rellena movimientos sin categoría con el artefacto estático de Jev
# python -X utf8 scripts/01_build_monthly_features.py --ai-categories resources/jev_categories/template_categories.parquet
python -X utf8 scripts/02_validate_features.py
python -X utf8 scripts/03_compute_scores.py fit                 # V1 control -> data/processed/scores/
python -X utf8 scripts/04_validate_scores.py
python -X utf8 scripts/05_compute_scores_v2.py fit              # V2 -> data/processed/scores_v2/
python -X utf8 scripts/06_validate_scores_v2.py --check-prefix 2026-02-01
python -X utf8 scripts/07_compare_scores.py                     # V1 frente a V2 -> data/processed/evaluation/
python -X utf8 scripts/08_treasury_advisor.py                   # advisor: planes de grupo + sensibilidad -> data/processed/advisor/
python -X utf8 scripts/08_treasury_advisor.py --group GROUP_0067    # o --company COMP_0007: narrativa en consola, sin publicar
python -W error -m pytest -q                                    # 422 tests
```

`08` comprueba que `scores_v2/` se calculó sobre las features actuales; tras regenerar features hay que volver a ejecutar `03`/`05` (también con `--panel group_currency`).

`-X utf8` evita problemas con la consola de Windows. Basta con el entorno existente (pandas/numpy/pyarrow/pytest). `XRAY_DATA_DIR` permite usar otra raíz de datos. En código, la capa limpia se lee con `from xray.io import read_cleaned` (añadiendo `src/` al path o con `pip install -e .`).

Validación extendida de prefijo:

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
    scores_v2/                   V2 candidato: mismos ficheros + episode, momentum_z y diagnósticos bache/tendencia
    evaluation/
        score_comparison.json / score_comparison.md
    advisor/                     08_treasury_advisor.py
        group_plans/{group_id}.json|.md          plan de grupo y su narrativa
        company_sensitivity/{company_id}.json|.md   sensibilidad por empresa y su narrativa
        advisor_steps / advisor_groups / sensitivity_levers .parquet
        _advisor_report.json / _advisor_manifest.json
```

Ni V1 ni V2 usan snapshots/contextos ni eventos reservados como predictores. Incluir liquidez requiere un contrato versionado y la auditoría de decisiones §12. Las versiones anteriores de cada capa se conservan en `.history/`; no eliminarlas sin revisar si hacen falta. No sustituir missingness por 0 ni convertir el contexto retrospectivo en predictores históricos sin una decisión nueva documentada.

## Continuación

1. Producto y demo sobre V2 y el advisor: cartera con `trajectory`/`episode`; ficha con la tabla de contribuciones, el relato «nivel 6m · trimestre reciente frente a anterior · mes actual» y el bloque «Qué mueve tu nivel»; vista de grupo con el plan solo si hay ≥2 filiales puntuadas (decisiones §11, §13, §14; [group-optimization.md](docs/group-optimization.md) §13).
2. Confirmar unidad/formato y semántica de saldos con Embat. `scores_v2/company_latest_scores.csv` es candidato, no submission.
3. Liquidez como dimensión del nivel y fallback de exportación siguen pendientes (decisiones §12 y §13 SC13).
4. Versionar candidato y referencia; no recalibrar con el test oculto. Registrar lo adoptado y descartado en decisiones. No restaurar país (S01).

`CLAUDE.md` está excluido de git; la información imprescindible está duplicada aquí y en `docs/decisiones.md`.
