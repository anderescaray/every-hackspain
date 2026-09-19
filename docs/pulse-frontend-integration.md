# Pulse → frontend: integración de contrato V1

## Fuente única y flujo

```text
CSV reales → limpieza → ledger Cash Truth → monthly facts
→ PulseFourPillars-v1.0 → run inmutable verificado
→ exporter de presentación → snapshot web inmutable → Next.js
```

El exporter **no calcula, ajusta, redondea ni completa** Health o pilares. Tampoco ajusta V2 ni consulta IA. El antiguo exportador se conserva separado en `src/xray/product/legacy_frontend_export.py`, exclusivamente para investigación; no es un fallback de la aplicación.

## Contrato

- Empresa `3.0`; cartera y grupo `2.0`; pointer y manifiesto web `1.0`.
- Todos los JSON comparten `snapshot_id`, `run_id`, `as_of`, `currency`, `score_version`, `classification_version`, `cleaning_version`, `facts_version` y `config_version`.
- `health_score` y `dimensions` copian valores **nullable** del motor. Los alias `cash_generation ← generation` y `debt ← debt_obligations` sólo cambian nombres.
- Cada empresa conserva `pulse` y `canonical_cash_truth` completos: features, contribuciones, límites, evidencia, confidence, flags, sensibilidad y trazabilidad originales.
- Los estados de presentación son `complete`, `partial` e `insufficient_evidence`. Este último identifica cuatro pilares nulos; no cambia el `status` del objeto Pulse original. Cero no equivale a `null`.
- La UI es una vista en **EUR**. Desde D32 el libro de caja convierte todas las monedas a EUR con un tipo fijo por moneda (`xray.fx`), así que cada empresa tiene un único panel EUR con todas sus cuentas; el manifiesto web sigue registrando cualquier panel de otra moneda o empresa sin panel EUR. Ninguna empresa se excluye por Health nulo.
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
  --raw-dir data --out-dir data/processed/pulse \
  --as-of 2026-08-31 --data-vintage 2026-09-01

/tmp/pulse_four_pillars_venv/bin/python scripts/09_export_frontend.py \
  --run-dir data/processed/pulse/runs/<run_id> \
  --currency EUR --out-dir frontend/public/generated
```

El catálogo declara 1.286 empresas y 1.790 paneles empresa/moneda: 1.208 EUR y 582 de otras monedas; 78 empresas no tienen panel EUR. La fecha económica no se confunde con la fecha de conocimiento: los artefactos indican `retrospective_restatement`, no reconstrucción histórica de información disponible entonces. Los CSV originales no se modifican.

Para contener memoria se liberan las copias de tablas raw/cleaned únicamente después de persistir snapshots y hashes, sin cambiar cálculos ni contenido. El ledger ya se indexaba por empresa/moneda; no se vuelve a recorrer todo por empresa.

### Materialización del 19 de septiembre de 2026

- Run completo: `pulse-9debd4f61f356501d9d171d8c114b35fe5d715e0c9434d7444c3200779ddfa05`.
- SHA-256 del manifiesto: `84151e98d557386173576d7303cdd64717b1b2a21d3e4efc6ba234340e387e64`.
- Duración del batch: **12m20**, salida normal `0`; 2.545.046 filas de ledger, 42.960 monthly facts y 1.790 resultados. El run anterior limitado a COMP_1084 permanece disponible.
- Estado original Pulse: 16 `complete`, 1.774 `partial`. Para EUR, la presentación distingue 16 `complete`, 939 `partial` y 253 `insufficient_evidence`, sin eliminar empresas ni alterar el objeto original.
- COMP_1084: Health y Deuda `null`; Generación `0`, Momentum `57.43434743818346`, Resiliencia `0`. No se sustituye su Health por el subtotal de pilares conocidos.
- Los ocho SHA-256 raw coinciden con `/tmp/pulse-four-pillars-raw-before.sha256`. Los artefactos de ejecución están ignorados por Git; no se añadieron como archivos versionados.
- Snapshot web final: `web-86e651dd87e159be5bd06c32a668a5112b3d57e5a3c55a7028faefe6165612b4`; SHA-256 del manifiesto `9a3b4188845a0cb8de53da84c6be86272c50fa8bb59df45496b97ea67443a5e3`. Exportación normal terminada: 1.208 empresas EUR y 248 grupos, con los mismos estados anteriores. El snapshot provisional real de una sola empresa se conserva, pero ya no es `current`.

## Verificación y límites de esta entrega

Por pedido explícito, **no se ejecutaron tests de validación**, suites, E2E ni scripts standalone de validación en esta integración. Los owners escriben regresiones de contrato sin ejecutarlas. Se permiten lint, comprobación de tipos, build solicitado y las comprobaciones inherentes a la ejecución normal del batch/exporter/loader. La revisión semántica es estática; no debe confundirse con cobertura ejecutada.

No hay cambios en fórmulas/pesos del motor, nuevo endpoint FastAPI, rediseño visual, commit ni push. Los cálculos financieros permanecen en Python; Next sólo presenta valores recibidos.

Quedan fuera de esta entrega una UI multimoneda, conexión API adicional y nuevas visualizaciones para toda la trazabilidad estructurada: el JSON ya conserva esos datos, pero no se añaden secciones visuales para ellos.
