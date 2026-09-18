# Decisiones de limpieza de datos

Registro de las decisiones sobre los datos: las **aplicadas** en la capa `data/cleaned/` y las **pendientes**. Cada regla tiene un ID que aparece en el código (`src/xray/clean/`) y en `data/cleaned/_cleaning_log.csv`.

La evidencia de cada punto está en `notebooks/01_exploracion_datos.ipynb` y `notebooks/02_limpieza_datos.ipynb`. Las cifras son de la ejecución del pipeline sobre el dataset completo.

## Cómo funciona

```
data/raw/        CSV originales. Nunca se modifican.
   │   python scripts/00_clean_data.py
   ▼
data/cleaned/    Parquet por tabla + _cleaning_log.csv + _manifest.json
   │   (features)
   ▼
data/processed/  Panel de features, scores, alertas...
```

**Criterio:** en `cleaned` solo se **quita** lo que es claramente un error. Lo dudoso **no se quita: se marca** con una columna booleana (`is_*`, `has_*`). Así, cuando se tome una decisión pendiente, basta con filtrar por la columna en la capa de features, sin volver a limpiar. Para cerrar una decisión, cambia su estado aquí y, si pasa a ser "quitar", muévela al código como regla aplicada.

```python
from xray.io import read_cleaned
tx = read_cleaned("transactions")
operativo = tx[~tx.is_extreme_amount & ~tx.is_sync_duplicate & ~tx.is_internal_transfer]
```

---

## Decisiones tomadas y por qué

### De arquitectura

**1. Tres capas separadas: `raw` → `cleaned` → `processed`.**
Los CSV originales no se tocan nunca, y cada paso escribe solo en su carpeta y la regenera entera. Si una regla resulta ser un error, basta con cambiar el código y volver a ejecutar: no hay que recuperar datos ni hay estados intermedios a medio arreglar. *Descartado:* limpiar "in situ" sobre los CSV o ir guardando ficheros sueltos a mano.

**2. Parquet en lugar de CSV para `cleaned`.**
Conserva los tipos (fechas, booleanos), pesa ~4 veces menos y se lee en segundos. Además evita volver a pelearse con los bytes NUL y los saltos de línea de `transactions.csv`, que solo se tratan una vez, al leer `raw`.

**3. Quitar lo obvio, marcar lo dudoso.**
Esta es la decisión central. Un error de limpieza que **quita** filas es invisible e irreversible aguas abajo. Un error que solo **marca** se corrige cambiando un filtro. Por eso solo se eliminan filas cuando no hay interpretación posible en la que sean datos válidos (importe 0, factura anulada, el mismo movimiento dos veces como `pending` y `booked`). Todo lo que depende de un umbral o de una interpretación (outliers, meses duplicados, traspasos) queda como columna `is_*`, y la capa de features decide.

**4. Cada regla tiene un ID** (T/F/S aplicadas, D pendientes), el mismo en el código, en `_cleaning_log.csv` y en este documento. Así cualquier cifra de un parquet se puede rastrear hasta la regla que la produjo y la razón de esa regla.

**5. Trazabilidad y seguridad de la ejecución.**
- `_manifest.json` guarda el hash de cada CSV original y el commit del código: se sabe exactamente de qué datos y con qué versión salió cada parquet.
- La escritura es atómica (carpeta temporal que sustituye a la anterior al final): una ejecución que falla no deja una capa a medias.
- Una validación final comprueba claves únicas e integridad referencial, y **falla en voz alta** si algo no cuadra.

**6. La lógica vive en `src/xray/`, no en notebooks ni scripts.** Los notebooks explican y justifican. `scripts/00_clean_data.py` solo lanza el paquete. El código importable y testeado es la única fuente de verdad, así que el resto del equipo reutiliza exactamente la misma limpieza.

### De datos (las reglas aplicadas, en prosa)

- **Transacciones duplicadas `pending`/`booked` (T02):** el banco publica primero un movimiento provisional y luego el definitivo. Se exige la misma cuenta, el mismo importe, el mismo concepto y menos de 5 días de diferencia. Una coincidencia casual con esas cuatro condiciones es muy improbable.
- **No se tocan los duplicados sueltos:** en transacciones, el 6,6% de las filas tiene un gemelo exacto, pero son importes pequeños (comisiones, pagos recurrentes) que la anonimización hace idénticos. Quitarlos borraría pagos reales. Solo se marcan los meses con una proporción anómala (D03).
- **`value_date` fuera (T03):** tiene fechas absurdas y en el 88% de los casos coincide con `date`, que es la fecha contable. Mantener dos fechas invita a usar la equivocada.
- **Facturas anuladas, albaranes y pedidos fuera (F02, F03):** ninguno representa dinero que haya que cobrar o pagar. Dejarlos inflaría la facturación y la morosidad.
- **`payment_date` vaciada en no pagadas (F04):** era un relleno igual al vencimiento. Dejarla hacía que una factura impagada pareciera pagada puntualmente, justo lo contrario de la realidad.
- **Fechas imposibles a nulo en lugar de quitar la factura (F05):** la factura existe y su importe cuenta. Lo que no sirve es su fecha.
- **`direction` explícita (F06):** el signo de `amount` es la única pista de si una factura es a cobrar o a pagar. Nombrarlo evita errores de signo en cada feature.
- **Columnas eliminadas (S01–S04):** solo las vacías, constantes o sin relación posible con la salud financiera. Las que tienen alguna duda (`countable`, `liquidity`, `accounting_status`) se mantienen y figuran como pendientes.

---

## Aplicadas en `data/cleaned/`

### Transacciones (2.556.437 → 2.554.288 filas)

| ID | Regla | Acción | Filas | Por qué es obvio |
|---|---|---|---:|---|
| — | Quitar bytes NUL al leer `transactions.csv` | lectura | 6 bytes | Rompen el parser. No son datos |
| T01 | `amount == 0` | quitar | 369 | No hay movimiento de dinero |
| T02 | `pending` con gemelo `booked` (misma cuenta, importe y concepto, ±5 días) | quitar | 1.780 | Es el mismo movimiento contado dos veces: provisional y asentado |
| T03 | Columna `value_date` | quitar columna | — | Contiene basura (2099-12-31) y `date` es la fecha contable de referencia |
| T04 | `category` `'-'` o nula → `'uncategorized'` | normalizar | 635.424 | Un único valor explícito para "sin categoría" |

### Facturas (897.894 → 876.756 filas)

| ID | Regla | Acción | Filas | Por qué es obvio |
|---|---|---|---:|---|
| F01 | `amount == 0` | quitar | 1.183 | Sin importe |
| F02 | `status == cancel` | quitar | 13.583 | Una factura anulada no existe a efectos financieros |
| F03 | `document_type` `deliveryNote` o `purchaseOrder` | quitar | 6.372 | Albaranes y pedidos: todavía no son una obligación de cobro o pago |
| F04 | `payment_date` → nulo si `status != paid` | anular valor | 219.367 | En facturas no pagadas es un relleno igual a `due_date` en el 96–98% de los casos |
| F05 | `due_date` / `payment_date` fuera de 2020–2030 → nulo | anular valor | 208 | Fechas imposibles (años 2000, 6913, 7025) |
| F06 | Nueva columna `direction`: `AR` si `amount > 0`, `AP` si `< 0` | normalizar | — | Hace explícita la convención de signos |

### Tablas pequeñas (solo columnas)

| ID | Tabla | Columna | Por qué |
|---|---|---|---|
| S01 | `companies` | `country` | 82% nulo y sin normalizar (`ES`, `ESPAÑA`, `Espanya`) |
| S02 | `banking_products`, `debt_products` | `label`, `service` | `label` es tipo + número. `service` es el código técnico del conector |
| S03 | `balances` | `available` | 100% nulo |
| S04 | `debt_schedule_config` | `amortization_type` | Constante (`constant quote`) |

Validación automática tras limpiar: claves primarias únicas y sin nulos, y todo `company_id`/`group_id` existe en su tabla maestra.

---

## Pendientes

Estado: 🟡 pendiente · ❓ requiere preguntar a Embat · ✅ decidida (moverla arriba)

### Transacciones

**D01 · Importes extremos (> 100 M€)** 🟡 · columna `is_extreme_amount` · 491 filas en 22 empresas
- *Evidencia:* suman el **38% de todo el importe entrante**. El 65% no tiene categoría y no se compensan entre sí (neto / absoluto = 0,18).
- *Opciones:* (a) quitarlas; (b) mantenerlas solo para la reconstrucción de saldos y excluirlas de los flujos.
- *Recomendación:* (b). Excluirlas de todas las features de flujo. Para esas 22 empresas, el saldo reconstruido no es fiable en ningún caso.

**D02 · Outliers relativos (> 20 × p99 de la empresa)** 🟡 · `is_relative_outlier` · 253 filas
- *Evidencia:* importes desproporcionados para el tamaño de la propia empresa. Solo 9 coinciden con D01.
- *Recomendación:* excluirlos de ratios y medias, o winsorizar las features al p99 de la empresa. Decidirlo al construir el panel.

**D03 · Meses cargados dos veces por la sincronización** 🟡 · `is_sync_duplicate` · 30.119 filas en 86 empresas
- *Evidencia:* en un mes normal, < 10% de filas repetidas (legítimas: la anonimización iguala pagos distintos). Hay 171 empresa-mes con ≥ 50%, hasta el 97%, que empiezan y terminan en meses concretos. Es un patrón típico de resincronización.
- *Duda:* el umbral del 50% es heurístico, y dentro de esos meses algún repetido puede ser real.
- *Recomendación:* excluir las filas marcadas en todas las features. Revisar el umbral si al construir el panel aparecen saltos raros en esas empresas.

**D04 · Traspasos entre cuentas propias** 🟡 · `is_internal_transfer` · 63.642 filas (14% del importe entrante)
- *Evidencia:* pares +X / −X el mismo día en cuentas distintas de la misma empresa. Muchos vienen categorizados como `collection` o `payment`, así que la categoría no basta.
- *Recomendación:* excluirlos de entradas y salidas operativas. **Mantenerlos** para reconstruir el saldo de cada cuenta. Riesgo: algún par puede ser una coincidencia real (mismo importe el mismo día); es poco probable con importes no redondos.

**D05 · Movimientos intragrupo** 🟡 · `is_intragroup` · 90.418 filas (9% del importe entrante)
- *Evidencia:* pares +X / −X el mismo día entre empresas del mismo grupo.
- *Recomendación:* depende de D18. Si el score es por grupo, excluirlos (se anulan al consolidar). Si es por empresa, son flujos reales (con matices: financiación intragrupo).

**D06 · Movimientos en productos desconocidos** 🟡 · `is_unknown_product` · 1.313 filas en 14 empresas
- *Evidencia:* el `product_id` no está ni en `banking_products` ni en `debt_products`. Hay importes relevantes (p. ej. un cobro de 1,2 M€).
- *Opciones:* quitarlos, o tratarlos como una cuenta corriente más. No tienen saldo final, así que no sirven para reconstruir saldos.
- *Recomendación:* incluirlos en flujos y excluirlos de la reconstrucción de saldos.

**D07 · Moneda y `exchange_rate`** ❓ · sin columna
- *Evidencia:* ~10% de los movimientos están en cuentas que no son EUR. Hay 10.312 movimientos en cuentas **EUR** con `exchange_rate != 1`. No se puede verificar si `amount` va en la moneda de la cuenta o en la original.
- *Mientras tanto:* usar ratios dentro de cada empresa (independientes de la moneda) y convertir a EUR solo para agregar entre empresas.
- *Pregunta a Embat:* cuando `exchange_rate != 1`, ¿en qué moneda está `amount`?

**D08 · Categorías → bloques de negocio** 🟡 · sin columna
- *Propuesta (notebook 02, §3.7):* `entrada_operativa` (collection, bulk_collection, pos/cash_settlement), `salida_operativa` (payment, bulk_payment, utility, retiradas), `gasto_fijo` (salary, social_security, tax), `deuda` (debt_repayment, interest_charge), `coste_bancario` (fee), `devolucion`, `inversion`, `tesoreria` (transfer).
- *Duda:* el 25% está `uncategorized` (38% del importe entrante). ¿Merece la pena recategorizar con reglas sobre `description` (TRASPASO, NOMINA, SEPA…)?
- *Recomendación:* aplicar el mapeo en la capa de features. Recategorizar solo si da tiempo.

**D09 · `accounting_status`** 🟡 · se mantiene la columna
- *Evidencia:* es el estado de conciliación en Embat (el 31% es `DISCARDED`). Refleja el flujo de trabajo del contable, no un hecho financiero.
- *Recomendación:* no usarla como feature del score. Se puede usar como contexto del producto ("% de movimientos sin conciliar").

**D19 · Texto mal codificado** 🟡 · sin acción
- *Evidencia:* algunas descripciones y concepts traen `�` (latin-1 mal decodificado en origen). El carácter original se ha perdido y no es recuperable.
- *Recomendación:* ignorarlo. Afecta poco a la búsqueda de palabras clave (EMBARGO, IMPAGADO…), porque son ASCII.

### Facturas

**D10 · Posibles duplicados** 🟡 · `is_possible_duplicate` · 18.534 filas
- *Evidencia:* coinciden empresa, contraparte, tipo, fechas, importe **y concepto**. Se concentran en 7 empresas con > 20% duplicado (hasta el 75%), lo que apunta a sincronizaciones del ERP repetidas.
- *Duda:* dos facturas idénticas legítimas son posibles (por ejemplo, dos licencias iguales).
- *Recomendación:* excluirlas de las features.

**D11 · Documentos ambiguos** 🟡❓ · `is_ambiguous_document` · 75.900 filas
- *Evidencia:* `paymentDocument` (53 K), `deposit` (21 K), `other`, `cheque`. Podrían ser el pago de una factura que ya está en la tabla, y entonces contarían doble.
- *Recomendación:* fuera de las métricas de facturación, plazos y morosidad. Solo `invoice` e `invoiceGroup` (y `note`/`refund` como abonos).
- *Pregunta a Embat:* ¿qué representa un `paymentDocument`?

**D12 · Plazos anómalos** 🟡 · `has_anomalous_term` · 20.412 filas
- *Evidencia:* vencimiento anterior a la emisión, plazo > 365 días o vencimiento anulado por F05.
- *Recomendación:* cuentan para la facturación, pero no para métricas de plazo y retraso.

**D13 · Pagadas con fecha de pago futura** 🟡 · `is_future_payment` · 18.237 filas
- *Evidencia:* `status == paid` pero `payment_date` es posterior a la extracción. Es imposible. Probablemente es la fecha prevista de pago.
- *Opciones:* tratarlas como no pagadas en la fecha de extracción, o anular su `payment_date`.
- *Recomendación:* excluirlas del cálculo de retrasos. En `facturas_abiertas(t)` cuentan como abiertas hasta su `payment_date`.

**D14 · Pendientes vencidas hace más de 30 días** 🟡 · `is_stale_pending` · 3.068 filas
- *Recomendación:* tratarlas como `overdue`.

**D20 · `overdue` como señal** 🟡 · sin columna
- *Evidencia:* ~20% de las facturas están `overdue`, incluso de 2024. El `% overdue` AR y AP de una misma empresa correlaciona (ρ≈0,66), lo que apunta a higiene del ERP más que a impago.
- *Recomendación:* no usar el nivel absoluto. Usar la desviación respecto a la historia de la propia empresa. Y recordar que `status` es una foto: para el mes *t*, reconstruir con `facturas_abiertas()`.

### Saldos y deuda

**D15 · Columnas `countable`, `liquidity` y `granted` de `balances`** 🟡 · se mantienen
- *Evidencia:* entre el 67% y el 92% son nulas y su significado depende del banco (`countable` coincide con `balance` solo en la mitad de los casos).
- *Recomendación:* no usarlas. Si en la siguiente iteración nadie las ha usado, quitarlas (S03).

**D21 · Productos de deuda sin movimientos ni saldo** 🟡
- *Evidencia:* `outstanding` y `granted` son una foto final. 224 de 536 pólizas de crédito no tienen movimientos.
- *Recomendación:* la deuda estática solo como contexto del último mes. La dinámica sale de reconstruir las pólizas con movimientos.

### Cobertura y unidad (se deciden al construir el panel)

**D16 · Meses sin datos, huecos y meses finos** 🟡
- *Evidencia:* el 72% de las empresas entra a mitad de ventana. Hay 408 empresa-mes vacíos en medio de la historia (114 empresas), 2.285 empresa-mes con < 5 movimientos y 8 empresas con < 6 meses de datos.
- *Recomendación:* fuera del rango de datos de la empresa → NaN (nunca 0). Hueco → NaN + flag. < 5 movimientos → flag `mes_fino` y usar ventanas de 3 meses. < 6 meses → fuera del entrenamiento.

**D17 · Empresas que dejan de tener datos** ❓
- *Evidencia:* 123 empresas no tienen transacciones después de 2026-07, y 62 dejan de tenerlas antes de 2026-06.
- *Pregunta a Embat:* ¿cese de actividad, desconexión del banco o baja en Embat? Si es cese, es un evento (¿target?). Si es baja, hay que cortar su panel en el último dato.

**D18 · Unidad del score: empresa o grupo** ❓
- *Evidencia:* el enunciado dice "250 empresas", pero son 250 grupos con 1.286 sociedades.
- *Pendiente:* confirmarlo con el script del leaderboard. Afecta a D05 y a cómo se agregan features y saldos.

---

## Preguntas abiertas para Embat

1. ¿El leaderboard puntúa por empresa o por grupo? (D18)
2. Cuando `exchange_rate != 1`, ¿en qué moneda está `amount`? (D07)
3. ¿Las empresas que dejan de tener datos han cesado o se han dado de baja? (D17)
4. ¿Qué es un `paymentDocument` en las facturas? (D11)
5. ¿Por qué hay facturas `paid` con fecha de pago posterior a la extracción? (D13)
