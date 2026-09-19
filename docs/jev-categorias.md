# Categorías AI para movimientos sin categoría (D31) — nota de relevo

**Para quien esté tocando `clean/`, `features/` o `score_v2/` en paralelo.** Este documento explica qué añade D31, qué archivos toca, qué NO toca y cómo convive con D25–D30 / FE10. Registro de decisión y cifras en [decisiones.md](./decisiones.md) §15.

## Qué problema resuelve

El 24,9 % de las filas y el **38,8 % del importe** de transacciones no tienen categoría de banco (`uncategorized`). Como FE03 solo cuenta como operativo lo que tiene categoría, el margen `(in−out)/(in+out)` se calcula sobre ~la mitad de los flujos, y en bancos no españoles (HSBC/ING/Revolut, 76–85 % sin categoría) el nivel del score es directamente ficticio (ej. COMP_0045 con score 100 porque todas sus salidas eran `SEPA Overboeking` invisibles). Es el punto 5 de `hallazgos-datos.md` §11 («fallback para >40 % sin categoría»), resuelto con categoría real en lugar de fallback por signo.

## Qué es Jev y por qué encaja

Jev (TypeSafe) no genera texto: recibe un `state` y preguntas tipadas y devuelve una elección con distribución de probabilidad y `confidence`. Se usó **una sola vez, offline**, para clasificar cada plantilla de texto bancario en 12 bloques económicos. El resultado es un parquet estático versionado; **el pipeline no llama a ninguna API** y no hay dependencia nueva (se usó `urllib`). Los créditos de la cuenta se agotaron al final de la pasada: no se puede volver a ejecutar sin recargar.

## Archivos

| Archivo | Estado | Qué es |
|---|---|---|
| `resources/jev_categories/template_categories.parquet` | **versionado, 11 MB** | Una fila por (plantilla, signo): `jev_block`, `jev_confidence`, `jev_coarse`, `sign_conflict`, dos `noul_*`, categoría del banco si la había, conteos |
| `resources/jev_categories/_manifest.json` | versionado | Preguntas exactas enviadas, mapeos, hashes, conteos |
| `src/xray/features/ai_categories.py` | nuevo | `template()`, `load_template_categories()`, `apply_ai_categories()`, `BLOCK_TO_CATEGORY` |
| `src/xray/features/config.py` | +2 campos | `ai_categories_path: str | None = None`, `ai_min_confidence: float = 0.7` |
| `src/xray/features/transactions.py` | hook en `prepare_transactions` | Aplica el artefacto si hay ruta; añade `tx_ai_categorized_amount`, `tx_ai_nonoperating_amount` a `AMOUNTS` |
| `src/xray/features/__main__.py` | +2 flags | `--ai-categories PATH`, `--ai-min-confidence 0.7` |
| `src/xray/features/__init__.py` | +1 clave manifiesto | `ai_categories_sha256` |
| `tests/test_ai_categories.py` | nuevo, 5 tests | plantilla estable, solo `uncategorized` cambia, umbral, `tax_refund`, integración en `build_features` |
| `scripts/experimental/jev_categorize_{prototype,all}.py` | experimental | Cómo se generó el artefacto; no forman parte del pipeline |
| `data/enriched/` | gitignored | Respuestas crudas (99 MB), universo, log de la pasada |

## Cómo funciona `apply_ai_categories` (en `prepare_transactions`, antes de FE03)

1. Solo filas con `category == "uncategorized"` (el valor que fija T04). **La categoría del banco nunca se sobreescribe.**
2. Calcula `template(description)` y `sign(amount)`, hace `merge` con el artefacto.
3. Mapea `jev_block → categoría FE03`:
   - `operating_inflow→collection`, `supplier_payment→payment`, `utility/salary/social_security/tax` iguales, `tax` con signo `+` → `tax_refund`, `bank_fee→fee`
   - `internal_transfer/cash/bank_adjustment → "ai_nonoperating"` (categoría nueva: fuera de `INFLOW/OUTFLOW`, entra en `tx_cash_*` como cualquier fila utilizable)
   - `interest_or_debt → None` (no se usa: acuerdo débil con el banco) y `unknown → None`
4. Acepta solo si `jev_confidence ≥ ai_min_confidence` y no hay `sign_conflict` (bloque operativo incoherente con el signo; ya vetado en el artefacto).
5. Escribe `category` (nueva), y conserva `category_bank`, `category_source ∈ {bank, ai, none}`, `category_ai_confidence`.

Sin `ai_categories_path`, `prepare_transactions` solo añade `category_source = "none"`: ninguna feature ni score cambia (verificado: `is_training_eligible` idéntico, 233 tests).

## Interacción con D25–D30 y FE10

- **D26 `is_scf_adjustment`, D27 `is_repo_pair`, D28 `is_cash_disposal`**: son flags en cleaned; D31 clasifica esos mismos textos como `bank_adjustment`/`internal_transfer`/`cash` → `ai_nonoperating`. Son coherentes y redundantes; si en features se decide excluir D26–D28 de `tx_cash_*`, hacerlo por el flag (más preciso) y dejar D31 para el resto.
- **D29 pasarela**: `[fecha] stripe_fee` etc. sin categoría desde 2025-01 → Jev los manda a `bank_fee` (→ `fee`), lo que recompone `tx_fees_paid` tras la ruptura. No toca `interest_charge`.
- **D30 `event_type`**: el artefacto trae `noul_unpaid_return` (129 plantillas / 10.307 filas ≥ 0,7, p. ej. `COBRO DE EFECTOS DEVUELTOS`, `DEVOL DE TITULO`) y `noul_overdraft_or_seizure` (409 / 3.960). **Ninguna feature los consume todavía.** Son un complemento semántico y multilingüe a los regex de D30; distinguen «devolución de fianza / error» de «recibo devuelto por impago», que el regex `DEVOLUC` no distingue.
- **FE10 `coverage_state`**: independiente. D31 no cambia `tx_count` ni `tx_usable_count`, así que `dormant`/`onboarding` no se mueven. Sí sube `tx_operating_amount_share` (mediana 0,557 → 0,630) y por tanto menos meses caen por «<10 % operativo» en el score.
- **score_v2**: no requiere cambios; consume `tx_inflow/tx_outflow` como siempre. El A/B está en `data/processed_ai/` (features + `scores_v2`) frente a `data/processed/`.

## Cómo regenerar con D31

```bash
python -X utf8 scripts/01_build_monthly_features.py --ai-categories resources/jev_categories/template_categories.parquet
python -X utf8 scripts/05_compute_scores_v2.py fit
```

Para un A/B sin pisar `processed`: añadir `--out-dir data/processed_ai` y `--features-dir data/processed_ai --out-dir data/processed_ai/scores_v2`.

## Resultado del A/B (misma cleaned)

| | Base | D31 |
|---|---:|---:|
| Empresa-mes (≥5 mov.) que fallan «≥10 % operativo» | 2.188 | 1.164 (0 nuevos fallos) |
| Score V2 agosto: puntuadas / `not_scored` | 922 / 364 | 977 / 309 |
| Filas puntuadas en toda la historia | 14.084 | 14.932 (+848, 0 perdidas) |
| Δ score donde ambas puntúan | — | mediana 0,78; >10 pts en 7,2 %, revisados como correcciones reales |
| Acuerdo con el banco en control (bloque grueso, conf ≥ 0,7) | — | 85 % (suelo: el banco tiene errores visibles) |

## Qué NO hacer

- No modificar `template()` sin regenerar el artefacto: la clave de join es la plantilla exacta. Está definida en `ai_categories.py` y los scripts experimentales la importan de ahí.
- No aplicar D31 en cleaned: A03 (cleaned marca, features decide). Si se quiere una columna en cleaned, que sea `category_ai`+`confidence`, nunca sobre `category`.
- No usar `interest_or_debt` para servicio de deuda sin revisar el control (acuerdo 4/10 en la muestra).
- No interpretar el 85 % como accuracy: se mide contra la categoría del banco, que no es oro.

## Pendientes (decidir en equipo)

1. ¿D31 pasa a default? Implica regenerar `processed`/`scores_v2` y actualizar SC10/§13.
2. Umbral 0,7 propuesto; comparar 0,6/0,85 con el mismo holdout.
3. Consumir los `noul_*` en `event_type`/`stress_events` o dejarlos como reservados.
4. Un dataset nuevo (test oculto) con plantillas no vistas queda `uncategorized` como hoy; haría falta otra pasada con créditos.

---

## Anexo A · Cómo se llegó a D31: análisis previo y prototipo

Antes de la pasada completa se evaluó, con cifras sobre el dataset, dónde podía aportar Jev. Se conserva aquí el razonamiento para no repetirlo.

### A.1 Qué es Jev y qué lo hace apto para este pipeline

Jev (TypeSafe, «System One model») no genera texto: recibe un `state` (texto u objeto) y un mapa de preguntas tipadas, y devuelve una respuesta estructurada por pregunta. Tres primitivas: **Choice** (una opción de una lista → `choice`, `probabilities`, `confidence`), **Score** (nivel en una rúbrica ordenada → `score`, `probabilities`, `confidence`) y **Noul** (¿es cierta esta afirmación? → 0–1). Todas las preguntas de una llamada se evalúan en paralelo y aisladas contra el mismo state; añadir preguntas apenas cambia latencia ni coste. La doc recomienda preguntas atómicas (una cosa cada una) y combinar en código. Encaja con la regla de oro del proyecto («el LLM nunca calcula un número»): Jev decide una categoría por texto; el número lo calcula FE03 como siempre. Endpoint `POST https://api.typesafe.ai/v1/systemone`, sin batch, con 429/529 reintentables; se usó `urllib` para no añadir dependencias (A02).

### A.2 Candidatos evaluados y por qué se eligió el de categorías

| Candidato | Evidencia medida | Decisión |
|---|---|---|
| **Categorizar movimientos sin categoría** | 635.860 filas (24,9 %) = 38,8 % del importe; importe sin categoría ≈ 0,95× el operativo identificado; 293 empresas con >50 % sin categoría; si todo lo sin categoría fuese operativo, el margen cambiaría >0,10 en el 33 % de empresa-mes y de signo en el 15 %; 1.786 empresa-mes fallaban el filtro «≥10 % operativo» y en el 79 % la causa era esta | **Elegido (D31)**: problema de medición, no solo de cobertura; texto multilingüe (ES/PT/FR/NL/DE/IT/NO/EN) inabordable con regex |
| Eventos de estrés semánticos | Regex actual: 10.072 filas / 333 empresas. Ampliarlo por palabras clave (25.222 / 846) falla: `DEVOLUCION` es mayoritariamente fianzas, reembolsos tributarios o transferencias devueltas por error | Incluido como 2 `Noul` en la misma llamada (coste marginal ~0). Aún sin consumir |
| Documentos ambiguos de facturas (D11) | `note`+`refund`+`invoiceGroup` = 53.947 filas / 574 empresas, pero solo 23 empresas donde superan el 30 % de sus documentos; el concepto suele ser no informativo (`CM-4063`, `Opening Balance`); el signo ya da AR/AP | Descartado: no mueve el score |
| Etiquetas para la ficha / triage de alertas | No evaluable sin `processed` en la máquina; conceptualmente cosmético: el score ya trae explicación aditiva exacta y trayectoria | Descartado para la entrega; ver Anexo B |
| Sector por contrapartes | Riesgo de sesgo, sin referencia para validarlo, exigiría cambiar SC03 | Descartado |

### A.3 Prototipo (1.274 plantillas, 228 s, 0 errores)

1.000 plantillas sin categoría más frecuentes (270k filas) + 274 de control con categoría del banco. Acuerdo Jev↔banco: **45 %** en 12 bloques finos, **61 %** en 5 bloques gruesos FE03; con `conf ≥ 0,7`, 60 % / 70 %; con `≥ 0,85`, 67 % / 77 %. Al revisar los desacuerdos, muchos eran errores del banco (`PRIMEVIDEO.ES`=utility, `FACEBK ads`=fee, `CLARET LOAN`=tax, `TRANSF INTERNA`=tax, `MOD353 IVA`=debt_repayment), y en la matriz gruesa no había cruces `op_in↔op_out`. Conclusiones que fijaron el diseño: (1) trabajar a nivel grueso, (2) umbral 0,7, (3) veto por incoherencia signo/bloque, (4) `interest_or_debt` fuera (acuerdo 4/10), (5) `unknown` con alta confianza es texto redactado irrecuperable (~53 % del importe sin categoría en la muestra; 13 % en la pasada completa tras excluir extremos D01).

Coste/cobertura para dimensionar la pasada: 140.818 plantillas sin categoría; `rows≥5` = 14.805 plantillas → 73 % filas / 75 % importe (~45 min); `rows≥2` = 41.742 → 84 % / 87 % (~2 h); todas → 100 % (~7 h a 5,6 req/s; al final fueron 80 min a ~30 req/s con 32 hilos). Se eligió «todas» + 5.000 con categoría como control.

## Anexo B · Otras aplicaciones de Jev evaluadas (propuestas, no implementadas)

Restricción: los créditos de la cuenta se agotaron al final de D31. Lo marcado «gratis» usa lo que ya está en el artefacto; lo demás requiere recarga y una nueva pasada única con la misma arquitectura (script reanudable → parquet estático versionado → manifiesto).

| # | Aplicación | Para qué pilar | Coste | Valor esperado |
|---|---|---|---|---|
| B1 | Consumir `noul_unpaid_return` (129 plantillas / 10.307 filas ≥0,7) y `noul_overdraft_or_seizure` (409 / 3.960) en `event_type` (D30) | Anticipación con ancla independiente | **Gratis** | Distingue «recibo devuelto por impago» de «devolución de fianza/error»; multilingüe |
| B2 | `cash_certainty` en `product/confidence.py` = parte identificada × `category_ai_confidence` | Confidence | **Gratis** | Usa la confianza para lo que TypeSafe la publica |
| B3 | Rol de contraparte `{customer, supplier, bank_or_lender, tax_authority, social_security, payroll, payment_processor, group_or_shareholder, public_grant}` sobre narrativas agregadas por contraparte (~48k bancarias + facturas) | Cash Truth / Time Borrowed | Pasada ~1 h | Separa cobro de cliente vs aportación de socio; pago a proveedor vs devolución al grupo |
| B4 | Dos `Noul` específicos «es cargo de intereses» / «es cuota de préstamo o leasing» sobre plantillas de `debt_repayment`, `interest_charge`, `fee` | Servicio de deuda desde transacciones (hallazgos §7, §11.7) | Misma pasada | Repara la ruptura D29 de `interest_charge`; el bloque genérico `interest_or_debt` falló, dos preguntas atómicas es lo que recomienda la doc |
| B5 | `Noul` «pago recurrente contractual (alquiler, leasing, seguro, suscripción, cuota)» | `tx_fixed_cost_coverage` | Misma pasada | Un alquiler de 9.000 €/mes etiquetado `utility` hoy no cuenta como fijo |
| B6 | `Choice` tipo de impuesto `{vat, corporate_tax, withholding, social_security, local_tax, customs, other}` | Estacionalidad (hallazgos §3: julio = 13,7 % del año) | Misma pasada | «Descubierto en mes de IVA» ≠ «descubierto estructural» |
| B7 | Pantalla 0 «Import Dataset»: calcular plantillas, buscar en caché, **llamar a Jev solo para las no vistas**, guardar | Producto / test oculto | Créditos + decisión de arquitectura | Única aplicación «en vivo» coherente con «la API sirve, no calcula»; argumento comercial directo (Embat tiene 25 % sin categoría) |

B3–B6 pueden ir en **una sola pasada combinada** (varias preguntas por llamada ≈ mismo coste que una): ~150k llamadas, ~80 min.

### No recomendado

- Jev juzgando números (¿bache o caída?, ¿prioridad de revisión?): está hecho para leer estados textuales; la regla de racha/confirmación de V2 lo hace mejor y sin romper «el LLM nunca calcula».
- Jev como redactor de fichas o narrativas: no genera texto.
- Facturas ambiguas (D11) y sector por contraparte: ver A.2.
