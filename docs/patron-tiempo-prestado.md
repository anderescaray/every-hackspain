# Tiempo prestado: el crédito que se esconde dentro de las fechas

**Investigación y propuesta para X-Ray · Embat · HackSpain 2026**  
**Fecha:** 19 de septiembre de 2026.  
**Alcance:** análisis sin modificar el producto. Este documento es el único archivo creado en esta sesión. No se han añadido scripts, features, modelos, dependencias ni cambios de configuración.

## 1. Mi conclusión, sin venderte humo

**No sustituiría Cash Truth. Lo ampliaría con una pregunta que el score actual no sabe contestar:**

> **¿Estás convirtiendo mejor tu actividad en dinero, o alguien está financiando la diferencia dándote más tiempo?**

El patrón más interesante que he encontrado no es simplemente que una empresa pague tarde. Es que **puede mejorar su puntualidad mientras empeora el tiempo que tarda en liquidar sus facturas**, porque también ha cambiado el vencimiento contra el que medimos esa puntualidad.

Y puede ocurrir al revés: liquidar antes desde la emisión, pero parecer más impuntual porque ahora el plazo es más corto.

El punto casi imperceptible es este:

> **La regla con la que medimos el retraso también se mueve. Si solo miramos el retraso, podemos confundir una concesión de crédito comercial con una mejora de conversión de caja.**

Hay evidencia concreta en estos datos. En una relación de clientes de `COMP_1171`, el retraso medio registrado pasa de **19,65 días a cero**, pero el tiempo emisión–liquidación pasa de **81,24 a 102,25 días**. No se está cobrando antes en esa población de documentos; se están liquidando documentos con plazos más largos. La comparación resiste ponderación monetaria, medianas y controles de deduplicación.

**Lo que NO he encontrado:** un predictor extraordinario que permita prometer ganar el leaderboard o anticipar universalmente el deterioro. La contracción de plazos a proveedores tiene una asociación exploratoria modesta, intervalos amplios y no mejora de manera consistente un baseline de caja.

Mi apuesta sería un producto de **diagnóstico y gestión del crédito comercial implícito**, apoyado en un score corregido. No otro indicador sofisticado al que asignarle un peso grande porque tiene una historia atractiva.

### Las tres afirmaciones que sí defendería

1. **Un buen comportamiento respecto al vencimiento y una buena velocidad de conversión no son lo mismo.** Pueden moverse en direcciones opuestas, incluso para la misma contraparte.
2. **Los plazos contienen una dimensión de financiación que no aparece en `debt_products.csv`.** Son tiempo concedido o recibido, aunque no sepamos quién decidió cambiarlo ni por qué.
3. **El producto puede convertir esa diferencia en una decisión concreta:** qué relación revisar, qué vencimientos han cambiado, qué importes quedan comprometidos durante más tiempo y qué negociación tendría sentido estudiar.

No puedo garantizar que nadie más haya pensado en esto. El crédito comercial es un concepto conocido. La aportación diferencial sería **medirlo dentro de las mismas relaciones, separar tres relojes y demostrar cuándo una explicación del score sería equivocada**.

---

## 2. Qué rescato de tu ejemplo de los tokens de Claude

No sabemos por esta anécdota por qué un proveedor concede tokens a una empresa y no a otra. Puede influir su potencial como cliente, el uso esperado, un programa comercial, una integración o una relación estratégica. No permite concluir que el proveedor haya diagnosticado mejor salud financiera.

Pero la intuición útil es muy buena:

> **Las condiciones que otros aceptan ofrecerte pueden contener información que aún no aparece en tus resultados.**

En estos CSV no tenemos decisiones comerciales de Anthropic ni solicitudes de crédito aprobadas y rechazadas. El equivalente observable más cercano es:

- cuánto tiempo aparece concedido para pagar a un proveedor;
- cuánto tiempo concede la empresa a sus clientes;
- cómo cambian esas condiciones para una misma relación;
- cuánto tiempo tarda realmente la liquidación registrada;
- y cuánto de esa espera sucede antes o después del vencimiento.

Hay una distinción esencial de dirección:

| Lado | Qué observamos | Quién financia a quién |
|---|---|---|
| AP: facturas a pagar | Plazo recibido por la empresa | El proveedor financia a la empresa durante ese plazo |
| AR: facturas a cobrar | Plazo concedido por la empresa | La empresa financia a su cliente durante ese plazo |

**Un aumento de plazo AR no significa que otros confíen más en la empresa. Significa que la empresa está concediendo más tiempo a sus clientes.** Confundir esas dos direcciones destruiría la tesis.

Tampoco llamaría automáticamente «retirada de confianza» a una reducción de plazo AP. Puede ser una condición negociada, un cambio de producto, un descuento, una política de grupo, estacionalidad o una diferencia de registro.

El nombre prudente de la señal es **cambio de condiciones observadas**, no «lo que el mercado sabe de ti».

---

## 3. Qué he revisado de lo que ya tienes

He leído el motor de features, el scoring, la limpieza de facturas, la documentación de producto y scoring, el informe de investigación anterior y los métodos que generan sus paneles y validaciones.

### Conservaría

- La separación entre Health, Momentum, Stability y Confidence.
- La explicación por dimensiones y la navegación empresa–mes prevista.
- La neutralización de circulación de dinero antes de interpretar generación operativa.
- El análisis local de contrapartes: no hace falta inventar una red global.
- La cobertura y las advertencias de datos como parte visible del producto.
- El rigor del informe anterior al descartar predicciones que no se sostienen.

### El hueco que veo

En `src/xray/features/__init__.py`, las features de pagos se centran en `payment_date - due_date`. El score utiliza retrasos de clientes/proveedores y ratios de vencidos, pero no separa explícitamente:

1. **el plazo registrado:** vencimiento menos emisión;
2. **la duración hasta liquidación:** liquidación menos emisión;
3. **el exceso sobre el plazo:** liquidación menos vencimiento.

El panel de investigación ya contiene medianas de plazo por empresa, pero las 31 hipótesis y las 33 señales temporales del trabajo anterior no prueban el cambio de plazo dentro de la misma relación de la forma desarrollada aquí.

Por tanto, esto no es renombrar supplier stretching. **Estirar unilateralmente un pago y recibir más plazo son hechos distintos.** Ambos pueden sostener caja, pero tienen consecuencias contractuales y explicaciones diferentes.

### Antes de añadir una feature, corregiría estos problemas

Los cinco primeros ya estaban señalados en la investigación anterior y siguen siendo relevantes:

- Foto final de deuda distribuida por meses históricos.
- Uso histórico de flags de vencimiento calculados con la extracción final.
- Percentiles expansivos que dan el máximo a una serie constante.
- Comparación transversal de importes absolutos sin normalizar tamaño.
- Flujos que todavía mezclan circulación, operación y financiación.

Además, he comprobado en memoria dos problemas concretos del código actual:

**A. La trayectoria puede cambiar porque cambian los demás.**

Al ejecutar `_dimension_score` con una única feature favorable, A conserva el valor 10 en dos meses. B pasa de 20 a 5. El componente de A pasa de **80 a 100**, aunque A no cambia. Es consecuencia de mezclar percentil propio con ranking transversal del mes.

Eso puede ser válido como posición relativa. No debe explicarse como mejora propia. También obliga a definir una referencia estable para puntuar un lote oculto: el score absoluto no debería depender arbitrariamente de qué otras empresas vengan en la misma petición.

**B. Hay una explicación con signo incorrecto en el fallback.**

La llamada a `_row_drivers` con una feature favorable que baja de 100 a 90, sin cambio de dimensión disponible, devuelve una contribución **+0,1**. El fallback usa `direction * abs(delta)` y pierde el signo del cambio. No he modificado esa función.

Además, sus contribuciones aproximadas no constituyen una descomposición exacta del cambio final del score. No las presentaría como puntos aditivos auditables sin revisar el cálculo.

**Prioridad:** arreglar la validez del motor y de sus explicaciones tiene más valor que añadir una señal sutil encima de una medición inconsistente.

---

## 4. Qué he analizado en esta sesión y qué he reutilizado

### Recalculado desde los originales de Descargas

- Las **897.894 filas** de `invoices.csv`.
- Las **2.556.437 transacciones**, para la exploración de fechas contables y fechas valor, leyendo las columnas necesarias.
- El maestro de sociedades y el diccionario original.
- Comparaciones de plazos dentro de relaciones repetidas.
- Descomposiciones del tiempo hasta liquidación.
- Casos con identificadores de documentos originales.
- Sensibilidades de población, tipos de documento, importes y deduplicación.

Los cálculos se han ejecutado en memoria. No se han guardado datasets derivados nuevos.

### Reutilizado, con lectura del método

Para contrastar si los nuevos plazos anticipan el proxy de deterioro de caja, he utilizado el panel existente:

`research/sweep_corrected/temporal_signals.parquet`

Contiene la caja corregida de barridos, las condiciones de calidad y las particiones de la investigación anterior. **No he reconstruido de nuevo toda esa depuración bancaria ni sus 35 tests.** Las métricas nuevas dependen de ese panel y de sus limitaciones, además de los nuevos cálculos de facturas.

### Selección de facturas

Para hacer comparable la investigación con la anterior:

- `document_type` en `invoice` / `invoiceGroup`;
- `status != cancel`;
- importe distinto de cero y valor absoluto no superior a 100 millones de moneda nativa;
- emisión desde 2024-09-01 hasta antes de 2026-09-01;
- moneda de factura = moneda contable = moneda de la sociedad;
- `exchange_rate = 1`;
- eliminación de duplicados candidatos por empresa, contraparte, tipo, emisión, vencimiento, importe y concepto.

Resultado: **689.170 documentos**, coincidente con la selección anterior.

Para explorar plazos añado contraparte explícita y plazo entre 0 y 180 días:

| Población | Documentos | Sociedades |
|---|---:|---:|
| Total elegible de plazos | 666.753 | 764 |
| AP | 392.099 | 760 |
| AR | 274.654 | 693 |

Hay **257.105 documentos con plazo cero** en esa selección. No daría por hecho que todos son exigibles al contado: algunos pueden reflejar una convención o una carencia del ERP. Por eso hay controles adicionales sin esos plazos.

AR/AP se deduce del signo, como en el proyecto. No existe una columna contractual explícita de dirección. Los resultados heredan ese supuesto.

---

## 5. El mecanismo: tres relojes en lugar de uno

Para un documento liquidado, con fechas comparables:

```text
L = fecha_vencimiento − fecha_emisión
A = fecha_liquidación − fecha_emisión
D = fecha_liquidación − fecha_vencimiento

A = L + D
```

- **L: tiempo concedido.** Condición registrada, no necesariamente contrato verificado.
- **A: tiempo transcurrido hasta la liquidación registrada.** No es DSO/DPO contable exacto.
- **D: retraso respecto al vencimiento.** Disciplina contractual registrada.

Con medias calculadas sobre los mismos documentos y los mismos pesos:

```text
ΔA = ΔL + ΔD
```

La identidad no se puede trasladar sin más a tres medianas independientes. Las medianas sirven como sensibilidad, no como descomposición aditiva.

### Cuatro estados que un único retraso no distingue

| Cambio observado | Lectura razonable | Lectura que evitaría |
|---|---|---|
| AR: A baja y D baja, con L estable | Conversión registrada más rápida y mejor puntualidad | «Seguro que no habrá problemas» |
| AR: D baja, pero A sube porque L sube más | Mejor puntualidad con más tiempo de financiación concedida al cliente | «Estamos cobrando antes» |
| AP: A sube, D no sube y L aumenta | Más financiación comercial dentro del plazo observado | «La empresa ha dejado de pagar» |
| AP: D sube, pero A baja porque L cae más | Menos tiempo disponible aunque se liquide antes desde emisión | «Paga cada vez más despacio» |

**Una concesión legítima puede ser buena gestión.** El objetivo no es castigarla. Es no atribuirle una mejora de generación operativa que no demuestra.

Para implementación futura, normalizaría primero las fechas a un calendario coherente. En la exploración hay seis documentos liquidados donde truncar horas con `.dt.days` rompe la identidad en un día. No pertenecen a las sociedades de los diez casos que sobreviven todos los controles del apartado 7. No atribuiría significado financiero a diferencias horarias de ese tipo.

---

## 6. El caso principal: puntualidad perfecta, conversión más lenta

### Sociedad y relación

- Sociedad: **COMP_1171**.
- Grupo: **GROUP_0139**.
- Moneda: **EUR**.
- ERP registrado: `businessCentral`.
- Cliente: **COUNTERPARTY_06105**.
- Documentos: `invoice`, AR.

Comparo documentos con liquidación registrada en dos ventanas consecutivas. Se exige pago observado válido y duración emisión–liquidación entre 0 y 180 días.

| Medida | Ago–oct 2025 | Nov 2025–ene 2026 | Cambio |
|---|---:|---:|---:|
| Documentos liquidados de la relación | 17 | 8 | — |
| Plazo medio L | 61,59 días | 102,25 días | +40,66 días |
| Duración media A | 81,24 días | 102,25 días | +21,01 días |
| Retraso medio D | 19,65 días | 0,00 días | −19,65 días |
| Duración mediana | 77 días | 114 días | +37 días |
| Retraso mediano | 15 días | 0 días | −15 días |
| Importe de los documentos de la ventana | 52.697,13 € | 27.171,18 € | Poblaciones de distinto volumen |

La identidad explica la aparente paradoja:

```text
+21,01 días de duración = +40,66 de plazo − 19,65 de retraso
```

Ponderando por importe tampoco desaparece:

| Media ponderada por importe | Ago–oct | Nov–ene |
|---|---:|---:|
| Duración hasta liquidación | 84,32 días | 108,47 días |
| Plazo | 61,38 días | 108,47 días |
| Retraso | 22,94 días | 0,00 días |

**Conclusión exacta:** mejora la puntualidad de los documentos liquidados de esa relación, pero no la velocidad emisión–liquidación. No estoy afirmando que se haya deteriorado toda la empresa ni que su banco haya cobrado exactamente esos importes en esas fechas.

### La parte que puede verse antes de la liquidación

La comparación anterior usa documentos ya liquidados. Para buscar una señal anterior hay que mirar las facturas **por emisión**, no esperar a su pago.

En junio–agosto de 2025, esta relación tiene **16 facturas emitidas**, con plazos entre 61 y 64 días y mediana **61,5 días**.

El **26 de septiembre de 2025** aparecen cuatro facturas nuevas con plazo **120 días** y vencimiento **24 de enero de 2026**:

| `operation_id` | Importe |
|---|---:|
| `7827cac0abfa1dee6f87fe8f8af3b4c5` | 6.025,80 € |
| `a2ee944be742d0dc7916873e75361323` | 1.815,00 € |
| `8289cdbcc553bc656f98d5f95399ca6c` | 2.420,00 € |
| `1c16d5effaf74ce578225b5d3d2deea3` | 9.259,11 € |
| **Total** | **19.519,91 €** |

Todas figuran finalmente liquidadas el 24 de enero de 2026. Ese desenlace sirve para verificar la historia, **no para construir la señal en septiembre**.

Respecto a la referencia de 61,5 días:

```text
Extensión de plazo: 120 − 61,5 = 58,5 días
Exposición adicional de tiempo: 19.519,91 × 58,5
                              = 1.141.914,74 euro-días
```

Los euro-días no son euros de pérdida ni euros de ahorro. Expresan importe por tiempo adicional de financiación contractual respecto a una referencia. El vencimiento hipotético basado en una mediana tampoco es un vencimiento legal anterior.

**Acción comercial defendible:** revisar por qué esa relación pasa a necesitar más plazo, si el precio compensa la financiación y qué condiciones conviene proponer en la próxima operación.

### El control que impide exagerar la historia

En septiembre–noviembre de 2024 esa misma relación ya tenía plazos largos: **7 facturas, mediana 93 días**. En septiembre–noviembre de 2025 hay **13 facturas, mediana 120 días**.

Por tanto:

- comparar solo con el trimestre de verano puede exagerar un cambio estacional;
- la diferencia de 58,5 días no es una estimación causal de deterioro;
- incluso el contraste interanual tiene pocos documentos y solo dos ciclos anuales;
- puede haber cambios de operaciones o condiciones no recogidos en los CSV.

Además, la caja agregada de COMP_1171 no muestra aquí una caída posterior monotónica: el margen operativo clasificado del panel es aproximadamente **+16,4% en enero de 2026**, **−1,5% en febrero** y **−1,4% en marzo**. No convertiría esta relación en una profecía de hundimiento de la sociedad.

**Es una demostración de interpretación y de financiación comercial, no un caso de anticipación de insolvencia.**

---

## 7. ¿Es una anécdota escogida? Qué sobrevivió y qué descarté

### Exploración de los tres relojes

Usé relaciones definidas por:

```text
sociedad × contraparte explícita × AR/AP × tipo documental × moneda
```

En cada cierre mensual, de febrero de 2025 a agosto de 2026, comparé los tres meses recientes de liquidaciones con los tres anteriores. Partí de la selección de plazos 0–180 días y acepté liquidaciones solo con `status = paid`, fecha no anterior a emisión y anterior a 2026-09-01. Limité también la duración emisión–liquidación a 0–180 días. Exigí al menos tres documentos en cada ventana por relación. Para las agregaciones de sociedad exigí al menos tres contrapartes; los cambios de medias por relación se ponderaron por `min(n_documentos_referencia, 30)`.

Hay **3.723 sociedad-mes AP de 392 sociedades** y **1.481 sociedad-mes AR de 185 sociedades** con esa cobertura agregada. Esto no significa que todas presenten el patrón.

Para seleccionar casos locales más exigentes utilicé:

- solo `invoice`;
- al menos cinco liquidaciones por ventana;
- plazo medio de cada ventana de al menos siete días;
- aumento medio de A de al menos siete días;
- caída media de D de al menos siete días.

Aparecen **38 relación-mes candidatas**.

### Controles posteriores de sensibilidad

Para cada candidata comprobé cuatro poblaciones:

1. `invoice`;
2. `invoice` más `invoiceGroup` de la misma relación y dirección;
3. solo facturas con plazo positivo;
4. deduplicación más agresiva ignorando concepto y conservando una fila por emisión, vencimiento, liquidación e importe.

En cada población calculé media simple, media ponderada por importe y mediana. Exigí al menos tres documentos por ventana y que **A siguiera aumentando ≥3 días y D disminuyendo ≥3 días en todas las variantes**.

Sobreviven **10 relación-mes, correspondientes a 8 sociedades y 7 grupos**:

| Sociedad | Lado | Contraparte | Cierre |
|---|---|---|---|
| COMP_0737 | AP | COUNTERPARTY_11150 | 2025-03 |
| COMP_1171 | AR | COUNTERPARTY_06105 | 2026-01 |
| COMP_1171 | AR | COUNTERPARTY_06105 | 2026-02 |
| COMP_1171 | AR | COUNTERPARTY_06105 | 2026-03 |
| COMP_0788 | AP | COUNTERPARTY_69365 | 2026-04 |
| COMP_0506 | AP | COUNTERPARTY_67399 | 2026-05 |
| COMP_0743 | AR | COUNTERPARTY_03948 | 2026-05 |
| COMP_0594 | AP | COUNTERPARTY_13858 | 2026-06 |
| COMP_0042 | AP | COUNTERPARTY_68552 | 2026-07 |
| COMP_0054 | AP | COUNTERPARTY_10037 | 2026-08 |

Son controles exploratorios posteriores a la búsqueda, no una prueba estadística confirmatoria. Las ventanas se solapan: **diez filas no equivalen a diez eventos independientes**.

Quitando GROUP_0139 quedan siete filas de siete sociedades y seis grupos. El mecanismo no depende enteramente del caso principal.

### Un caso llamativo que NO usaría como prueba robusta

`COMP_0665 / COUNTERPARTY_48839`, por el lado AP, parecía ideal: retraso medio de 20,55 a cero y duración de 37,82 a 79,94 días.

Pero al excluir los plazos cero y ponderar por importe, el aumento de duración se reduce a **0,89 días**, por debajo del mínimo de tres días exigido en los controles. La lectura fuerte no resiste todas las variantes.

Por eso no lo elegí como caso principal. No se debe seleccionar únicamente la ponderación que produce la historia más llamativa. Además, esa misma contraparte tiene documentos AR y AP: hay que mantenerlos separados incluso cuando comparten ID; mezclarlos cambia la pregunta financiera.

### Qué todavía no resuelven estos controles

- Solo describimos documentos con liquidación registrada: falta la población todavía abierta para evaluar toda la cartera.
- Un mismo cliente puede comprar productos distintos con condiciones diferentes; no hay SKU ni contrato homogéneo.
- La concentración de liquidaciones en un día puede ser remesa, actualización del ERP o generación sintética.
- Distintos documentos pueden representar fases de una misma obligación; no hay enlace completo entre factura, agrupación y banco.
- No sabemos si un vencimiento fue revisado después de emitirse.

La extensión imprescindible del producto sería combinar esta explicación con **cohortes completas de emisión y censura explícita**, no tratar a los documentos pagados como una muestra aleatoria de todas las facturas.

---

## 8. La hipótesis del mentor: cambios de plazo en las mismas relaciones

Esta es la parte más cercana a «qué te concede otro que no concede a los demás», pero la mediría **contra la historia de esa misma relación**, no contra otra empresa de tamaño o sector desconocido.

### Diseño exploratorio

Para cada cierre entre febrero de 2025 y agosto de 2026:

- ventana reciente: tres meses de emisión;
- referencia: tres meses inmediatamente anteriores;
- misma sociedad, contraparte, dirección, tipo documental y moneda;
- al menos tres documentos por ventana y relación;
- mediana del plazo en cada ventana;
- peso fijo por relación `min(n_documentos_referencia, 30)`;
- al menos tres contrapartes para agregar a sociedad.

```text
δL_relación = mediana(L_reciente) − mediana(L_referencia)

δL_sociedad = Σ peso_referencia × δL_relación / Σ peso_referencia
```

Se mantiene la misma cesta de relaciones comparables y se evita que una contraparte con miles de facturas domine por frecuencia. El peso no representa exposición monetaria: esta se muestra aparte.

Cobertura:

| Lado | Sociedad-mes | Sociedades | Grupos |
|---|---:|---:|---:|
| AP | 5.011 | 490 | 143 |
| AR | 2.496 | 286 | 113 |

Regla descriptiva de contracción AP: cambio ponderado ≤−7 días y al menos la mitad de las relaciones comparables reducen su mediana ≥7 días.

- **74 sociedad-mes, 45 sociedades, 30 grupos.**
- Si esas relaciones deben cubrir al menos el 50% del importe AP elegible reciente: **28 sociedad-mes de 18 sociedades**.

No son 74 retiradas de confianza demostradas. Son 74 ventanas con esa geometría de plazos.

### Versión más conservadora

Además de lo anterior, para admitir cada relación:

- solo `invoice`;
- mediana de plazo de ambas ventanas entre 7 y 120 días;
- ticket mediano reciente entre la mitad y el doble del anterior;
- al menos tres contrapartes admitidas por sociedad;
- cobertura de al menos el 30% del importe AP elegible reciente.

El límite de 7–120 días se aplica a **las medianas de las relaciones**; no significa que cada documento individual tenga ese plazo. La población original de documentos sigue limitada a 0–180 días.

Resultados:

| Patrón conservador | Sociedad-mes | Sociedades | Grupos |
|---|---:|---:|---:|
| Contracción ≥7 días y amplitud ≥50% | 16 | 14 | 10 |
| Expansión ≥7 días y amplitud ≥50% | 10 | 8 | 8 |

La señal no solo detecta menos plazo; también encuentra ampliaciones. **No equipararía ampliación a mejora financiera sin más contexto.** Puede ser negociación favorable, estacionalidad o reestructuración.

### Caso de contracción: COMP_0817

En junio de 2026, comparando abril–junio con enero–marzo:

- seis proveedores comparables;
- todos reducen su mediana al menos siete días;
- cambio agregado: **−28,94 días**;
- cobertura monetaria de esas relaciones: **67,4%** del AP elegible reciente.

| Contraparte | Documentos antes / después | Plazo mediano antes | Después |
|---|---:|---:|---:|
| COUNTERPARTY_01323 | 3 / 4 | 57 | 44 |
| COUNTERPARTY_02245 | 9 / 4 | 95 | 35,5 |
| COUNTERPARTY_02544 | 6 / 3 | 68 | 43 |
| COUNTERPARTY_13574 | 3 / 3 | 67 | 60 |
| COUNTERPARTY_19182 | 5 / 4 | 44 | 23,5 |
| COUNTERPARTY_24223 | 6 / 5 | 62 | 49 |

Las seis relaciones tienen al menos dos fechas distintas de emisión en cada ventana. No son solo seis filas del mismo lote.

**Pero hay dos cautelas importantes:**

1. COUNTERPARTY_19182 concentra 551.879,11 € de los importes recientes emparejados. Seis proveedores no equivalen a seis exposiciones monetarias equilibradas.
2. En junio de 2026, las seis sociedades de GROUP_0070 con cobertura en la variante amplia reducen el plazo agregado al menos siete días. Puede haber política de grupo, ERP o mecanismo sintético común. No son seis votos independientes de seis mercados.

Excluyendo GROUP_0070, sobreviven **11 ventanas de 10 sociedades y 9 grupos** en la contracción conservadora. Hay otros casos, pero no convertiría la sincronía en causalidad.

### Caso de las dos direcciones: COMP_0521

Es una sociedad en **USD**, no en EUR. Las comparaciones siguientes son de días, sin mezclar importes entre monedas.

- Septiembre de 2025: ampliación conservadora **+25,87 días**, ocho proveedores, cobertura 53,3%.
- Agosto de 2026: contracción conservadora **−13,92 días**, cuatro proveedores, cobertura 72,2%.

Esto permite una historia de **margen contractual que se amplía y después se estrecha**. No demuestra por sí solo recuperación y posterior deterioro económico.

---

## 9. La prueba predictiva: resultados modestos, no una señal mágica

He contrastado la contracción AP contra el mismo proxy de la investigación anterior:

```text
futuro = media del margen operativo de t+1, t+2 y t+3

Deterioro = futuro < −10%
            y futuro − media_actual_3m < −15 puntos porcentuales
```

Es un resultado futuro de caja clasificada, **no impago, quiebra ni etiqueta oficial del reto**.

Se conservan los filtros `evaluation_ok` y las particiones ya existentes: desarrollo hasta noviembre de 2025, validación temporal marzo–mayo de 2026 y reserva de grupos completos por la regla previa. Estas particiones son internas y ya inspeccionadas; no son un test externo intacto.

### Señal amplia AP, sin optimizar sus umbrales contra el resultado

| Partición | Filas | Grupos | Positivos de deterioro | AUC deterioro | AUC recuperación, sentido inverso |
|---|---:|---:|---:|---:|---:|
| Desarrollo | 822 | 52 | 154 | 0,498 | 0,518 |
| Temporal | 432 | 57 | 39 | 0,592 | 0,487 |
| Temporal + grupos reservados | 101 | 21 | 11 | 0,592 | 0,375 |

Bootstrap por grupos, 600 remuestreos, semilla 73:

- Temporal, IC exploratorio 95% de AUC: **0,481–0,685**.
- Temporal + grupos, IC: **0,371–0,831**.
- Los positivos están en 21 y 6 grupos, respectivamente.

No hay precisión extraordinaria. Tampoco evidencia de una señal simétrica potente de recuperación.

### ¿Aporta algo sobre mirar ya la caja?

Comparé una ridge para margen futuro con y sin cambio de plazo. Baseline: margen reciente de tres meses, cambio de margen y volatilidad de seis meses. Normalización y recorte 1%–99% aprendidos solo en desarrollo; penalización 10, intercepto sin penalizar. Cada comparación usa exactamente las mismas filas.

| Partición | Train / test | MAE baseline | MAE con plazo |
|---|---:|---:|---:|
| Temporal | 815 / 432 | 0,156814 | 0,157165 |
| Temporal + grupos | 815 / 100 | 0,148867 | 0,148291 |

Empeora ligeramente en una partición y mejora muy poco en la otra. **No hay ganancia consistente que justifique incorporarlo con peso material al score predictivo.**

También exploré expansión AR: AUC de deterioro 0,493 en desarrollo, 0,462 temporal y 0,696 en temporal + grupos; este último resultado tiene solo siete filas positivas. No seleccionaría ese 0,696 aislado como un descubrimiento validado.

### Qué significa para la decisión

- **Mantener:** interpretación de financiación comercial, evidencia y escenarios.
- **Investigar:** incremento predictivo, con más datos y objetivos oficiales.
- **No hacer:** asignar un 20% del score a «confianza de proveedores» basándose en estas cifras.
- **No afirmar:** «lo anticipamos dos/tres meses» sin medir episodios completos, falsas alarmas y cobertura.

---

## 10. Las features que plantearía, en este orden

No implementaría treinta señales nuevas. Haría una capa pequeña con procedencia y capacidad de abstención.

| Feature propuesta | Qué mide | Uso inicial |
|---|---|---|
| `matched_ap_term_change` | Cambio de plazo recibido, misma relación y tipo documental | Diagnóstico; predictor experimental |
| `matched_ar_term_change` | Cambio de plazo concedido a clientes | Diagnóstico y exposición comercial |
| `settlement_clock_decomposition` | Δduración = Δplazo + Δretraso en población comparable | Explicación y detección de falsas lecturas |
| `term_change_amount_days` | Importe × diferencia de plazo frente a referencia explícita | Materialidad de la negociación; no pérdida prevista |
| `unsettled_at_fixed_age` | Sin liquidación registrada a 60/90 días desde emisión | Complemento a cohortes relativas al vencimiento |
| `contractual_maturity_scenario` | Calendario de obligaciones/cobros bajo plazos observados y de referencia | Escenario comercial trazable |

### El detalle más importante: dos anclas para las cohortes

La investigación anterior usa cohortes a vencimiento +15/+30/+60. Es útil para puntualidad, pero **su fecha de evaluación también cambia cuando cambia el plazo**.

Una factura a 30 días alcanza vencimiento +30 a los 60 días de emitirse. Una a 120 alcanza ese mismo punto a los 150 días. Compararlas solo por «pagó antes de vencimiento +30» no compara el mismo tiempo de financiación.

Por eso combinaría:

```text
Cohorte de disciplina:
  ¿Se liquidó antes de vencimiento +30?

Cohorte de conversión a edad fija:
  ¿Se liquidó antes de emisión +60 o emisión +90?

Condición comercial:
  ¿Qué plazo tenía y cómo cambió frente a la misma relación?
```

No llamaría morosa a una factura a 120 días por seguir abierta a los 90. **Está dentro de plazo, pero mantiene dinero financiando al cliente.** Esa es precisamente la diferencia que queremos mostrar.

Cada cohorte solo entra cuando ha alcanzado su horizonte al cierre analizado. No se trata a las facturas jóvenes como pagadas ni impagadas. Para liquidaciones parciales falta historial suficiente: deben quedar como limitación, no reconstruirse desde el `pending_amount` final.

### Reglas de activación propuestas, no validadas

- Referencia de relaciones suficientemente antiguas y mínimo de documentos y fechas distintas.
- Separación por dirección, moneda y tipo documental.
- Cobertura por importe, número de relaciones y concentración del mayor proveedor/cliente.
- Alerta local inmediata de cambio de condición, distinta de alerta de deterioro de toda la sociedad.
- Confirmación en dos cierres para elevar una tendencia, registrando el segundo como fecha de confirmación.
- No tratar dos ventanas solapadas como dos muestras independientes.
- Contraste interanual cuando sea posible; si no, mostrar que falta.
- Si cambia simultáneamente el patrón de muchas filiales con mismo ERP, marcar posible cambio común de registro o política.
- Cuando una variante de deduplicación o documento invierta el signo, abstenerse de la conclusión fuerte.

---

## 11. Cómo lo integraría con Cash Truth y con el score

La investigación anterior separa:

```text
Dinero generado / dinero que circula / dinero procedente de apoyo
```

Esta propuesta añade:

```text
Tiempo de financiación concedido / recibido / excedido
```

No sustituye una por otra. Una empresa puede:

- generar caja y conceder demasiado crédito a un cliente;
- tener caja estable gracias a un plazo AP legítimamente negociado;
- parecer excelente en puntualidad porque los vencimientos son muy largos;
- parecer peor en retrasos porque pierde margen contractual;
- mejorar operativamente sin haber recuperado todavía autonomía financiera.

### Separaría tres juicios que hoy se pueden mezclar

1. **Generación:** qué produce la operación depurada.
2. **Disciplina:** qué ocurre respecto a los compromisos registrados.
3. **Dependencia y exposición:** cuánto depende del grupo, de financiación o del tiempo concedido por proveedores; cuánto concede a sus clientes.

Un plazo AP más largo puede mejorar disciplina y liquidez sin mejorar generación. Un plazo AR más largo puede responder a una venta rentable y no ser una mala decisión. Sin margen comercial, precio y contrato no podemos resolver esa evaluación completa.

**No diseñaría una penalización universal por plazo largo.** Mostraría el efecto y evaluaría la capacidad para sostenerlo.

### Qué alimentaría inicialmente el número

- Un baseline de caja, obligaciones y trayectoria normalizadas, temporalmente válido.
- Las señales nuevas como explicaciones y banderas de interpretación.
- Solo incorporaría su componente predictivo después de una prueba incremental consistente.

Sin etiquetas oficiales no inventaría pesos «óptimos». Tampoco entrenaría un modelo contra un score que nosotros mismos hemos fabricado y lo presentaría como validación externa.

### Unidad del reto: pregunta obligatoria a organización

El enunciado alterna «250 empresas» con **250 grupos y 1.286 sociedades**. Antes de exportar, confirmaría si la unidad evaluada es `group_id`, `company_id` o ambas, así como el formato, la escala, el horizonte y las etiquetas del script oficial.

No promediaría sin más scores de filiales para inventar salud de grupo. Hay que distinguir consolidación de flujos externos, concentración de exposición y cobertura del perímetro. El dinero intragrupo no crea generación externa al consolidar.

---

## 12. El producto que vendería

### Nombre funcional: Cash Truth · Tiempo prestado

**Comprador principal:** CFO o responsable de tesorería de la propia empresa o grupo que conecta los datos. Embat puede ser canal, integrador o comprador de la capacidad; no confundirlo con el usuario que necesita tomar la decisión.

**Trabajo concreto que resuelve:**

> «Dime qué condiciones comerciales están cambiando mi necesidad de financiación, aunque mi saldo y mi ratio de morosidad todavía parezcan normales.»

### Una pantalla, no seis productos

Para una alerta:

1. **Qué cambió:** este cliente pasó de una referencia de 61,5 días a 120 en cuatro nuevas facturas.
2. **Cuánto representa:** 19.519,91 € y 58,5 días adicionales frente a esa referencia.
3. **Qué sabemos:** sociedad, contraparte, moneda, documentos y fechas.
4. **Qué no sabemos:** motivo, fecha de ingestión, posibles revisiones y si cambia el precio o el tipo de operación.
5. **Contexto:** el otoño anterior también tenía plazos largos; referencia interanual 93 días.
6. **Qué revisar:** próxima negociación, política de crédito comercial y coherencia entre margen de venta y coste de financiación.
7. **Evidencia:** abrir las cuatro facturas; alternar referencia reciente e interanual.

No hace falta un LLM para detectar ni cuantificar el patrón. Un LLM podría ayudar a redactar una explicación a partir de evidencia estructurada, pero no debe inventar condiciones, causalidad ni acciones ejecutadas.

### Acciones sugeridas, no automatizadas

- Confirmar si el cambio era intencionado y si corresponde a la misma clase de operación.
- Pedir al comercial/CFO que revise el plazo de la próxima venta.
- Estudiar anticipo parcial, hitos o descuento por pronto pago.
- Revisar concentración de vencimientos de proveedores si se reduce el plazo recibido.
- Evaluar alternativas de circulante con datos adicionales, sin emitir una aprobación de crédito automática.

El sistema no enviaría correos, modificaría ERP ni retrasaría pagos por su cuenta.

### Qué sería un escenario honesto

Comparar el calendario de los documentos observados bajo dos conjuntos explícitos de fechas:

```text
Escenario observado: plazos registrados actualmente.
Escenario de referencia: mismas emisiones e importes, plazo histórico elegido.
```

Para documentos abiertos a fecha t, se puede mostrar qué importes caen dentro de cada horizonte bajo esos supuestos. Esto exige no usar pagos posteriores a t ni saldos pendientes finales como si fueran históricos.

**No es una predicción causal.** No sabemos si un cliente aceptaría el nuevo plazo, si se perdería una venta, si existe descuento, si un proveedor permite aplazar o si el registro refleja toda la obligación.

Tampoco convertiría euro-días en «ahorro» dividiendo por un número arbitrario. Para valorar el coste de financiación hace falta un tipo, una convención temporal y un escenario explícitos.

### Cómo demostraría que alguien pagaría

Todavía no está validado. Propondría enseñar alertas trazables a un tesorero y comprobar:

- cuántas relaciones detectadas merecían revisión;
- si ya conocía el cambio y cuánto tardó en reconocerlo;
- cuánto trabajo de conciliación y búsqueda le evita;
- si las decisiones posteriores consiguen condiciones distintas;
- y si el beneficio observado justifica la suscripción.

No inventaría ahorro anual ni disposición a pagar. La propuesta tiene una unidad de valor verificable: **decisiones sobre relaciones e importes concretos**, no un semáforo genérico.

---

## 13. Demo propuesta: una sorpresa que se puede auditar

### Apertura

> «Esta relación parece haber mejorado: el retraso baja de veinte días a cero. ¿Eso significa que cobramos antes?»

### Revelación

Mostrar la comparación de COMP_1171 / COUNTERPARTY_06105:

- duración 81 → 102 días;
- plazo 62 → 102;
- retraso 20 → 0;
- selector de media simple, importe y mediana.

> «No. Ha mejorado la puntualidad, pero el dinero permanece más tiempo financiando a este cliente. Son dos cosas distintas.»

### Evidencia anterior

Abrir las cuatro facturas del 26 de septiembre por 19.519,91 €, todas con plazo 120 días. Mostrar la referencia reciente y la interanual.

> «La condición estaba escrita antes de la liquidación. Si la recibimos entonces y no fue revisada, podemos avisar al emitirse, sin esperar a que venza.»

La condicional es importante: no hay historial de ingestión ni versiones para certificar ese conocimiento histórico.

### Acción

> «El CFO no necesita que le digamos que tiene un cliente malo. Necesita saber qué financiación está concediendo, cuánto dura y qué relación conviene revisar.»

### Cierre con Cash Truth

> «Primero distinguimos dinero que se genera, circula o viene de apoyo. Después distinguimos cuánto tiempo te financian otros y cuánto financias tú. Así evitamos explicar una mejora que los datos no demuestran.»

**No diría:** «Predijimos la caída cuatro meses antes». Este caso no lo demuestra.

Si la señal nueva no está lista o su cobertura resulta insuficiente, mantendría la demo de cash pooling anterior como pieza principal y esta como segunda lectura. No destruiría un mecanismo bien demostrado por perseguir una narrativa más ambiciosa.

---

## 14. Validación que exigiría antes de convertirlo en promesa comercial

### A. Validación de significado

- Confirmar con el especialista del reto qué representa `due_date`: compromiso original, último vencimiento, fecha operativa o campo reconstruido.
- Confirmar la dirección por signo y la relación entre `invoice` e `invoiceGroup`.
- Verificar si `payment_date` es fecha de liquidación económica o de registro administrativo.
- No adjudicar intención a clientes, proveedores o bancos sin evidencia externa.

### B. Validación temporal

- Construir cada mes con lo que sería conocido a ese corte.
- No adelantar la fecha de alerta al primer mes después de comprobar que persistió.
- Cortar datos y comprobar invariancia de features anteriores.
- Comparar dos anclas de cohortes y no usar pendientes finales como históricos.
- Separar capacidad de observar una condición antes del pago de capacidad de predecir un deterioro.

### C. Generalización

- Separar grupos completos, no filas ni filiales hermanas.
- Mantener hueco temporal equivalente al horizonte de evaluación.
- Definir escalas con desarrollo, no con el lote oculto que llega a la API.
- Evaluar por cobertura, ERP, moneda y tamaño cuando haya muestra suficiente.
- Probar exclusión de los grupos que concentran los ejemplos y de las relaciones dominantes.
- No usar IDs, alta en plataforma, nombres de bancos o ausencia de ERP como atajos de salud.

### D. Métrica correcta

Con el objetivo oficial: medir mejora incremental frente al baseline en exactamente las mismas empresas y fechas.

Para alertas: registrar todos los episodios, positivos y negativos, con seguimiento suficiente; informar precisión, sensibilidad, falsas alarmas por empresa-año y lead time. Una mediana de anticipación solo entre aciertos no resume utilidad.

Para esta propuesta: añadir una métrica de **corrección de explicación**. ¿Cuántas veces el sistema evita decir «cobra antes» cuando solo ha cambiado el plazo? Es un valor distinto del AUC y debe medirse como tal.

### E. Pruebas de coherencia del producto

- Una empresa constante no mejora porque empeore otra, salvo en una vista explícitamente relativa.
- Añadir empresas ajenas al lote no debe cambiar un score absoluto ya emitido.
- Cambiar de EUR a otra unidad equivalente no debe cambiar salud.
- Un traspaso propio no crea ingresos.
- Cambiar un plazo no puede reescribir silenciosamente el histórico.
- Una feature desconocida debe producir «no observable», no una cifra tranquilizadora.
- Las contribuciones declaradas al cambio del score deben reconciliar con ese cambio si se presentan como exactas.

---

## 15. Líneas que exploré o consideré y no convertiría en producto ahora

### Fecha valor como supuesta confianza del banco

Revisé las fechas contables y valor de las 2.556.437 transacciones. **293.464 tienen fechas distintas**, distribuidas en 1.161 sociedades. El signo y la magnitud dependen mucho de la categoría: por ejemplo, las devoluciones de cobros tienen mediana de diferencia de −4 días.

Eso no demuestra que el banco retenga dinero por desconfiar de la empresa. La fecha valor puede afectar liquidación o cálculo de intereses y no equivale a fecha de disponibilidad. Sin reglas de producto y banco, la descartaría como «rating implícito del financiador». Esta fue una exploración de factibilidad, no una validación predictiva.

### Pagar antes del vencimiento como prueba de caja sobrante

Puede ser descuento, domiciliación, condición comercial o convención del ERP. No lo llamaría liquidez libre ni capacidad de pago revelada sin conocer alternativas y restricciones.

### Un grafo de confianza transversal

La investigación anterior ya demuestra que la red compartida de clientes no tiene cobertura suficiente. Esta propuesta necesita relaciones locales, no rescatar ese grafo con menciones ambiguas del texto.

### Aprender veinte señales nuevas porque son sutiles

No hay motivo para pensar que más sofisticación estadística resolverá falta de etiquetas, cobertura, contratos o versiones. La ridge exploratoria de plazos ya muestra lo pequeño e inestable del incremento.

### Diagnosticar manipulación del vencimiento

Vemos distintas condiciones registradas en diferentes documentos. **No vemos un historial de la misma factura cambiando su vencimiento.** No podemos afirmar reaging deliberado, ocultación de mora ni maquillaje contable.

---

## 16. Orden en que lo plantearía, sin implementar todavía

### P0 — Que el número sea defendible

1. Aclarar unidad y métrica de evaluación oficial.
2. Corregir leakage, empates, tamaño y dependencia del lote.
3. Separar circulación operativa y apoyo con los mecanismos ya demostrados.
4. Corregir explicaciones, faltantes y significado de Confidence.
5. Retirar del pitch afirmaciones no medidas de anticipación; en la documentación actual aparecen ejemplos de «2–3 meses» y «2.8m» que no son una validación de esta propuesta.

### P1 — Una capacidad nueva pequeña y visible

6. Añadir los tres relojes a la explicación local de facturas.
7. Comparar plazos dentro de la misma relación, con cobertura y contraste de población.
8. Mostrar el caso COMP_1171 y los documentos originales.
9. Añadir una referencia interanual para evitar la historia fácil pero engañosa.
10. Mostrar un escenario de calendario comercial, sin vender ahorro ni causalidad.

### P2 — Solo si supera la prueba incremental

11. Cohortes de emisión a edad fija con censura.
12. Alertas confirmadas y métricas completas de episodios.
13. Evaluar si alguna señal aporta a la puntuación oficial, sin elegir por el mejor resultado aislado.
14. Ampliar a supervivencia de liquidaciones o modelos jerárquicos solo si lo justifican muestra, tiempo y evaluación.

**Decisión de producto:** una pantalla excelente y verificable sobre condiciones comerciales es preferible a una segunda familia de puntuaciones sin calibrar.

---

## 17. Trazabilidad y cómo reproducir las cifras sin crear nuevos artefactos

### Fuentes

- Originales: `/Users/alvaro/Downloads/output/`.
- Convenciones: `data_dictionary.md` de esa carpeta.
- Código actual: `src/xray/features/__init__.py`, `src/xray/scoring/__init__.py`, `src/xray/clean/invoices.py`.
- Investigación anterior: `research/astra_findings.md`, `research/hypotheses_results.csv`, `research/02_build_research_panel.py`, `research/04_signal_investigation.py`.
- Resultado bancario reutilizado: `research/sweep_corrected/temporal_signals.parquet`.

### Huellas de los dos CSV principales

```text
invoices.csv
6686bd878244881bac78348a108852f3f30713ef244267f1fa3754b9be619c53

transactions.csv
000a6820a7500c66aa70a17b3e813d0c57a8270b3c58f6f2f006708a20228f2b
```

Los 25 bytes NUL del CSV bancario se sustituyeron únicamente en el buffer de lectura en memoria para la exploración de fechas. El archivo original no se reescribió.

### Receta exacta para el caso principal

1. Aplicar la selección del apartado 4.
2. Filtrar `company_id = COMP_1171`, `counterparty_id = COUNTERPARTY_06105`, `document_type = invoice`, importe positivo y moneda EUR.
3. Para plazos, mantener 0–180 días.
4. Aceptar liquidación observada solo si `status = paid`, fecha de pago no anterior a emisión y anterior a 2026-09-01.
5. Para el cuadro de documentos liquidados, exigir duración 0–180 días y comparar `[2025-08-01, 2025-11-01)` con `[2025-11-01, 2026-02-01)`.
6. Calcular L, A y D sobre exactamente las mismas filas. Usar pesos `abs(amount)` para la versión monetaria.
7. Para la señal por emisión, usar todas las facturas elegibles de la relación, no solo las pagadas. Referencia `[2025-06-01, 2025-09-01)`; nuevas facturas emitidas 2025-09-26.
8. Para estacionalidad, comparar emisiones de septiembre–noviembre de 2024 y 2025.
9. Para sensibilidades, aplicar las variantes y umbrales del apartado 7 sin cambiar ventanas.

Los apartados 8 y 9 especifican ventanas, claves, pesos, mínimos, filtros, particiones y modelo de las otras pruebas. No se ha guardado un ejecutable nuevo: este documento deja el protocolo y los resultados, respetando la restricción de no construir nada más.

### Límites generales que acompañan a todas las cifras

Los datos son sintéticos. La extracción es final, sin `ingested_at` ni historial de versiones. Excluir facturas finalmente canceladas y aceptar estados finales bajo fechas de evento introduce supuestos de replay. La señal a emisión solo habría sido disponible entonces si esos campos ya existían y no fueron revisados.

Las identidades son descriptivas, las sensibilidades son exploratorias y los ejemplos están seleccionados retrospectivamente. No hay una probabilidad calibrada de insolvencia, una prueba causal de confianza ni una evaluación sobre el test oculto.

---

## 18. La decisión que tomaría

**No intentaría ganar diciendo que hemos descubierto una inteligencia secreta del mercado. Intentaría ganar demostrando que no confundimos puntualidad, liquidez y financiación.**

El hallazgo anterior dice:

> «Ese dinero no se ha generado de nuevo: está circulando.»

Este añade:

> «Ese retraso ha mejorado, pero no estás convirtiendo más rápido: ha cambiado el tiempo que financias.»

Ambos atacan el mismo fallo de muchos dashboards: atribuir una mejora al negocio cuando se ha movido el mecanismo que la mide o la sostiene.

**Mi recomendación final:** corregir el score, conservar Cash Truth y añadir una explicación comercial de los tres relojes con documentos trazables. Mantener la contracción de plazos como hipótesis predictiva, no como verdad aprendida. Vender al CFO una decisión concreta sobre su circulante, no una promesa de adivinar el futuro.
