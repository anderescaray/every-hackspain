# Pulse → frontend: integración de contrato V1

**Estado de la rama `score_v2` (19-09-2026):** `scripts/09_export_frontend.py`
publica el run versionado `PulseFourPillars-v1.2` en un snapshot web atómico;
Next.js consume exclusivamente ese snapshot. El exportador `financial_smoothed_v2`
permanece en `src/xray/product/legacy_frontend_export.py` para investigación;
no existe fallback V2 en el loader. Los números, runs y snapshots v1.0/v1.0.1
de las secciones históricas de abajo **no describen** el nuevo run D32.

V1.2 conserva sin cambios las fórmulas de G/M/R/D y ambas composiciones Health
de v1.1. Versiona aparte `cleaning-v2`, `cash-truth-v2` y
`monthly-facts-v2`, porque D32 convirtió todas las monedas conocidas a EUR,
eliminó exclusiones por importe extremo/`exchange_rate` y cambió el
perímetro de los hechos mensuales. El manifiesto del run incluye el hash
de `xray/fx.py`; el metadata de clasificación incluye fecha de tasa, fecha
de conocimiento (2026-09-19), fuente y hash de la tabla de tipos fijos. El
pipeline rechaza un `data_vintage` anterior a esa fecha: `as_of=2026-08-31`
con vintage 2026-09-19 es un **restate retrospectivo**, no información conocida
al cierre de agosto ni al 1 de septiembre. Un salto v1.1→v1.2 no debe
etiquetarse como mejora/deterioro económico comparable. La composición
histórica v1.1 sigue registrada,
pero reproducirla exactamente requiere el código previo a D32.

El `main` posterior añade D38 (`is_technical_placeholder` en transacciones y
`is_sentinel_balance` en saldos). Son marcas diagnósticas: D32 mantiene esos
movimientos en los flujos de caja y el scorer Pulse no usa saldos de liquidez
reconstruida. Esta integración conserva esas marcas sin introducirlas como
nuevos gates o features puntuadas; el nuevo `run_id` registra el cambio de
código aunque los valores de pilares coincidan en la comparación reproducida.

## Fuente única y flujo

```text
CSV reales → limpieza → ledger Cash Truth → monthly facts
→ PulseFourPillars-v1.2 → run inmutable verificado
→ exporter de presentación → snapshot web inmutable → Next.js
```

El exporter **no calcula, ajusta, redondea ni completa** Health o pilares. Tampoco ajusta V2 ni consulta IA. El antiguo exportador se conserva separado en `src/xray/product/legacy_frontend_export.py`, exclusivamente para investigación; no es un fallback de la aplicación.

## Contrato

- Empresa `3.0`; cartera y grupo `2.0`; pointer y manifiesto web `1.0`.
- Todos los JSON comparten `snapshot_id`, `run_id`, `as_of`, `currency`, `score_version`, `classification_version`, `cleaning_version`, `facts_version` y `config_version`.
- `health_score` y `dimensions` copian valores **nullable** del motor. Los alias `cash_generation ← generation` y `debt ← debt_obligations` sólo cambian nombres.
- Cada empresa conserva `pulse` y `canonical_cash_truth` completos: features, contribuciones, límites, evidencia, confidence, flags, sensibilidad y trazabilidad originales.
- V1.0.1 distingue `complete_verified`, `complete_bounded`, `partial` e `insufficient_evidence`; muestra los puntos e intervalos recibidos, sin completar ni recalcular nada. Los snapshots V1.0 conservan sus estados `complete`, `partial` e `insufficient_evidence`. Este último identifica cuatro pilares nulos. Cero no equivale a `null`.
- La UI actual es una vista **EUR explícita**. Desde D32, el ledger convierte movimientos de moneda conocida a EUR con tipo fijo (`xray.fx`); cada empresa tiene un único panel EUR. Los importes sin moneda verificable permanecen no evaluables. La política de conversión es parte de la versión del run; ninguna empresa se excluye por Health nulo.
- No se inventan Health de grupo, histórico, pronósticos, emparejamientos de transferencias, apoyo confirmado ni confianza escalar. Los apartados sin producto de datos quedan vacíos o no evaluables.
- La columna heredada «Cobertura» consume una confianza escalar que este motor no define: aparece «No evaluable». El objeto `pulse.confidence` sí conserva cobertura histórica, clasificación, incertidumbre, perímetro, moneda y evidencia de deuda; no se confunde una de esas métricas con un índice compuesto.

## Publicación y lectura

```text
frontend/public/generated/
  current.json
  snapshots/web-<hash>/
    manifest.json
    portfolio.json
    companies/COMP_<id>.json
    groups/GROUP_<id>.json
```

El exporter verifica el manifiesto recursivo del run, prepara el snapshot completo y cambia `current.json` mediante rename atómico bajo lock. Comprueba rutas, symlinks, hashes y conflictos de snapshots existentes. Next fija el snapshot por petición y comprueba hashes/esquemas/procedencia al leer cada documento; nunca busca los JSON sueltos legacy. `PULSE_GENERATED_DIR` permite otra raíz absoluta compartida.

## Generación real

Desde `/Users/pablo/every.hackspain`:

```bash
/tmp/pulse_four_pillars_venv/bin/python -m xray.pulse \
  --raw-dir data/raw --out-dir data/processed/pulse \
  --as-of 2026-08-31 --data-vintage 2026-09-19

/tmp/pulse_four_pillars_venv/bin/python scripts/09_export_frontend.py \
  --run-dir data/processed/pulse/runs/<run_id> \
  --currency EUR --out-dir frontend/public/generated
```

La materialización histórica v1.1 pre-D32 tenía 1.286 empresas y 1.790 paneles empresa/moneda: 1.208 EUR y 582 de otras monedas. La nueva materialización v1.2 debe recalcularse con el ledger EUR consolidado, no reutilizar ese run. La fecha económica no se confunde con la fecha de conocimiento: los artefactos indican `retrospective_restatement`, no reconstrucción histórica de información disponible entonces. Los CSV originales no se modifican.

Para contener memoria se liberan las copias de tablas raw/cleaned únicamente después de persistir snapshots y hashes, sin cambiar cálculos ni contenido. El ledger ya se indexaba por empresa/moneda; no se vuelve a recorrer todo por empresa.

### Materialización V1.0 del 19 de septiembre de 2026 — baseline conservado

- Run completo: `pulse-9debd4f61f356501d9d171d8c114b35fe5d715e0c9434d7444c3200779ddfa05`.
- SHA-256 del manifiesto: `84151e98d557386173576d7303cdd64717b1b2a21d3e4efc6ba234340e387e64`.
- Duración del batch: **12m20**, salida normal `0`; 2.545.046 filas de ledger, 42.960 monthly facts y 1.790 resultados. El run anterior limitado a COMP_1084 permanece disponible.
- Estado original Pulse: 16 `complete`, 1.774 `partial`. Para EUR, la presentación distingue 16 `complete`, 939 `partial` y 253 `insufficient_evidence`, sin eliminar empresas ni alterar el objeto original.
- COMP_1084: Health y Deuda `null`; Generación `0`, Momentum `57.43434743818346`, Resiliencia `0`. No se sustituye su Health por el subtotal de pilares conocidos.
- Los ocho SHA-256 raw coinciden con `/tmp/pulse-four-pillars-raw-before.sha256`. Los artefactos de ejecución están ignorados por Git; no se añadieron como archivos versionados.
- Snapshot web final: `web-86e651dd87e159be5bd06c32a668a5112b3d57e5a3c55a7028faefe6165612b4`; SHA-256 del manifiesto `9a3b4188845a0cb8de53da84c6be86272c50fa8bb59df45496b97ea67443a5e3`. Exportación normal terminada: 1.208 empresas EUR y 248 grupos, con los mismos estados anteriores. El snapshot provisional real de una sola empresa se conserva, pero ya no es `current`.

## Verificación y límites de la integración original V1.0

Por pedido explícito, **no se ejecutaron tests de validación**, suites, E2E ni scripts standalone de validación en esta integración. Los owners escriben regresiones de contrato sin ejecutarlas. Se permiten lint, comprobación de tipos, build solicitado y las comprobaciones inherentes a la ejecución normal del batch/exporter/loader. La revisión semántica es estática; no debe confundirse con cobertura ejecutada.

No hay cambios en fórmulas/pesos del motor, nuevo endpoint FastAPI, rediseño visual, commit ni push. Los cálculos financieros permanecen en Python; Next sólo presenta valores recibidos.

Quedan fuera de esta entrega una UI multimoneda, conexión API adicional y nuevas visualizaciones para toda la trazabilidad estructurada: el JSON ya conserva esos datos, pero no se añaden secciones visuales para ellos.

## Patch Debt V1.0.1

La configuración y los artefactos V1.0 y v1.0.1 se conservan. La composición Operating/Extended de v1.1 también permanece inmutable; v1.2 conserva las mismas fórmulas pero versiona el cambio upstream D32 de FX/limpieza/clasificación/facts. El patch añade evaluación financiera conservadora de salidas inciertas y publica intervalos de identificación; no modifica G/M/R ni la caja canónica. La política exacta y sus límites están en la sección 14 de `pulse-four-pillars-v1-implementation.md`.

Una empresa `complete_bounded` tiene un punto explícitamente estimado, no evidencia de deuda `verified`. El intervalo Health sólo propaga el intervalo Debt con los demás pilares/hechos fijos: **no es un intervalo de confianza ni toda la incertidumbre de clasificación**. La UI usa el estimador, motivo e intervalos calculados por Python.

Para este patch el usuario sí autorizó pruebas focalizadas: 24 ledger, 55 motor, una integración determinista, 20 exporter y 24 contratos frontend pasan; comprobaciones rápidas de lint/tipos y build frontend pasan. No se volvieron a ejecutar las suites generales históricas ni se añadieron endpoints. Un primer intento de batch se interrumpió antes de publicar al detectar una regresión de atribución; se corrigió y quedó cubierta por una prueba focalizada antes de reiniciar.

### Materialización V1.0.1 y comparación exacta

- Batch normal: **18m02**, salida `0`, del 2026-09-19 17:05:43 al 17:23:45 UTC; mismos argumentos, raw, fecha económica y vintage que el baseline, sin AI ni refit legacy.
- Run `pulse-7c9bd83dbe4dbb4505918267e021f98e3706c43fe0669beb60cd0fecbe61c649`; manifiesto SHA-256 `5b229e451f733f91a83487362ab34ab7d986746c6c01ca277765c35aa2663ceb`.
- Snapshot web `web-5156ee063698c7ab1a7923d13522f3747553e450a079a264781363cfd8af49e4`; manifiesto SHA-256 `4733e1c3f65015fc79e28269eac1112f3e2306dd5c5bae8564c8b5d603e9d365`. Mantiene 1.208 empresas EUR, 248 grupos, 582 paneles de otras monedas excluidos explícitamente y 78 empresas sin EUR. Los artefactos anteriores permanecen intactos.
- Los 1.790 paneles conservan **G/M/R idénticos bit a bit** (`float.hex`), incluidos sus nulos; todos los `economic_facts`, 50 columnas originales de las 2.545.046 filas ledger, 42.960 filas de hechos anteriores y listas normalizadas de cuentas activas son iguales. Sólo se añaden evidencia/campos y versiones. Los ocho SHA raw y hashes de inputs consumidos coinciden; los 16 Health/Debt previamente válidos tampoco cambian.

| Presentación EUR | V1.0 | V1.0.1 |
|---|---:|---:|
| Complete / complete_verified |16|16|
| complete_bounded |0|136|
| partial |939|804|
| insufficient_evidence |253|252|

Se identifican **136 Health adicionales**, todos procedentes de empresas que sólo tenían Debt ausente. `COMP_0076` identifica únicamente Debt: G/M/R siguen nulos por O6=0 y Health sigue nulo; pasa legítimamente de insufficient a partial. G/M/R mantienen 955 válidos y 253 nulos cada uno. Los patrones nuevos son: 152 sin componentes ausentes, 803 sólo Debt ausente, una sólo G/M/R ausentes, 252 con cuatro ausentes.

| Evidencia Debt V1.0.1 | Total EUR | Punto válido | Punto nulo |
|---|---:|---:|---:|
| verified |16|16|0|
| bounded |137|137|0|
| partial |392|0|392|
| unknown |663|0|663|

No se confunden estados de evidencia y scores: V1.0 tenía 25 `verified`, pero nueve no puntuaban por I6=0. Ahora los 1.055 puntos Debt nulos registran: 463 sin servicio identificado, 234 historia incompleta, 310 intervalo demasiado ancho, 30 salidas excluidas, dos moneda incierta y 16 I6=0. El cruce observado de los 392 con evidencia `partial` es **310 anchura +34 historia +16 I6=0 +30 exclusiones +2 moneda**; `unknown` comprende 463 sin servicio y 200 historias incompletas. Las 34 historias incompletas con servicio observado conservan ese importe; no son ausencia de servicio.

### Anchuras del intervalo Debt

**Universo de la tabla: 463 EUR con intervalo finito**; los otros 745 no tienen rango evaluable y quedan fuera del denominador. Se incluyen explícitamente los 16 verified con anchura cero. Cortes acumulados (NO sumables): ≤1: **116**, ≤2: **126**, ≤5: **153**, ≤10: **178**; >10: **285**.

| Tramo disjunto | Todas con rango (N=463) | Antiguas partial sólo por Debt, con rango (N=446) |
|---|---:|---:|
| ≤1 |116|99|
| >1 y ≤2 |10|10|
| >2 y ≤5 |27|27|
| >5 y ≤10 |25|25|
| >10 |285|285|

En la cohorte original de 939 partial, 446 tienen ahora rango y 493 siguen sin rango; cortes acumulados ≤1/≤2/≤5/≤10: 99/109/136/161. Las 136 nuevas Health incluyen **75 con Debt saturado en `[0,0]`** y 61 con anchura positiva ≤5. En todo EUR hay 76 bounded de anchura exactamente cero (el adicional es COMP_0076), todos por saturación en cero: **no implica incertidumbre monetaria pequeña**, sino insensibilidad del score en esa región. Ninguna salida se declaró `debt_impossible`; potencialmente financiero coincide exactamente con la incertidumbre original.

| Caso real EUR | Resultado patch | Debt / rango | Motivo |
|---|---|---|---|
| COMP_0001 | complete_bounded; Health 27.125483261960216 |99.9501962443776; `[99.94547055991742,99.95492192883778]`|S identificado30; incertidumbre6.29; anchura0.009451368920352365|
| COMP_1084 | partial; Health null |null; sin rango|S identificado0; ausencia NO verificada; G0/M57.43434743818346/R0 intactos|
| COMP_0003 | partial; Health null |null; `[0,99.68572163184643]`|S identificado180; incertidumbre10,050,757.07; anchura material99.68572163184643|

Informes analíticos de esta ejecución (sólo lectura de salidas): `/tmp/pulse-debt-hardening-output-report.json`, `/tmp/pulse-debt-invariants.json`; no generan scores alternativos. No se publicaron CSV ni artefactos runtime en Git.
