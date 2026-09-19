# Hallazgos no evidentes en los datos (para el motor de scoring)

Análisis exploratorio sobre `data/*.csv` (raw), 19-09-2026. Scripts de apoyo en `data/_cache/a*.py` (gitignored). Cifras verificadas sobre el dataset completo; no son interpretación del organizador.

## 1. La trayectoria "obvia" es un artefacto de cobertura

- Solo **439 de 1.286 empresas** tienen movimientos en 2024-09. Las altas se concentran en **enero 2025 (128)** y **enero 2026 (132)**; el volumen total de transacciones se multiplica por 4,5 (42k → 185k/mes) por onboarding, no por crecimiento.
- El histórico bancario típico empieza **~2 meses antes de `created_at`** (moda: 372 empresas). Todo lo anterior a la conexión es backfill parcial.
- **580 empresas** tienen ≥4 meses "dormidos" (≤3 movimientos, <2.000 de importe: comisiones de 12 €, 30 €, 182 €, 250 €) antes de la actividad real. Las 5 empresas con mayor pendiente positiva de entradas son cuentas que pasan de solo-comisiones a operativa (COMP_0794: 1 → 792 mov/mes en 26-02).
- Las 5 empresas con mayor caída son **desconexiones**, no colapsos: la actividad cae a 1-2 movimientos de comisión (COMP_0612 → 30 €/mes desde 26-01). **39 empresas** acaban dormidas tras ≥6 meses activas; **307 de 2.560 cuentas** activas se silencian >60 días antes del cierre y su saldo final mediano es **0,33** (cuenta cerrada, dinero movido a otra cuenta).

Implicación: sin detectar "mes dormido" y sin crecimiento like-for-like por cuenta, el momentum premia altas y castiga cierres de cuenta.

## 2. El ruido mensual es blanco: un mes no dice nada

- Autocorrelación lag-1 de la desviación mensual del margen `(in−out)/(in+out)` respecto a la media de la empresa: **−0,03**; tras quitar tendencia lineal, **−0,13** (entradas: −0,04). Es ruido blanco alrededor de un nivel.
- Desviación típica intra-empresa del margen mensual: **mediana 0,34**. Las anclas del score van de 0→55 a 0,25→90: un solo mes recorre toda la escala por azar.
- P(mes malo) = 0,24; P(malo | malo anterior) = 0,32. Rachas malas: 1.567 de longitud 1, 364 de 2, 95 de 3… solo **27 rachas ≥6 meses** — esos son los deterioros estructurales reales.
- Correlación entre la pendiente de entradas de los 12 primeros y los 12 últimos meses: **0,015**. No hay tendencias lineales persistentes; lo que hay son niveles con saltos.

Implicación: "bache vs caída" = longitud de racha y cambio de nivel sostenido (≥4-6 meses), no delta a 3 meses. El momentum actual (`tanh(Δ3m/0,10)`) satura por ruido: la std de un delta 3m de la media 3m es ≈0,28, casi 3× la escala.

## 3. Estacionalidad fuerte y asimétrica

Desviación media del log de entradas (sin tendencia, empresas con ≥18 meses): **dic +0,33, jul +0,32, ago −0,39, feb −0,26**, sep-2024 −0,56 (mes de backfill parcial). Impuestos: **julio = 13,7 % del año** (IS + IVA T2), abril 9,4 %, octubre 8 %, enero 7 %; día 20. Los descubiertos (`DESCUBIERTO/EXCEDIDO`) tienen pico en **ene/abr/jul/oct** (2,0-3,0 % de empresas vs 0,2-0,8 % el resto).

Implicación: comparar jul→ago sin ajuste estacional produce una "caída" del 50 % cada año; un descubierto en mes de impuestos es menos informativo que uno en mes normal.

## 4. La taxonomía de categorías cambia en enero 2025

Comparando las mismas 528 empresas activas en ambos periodos:

| categoría | antes de 2025-01 | desde 2025-01 |
|---|---|---|
| `payment_refund` | 244/mes, **1 % positivos** | 36/mes, **100 % positivos** |
| `collection_refund` | 75/mes, **90 % positivos** | 535/mes, **0 % positivos** |
| `interest_charge` | 451/mes; incluye `STRIPE_FEE`, `NETWORK_COST`, `REFUND` | 243/mes; esos textos pasan a `-` |

Implicación: cualquier feature por nombre de categoría (refunds, `interest_charge` para servicio de deuda) tiene una ruptura estructural en 2025-01. Usar el signo, no el nombre; y para intereses excluir descripciones de pasarela de pago.

## 5. Sin categoría = 39 % del importe, y depende del banco

- `-` es el 25 % de las filas pero el **38,8 % del importe absoluto**. Por empresa: mediana 10 %, **P75 43 %, P90 77 %**.
- Está determinado por el banco/país: HSBC 85 %, ING 85 %, Revolut EU 76 %, "Other (customer-defined)" 67 %, GBP/USD ~70 %, vs Santander Empresas 3 %, Sabadell 1 %.
- Dentro de `-` hay bloques enormes e identificables: `SCF-AJUS.SALDO` (16.356 filas, 42 empresas, ~1.400 M en valor absoluto: ajustes de confirming/Supply Chain Finance), pares espejo `PR.A`/`VT.A` (repos de tesorería, sumas idénticas 2,22e8), `DISP.ENTREG.EFECT.` (disposiciones de efectivo), textos bancarios extranjeros (`SEPA OVERBOEKING`, `PAYOUT`, `REMISE`).

Implicación: un score basado solo en categorías operativas está ciego o sesgado para ~25 % de las empresas y penaliza sistemáticamente a las de banca no española. Hace falta un fallback por signo (neto de todo lo que no sea espejo/intragrupo) y un peso de cobertura explícito.

## 6. Cuentas de crédito usadas como cuenta operativa

- **312 pólizas de crédito** tienen movimientos (182k, 7 % del total) en **170 empresas**: cobros, nóminas, impuestos… se operan desde la línea. La reconstrucción de caja solo con `checking` las ignora.
- En `balances`: `liquidity = balance − granted` (disponible); utilización = `balance/granted`. Mediana 9 %, **P75 85 %, P90 100 %**; 45 líneas con `granted == balance` exactos (disponible 0, probablemente `granted` desconocido y rellenado con el saldo).
- Reconstruyendo saldo hacia atrás (foto − movimientos posteriores) se obtiene utilización mensual para **106 líneas / 59 empresas** con ≥12 meses; el 20 % cambia más de ±0,5 entre inicio y fin.

Implicación: la utilización de póliza es una señal de tesorería directa (más que el margen de flujos) para ~10 % de empresas; hoy no se usa.

## 7. La deuda de `debt_products` no es la deuda real

- **523 empresas pagan cuotas** (`debt_repayment`) pero solo **378 tienen productos de deuda**: 239 pagan préstamos que no figuran; 94 tienen producto sin cuota observada. El 38 % de los `loan` tienen `outstanding = 0`.
- Entre pagadores regulares (≥8 meses de cuota), **~37 dejan de pagar ≥3 meses antes de su último mes activo**. Casi ninguno acaba dormido; varios tienen `outstanding` grande (COMP_0594: −7,7 M, además con impagos) → parada de cuota con saldo vivo = señal de estrés; con saldo 0 = préstamo amortizado (señal positiva).
- `CUOTA IMPAGADA` en `debt_repayment`: **356 filas, 60 empresas**, repartidas uniformemente en el tiempo (2-6 empresas nuevas por mes). Es el evento de estrés más limpio del dataset.

## 8. Eventos de estrés en texto: pocos pero limpios

Empresas con ≥1 evento: devolución de recibo 382, embargo 159, descubierto 95, recargo/apremio/sanción 85, aplazamiento 76, cuota impagada 60, reclamación 51, demora 31. El **41,8 %** de las empresas tiene alguno.

- **Embargo crece de 0,8 % a 2,5-3,0 % de empresas activas/mes a lo largo de 2026**: hay un deterioro agregado real en la cola del dataset.
- `IMPAGADO` en `collection_refund` (6.934 filas): recibos girados a clientes que vuelven = tus clientes no pagan; distinto de la cuota impagada propia.
- Falsos positivos a evitar: `NOMINA` aparece en `bulk_collection` como "LIQUIDACION NOMINAL REMESAS" (35 empresas); `RENOVACION` es "Renovación de lote (app)" de céntimos.

## 9. Facturas: `overdue` es higiene del ERP, no impago

- 22 % de las facturas están `overdue`. La proporción **no decae con la antigüedad**: facturas emitidas en 2024-09 siguen 16-19 % overdue dos años después; el 96 % de las overdue tienen `payment_date == due_date` (fecha prevista, no real).
- Por empresa, el overdue por importe es un efecto fijo: **P90 = 84 % en AP y 96 % en AR**, 111 empresas con >50 % de AP "vencido" (imposible operativamente). Correlación AR-AP de overdue por empresa: 0,59 → mide al usuario del ERP, no al deudor.
- El 39 % de las facturas tienen plazo 0 y el 49 % de las pagadas se pagan exactamente el día de vencimiento: la **mediana de retraso es 0 casi siempre**; la señal está en la cola (p75/p90, proporción tardía ponderada por importe), no en la mediana.
- Cruce factura↔banco (misma empresa, `counterparty_id`, importe exacto, signo): **19,7 % de facturas** casan (150k). Da un "DSO real" (mediana 20 días AR, retraso real +4) y demuestra que **12.186 facturas overdue están cobradas/pagadas en banco**. Limitado porque el 90 % de las transacciones no traen `counterparty_id`.
- Concentración AR: el **cliente top-1 es el 54 % de la facturación (mediana)**; el 25 % de las empresas dependen >92 % de un cliente.

## 10. Lo que NO hay

- `counterparty_id` está anonimizado **por empresa**: 0 contrapartes de factura compartidas entre empresas, 91 de 47.796 en banco (solo pares). No hay red ni contagio observable; el HHI local sí.
- Correlación intra-grupo de tendencias de entradas: **0,023** (vs 0,02 aleatorio). El grupo no informa la trayectoria de la filial.
- `country` 82 % nulo; `balances.available` 100 % nulo; `debt_schedule_config` solo 87 filas.

## 11. Recomendaciones concretas para el motor

1. **Máscara de cobertura antes que nada**: mes dormido (≤3 mov y <2k), cuenta nueva/cerrada, cambio en el nº de cuentas activas → no puntuar momentum ese mes; crecimiento solo like-for-like.
2. **Nivel = media robusta de ≥6 meses estacionalmente ajustada** (factores mes-del-año de la propia muestra: ago/feb negativos, dic/jul positivos). Un mes vale poco.
3. **Trayectoria = cambio de nivel sostenido** (p.ej. media 6m vs 6m previos, o CUSUM) + longitud de racha; no delta 3m con escala 0,10.
4. **Señales de estrés discretas con peso propio**: cuota impagada, embargo, apremio, aplazamiento, parada de cuota con saldo vivo, descubierto fuera de mes fiscal, utilización de póliza >85 % y creciente.
5. **Fallback por signo para empresas con >40 % sin categoría**, excluyendo espejos propios, intragrupo, `SCF-AJUS`, pares `PR.A/VT.A`; publicar cobertura como atributo del score.
6. **Facturas**: usar cambios intra-empresa de aging y colas (p90, tardío ponderado), nunca nivel de `overdue`; complementar con DSO real vía cruce banco donde exista.
7. **Deuda**: servicio de deuda desde transacciones (no desde `debt_products`); `interest_charge` pre-2025 filtrado de textos de pasarela; refunds por signo.
8. **Descuento de la cola temporal**: el aumento de embargos en 2026 sugiere que el test oculto puede contener más deterioros recientes; medir anticipación contra eventos discretos (§7-8), no contra el propio score.
