# Guion del vídeo de presentación — X Ray (3:00)

**Objetivo:** vender el producto y, a la vez, enseñar que debajo hay trabajo de datos serio (limpieza, pipeline, score medido). Reparto: ~50 % venta (0:00–1:32), ~40 % cómo está construido (1:32–2:40), ~10 % prueba y cierre (2:40–3:00).

**Formato recomendado: híbrido con tres registros** (≈40 % cámara, 40 % app, 20 % gráfico), alternados cada 15–40 s para dar ritmo.

| Registro | Bloques | Por qué |
|---|---|---|
| **CÁMARA** (persona hablando, tarjetas superpuestas) | A, D, E, G | La venta y la artesanía las cuenta alguien a la cara; el bloque de limpieza no tiene interfaz y un terminal no se lee en vídeo |
| **APP** (grabación de pantalla) | B, C | Es la demo: la app es la prueba de que existe |
| **GRÁFICO** (diagrama animado + voz en off) | F | El pipeline se entiende en 5 s con un diagrama, no con una ristra de scripts |

Dos voces como máximo: una "vende" (A, B, C, D, G) y otra "construye" (E, F). El resto del equipo aparece en el plano final. Versión mínima si no hay tiempo de grabarse: cámara solo en A y G; nunca cero cámara.

**Ritmo:** ~500 palabras en 180 s (≈170 ppm). Es brioso. Si al grabar se pasa de 3:00, cortar primero las frases marcadas `[opcional]`.

**Nombre:** el frontend dice **X Ray**; los docs antiguos dicen *Embat Pulse*. El guion usa X Ray. Decidir uno y no mezclarlos.

---

## Guion

| Tiempo | Pantalla | Voz en off |
|---|---|---|
| **A · 0:00–0:15**<br>Gancho<br>`CÁMARA` | Persona a cámara; a su lado (o en corte de 5 s) el gráfico de dos líneas con datos reales (`history` de los JSON): COMP_0142 45→59 y COMP_0262 84→59, las dos acaban en **59** en agosto 2026. Aparecen las etiquetas `improving` / `deteriorating`. | Dos empresas. Hoy tienen exactamente el mismo score: 59. Una viene de 45 y sube; la otra viene de 84 y cae. En la foto de hoy no se distinguen. En el rastro de su dinero, sí. Eso es lo que lee X Ray. |
| **B · 0:15–1:00**<br>Producto<br>`APP` | `/` Portfolio: filtrar `improving`, luego `deteriorating`. Abrir `/companies/COMP_0262`: Health Score, trayectoria 24 meses, bloque "por qué ha cambiado" (drivers con sus puntos). Bajar a **Origen de la caja**. Terminar en el **simulador** moviendo un slider (COMP_0764: entradas −20 % → 34 → 23). | X Ray lee cada mes bancos, facturas y deuda de una cartera entera y responde por empresa: cómo está, hacia dónde va y por qué.<br><br>En la cartera ves en diez segundos quién mejora y quién empieza a torcerse, no solo quién está mal.<br><br>En la ficha, un Health Score de 0 a 100, su trayectoria de 24 meses y qué señal lo movió: margen operativo, servicio de deuda, retrasos de cobro y de pago. Las contribuciones suman exactamente el score: sin caja negra.<br><br>Origen de la caja separa lo que la empresa genera de lo que solo circula entre cuentas o llega del grupo. Y el simulador muestra el score si las entradas caen un 20 % o cobras 30 días más tarde. `[opcional]` Escenario, no predicción. |
| **C · 1:00–1:18**<br>Grupo y monitor<br>`APP` | `/groups/GROUP_0067` → red de flujos → `/recommendations` ("Acciones para revisar", guardas, supuestos). Corte a la lista del monitor (`data/processed/monitor/alerts.json` renderizada: empresa, tipo, severidad, evidencia). | En un holding, la vista de grupo dibuja quién financia a quién y propone escenarios con guardas: qué filial puede asumir las cuotas de otra, qué descubierto se cubre con caja de una hermana. Supuestos en pantalla; nada se ejecuta solo.<br><br>Y el monitor levanta la mano sin que le preguntes: en agosto, 87 alertas en 85 empresas, con evidencia y severidad. |
| **D · 1:18–1:32**<br>Comprador<br>`CÁMARA` | Persona a cámara. Superponer: "¿Quién paga?" → logo Embat → dos flechas: "capa premium para el CFO" / "su cartera: quién se tensiona, a quién ofrecer circulante". | ¿Quién lo paga? Embat. Ya tiene estos datos conectados; X Ray es la capa premium que los convierte en decisiones para el CFO. Y sobre su propia cartera, Embat ve antes qué cliente se tensiona y a cuál ofrecer circulante. |
| **E · 1:32–2:12**<br>Datos y limpieza<br>`CÁMARA` | La segunda voz ("construye") a cámara. Según nombra cada trampa aparece una tarjeta grande a su lado: bytes NUL, año 7025, 39 % sin categoría, 14 % espejos + 9 % intragrupo, 219.367 fechas de pago anuladas, `status` = foto. Un solo corte a pantalla de 3–4 s al final: tabla de `data/cleaned` con las columnas `is_internal_transfer`, `is_intragroup`, `is_sync_duplicate`, `is_stale_pending` resaltadas. Sin terminal corriendo: no se lee. | Esto solo vale si los datos son de fiar, y no lo eran. Dos millones y medio de movimientos y 900.000 facturas de 1.286 sociedades en 250 grupos.<br><br>El fichero de transacciones ni se parseaba: bytes nulos y saltos de línea dentro de campos. Vencimientos en el año 7025. El 39 % del importe sin categoría. Un 14 % de movimientos eran espejos entre cuentas propias y un 9 % intragrupo: no son ingresos. Doscientas mil fechas de pago que eran relleno, y un estado de factura que es foto de hoy, no historia: usarlo tal cual mete el futuro en el pasado.<br><br>Nuestra regla: la limpieza no borra, marca. Cada duda es una columna con su decisión numerada y su porqué; las features deciden qué filtrar. |
| **F · 2:12–2:40**<br>Pipeline y score<br>`GRÁFICO` | Diagrama animado: `raw → cleaned (Parquet + manifest/hash) → features mensuales (empresa, grupo, EUR) → score V2 → producto (Origen de caja, what-if, monitor) → JSON → Next.js`. Después, tres tarjetas: **Nivel** (flujos 6m) · **Momentum** (trimestre vs trimestre ÷ σ propia) · **Episodio** (2 meses de confirmación). Insertar salida de `06_validate_scores_v2.py --check-prefix 2026-02-01` en verde. | Todo es un pipeline reproducible: raw inmutable, capa limpia en Parquet con hashes, features mensuales por empresa y grupo, score, producto y web. Nada del mes t mira más allá de t; un test lo comprueba cortando la historia.<br><br>El score tiene tres capas: nivel, sobre flujos de seis meses; momentum, trimestre contra trimestre, dividido por la volatilidad propia de cada empresa; y episodio: dos meses de confirmación para separar bache de tendencia. La referencia se congela: el test oculto se puntúa sin recalibrar. |
| **G · 2:40–3:00**<br>Medido y cierre<br>`CÁMARA` | Vuelve la primera voz a cámara con la tarjeta "3,5 meses de antelación · 44 % detectado · 9 % de meses en alarma" y, pequeño, "78 % de falsas alarmas en la alarma de score, publicado". Corte de 2 s a `pytest` y `npm test` en verde. Última frase con el equipo entero en plano; cierre: logo X Ray + URL de la demo. | Y lo medimos antes de venderlo: la alerta de presión de deuda anticipa el estrés propio con tres meses y medio de mediana, encendida solo el 9 % de los meses. `[opcional]` Publicamos también las falsas alarmas. Más de 600 tests automatizados.<br><br>X Ray. No cuenta el dinero: lo lee. |

---

## Cifras que se dicen y de dónde salen

Todas comprobadas el 20-09 sobre los artefactos locales. No improvisar otras.

| Cifra | Valor | Fuente |
|---|---|---|
| Gancho | COMP_0142: 45 (feb-26) → 59 (ago-26), `improving`. COMP_0262: 84 (feb-26), 100 (mar-26) → 59 (ago-26), `deteriorating`. Ambas `scored`, confianza 95/93 | `frontend/public/generated/companies/*.json` (`history`), `portfolio.json` |
| Dataset | 1.286 sociedades, 250 grupos, 24 meses; 2.556.437 transacciones; 897.894 facturas; 9 CSV, ~615 MB | `CLAUDE.md`, `decisiones.md` §5 |
| Transacciones ilegibles | Bytes NUL, `\r` sueltos y saltos de línea dentro de campos entrecomillados; pyarrow falla | `CLAUDE.md` |
| Fechas absurdas | `due_date` en el año 7025; `value_date` 2099-12-31 (eliminada) | `CLAUDE.md`, F05/T03 |
| Sin categoría | 25 % de filas, **38,8 % del importe absoluto**; depende del banco (HSBC/ING 85 %) | `hallazgos-datos.md` §5 |
| Espejos / intragrupo | `is_internal_transfer` 14 %, `is_intragroup` 9 % | `CLAUDE.md` (limpieza) |
| Fechas de pago de relleno | 219.367 `payment_date` anuladas por no estar `paid` (F04) | `decisiones.md` §5 |
| `status` es foto | Fuga del futuro si se usa en el mes t; `overdue` ~20 % desde 2024, ρ AR-AP ≈ 0,6 (higiene ERP) | `CLAUDE.md`, `hallazgos-datos.md` §9 |
| Puntuadas | 1.011 empresas con Health Score en agosto 2026 (284 `scored`, 727 `provisional`); 275 sin puntuar con motivo | `ESTADO-ACTUAL.md` §3 |
| Estabilidad V2 | Cambio mensual mediano 3,3 puntos (V1: 8,8); cambios >10 puntos 6,5 % (V1: 20 %) | `scoring-v2.md` §6 |
| Prefijo temporal | `--check-prefix 2026-02-01` invariante en features y scores | `ESTADO-ACTUAL.md` §3 |
| Monitor | 87 alertas en 85 empresas (70 presión de deuda, 17 deterioro confirmado) | `decisiones.md` D44, `data/processed/monitor/alerts.json` |
| Alerta presión de deuda | 44 % de detección, 9 % de meses en alarma, ×1,8 sobre la tasa base en reserva, 3,5 meses de antelación | `ESTADO-ACTUAL.md` §6.4, D43 |
| Alarma del score (V2) | 32 % de 142 eventos detectados, mediana 3 meses (p25–p75 2–5), **78 % de falsas alarmas**, ×1,2 | `decisiones.md` D41 |
| Mejora (dos direcciones) | 26 % de 94 recuperaciones avisadas con `improving`/`emerging_improvement`, mediana 3 meses | `decisiones.md` D41 ampliado |
| Simulador | 81 escenarios precalculados por empresa; COMP_0764: entradas −20 % → 34 → 23 | `decisiones.md` FE-05 |
| Grupo | Cash pooling: 85,4 % de meses en negativo cubribles con caja de una hermana; netting 92,5 % menos bruto; 48 planes de advisor con palanca O | `decisiones.md` D47, D48 |
| Tests | 566 Python + 67 frontend (> 600); lint y typecheck limpios | `checklist-entrega.md` §3.2 |

---

## Lo que NO se dice (aunque venda)

- **"Predice quiebras" / "anticipa 3 meses" como promesa universal.** Se dice "anticipa el estrés propio con 3,5 meses de mediana en el 44 % de los casos" y se enseña la tasa de alarma. Los propios docs registran que la alarma del score tiene 78 % de falsas alarmas: si lo pregunta el jurado, ya está publicado.
- **"Nuestro score discrimina mejor que…"**: frente a los proxies internos ni V1 ni V2 discriminan (AUC 0,49–0,56). V2 se adoptó por estabilidad y explicabilidad. No hay comparación con la nota del organizador.
- **"Red de contagio" / "radar de clientes"**: no hay contrapartes compartidas entre empresas. La vista de grupo es intragrupo, no red de mercado.
- **"Recomendación" ejecutable**: es "escenario mecánico bajo supuestos explícitos", con guardas; la UI ya lo dice ("Sin ejecución automática").
- **"Probabilidad" o "crédito preaprobado"**: el score es un índice 0–100, la confianza es cobertura de datos, no probabilidad.
- **"250 empresas"**: son 250 grupos y 1.286 sociedades.
- Nada de "las pymes" como comprador: el comprador es Embat (y, en segundo lugar, un financiador).

---

## Notas de producción

**Antes de grabar**

1. **Alertas en la ficha:** el exportador publica `alerts: []` (`src/xray/product/frontend_export.py`, líneas 273 y 384), así que el monitor **no se ve en la UI** todavía. Para el bloque C: o se conecta `data/processed/monitor/alerts.json` a `alerts[]` y a una columna del Portfolio, o se graba el JSON renderizado como tabla (una hoja o un HTML de un minuto). No enseñar el bloque de alertas vacío.
2. **URL pública:** si el deploy en Vercel está hecho, grabar sobre él y mostrar la URL en el cierre. Si no, `npm run dev -- --port 3111` a pantalla completa sin barra de direcciones y sin mencionar "local".
3. **Regenerar el gancho:** si se vuelve a ejecutar el pipeline, recomprobar que COMP_0142 y COMP_0262 siguen en 59 (`portfolio.json`). Si cambian, buscar otro par con `|Δscore| ≤ 3` y trayectorias opuestas.
4. **Nombre único** (X Ray o Embat Pulse) en slides, UI y voz.

**Orden de trabajo: audio primero**

1. Grabar la voz completa por bloques (dos voces). El vídeo dura lo que dura la voz.
2. Grabar la pantalla siguiendo el audio ya grabado, no al revés.
3. Grabar cámara: cada bloque en 2–3 tomas; se elige la mejor.
4. Montar, superponer cifras y exportar. Comprobar que no pasa de 3:00.

**Grabación de pantalla (B, C y los cortes de E, F, G)**

- Un solo navegador a 1080p, zoom 125 %, modo claro, sin extensiones, pestañas ni barra de marcadores. Ocultar la barra de direcciones si la demo es local.
- Cursor lento y deliberado; sin scroll muerto. Ninguna vista más de 6–8 s. En edición, zoom sobre los drivers y sobre el score cuando se nombran.
- Recorrido B en un plano continuo (Portfolio → filtro → ficha → scroll → simulador); los cortes van en C.
- Planos de 2–3 s para `06_validate_scores_v2.py --check-prefix` y `pytest -q` en verde: fondo oscuro, fuente grande, solo el final del log.

**Cámara (A, D, E, G)**

- Móvil en horizontal a la altura de los ojos, luz de frente (una ventana vale), fondo neutro y sin ruido. Micro de auriculares o el del móvil a menos de un metro.
- Mirar a la lente, no a la pantalla. Memorizar la idea de cada frase, no la frase.
- Las tarjetas con cifras se añaden en edición sobre el plano de cámara: siempre que se dice un número, se ve.

**Gráficos (A, F y tarjetas)**

- Slides planas, misma tipografía y colores que la UI; nada de stock ni de plantillas. Diagrama de F con animación de aparición por etapas.

**Voz**

- El bloque E es el más denso: leerlo con pausas en los dos puntos.
- Si sobran segundos, alargar el silencio del gancho (A) antes de "Eso es lo que lee X Ray", no añadir texto.

**Plan B de 2:30** (si la organización exige menos): quitar el bloque D como slide y decir su primera frase al final de C; quitar el `[opcional]` y la frase de netting/descubiertos de C.
