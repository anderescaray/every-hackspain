# Contrato de datos del frontend — Embat Pulse

## Responsabilidad y flujo de integración

`CSV originales → pipeline de Data (Pandas / Polars / Parquet, fuera del frontend) → JSON de presentación → Next.js`

El pipeline calcula **todos** los resultados: Health Score, dimensiones, histórico, factores, clasificaciones de caja, tiempos, alertas, cobertura y escenarios. Next.js no lee CSV ni Parquet, no procesa transacciones completas y no calcula ni corrige scores. Valida el contrato, presenta valores suministrados y selecciona escenarios precalculados. La única suma de presentación del bloque de caja es el subtotal explícito de los dos netos recibidos (operación + apoyo/financiación); no es un score ni un modelo financiero.

La fuente única de la página es `getCompanyDetail(companyId)`, en `frontend/services/companyData.ts`. Los componentes reciben un `CompanyDetail` y no importan fixtures ni conocen rutas de archivos.

## Archivos que debe generar el pipeline

Desde la raíz del repositorio:

```text
frontend/public/generated/companies/COMP_0356.json
frontend/public/generated/companies/COMP_0655.json
frontend/public/generated/companies/COMP_1171.json
frontend/public/generated/companies/<company_id>.json
```

- Un objeto JSON UTF-8 completo por empresa, no JSONL ni una lista de empresas. Exportar números JSON nativos; usar `null` solo donde el contrato lo permite, nunca `NaN` ni `Infinity` (en Python, `allow_nan=False`).
- `company_id` debe coincidir exactamente con el nombre del archivo: `COMP_` seguido de 4–10 dígitos.
- En resultados reales, `source` debe ser `"generated"` y `schema_version` debe ser `"2.0"`.
- El adaptador lee estos archivos desde el servidor Next.js con runtime Node, no mediante un endpoint de backend adicional. Equivale a consumir `/generated/companies/<company_id>.json`, sin descargar los archivos directamente en el navegador.
- La página es dinámica y el adaptador no mantiene caché de archivos. Un archivo nuevo o actualizado aparece al recargar la página, sin modificar los componentes ni reconstruir el frontend, siempre que el proceso Next.js tenga acceso al mismo sistema de archivos.
- En despliegues con sistema de archivos inmutable, incorporar los JSON al artefacto antes de desplegar o montar un directorio compartido. `COMPANY_ANALYSIS_DIR` permite indicar una ruta alternativa absoluta de archivos por empresa. No requiere cambiar componentes.
- Escribir primero un archivo temporal y sustituir el JSON mediante renombrado atómico para no exponer archivos a medio escribir.
- No es necesario un manifiesto para Company Detail. `frontend/public/generated/manifest.json` queda reservado para otra integración; esta página no lo consume.
- Máximo **2 MiB por empresa**. Exportar agregados y muestras pequeñas, nunca millones de movimientos.
- Los JSON generados están excluidos de git. Se conserva solo el directorio mediante `.gitkeep`.
- **`public/` es público**: sus archivos pueden servirse sin autenticación. Exportar solo los agregados anonimizados y muestras autorizadas para la demo. Esta rama no implementa control de acceso.

Una vez exportados, desde `frontend/`:

```bash
npm run validate:generated
npm run dev
```

El primer comando comprueba todos los JSON del directorio utilizando el mismo contrato y adaptador que la aplicación. Devuelve error si no hay archivos o si alguno es inválido. Abrir `/companies/COMP_0356` o el identificador correspondiente.

Para servir una compilación de producción: `npm run build` y `npm start`. No se exige que los JSON existan durante el build.

## Ausencia, errores y desarrollo aislado

- Archivo ausente: **«Datos de análisis todavía no disponibles.»** No se crean resultados y no existe fallback a fixtures, ni siquiera para los tres casos conocidos.
- JSON ilegible, demasiado grande o incompatible: **«Los datos de análisis necesitan revisión.»** No se muestran puntuaciones parciales.
- Fallo de lectura del sistema: estado de error en español con posibilidad de reintentar.
- Identificador con formato incorrecto: página de empresa no disponible. No se permiten rutas arbitrarias.
- Los fixtures están exclusivamente en `frontend/tests/fixtures/companyDetails.ts`. Sus puntuaciones y escenarios son valores ficticios ya fijados, no un motor financiero. Además de los tres casos principales, COMP_9001 ilustra una empresa independiente con financiación externa y COMP_9002 una empresa independiente sin apoyo identificado; ambos declaran explícitamente ausencia de traslados propios en el periodo.
- `npm run dev:fixtures` es la única entrada de desarrollo de ejemplo. El lanzador exporta los fixtures a un directorio temporal fuera de `public/generated`, configura un proceso Next.js aislado y borra solo ese directorio temporal al finalizar. Puede recibir `-- --port 3107`.
- Este modo muestra **«Demo · Datos de ejemplo»**. No modifica, sustituye ni borra los JSON del pipeline. Next.js permite un solo servidor `dev` por directorio: cerrar el servidor de desarrollo anterior antes de cambiar de modo, aunque se use otro puerto.
- La aplicación normal rechaza `source: "fixture"`. Solo el modo explícito habilita `COMPANY_DATA_MODE=fixtures`. No configurar esa variable en producción.
- Los tests de navegador usan JSON temporales a través del adaptador real, y un segundo servidor vacío para comprobar que no aparecen datos falsos.

## Tipo único y validación

`frontend/types/companyDetail.ts` exporta `companyDetailSchema` (Zod) y deriva `CompanyDetail` de ese mismo esquema. No hay un segundo contrato paralelo. El objeto raíz es estricto: no acepta campos antiguos como `pulse`, `health` o `stability`.

| Campo | Contrato |
|---|---|
| `schema_version`, `source` | `"2.0"`, `"generated"` en el pipeline |
| `company_id`, `group_id` | Identificadores, sin nombres reales necesarios. `group_id: null` declara que la empresa no pertenece a un grupo; no omitir el campo ni usar una cadena vacía |
| `as_of`, `currency` | Fecha de corte `YYYY-MM-DD`, moneda `"EUR"` |
| `health_score` | Entero 0–100 ya calculado por Data |
| `dimensions` | Cuatro números 0–100: `momentum`, `cash_generation`, `resilience`, `debt` |
| `health_score_model` | `version`, `provisional`, `weights` utilizados por Data |
| `assessment`, `summary` | Valoración breve y explicación en español; no derivadas automáticamente del score por la UI |
| `confidence` | Número 0–100 de calidad/cobertura, o `null` si no evaluable. Nunca probabilidad de acierto ni parte del score |
| `trajectory` | `improving`, `deteriorating` o `stable`; la UI los traduce |
| `history` | Hasta 24 puntos `{month, health_score}`, orden cronológico estricto, fechas no posteriores a `as_of`; el último score coincide con el actual. Usar `[]` si no hay histórico, sin rellenarlo artificialmente |
| `drivers_period`, `drivers` | Periodo y hasta 20 factores; cada uno con `id`, `driver`, `affected_dimensions`, `impact` en puntos, `direction`, `explanation`, `evidence_count`, `evidence_refs` |
| `cash_truth` | Periodo, importes brutos/netos, cuatro categorías únicas, explicación, cobertura, referencias, corrección/comparación opcionales mediante `null` |
| `time_borrowed` | Objetos `ar` y `ap`; cada lado puede ser `null` por falta de evidencia |
| `alerts` | Hasta 5 alertas; `severity`: `high`, `medium`, `low`; título, explicación, periodo y referencias |
| `evidence` | Hasta 50 grupos, máximo 10 filas representativas por grupo; los recuentos totales se suministran aparte |
| `simulation` | Cuatro controles, resultados precalculados, `example_id` nullable y metodología |

Todos los textos de producto suministrados por Data (`label`, `explanation`, `period`, `title`, etc.) deben llegar **en español**. Los enums internos, identificadores, `Health Score`, `Momentum`, AR/AP y EUR no requieren traducción en el JSON. La UI traduce los enums, no narrativas arbitrarias.

### Health Score y pesos

Configuración provisional centralizada en `frontend/lib/healthScore.ts`, constante `HEALTH_SCORE_WEIGHTS`:

- Momentum: 25 %.
- Generación de caja: 30 %.
- Resiliencia: 25 %.
- Deuda: 20 %.

El cálculo ponderado y su redondeo corresponden **al pipeline**, no al frontend. Data debe exportar tanto el resultado como los pesos efectivos en `health_score_model.weights`. Los pesos deben estar entre 0 y 1 y sumar 1. La interfaz muestra los pesos del archivo, por lo que Data puede cambiarlos y versionar su modelo sin modificar componentes. La constante solo centraliza la referencia provisional usada por los fixtures; nunca sustituye valores ausentes del JSON.

Las cuatro dimensiones indican una mejor situación cuando suben, no más crecimiento ni más deuda. «Crecimiento bajo presión» debe exportarse como factor/alerta asociado a `momentum`, `cash_generation` y/o `resilience`, no como una quinta puntuación. La cobertura se presenta de forma secundaria (alta ≥80, media ≥60, limitada por debajo; `null`: no evaluable), sin alterar la puntuación recibida.

### Origen de la caja

El primer valor visible es **Total de caja neta identificada = neto operativo + neto de apoyo/financiación**. Se muestra con importes completos y la fórmula al lado, antes del desglose. Para COMP_0356: **4.165.600 € = 25.600 € + 4.140.000 €**.

Este subtotal solo suma los dos `components[].net_amount` de categorías `operating` y `support`. No usa `apparent_net`, no reconstruye saldos bancarios y no incorpora circulación ni importes no identificados. No cambia el contrato ni los valores recibidos de Data. Para que la ecuación cuadre con los importes mostrados, ambos sumandos se redondean a céntimos y se suman en unidades enteras de céntimo; no se recalcula ningún score. Se conservan importes negativos (salidas) y cero. Si falta cualquiera de los dos netos o excede la precisión monetaria segura, el total aparece como no disponible: nunca se trata un dato ausente como cero. Sin apoyo identificado y con neto explícito 0, el total coincide con la operación; el sumando 0 se explica en la fórmula sin reintroducir la tarjeta vacía de apoyo.

- Importes en **euros**, no céntimos ni cadenas formateadas. El frontend aplica formato español.
- `total_gross_movement` y `gross_movement` son movimientos en valor absoluto. En circulación se cuentan entrada y salida.
- `net_amount` es entradas menos salidas; `null` significa que el neto no está identificado, nunca cero implícito.
- Categorías: `operating`, `circulation`, `support`, `uncertain`, exactamente una de cada una. Se conserva el registro `support` aunque sus movimientos sean cero; la UI decide si mostrarlo.
- El bloque de apoyo solo aparece si `support.gross_movement > 0`, es decir, Data ha clasificado movimientos en esa categoría. Con `group_id` informado se etiqueta «Apoyo intragrupo»; con `group_id: null`, «Financiación o apoyo externo». La categoría y las narrativas deben corresponder a ese origen: pertenecer a un grupo no autoriza al frontend a reclasificar un préstamo bancario como transferencia intragrupo.
- Sin apoyo detectado, exportar `gross_movement: 0`, `net_amount: 0` y referencias vacías. No se muestra una tarjeta de importe cero ni una fila vacía de apoyo en el desglose. Un neto cero con bruto positivo sí conserva el bloque, porque existen entradas y salidas que se compensan. Si el bruto es cero pero el neto es `null`, no se presenta la tarjeta, pero se advierte que falta información; no se afirma que no exista financiación.
- En empresas sin grupo, usar también textos de financiación externa en factores, alertas y escenarios. La clave de simulación `internal_support` se conserva por compatibilidad; su etiqueta y metodología las proporciona Data.
- No sumar los importes principales mostrados: pueden usar bases brutas o netas, siempre etiquetadas.
- `apparent_net` es una observación independiente suministrada, no un saldo reconstruido por el frontend.
- La presentación se divide en dos bloques. «Origen de la caja» muestra Generación operativa y, cuando hay movimientos identificados, Apoyo intragrupo o Financiación o apoyo externo como netos; No identificado se muestra como volumen bruto sin atribuir. No sumar esas bases como caja generada. «Movimientos de tesorería» muestra aparte los traslados identificados entre cuentas propias, contados una sola vez; no son saldo disponible ni una nueva fuente de liquidez.
- `cash_truth.own_account_circulation` es un agregado opcional/nullable suministrado por Data: `transferred_amount` (EUR no negativos, cada traslado contado una vez), `transfer_count` (entero no negativo), `explanation`, `confidence` nullable y `evidence_refs`. Su periodo es `cash_truth.period`. Solo incluye traslados emparejados entre cuentas del mismo titular: excluir otras sociedades, comisiones, divisas no resueltas y movimientos pendientes o no identificados. Data prepara este agregado fuera del frontend.
- El frontend no obtiene el importe transferido dividiendo `circulation.gross_movement` entre dos ni sumando unas pocas filas de muestra. Si falta `own_account_circulation`, muestra «Datos insuficientes / No disponible», nunca «Sin movimientos». Con `transferred_amount: 0` y `transfer_count: 0` muestra claramente «No se han detectado movimientos entre cuentas propias» en los datos del periodo, sin una tarjeta numérica de 0 € ni detalles vacíos. Si existen tramos propios pendientes de emparejar, muestra un estado pendiente en lugar de afirmar ausencia de movimientos. Importe y recuento deben ser ambos cero o ambos positivos; un agregado cero no puede coexistir con una muestra de traslado propio emparejado. Para la demo aislada, COMP_0356 suministra 86.725.600 € en 34 traslados; se presenta redondeado como 86,7 M€, con el importe exacto en el detalle emergente.
- El desglose bruto, las cuentas y las transferencias representativas permanecen en desplegables. Las referencias de evidencia del nuevo agregado deben existir igual que las demás; las muestras no tienen por qué reproducir el total.
- `comparison` contiene observaciones preparadas por Data. `correction` se conserva como campo legado por compatibilidad, pero ya no se representa en la UI: exportar `null` si no existe una corrección real documentada. No fabricar un antes/después para explicar la circulación.
- COMP_0356 ilustra +25,6 mil € de operación, +4,14 M€ de apoyo y cero neto en circulación identificada. Esto señala el peso del apoyo, no demuestra insolvencia ni autosuficiencia.
- Se ha retirado la biblioteca independiente de evidencia; se mantienen los botones contextuales en factores, caja, transferencias, tiempos y alertas.

### Cuentas y transferencias: extensión compatible de la versión 2.0

`cash_truth.account_flows` es opcional y admite `null`. Los JSON anteriores siguen siendo válidos: si no hay detalle, la UI muestra «Detalle por cuentas todavía no disponible», sin inventar titularidad ni asumir que toda circulación es entre cuentas propias.

El bloque contiene `period`, `explanation`, `accounts` (hasta 50 cuentas incluidas en las muestras) y `transfers` (hasta 10 transferencias representativas). No es una nueva suma ni un inventario necesariamente completo; sus importes ya están incluidos en los agregados de caja. No se muestran saldos por cuenta porque no se suministran en este contrato.

**Cuentas**:

- `account_id`: identificador estable. Puede ser el `product_id` de la fuente original; `transactions.product_id` identifica la cuenta y el registro de productos aporta `company_id`. Ese cruce corresponde al pipeline, no al frontend.
- `label`, `bank_name` (nullable), `currency`: alias en español, banco y EUR. Usar IDs anonimizados, nunca IBAN completos o credenciales en archivos públicos.
- `ownership`: `company` (empresa analizada), `group_company` (otra sociedad del mismo grupo), `external` (empresa de otro grupo identificada) o `unknown`.
- `owner_company_id`, `owner_group_id`, `ownership_source`: empresa titular, grupo y fuente textual que respalda esa asignación. Para titularidad identificada, empresa y fuente son obligatorias; el grupo puede ser `null` para una empresa independiente. Las cuentas propias deben tener la misma empresa y grupo (también si es `null`) que el análisis. `group_company` exige un grupo no nulo compartido y otra empresa; dos empresas con grupo `null` no pertenecen por ello al mismo grupo. Para `unknown`, empresa y grupo son `null`; no atribuir el titular por similitud del nombre del banco o del importe.
- `confidence`: cobertura/calidad del dato suministrado, nullable; no probabilidad de acierto.

**Transferencias**:

- `id`, `kind`, `from_account_id`, `to_account_id`, `date`, `amount`, `gross_movement`, `company_net_amount`, `category`, `match_status`, `debit`, `credit`, `explanation`, `confidence`.
- `kind`: `own_transfer`, `intragroup_transfer`, `external_transfer` o `unresolved`. Al menos un extremo debe ser una cuenta identificada de la empresa analizada. Una cuenta de origen/destino desconocida se representa con `null` o mediante una cuenta de titularidad `unknown`.
- `amount` es el importe de la transferencia, contado una vez; `gross_movement` cuenta los tramos observados **de la empresa analizada**, no los de todas las sociedades; `company_net_amount` es el neto suministrado atribuible a ese movimiento en la empresa, o `null` si no identificado. No es saldo disponible ni neto consolidado del grupo.
- Ejemplo propio: salida 2,5 M€ y entrada 2,5 M€ en dos cuentas de COMP_0356 → importe trasladado 2,5 M€, bruto 5 M€, neto suministrado 0 €. Ejemplo intragrupo: entrada observada de 600 mil € desde otra sociedad → bruto de COMP_0356 600 mil €, neto +600 mil €, sin duplicar el cargo de la otra sociedad.
- `category` es independiente de `kind`: una transferencia intragrupo puede ser un cobro operativo, apoyo u otra clasificación respaldada. No se convierte automáticamente en apoyo por pertenecer al mismo grupo.
- `match_status`: `matched` exige salida y entrada documentadas; `partial` documenta exactamente un tramo; `unmatched` no declara una pareja completa.
- `debit` y `credit`: `{ "evidence_id": "id-del-grupo", "transaction_id": "id-de-la-fila" }`, o `null` si falta ese tramo. Las filas deben ser de tipo `transaction` e incluir `account_id`, coherente con origen/destino, signo, importe y categoría. El botón de evidencia filtra exclusivamente esos registros.
- Un traslado propio solo puede declararse `circulation` con neto 0 si está emparejado y ambos titulares son la misma empresa. Si está parcial/sin emparejar: `category: "uncertain"`, `company_net_amount: null`. No reconstruir el tramo ausente.
- `unresolved` exige `category: "uncertain"` y neto `null`, incluso si se observa una entrada. No equivale a cero.
- El validador comprueba consistencia de IDs, titularidad, referencias y los importes ya suministrados de esas pocas filas. No busca parejas, no reclasifica y no calcula scores. No se reutiliza un movimiento en varias transferencias.
- Esta versión solo representa transferencias simples en EUR con tramos de igual importe. Comisiones, cambio de divisa, agrupaciones de pagos y diferencias de fecha de corte necesitan tratamiento previo de Data; no atribuirles automáticamente neto cero. Si la pareja no puede acreditarse dentro del corte, usar estado parcial/no identificado u omitir la muestra.

### Tiempo financiado

`before` y `after` incluyen `period`, `payment_term`, `time_to_cash`, `delay`, todos en días naturales no negativos. Para AP, `time_to_cash` representa el tiempo hasta **pago**, que la UI etiqueta correctamente.

Son medianas independientes. No exigir `payment_term + delay === time_to_cash`. Para COMP_1171 se mantiene 62/81/20 → 102/102/0. AR describe tiempo concedido a clientes; AP describe tiempo recibido de proveedores. No inferir motivos ni considerar más retraso a proveedores una mejora.

### Evidencia

Cada `evidence_refs` apunta a un `evidence[].id` existente. Los IDs de grupos, factores, alertas y filas dentro de un grupo son únicos. `total_count` es mayor o igual al número de filas. Una muestra de 5–10 filas es suficiente; se admiten muestras vacías si no hay registros representativos. Las muestras no son conciliaciones completas.

Tipos de fila:

- `transaction`: `id`, `transaction_date`, `amount`, `category`, `description`; `account_id` es opcional/nullable en archivos anteriores y obligatorio para las filas enlazadas desde `account_flows`.
- `invoice`: `id`, `invoice`, `counterparty_id`, `side` (`ar`/`ap`), `issue_date`, `due_date`, `payment_date` (nullable), `amount`.
- `observation`: `id`, `metric`, `before`, `after`, `unit` (`EUR`, `%`, `days`). Para indicadores agregados de crecimiento bajo presión. No sustituye la evidencia transaccional por una causa inferida.

### Escenarios, no predicciones

`simulation.inputs` contiene exactamente una entrada por clave: `customer_term`, `collection_delay`, `supplier_term`, `internal_support`. `min`, `max`, `step` son límites de **ajustes relativos**. El rango debe contener cero y respetar que `baseline + min` no sea negativo. En apoyo interno, `baseline: 100` significa 100 % del apoyo actual; −10 equivale al 90 %.

`simulation.scenarios` contiene hasta 1000 resultados ya calculados por Data. Cada uno incluye `id`, `label`, los cuatro ajustes en `inputs`, `health_score`, `impacts` y `explanation`. `impacts` son contribuciones precalculadas en puntos, no coeficientes para calcular en el navegador. Un resultado de cero es válido.

Los IDs y combinaciones de ajustes deben ser únicos; cada ajuste debe respetar rango y paso. `example_id` debe referenciar un escenario existente o ser `null`.

La UI conserva controles, selector de escenarios preparados, ejemplo y restablecimiento. Busca una coincidencia **exacta**. Si no existe, muestra «No hay un escenario precalculado para esta combinación», sin interpolar ni inventar un Health Score. Todos los ajustes a cero muestran el score actual. Si se exporta ese escenario base, su score debe coincidir con el actual.

Si Data aún no suministra simulaciones, exportar `scenarios: []` y `example_id: null`, manteniendo los cuatro controles y una metodología que explique la ausencia. El resto del análisis sigue funcionando.

## JSON completo de ejemplo

**Este ejemplo es ficticio y solo documenta el formato. No se instala ni se usa por defecto en la aplicación.** `source: "generated"` muestra lo que debe indicar el pipeline cuando exporte sus resultados reales. Todos los campos necesarios están incluidos; el test del contrato valida este bloque para evitar divergencias.

```json
{
  "schema_version": "2.0",
  "source": "generated",
  "company_id": "COMP_0356",
  "group_id": "GROUP_0042",
  "as_of": "2026-08-31",
  "currency": "EUR",
  "health_score": 72,
  "dimensions": { "momentum": 68, "cash_generation": 81, "resilience": 74, "debt": 59 },
  "health_score_model": {
    "version": "provisional-v1",
    "provisional": true,
    "weights": { "momentum": 0.25, "cash_generation": 0.30, "resilience": 0.25, "debt": 0.20 }
  },
  "assessment": "Señales de presión y dependencia de apoyo",
  "confidence": 88,
  "trajectory": "deteriorating",
  "summary": "La operación genera poca caja neta frente al apoyo intragrupo recibido. El saldo por sí solo no explica el origen de la liquidez.",
  "history": [
    { "month": "2024-09-01", "health_score": 86 },
    { "month": "2024-10-01", "health_score": 87 },
    { "month": "2024-11-01", "health_score": 85 },
    { "month": "2024-12-01", "health_score": 88 },
    { "month": "2025-01-01", "health_score": 87 },
    { "month": "2025-02-01", "health_score": 86 },
    { "month": "2025-03-01", "health_score": 88 },
    { "month": "2025-04-01", "health_score": 86 },
    { "month": "2025-05-01", "health_score": 85 },
    { "month": "2025-06-01", "health_score": 86 },
    { "month": "2025-07-01", "health_score": 84 },
    { "month": "2025-08-01", "health_score": 83 },
    { "month": "2025-09-01", "health_score": 85 },
    { "month": "2025-10-01", "health_score": 84 },
    { "month": "2025-11-01", "health_score": 82 },
    { "month": "2025-12-01", "health_score": 83 },
    { "month": "2026-01-01", "health_score": 81 },
    { "month": "2026-02-01", "health_score": 80 },
    { "month": "2026-03-01", "health_score": 78 },
    { "month": "2026-04-01", "health_score": 77 },
    { "month": "2026-05-01", "health_score": 76 },
    { "month": "2026-06-01", "health_score": 74 },
    { "month": "2026-07-01", "health_score": 73 },
    { "month": "2026-08-01", "health_score": 72 }
  ],
  "drivers_period": "sep 2024 – ago 2026 · contribuciones seleccionadas",
  "drivers": [
    { "id": "support", "driver": "Dependencia de liquidez", "affected_dimensions": ["resilience", "cash_generation"], "impact": -8, "direction": "negative", "explanation": "El apoyo identificado gana importancia en la liquidez observada.", "evidence_count": 12, "evidence_refs": ["cash-movements"] },
    { "id": "terms", "driver": "Plazos concedidos a clientes", "affected_dimensions": ["momentum", "cash_generation"], "impact": -5, "direction": "negative", "explanation": "Los plazos más largos mantienen la caja en manos del cliente durante más tiempo.", "evidence_count": 48, "evidence_refs": ["ar-timing"] },
    { "id": "collections", "driver": "Cobros", "affected_dimensions": ["cash_generation"], "impact": 2, "direction": "positive", "explanation": "El menor retraso compensa parcialmente la ampliación de los plazos.", "evidence_count": 48, "evidence_refs": ["ar-timing"] }
  ],
  "cash_truth": {
    "period": "sep 2025 – ago 2026",
    "total_gross_movement": 179046800,
    "apparent_net": 4165600,
    "own_account_circulation": {
      "transferred_amount": 86725600,
      "transfer_count": 34,
      "explanation": "Agregado de traslados emparejados entre cuentas de COMP_0356, contado una vez por traslado. Excluye otras sociedades, comisiones y movimientos sin resolver. Las filas de evidencia son muestras, no el conjunto completo.",
      "confidence": 94,
      "evidence_refs": ["cash-movements"]
    },
    "account_flows": {
      "period": "sep 2025 – ago 2026",
      "explanation": "Muestras representativas ya incluidas en el desglose; no sumar de nuevo ni presumir un inventario completo.",
      "accounts": [
        { "account_id": "ACCOUNT_0356_A", "label": "Cuenta operativa", "bank_name": "Banco A", "currency": "EUR", "ownership": "company", "owner_company_id": "COMP_0356", "owner_group_id": "GROUP_0042", "ownership_source": "Registro de cuentas suministrado: cuenta asignada a COMP_0356.", "confidence": 94 },
        { "account_id": "ACCOUNT_0356_B", "label": "Cuenta de tesorería", "bank_name": "Banco B", "currency": "EUR", "ownership": "company", "owner_company_id": "COMP_0356", "owner_group_id": "GROUP_0042", "ownership_source": "Registro de cuentas suministrado: cuenta asignada a COMP_0356.", "confidence": 94 },
        { "account_id": "ACCOUNT_GROUP_A", "label": "Cuenta de otra sociedad del grupo", "bank_name": "Banco A", "currency": "EUR", "ownership": "group_company", "owner_company_id": "COMP_0007", "owner_group_id": "GROUP_0042", "ownership_source": "Registro de cuentas y sociedades suministrado: COMP_0007 pertenece a GROUP_0042.", "confidence": 91 }
      ],
      "transfers": [
        { "id": "own-cycle", "kind": "own_transfer", "from_account_id": "ACCOUNT_0356_A", "to_account_id": "ACCOUNT_0356_B", "date": "2026-08-03", "amount": 2500000, "gross_movement": 5000000, "company_net_amount": 0, "category": "circulation", "match_status": "matched", "debit": { "evidence_id": "cash-movements", "transaction_id": "TX-001" }, "credit": { "evidence_id": "cash-movements", "transaction_id": "TX-002" }, "explanation": "Dos cuentas del mismo titular: se traslada dinero, no se genera caja nueva.", "confidence": 94 },
        { "id": "group-support", "kind": "intragroup_transfer", "from_account_id": "ACCOUNT_GROUP_A", "to_account_id": "ACCOUNT_0356_A", "date": "2026-08-14", "amount": 600000, "gross_movement": 600000, "company_net_amount": 600000, "category": "support", "match_status": "partial", "debit": null, "credit": { "evidence_id": "cash-movements", "transaction_id": "TX-005" }, "explanation": "Entrada identificada de otra sociedad, clasificada como apoyo. Solo se documenta la entrada en la empresa analizada.", "confidence": 91 },
        { "id": "unidentified-source", "kind": "unresolved", "from_account_id": null, "to_account_id": "ACCOUNT_0356_A", "date": "2026-08-19", "amount": 210000, "gross_movement": 210000, "company_net_amount": null, "category": "uncertain", "match_status": "partial", "debit": null, "credit": { "evidence_id": "cash-movements", "transaction_id": "TX-006" }, "explanation": "Entrada observada sin suficiente identificación del origen. No se atribuye a generación operativa ni a apoyo.", "confidence": null }
      ]
    },
    "components": [
      { "category": "operating", "label": "Generado por la operación", "gross_movement": 1245600, "net_amount": 25600, "explanation": "Neto operativo identificado tras separar la circulación.", "confidence": 86, "evidence_refs": ["cash-movements"] },
      { "category": "circulation", "label": "Circulación de tesorería", "gross_movement": 173451200, "net_amount": 0, "explanation": "Movimiento bruto contando entrada y salida, no generación operativa.", "confidence": 94, "evidence_refs": ["cash-movements"] },
      { "category": "support", "label": "Apoyo interno / intragrupo", "gross_movement": 4140000, "net_amount": 4140000, "explanation": "Apoyo identificado, no ingreso de actividad.", "confidence": 91, "evidence_refs": ["cash-movements"] },
      { "category": "uncertain", "label": "Origen no identificado", "gross_movement": 210000, "net_amount": null, "explanation": "No identificable con suficiente confianza.", "confidence": null, "evidence_refs": [] }
    ],
    "headline": "Poca caja del negocio. Mucho apoyo del grupo.",
    "explanation": "La operación identificada aporta 25,6 mil € netos y el apoyo intragrupo 4,14 M€. La circulación identificada tiene neto cero. El peso del apoyo merece atención, sin concluir insolvencia ni autosuficiencia.",
    "confidence": 86,
    "evidence_refs": ["cash-movements"],
    "evidence_summary": ["34 ciclos de tesorería emparejados", "12 transferencias intragrupo identificadas"],
    "correction": null,
    "comparison": { "company_id": "COMP_0655", "apparent_net": 4165600, "operating_net": 3850000, "support_net": 315600, "circulation_gross": 2400000, "explanation": "Misma posición aparente de caja. Distinta realidad financiera." }
  },
  "time_borrowed": {
    "ar": {
      "counterparty_id": "COUNTERPARTY_02340",
      "before": { "period": "ene – mar 2026", "payment_term": 75, "time_to_cash": 85, "delay": 10 },
      "after": { "period": "jun – ago 2026", "payment_term": 90, "time_to_cash": 97, "delay": 7 },
      "headline": "Más plazo concedido. La caja tarda más en llegar.",
      "explanation": "El plazo aumentó 15 días y el menor retraso solo compensa parte del tiempo adicional financiado.",
      "methodology": "Medianas independientes en días naturales, agrupadas por fecha de pago. No se suman ni permiten inferir motivos.",
      "confidence": 88,
      "evidence_count": 48,
      "evidence_refs": ["ar-timing"]
    },
    "ap": {
      "counterparty_id": "COUNTERPARTY_04821",
      "before": { "period": "ene – mar 2026", "payment_term": 60, "time_to_cash": 64, "delay": 4 },
      "after": { "period": "jun – ago 2026", "payment_term": 45, "time_to_cash": 48, "delay": 3 },
      "headline": "Menos plazo recibido. La caja se necesita antes.",
      "explanation": "El plazo concedido por proveedores se redujo 15 días. No se identifica la causa.",
      "methodology": "Medianas independientes en días naturales. El tiempo hasta pago no es una medida de calidad del proveedor.",
      "confidence": 88,
      "evidence_count": 48,
      "evidence_refs": ["ap-timing"]
    }
  },
  "alerts": [
    { "id": "support", "severity": "high", "title": "Aumenta la dependencia de liquidez", "explanation": "El apoyo identificado acompaña a un neto operativo ligeramente positivo.", "period": "sep 2025 – ago 2026", "evidence_refs": ["cash-movements"] },
    { "id": "terms", "severity": "medium", "title": "Se amplían los plazos a clientes", "explanation": "La empresa financia más tiempo antes del vencimiento.", "period": "jun – ago 2026", "evidence_refs": ["ar-timing"] }
  ],
  "evidence": [
    {
      "id": "cash-movements", "title": "Clasificación de caja y apoyo identificado", "period": "sep 2025 – ago 2026", "explanation": "Movimientos representativos de ejemplo, no una conciliación completa.", "confidence": 86, "total_count": 156,
      "rows": [
        { "kind": "transaction", "id": "TX-001", "account_id": "ACCOUNT_0356_A", "transaction_date": "2026-08-03", "amount": -2500000, "category": "circulation", "description": "Salida de tesorería" },
        { "kind": "transaction", "id": "TX-002", "account_id": "ACCOUNT_0356_B", "transaction_date": "2026-08-04", "amount": 2500000, "category": "circulation", "description": "Entrada de tesorería emparejada" },
        { "kind": "transaction", "id": "TX-003", "account_id": "ACCOUNT_0356_A", "transaction_date": "2026-08-05", "amount": 180000, "category": "operating", "description": "Cobros identificados" },
        { "kind": "transaction", "id": "TX-004", "account_id": "ACCOUNT_0356_A", "transaction_date": "2026-08-07", "amount": -154400, "category": "operating", "description": "Pagos operativos identificados" },
        { "kind": "transaction", "id": "TX-005", "account_id": "ACCOUNT_0356_A", "transaction_date": "2026-08-14", "amount": 600000, "category": "support", "description": "Apoyo intragrupo identificado" },
        { "kind": "transaction", "id": "TX-006", "account_id": "ACCOUNT_0356_A", "transaction_date": "2026-08-19", "amount": 210000, "category": "uncertain", "description": "Finalidad no identificada" }
      ]
    },
    {
      "id": "ar-timing", "title": "Plazos y cobros de clientes", "period": "ene – mar 2026 frente a jun – ago 2026", "explanation": "Muestra de facturas de clientes. No reproduce el conjunto completo.", "confidence": 88, "total_count": 48,
      "rows": [
        { "kind": "invoice", "id": "AR-001", "invoice": "FACT-001", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-01-01", "due_date": "2026-03-17", "payment_date": "2026-03-27", "amount": 18000 },
        { "kind": "invoice", "id": "AR-002", "invoice": "FACT-002", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-01-01", "due_date": "2026-03-17", "payment_date": "2026-03-27", "amount": 20500 },
        { "kind": "invoice", "id": "AR-003", "invoice": "FACT-003", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-01-01", "due_date": "2026-03-17", "payment_date": "2026-03-27", "amount": 23000 },
        { "kind": "invoice", "id": "AR-004", "invoice": "FACT-004", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-05-01", "due_date": "2026-07-30", "payment_date": "2026-08-06", "amount": 25500 },
        { "kind": "invoice", "id": "AR-005", "invoice": "FACT-005", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-05-01", "due_date": "2026-07-30", "payment_date": "2026-08-06", "amount": 28000 },
        { "kind": "invoice", "id": "AR-006", "invoice": "FACT-006", "counterparty_id": "COUNTERPARTY_02340", "side": "ar", "issue_date": "2026-05-01", "due_date": "2026-07-30", "payment_date": "2026-08-06", "amount": 30500 }
      ]
    },
    {
      "id": "ap-timing", "title": "Plazos y pagos a proveedores", "period": "ene – mar 2026 frente a jun – ago 2026", "explanation": "Muestra de facturas de proveedores. No permite inferir motivos.", "confidence": 88, "total_count": 48,
      "rows": [
        { "kind": "invoice", "id": "AP-001", "invoice": "FACT-P-001", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-01-01", "due_date": "2026-03-02", "payment_date": "2026-03-06", "amount": 18000 },
        { "kind": "invoice", "id": "AP-002", "invoice": "FACT-P-002", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-01-01", "due_date": "2026-03-02", "payment_date": "2026-03-06", "amount": 20500 },
        { "kind": "invoice", "id": "AP-003", "invoice": "FACT-P-003", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-01-01", "due_date": "2026-03-02", "payment_date": "2026-03-06", "amount": 23000 },
        { "kind": "invoice", "id": "AP-004", "invoice": "FACT-P-004", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-05-01", "due_date": "2026-06-15", "payment_date": "2026-06-18", "amount": 25500 },
        { "kind": "invoice", "id": "AP-005", "invoice": "FACT-P-005", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-05-01", "due_date": "2026-06-15", "payment_date": "2026-06-18", "amount": 28000 },
        { "kind": "invoice", "id": "AP-006", "invoice": "FACT-P-006", "counterparty_id": "COUNTERPARTY_04821", "side": "ap", "issue_date": "2026-05-01", "due_date": "2026-06-15", "payment_date": "2026-06-18", "amount": 30500 }
      ]
    }
  ],
  "simulation": {
    "inputs": [
      { "key": "customer_term", "label": "Plazo acordado con clientes", "unit": "days", "baseline": 90, "min": -30, "max": 30, "step": 1, "explanation": "Ajuste del tiempo concedido a clientes." },
      { "key": "collection_delay", "label": "Retraso en los cobros", "unit": "days", "baseline": 7, "min": -7, "max": 30, "step": 1, "explanation": "Ajuste del retraso respecto al vencimiento." },
      { "key": "supplier_term", "label": "Plazo acordado con proveedores", "unit": "days", "baseline": 45, "min": -30, "max": 30, "step": 1, "explanation": "Ajuste del tiempo recibido de proveedores." },
      { "key": "internal_support", "label": "Apoyo intragrupo", "unit": "%", "baseline": 100, "min": -50, "max": 50, "step": 1, "explanation": "Cambio porcentual respecto al apoyo actual." }
    ],
    "scenarios": [
      {
        "id": "terms-example",
        "label": "Menos plazo a clientes y más plazo de proveedores",
        "inputs": { "customer_term": -15, "collection_delay": -3, "supplier_term": 7, "internal_support": -10 },
        "health_score": 78,
        "impacts": [
          { "key": "customer_term", "label": "Plazo acordado con clientes", "points": 4.5 },
          { "key": "collection_delay", "label": "Retraso en los cobros", "points": 1.5 },
          { "key": "supplier_term", "label": "Plazo acordado con proveedores", "points": 1.4 },
          { "key": "internal_support", "label": "Apoyo intragrupo", "points": -1.4 }
        ],
        "explanation": "Resultado ilustrativo precalculado para esta combinación exacta. Escenario, no predicción."
      },
      {
        "id": "less-support",
        "label": "Reducción del apoyo intragrupo",
        "inputs": { "customer_term": 0, "collection_delay": 0, "supplier_term": 0, "internal_support": -10 },
        "health_score": 71,
        "impacts": [{ "key": "internal_support", "label": "Apoyo intragrupo", "points": -1.4 }],
        "explanation": "Retirar apoyo reduce la liquidez disponible en este ejemplo; no demuestra autosuficiencia."
      }
    ],
    "example_id": "terms-example",
    "methodology": "Resultados precalculados por el proveedor de datos. El frontend solo selecciona coincidencias exactas. Las contribuciones pueden diferir de la variación final por el redondeo del proveedor. No se recalcula la confianza."
  }
}
```

## Inteligencia de grupo: contrato adicional `GroupDetail` 1.0

Empresa y grupo comparten un menú lateral desplegable. La parte de empresa enlaza Health Score, Tendencia, Origen de la caja y Tiempo financiado; una línea divisoria separa las tres vistas de grupo. El grupo aparece automáticamente en una ficha con `company.group_id` no nulo. No se infiere pertenencia por nombres, bancos o importes.

El parámetro de navegación `entity=COMP_…` conserva la empresa de referencia al recorrer las vistas de grupo y regresar a una sección individual. No modifica el contrato financiero ni sustituye el parámetro `company` utilizado para filtrar la red. El contexto se valida frente a miembros observados o, cuando falta ese dato, frente al JSON individual y su pertenencia al grupo. Sin contexto válido, se utiliza la primera sociedad observada; si no hay ninguna, no se inventa una selección. El estado plegado del menú se conserva durante la navegación y, en móvil, se abre en un cajón modal con cierre por Escape y devolución del foco.

El módulo tiene tres rutas: `/groups/<group_id>`, `/groups/<group_id>/network` y `/groups/<group_id>/recommendations`. Un acceso habilitado no implica que ya exista el análisis del grupo.

`getGroupDetail(groupId)` es la única entrada de datos del análisis financiero de las tres vistas. La navegación puede consultar `getCompanyDetail` para validar una empresa de referencia no incluida en el perímetro observado; no incorpora esos datos a los agregados del grupo. Lee y valida **`frontend/public/generated/groups/<group_id>.json`**. `GROUP_ANALYSIS_DIR` permite un directorio absoluto alternativo. El contrato runtime es `frontend/types/groupDetail.ts`; no requiere modificar el JSON de empresa. El nombre del archivo y `group_id` deben coincidir. Archivos ausentes, incompatibles, demasiado grandes o IDs inválidos producen estados explícitos, nunca redes ni conclusiones inventadas. Las lecturas no tienen caché propia y comparten el límite de 2 MiB con las empresas.

### Responsabilidades de Data y semántica

- Data prepara miembros, Health Score y dimensiones individuales, trayectorias, roles, liquidez, deuda, obligaciones, concentración, cambios, relaciones, evidencia y recomendaciones. **No existe Group Health Score**: el esquema raíz rechaza campos de puntuación agregada. El frontend solo cuenta sociedades por trayectoria para la navegación, filtra, ordena por prioridad suministrada y calcula posiciones geométricas del grafo.
- El grupo es un **perímetro observado**, no una consolidación jurídica completa. `coverage.known_company_count` puede ser `null`; si existe, no puede ser menor que el número de miembros observados. Los miembros deben corresponder al grupo indicado y sus datos individuales deben ser coherentes con sus JSON de empresa; esa consistencia entre exportaciones corresponde al pipeline.
- `available_liquidity`, `identified_debt` y `obligations` incluyen `value` en EUR (nullable), `covered_company_ids`, `explanation` y `evidence_refs`. Obligaciones añade `horizon`. Son agregados recibidos, nunca una suma de los miembros hecha por el navegador. Explicar perímetro, restricciones y eliminaciones intragrupo aplicadas. La liquidez es una posición a la fecha de corte: no se obtiene sumando flujos operativos y apoyo. La deuda agregada excluye las posiciones internas que Data pueda identificar y eliminar, declarando los límites de esa consolidación.
- Cada miembro tiene Health Score y cuatro dimensiones nullable, trayectoria nullable, prioridad `attention`, rol observado, importes identificados y `outlook`. `outlook.status: insufficient` exige `funding_need: null`. Las perspectivas son suministradas y deben describir sus supuestos; el frontend no predice necesidades ni simula distribuciones de caja.
- Los roles son `provider`, `receiver`, `both`, `none_identified` o `unknown`. No se deducen de un saldo, de un score ni de la ausencia de enlaces. Un `null` nunca se convierte en cero.
- El esquema permite hasta 50 miembros, 200 relaciones, 30 recomendaciones y 50 grupos de evidencia, con hasta 10 registros representativos en cada grupo. No enviar millones de movimientos ni credenciales, IBAN completos o datos personales innecesarios.

### Relaciones y evidencia

- `relations[].status`: `identified` significa identificada por Data con evidencia alta; `candidate`, hipótesis por confirmar; `unknown`, no atribuible de forma fiable. La cobertura numérica no se transforma automáticamente en ese estado ni representa probabilidad de acierto.
- Tipos: `support`, `transfer`, `cash_pooling`, `treasury_circulation`, `commercial`, `unknown`. Las relaciones comerciales no se convierten en apoyo por compartir grupo. Los traspasos entre cuentas de la **misma** sociedad se analizan en la ficha individual, no se convierten en autoenlaces del grafo.
- `from_company_id` y `to_company_id` deben ser miembros o `null` cuando no se identifica el extremo; al menos uno debe existir. No dibujar extremos inventados: esas relaciones siguen accesibles en la lista. La ausencia de una conexión no demuestra ausencia de relación.
- `volume` cuenta cada transferencia o pago una sola vez, no ambas patas bancarias. `transfer_count` es el recuento de transferencias/pagos, no de apuntes; ambos admiten `null`. No sumar candidatos, desconocidos y flujos confirmados como si tuvieran la misma base. Para relaciones comerciales, explicar si el importe corresponde a facturas o a pagos observados.
- `recurrence`, `change`, `first_seen`, `last_seen` y `explanation` vienen preparados por Data. Los cambios admiten `new`, `increasing`, `stable`, `decreasing`, `unknown`; no se buscan patrones en el frontend.
- Una relación identificada exige dos sociedades distintas, tipo conocido y evidencia enlazada que conecte esos extremos: transacciones con sociedad observada, contraparte y signo coherentes con la dirección, o facturas entre emisora/receptora para una relación comercial. Esta comprobación valida registros suministrados; no encuentra parejas ni reclasifica movimientos.
- La evidencia de grupo contiene registros `transaction`, `invoice` y `metric`. Cada grupo incluye título, periodo, explicación, cobertura y número total de registros. Usar grupos de evidencia específicos para cada relación cuando sea posible; la UI abre los grupos referenciados, no toda la biblioteca. Las referencias de sociedades, relaciones y evidencia se validan y los identificadores no pueden duplicarse.

### Recomendaciones

El pipeline suministra `recommendations[]`, incluyendo prioridad, motivo, señales de origen, pasos a revisar, límites, cobertura y referencias. Los siete tipos son `recurring_support`, `liquidity_distribution`, `increasing_dependency`, `funding_structure`, `concentration`, `stress_liquidity` e `insufficient_evidence`. Las señales pueden proceder de `health`, `momentum`, `resilience`, `cash_truth`, `network`, `liquidity`, `obligations`, `outlook`, `concentration` o `confidence`.

No hay API de transferencias ni botones para mover fondos. La UI propone revisar, investigar o preparar escenarios. **La caja no se presume fungible entre sociedades**; deben comprobarse restricciones legales, fiscales, contractuales y operativas antes de actuar. Una recomendación de estrés no calcula automáticamente un resultado futuro.

### Ejemplo completo de exportación de grupo

Ejemplo reducido a dos sociedades para ilustrar todos los bloques. Las cifras son ilustrativas, no resultados verificados: Data debe sustituirlas, no instalarlas como análisis real. El test valida este JSON con el mismo esquema y el mismo comando de producción.

```json
{
  "schema_version": "1.0",
  "source": "generated",
  "group_id": "GROUP_0042",
  "as_of": "2026-08-31",
  "period": "sep 2025 – ago 2026",
  "currency": "EUR",
  "summary": "El perímetro observado contiene una aportante y una receptora de apoyo. Revisar generación propia y condiciones del soporte.",
  "coverage": { "known_company_count": null, "confidence": 86, "explanation": "Dos sociedades observadas; no se conoce el perímetro completo del grupo." },
  "available_liquidity": { "value": 8450000, "covered_company_ids": ["COMP_0356", "COMP_0007"], "explanation": "Posición de liquidez suministrada para ambas sociedades. No implica disponibilidad para transferir entre ellas.", "evidence_refs": ["positions"] },
  "identified_debt": { "value": 9400000, "covered_company_ids": ["COMP_0356", "COMP_0007"], "explanation": "Deuda externa identificada en este perímetro; no es el total jurídico del grupo.", "evidence_refs": ["positions"] },
  "obligations": { "value": 1520000, "covered_company_ids": ["COMP_0356", "COMP_0007"], "horizon": "sep 2026 · 30 días", "explanation": "Vencimientos identificados de ambas sociedades.", "evidence_refs": ["positions"] },
  "limitations": ["No se presume que la caja sea fungible entre sociedades.", "La ausencia de relaciones observadas no demuestra que no existan otras."],
  "members": [
    {
      "company_id": "COMP_0356", "health_score": 72,
      "dimensions": { "momentum": 68, "cash_generation": 81, "resilience": 74, "debt": 59 },
      "trajectory": "deteriorating", "role": "receiver", "available_liquidity": 250000, "identified_debt": 3400000, "obligations_due": 620000,
      "cash_generation_net": 25600, "internal_received": 4140000, "internal_provided": 0,
      "confidence": 88, "attention": "high", "summary": "Generación neta reducida frente al apoyo identificado.",
      "outlook": { "status": "insufficient", "horizon": "sep 2026", "summary": "Sin perspectiva suficientemente respaldada.", "funding_need": null, "confidence": null, "evidence_refs": [] },
      "evidence_refs": ["positions", "support-records"]
    },
    {
      "company_id": "COMP_0007", "health_score": 85,
      "dimensions": { "momentum": 83, "cash_generation": 92, "resilience": 80, "debt": 84 },
      "trajectory": "improving", "role": "provider", "available_liquidity": 8200000, "identified_debt": 6000000, "obligations_due": 900000,
      "cash_generation_net": 1800000, "internal_received": 0, "internal_provided": 4140000,
      "confidence": 93, "attention": "medium", "summary": "Aportante observada; revisar límites y restricciones antes de valorar recursos internos.",
      "outlook": { "status": "insufficient", "horizon": "sep 2026", "summary": "Sin perspectiva suficientemente respaldada.", "funding_need": null, "confidence": null, "evidence_refs": [] },
      "evidence_refs": ["positions", "support-records"]
    }
  ],
  "insights": [
    { "id": "support-weight", "title": "Poca caja propia frente al apoyo recibido", "explanation": "La operación identificada de COMP_0356 aporta menos que el apoyo. Revisar su recurrencia sin inferir insolvencia.", "severity": "high", "company_refs": ["COMP_0356"], "relation_refs": ["support-main"], "evidence_refs": ["support-records"] }
  ],
  "alerts": [
    { "id": "review-support", "title": "Revisar el peso del apoyo", "explanation": "El flujo merece revisión junto a las condiciones de financiación.", "severity": "high", "period": "sep 2025 – ago 2026", "company_refs": ["COMP_0356", "COMP_0007"], "relation_refs": ["support-main"], "evidence_refs": ["support-records"] }
  ],
  "concentration": [
    { "id": "provider", "title": "Una aportante identificada en el perímetro", "explanation": "No se afirma que sea la única alternativa del grupo completo.", "severity": "medium", "company_refs": ["COMP_0007"], "relation_refs": ["support-main"], "evidence_refs": ["support-records"] }
  ],
  "recent_changes": [
    { "id": "last-flow", "date": "2026-08-14", "title": "Nueva observación de apoyo", "explanation": "Se documentó una transferencia dentro de una relación existente.", "severity": "medium", "company_refs": ["COMP_0007", "COMP_0356"], "relation_refs": ["support-main"], "evidence_refs": ["support-records"] }
  ],
  "relations": [
    { "id": "support-main", "from_company_id": "COMP_0007", "to_company_id": "COMP_0356", "kind": "support", "status": "identified", "volume": 4140000, "transfer_count": 12, "period": "sep 2025 – ago 2026", "recurrence": "Apoyo recurrente en el periodo", "change": "increasing", "first_seen": "2025-09-12", "last_seen": "2026-08-14", "explanation": "Relación clasificada por Data como apoyo intragrupo; importe contado una vez por transferencia.", "confidence": 91, "evidence_refs": ["support-records"] }
  ],
  "recommendations": [
    {
      "id": "support-review", "type": "recurring_support", "priority": "high", "title": "Revisar el apoyo interno recurrente",
      "explanation": "Revisar el peso del soporte observado junto a la capacidad operativa y las obligaciones de ambas sociedades.", "period": "sep 2025 – ago 2026", "confidence": 88,
      "signals": [ { "source": "network", "observation": "Se identifican doce transferencias en la relación." }, { "source": "confidence", "observation": "La perspectiva futura todavía no tiene evidencia suficiente." } ],
      "review_steps": ["Contrastar si la necesidad de soporte es recurrente.", "Revisar límites, acuerdos y capacidad del aportante antes de estudiar alternativas."],
      "constraints": ["No se autoriza ninguna transferencia.", "La caja no se considera libremente transferible entre sociedades."],
      "company_refs": ["COMP_0356", "COMP_0007"], "relation_refs": ["support-main"], "evidence_refs": ["support-records", "positions"]
    }
  ],
  "evidence": [
    {
      "id": "support-records", "title": "Muestra de apoyo intragrupo", "period": "sep 2025 – ago 2026", "explanation": "Dos tramos de una transferencia representativa; no son las doce transferencias del periodo.", "confidence": 91, "total_count": 24,
      "rows": [
        { "kind": "transaction", "id": "GROUP-TX-001", "company_id": "COMP_0007", "counterparty_company_id": "COMP_0356", "transaction_date": "2026-08-14", "amount": -600000, "category": "Apoyo intragrupo identificado", "description": "Salida documentada de la aportante" },
        { "kind": "transaction", "id": "GROUP-TX-002", "company_id": "COMP_0356", "counterparty_company_id": "COMP_0007", "transaction_date": "2026-08-14", "amount": 600000, "category": "Apoyo intragrupo identificado", "description": "Entrada documentada de la receptora" }
      ]
    },
    {
      "id": "positions", "title": "Posiciones recibidas de Data", "period": "31 ago 2026", "explanation": "Liquidez, deuda y obligaciones del perímetro observado.", "confidence": 86, "total_count": 6,
      "rows": [
        { "kind": "metric", "id": "POS-0356", "company_id": "COMP_0356", "metric": "Liquidez disponible observada", "value": 250000, "unit": "EUR", "period": "31 ago 2026", "source": "Posición preparada por Data" },
        { "kind": "metric", "id": "POS-0007", "company_id": "COMP_0007", "metric": "Liquidez disponible observada", "value": 8200000, "unit": "EUR", "period": "31 ago 2026", "source": "Posición preparada por Data" },
        { "kind": "metric", "id": "DEBT-0356", "company_id": "COMP_0356", "metric": "Deuda externa identificada", "value": 3400000, "unit": "EUR", "period": "31 ago 2026", "source": "Deuda preparada por Data" },
        { "kind": "metric", "id": "DEBT-0007", "company_id": "COMP_0007", "metric": "Deuda externa identificada", "value": 6000000, "unit": "EUR", "period": "31 ago 2026", "source": "Deuda preparada por Data" },
        { "kind": "metric", "id": "DUE-0356", "company_id": "COMP_0356", "metric": "Obligaciones identificadas", "value": 620000, "unit": "EUR", "period": "sep 2026", "source": "Calendario suministrado por Data" },
        { "kind": "metric", "id": "DUE-0007", "company_id": "COMP_0007", "metric": "Obligaciones identificadas", "value": 900000, "unit": "EUR", "period": "sep 2026", "source": "Calendario suministrado por Data" }
      ]
    }
  ]
}
```

Validar grupos desde `frontend/`: `npm run validate:generated -- --groups`. El modo normal no contiene resultados ficticios. Para probar localmente sin el pipeline, `npm run dev:fixtures -- --port 3107` exporta ambos contratos a directorios temporales separados y habilita los fixtures solo en ese proceso. `GROUP_0042` tiene seis sociedades, relaciones identificadas/candidatas/desconocidas y siete tipos de revisión; `GROUP_0099` cubre el estado de perímetro vacío. Las fichas individuales de las sociedades adicionales son resúmenes de demo sin histórico o escenarios inventados. No se escriben JSON en `public/generated` ni se tocan archivos reales.

## Verificación de la entrega

Desde `frontend/`: `npm test`, `npm run lint`, `npm run build`, `npm run typecheck`. Para navegador: `npx playwright install chromium` y `npm run test:e2e` tras el build. Las pruebas cubren JSON ausentes/inválidos, ruta predeterminada, actualizaciones, ausencia de fallback, valores suministrados sin recálculo, escenarios sin coincidencia, español, accesibilidad y responsive.
