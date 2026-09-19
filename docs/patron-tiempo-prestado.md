# Conclusiones del análisis y propuesta inicial: Tiempo prestado

**Reto X-Ray · Embat · HackSpain 2026 · 19 de septiembre de 2026**

## Cómo leer este documento

Este documento es un **punto de partida para construir el proyecto desde cero**. Reúne conclusiones del análisis de los datos, evidencias, hipótesis descartadas y una propuesta de features, score, producto y validación.

**No presupone ningún producto, motor de scoring, pantalla, pipeline ni feature implementados.** Todos los componentes descritos como propuesta están por construir y validar. No hace falta conocer otro informe, una rama de desarrollo ni archivos de investigación locales para entender las conclusiones.

Distinguimos tres niveles:

- **Observado:** un resultado descriptivo comprobado en los datos analizados.
- **Exploratorio:** una asociación o sensibilidad que no equivale a validación externa.
- **Propuesto:** algo que se podría construir a partir de las conclusiones; no es una capacidad entregada.

El objetivo es decidir **qué merece la pena construir y qué no deberíamos prometer**.

---

## 1. Conclusión principal

> **Una empresa puede mejorar su puntualidad sin convertir sus facturas en dinero más rápido: ha cambiado el plazo contra el que medimos el retraso.**

El patrón no consiste simplemente en detectar que alguien paga tarde. Consiste en separar:

1. cuánto tiempo se concede para pagar;
2. cuánto tiempo transcurre hasta la liquidación registrada;
3. cuánto se excede el vencimiento.

La diferencia es sutil porque un dashboard puede mostrar una mejora del retraso y atribuirla a una mejor conversión de caja. Pero si el plazo se ha ampliado todavía más, lo que ha cambiado es la financiación comercial concedida o recibida.

### Evidencia principal

En una relación de clientes de **COMP_1171**:

| Medida | Ago–oct 2025 | Nov 2025–ene 2026 |
|---|---:|---:|
| Retraso medio registrado | 19,65 días | **0 días** |
| Tiempo emisión–liquidación | 81,24 días | **102,25 días** |
| Plazo medio registrado | 61,59 días | **102,25 días** |

La puntualidad mejora, pero la duración hasta liquidación aumenta. La comparación resiste ponderación por importe, medianas y controles de deduplicación.

**Esto no demuestra insolvencia ni deterioro de toda la empresa.** Demuestra que puntualidad y velocidad de conversión no son la misma dimensión.

### La oportunidad de producto

> **Mostrar qué parte de la liquidez depende del tiempo que otros conceden a la empresa y qué financiación está concediendo la empresa a sus clientes.**

Ese crédito comercial no aparece necesariamente como un préstamo en el fichero de deuda. Sin embargo, cambia la necesidad de circulante y puede dar lugar a decisiones concretas sobre clientes, proveedores y condiciones comerciales.

### Lo que no se ha encontrado

No se ha encontrado un predictor extraordinario que permita prometer ganar el leaderboard o anticipar universalmente el deterioro. Los cambios de plazo tienen valor explicativo, pero su mejora predictiva sobre un baseline de caja ha resultado pequeña e inconsistente en las pruebas exploratorias.

**La recomendación es construir una medición defendible y un producto útil, no asignar un gran peso a una señal solo porque su narrativa es atractiva.**

---

## 2. La intuición: observar condiciones, no adivinar intenciones

Un proveedor puede ofrecer recursos o condiciones mejores a unas empresas que a otras. Esa decisión puede reflejar expectativas, una relación comercial, potencial de crecimiento o una política interna. No permite concluir automáticamente que esté evaluando salud financiera.

La parte útil de esa intuición es:

> **Las condiciones que otros aceptan ofrecerte pueden contener información que todavía no aparece en tus resultados.**

En estos datos no hay solicitudes de financiación aceptadas y rechazadas ni motivos de decisiones comerciales. Sí hay fechas de emisión, vencimiento y liquidación de facturas. Permiten observar condiciones registradas y su evolución.

| Lado | Qué significa | Quién financia a quién |
|---|---|---|
| AP: facturas a pagar | Plazo recibido por la empresa | El proveedor financia a la empresa durante ese plazo |
| AR: facturas a cobrar | Plazo concedido por la empresa | La empresa financia a su cliente durante ese plazo |

**Un aumento de plazo AR no significa que otros confíen más en la empresa. Significa que la empresa concede más tiempo a sus clientes.**

Tampoco una reducción de plazo AP demuestra retirada de confianza. Puede responder a negociación, descuentos, productos distintos, estacionalidad, política de grupo o registro del ERP.

Por tanto, la señal debería llamarse **cambio de condiciones observadas**, no «confianza secreta del mercado».

El crédito comercial es un concepto conocido. La diferenciación del proyecto estaría en medirlo dentro de relaciones comparables, explicar su efecto y evitar interpretaciones falsas, no en afirmar que nadie lo ha pensado antes.

---

## 3. Datos analizados y límites de lo observable

El conjunto contiene **1.286 sociedades en 250 grupos** y 24 meses completos, de septiembre de 2024 a agosto de 2026, con extracción final alrededor del 1 de septiembre de 2026.

Se analizaron:

- las **897.894 filas de facturas**;
- las **2.556.437 transacciones**, en las columnas necesarias para la exploración de fechas contables y valor;
- el maestro de sociedades y el diccionario de datos;
- cambios de plazo dentro de relaciones repetidas;
- descomposiciones de tiempo hasta liquidación;
- sensibilidades por importe, tipo documental, deduplicación y población;
- asociaciones exploratorias contra un panel auxiliar de caja depurada.

**La entrega de este documento no incluye ese panel, scripts ejecutables ni modelos entrenados.** Los resultados predictivos se obtuvieron con un panel bancario auxiliar de la investigación local, con correcciones de circulación de liquidez. No se reconstruyó de nuevo toda su depuración en el análisis de plazos. Es una dependencia metodológica de esas métricas, no una implementación disponible para el equipo. Antes de usarlas como garantía del producto habría que reconstruirlas y verificarlas.

### Selección utilizada para facturas

- Tipos `invoice` e `invoiceGroup`.
- Estado distinto de `cancel`.
- Importe no nulo y valor absoluto no superior a 100 millones en moneda nativa.
- Emisión desde 2024-09-01 hasta antes de 2026-09-01.
- Moneda de factura = moneda contable = moneda de la sociedad.
- `exchange_rate = 1`.
- Deduplicación candidata por sociedad, contraparte, tipo, emisión, vencimiento, importe y concepto.

Resultado: **689.170 documentos**.

Para estudiar plazos se exige además contraparte explícita y plazo entre 0 y 180 días:

| Población | Documentos | Sociedades |
|---|---:|---:|
| Total elegible de plazos | 666.753 | 764 |
| AP | 392.099 | 760 |
| AR | 274.654 | 693 |

La dirección AR/AP se deduce del signo del importe. Es un supuesto que debe confirmarse con la organización, no una columna contractual explícita.

Hay **257.105 documentos con plazo cero** en esta selección. No todos tienen por qué representar una exigencia real de pago inmediato: puede haber convenciones o valores por defecto del ERP. Por eso se aplicaron sensibilidades excluyéndolos.

### Límites esenciales

- Los datos son sintéticos; no describen empresas reales.
- No hay historial de versiones de cada factura ni fecha de ingestión de cada cambio.
- No sabemos si el vencimiento es el original o uno revisado posteriormente.
- La fecha de liquidación registrada no tiene un enlace bancario completo y validado para todas las facturas.
- El pendiente final no permite reconstruir todos los pagos parciales históricos.
- Los saldos y condiciones finales de deuda no constituyen series históricas.
- La cobertura del ERP y del banco puede ser diferente.
- Varias facturas, agrupaciones o registros pueden representar partes de una misma obligación.

Por tanto, se habla de **plazos y liquidaciones registrados**, no de contratos auditados ni de un replay histórico certificado.

---

## 4. El mecanismo: tres relojes

Para un documento liquidado, con fechas comparables:

```text
L = fecha_vencimiento − fecha_emisión
A = fecha_liquidación − fecha_emisión
D = fecha_liquidación − fecha_vencimiento

A = L + D
```

- **L: tiempo concedido.** Condición comercial registrada.
- **A: duración hasta liquidación.** Tiempo durante el que permanece abierta la operación según esas fechas.
- **D: retraso.** Diferencia respecto al compromiso registrado.

Con medias sobre los mismos documentos y pesos:

```text
ΔA = ΔL + ΔD
```

La identidad no se puede aplicar sin más a medianas calculadas por separado. Las medianas son una sensibilidad, no una descomposición aditiva.

| Cambio | Interpretación posible | Interpretación que debemos evitar |
|---|---|---|
| AR: A y D bajan con L estable | Conversión más rápida y mejor puntualidad | «Ya no existe riesgo» |
| AR: D baja, pero A sube porque L aumenta más | Mejor puntualidad con más financiación concedida | «Estamos cobrando antes» |
| AP: A sube, D no sube y L aumenta | Más financiación comercial dentro de plazo | «La empresa ha dejado de pagar» |
| AP: D sube, pero A baja porque L cae más | Menos margen contractual pese a liquidar antes desde emisión | «Paga cada vez más despacio» |

Una concesión legítima puede ser buena gestión. El propósito no es castigar los plazos largos, sino no atribuirles una mejora de generación operativa que no demuestran.

Para construir estas features habría que normalizar las fechas a un calendario coherente. En la exploración, seis documentos liquidados presentaban una diferencia de un día en la identidad al truncar horas con `.dt.days`. No pertenecen a las sociedades de los casos que superaron todos los controles del apartado 6.

---

## 5. Caso demostrable: COMP_1171 y COUNTERPARTY_06105

### Identificación

- Sociedad: **COMP_1171**.
- Grupo: **GROUP_0139**.
- Moneda: **EUR**.
- ERP registrado: `businessCentral`.
- Cliente: **COUNTERPARTY_06105**.
- Documentos: `invoice`, AR.

Se compararon documentos liquidados en dos ventanas consecutivas. El pago debe figurar como `paid`, no ser anterior a emisión y ser anterior al corte final. Se limitaron plazo y duración a 0–180 días.

| Medida | Ago–oct 2025 | Nov 2025–ene 2026 |
|---|---:|---:|
| Documentos liquidados | 17 | 8 |
| Plazo medio L | 61,59 días | 102,25 días |
| Duración media A | 81,24 días | 102,25 días |
| Retraso medio D | 19,65 días | 0,00 días |
| Duración mediana | 77 días | 114 días |
| Retraso mediano | 15 días | 0 días |
| Importe de la población | 52.697,13 € | 27.171,18 € |

```text
+21,01 días de duración = +40,66 días de plazo − 19,65 días de retraso
```

La conclusión no depende únicamente de contar igual cada documento:

| Media ponderada por importe | Ago–oct | Nov–ene |
|---|---:|---:|
| Duración hasta liquidación | 84,32 días | 108,47 días |
| Plazo | 61,38 días | 108,47 días |
| Retraso | 22,94 días | 0,00 días |

**Lo demostrado:** en esos documentos de esa relación mejora la puntualidad, pero no la velocidad emisión–liquidación. No demuestra deterioro de toda la sociedad ni certifica la fecha de cada cobro bancario.

### Qué condición aparece en las nuevas emisiones

En junio–agosto de 2025 se observan **16 facturas emitidas** de la relación, con plazos entre 61 y 64 días y mediana **61,5 días**.

El **26 de septiembre de 2025** se emiten cuatro facturas con plazo **120 días**, vencimiento el **24 de enero de 2026** e importe total **19.519,91 €**:

| `operation_id` | Importe |
|---|---:|
| `7827cac0abfa1dee6f87fe8f8af3b4c5` | 6.025,80 € |
| `a2ee944be742d0dc7916873e75361323` | 1.815,00 € |
| `8289cdbcc553bc656f98d5f95399ca6c` | 2.420,00 € |
| `1c16d5effaf74ce578225b5d3d2deea3` | 9.259,11 € |

Todas figuran finalmente liquidadas el 24 de enero. Ese desenlace verifica la historia, pero no debe utilizarse para construir una alerta en septiembre.

Respecto a la referencia reciente:

```text
Tiempo adicional = 120 − 61,5 = 58,5 días
Exposición de tiempo = 19.519,91 × 58,5 = 1.141.914,74 euro-días
```

Los euro-días no son euros perdidos, ahorro ni caja desaparecida. Son importe por tiempo adicional de financiación respecto a una referencia. La mediana histórica no es un vencimiento legal anterior.

**Posible decisión del CFO:** revisar por qué se concede ese plazo, si el precio compensa la financiación y qué condiciones negociar en la siguiente operación.

### Qué impide exagerar el caso

En septiembre–noviembre de 2024, esa misma relación tenía **7 facturas con mediana de plazo 93 días**. En septiembre–noviembre de 2025 hay **13 facturas con mediana 120 días**.

Por tanto, la comparación con el verano puede exagerar un cambio estacional. La diferencia de 58,5 días no es una estimación causal de deterioro. Incluso el contraste interanual tiene poca muestra y solo dos ciclos anuales.

Además, la caja clasificada de la sociedad no muestra una caída posterior monotónica: el margen operativo del panel auxiliar es aproximadamente **+16,4% en enero de 2026**, **−1,5% en febrero** y **−1,4% en marzo**.

Este es un caso de **interpretación y exposición comercial**, no de anticipación demostrada de insolvencia.

Una alerta a emisión solo habría sido posible si esos campos se conocían entonces y no fueron revisados después. Los CSV no permiten certificarlo.

---

## 6. Cobertura, controles y casos descartados

### Cómo se compararon relaciones

Clave de relación:

```text
sociedad × contraparte explícita × AR/AP × tipo documental × moneda
```

En cada cierre mensual entre febrero de 2025 y agosto de 2026 se compararon los tres meses recientes de liquidaciones con los tres anteriores. Se exigieron:

- plazo y duración entre 0 y 180 días;
- estado `paid`, fecha de pago válida y anterior al corte;
- al menos tres documentos en cada ventana por relación;
- al menos tres contrapartes para agregar a sociedad;
- peso por relación `min(n_documentos_referencia, 30)` para los cambios de medias agregados.

Cobertura: **3.723 sociedad-mes AP de 392 sociedades** y **1.481 sociedad-mes AR de 185 sociedades**. Tener cobertura no significa presentar el patrón.

### Selección más exigente de casos

Se seleccionaron relaciones `invoice` con:

- al menos cinco liquidaciones por ventana;
- plazo medio de ambas ventanas ≥7 días;
- aumento medio de duración ≥7 días;
- descenso medio de retraso ≥7 días.

Aparecieron **38 relación-mes candidatas**.

Para cada candidata se probaron cuatro poblaciones:

1. `invoice`;
2. `invoice` más `invoiceGroup`, manteniendo contraparte, dirección y moneda;
3. solo facturas con plazo positivo;
4. deduplicación más agresiva por emisión, vencimiento, liquidación e importe, ignorando concepto.

En todas se calcularon media simple, media ponderada por importe y mediana. Se exigió un mínimo de tres documentos por ventana y que la duración siguiera subiendo ≥3 días y el retraso bajando ≥3 días en cada variante.

**Sobreviven 10 relación-mes de 8 sociedades y 7 grupos:**

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

Quitando GROUP_0139 quedan siete filas de siete sociedades y seis grupos.

Son sensibilidades exploratorias posteriores a la búsqueda. Las ventanas se solapan: **no son diez eventos independientes ni una prueba confirmatoria**.

### Un ejemplo que no pasó todos los controles

`COMP_0665 / COUNTERPARTY_48839`, lado AP, parecía llamativo: retraso medio de 20,55 a cero y duración de 37,82 a 79,94 días.

Pero al excluir los plazos cero y ponderar por importe, la duración solo aumenta **0,89 días**, por debajo del mínimo de tres días exigido. No sería el caso principal de la demo.

Esa contraparte tiene documentos AR y AP. Hay que mantenerlos separados aunque compartan ID: mezclarlos cambia el sentido financiero del cálculo.

### Lo que aún falta

Estos controles no eliminan el sesgo de observar solo documentos liquidados. Para evaluar toda la cartera habría que incluir los documentos abiertos con censura temporal explícita. Tampoco resuelven cambios de producto, condiciones contractuales no observadas o versiones del ERP.

---

## 7. Segunda conclusión: el plazo recibido o concedido también cambia

La hipótesis es observar cómo cambian las condiciones de la **misma relación**, en lugar de comparar empresas de tamaño o sector desconocido.

### Método exploratorio

En cada cierre de febrero de 2025 a agosto de 2026:

- comparar los tres meses recientes de **emisión** con los tres anteriores;
- mantener sociedad, contraparte, AR/AP, tipo documental y moneda;
- exigir ≥3 documentos por relación en ambas ventanas;
- calcular la mediana de plazo de cada ventana;
- ponderar por `min(n_documentos_referencia, 30)`;
- exigir ≥3 contrapartes para agregar a sociedad.

```text
δL_relación = mediana(L_reciente) − mediana(L_referencia)
δL_sociedad = Σ peso_referencia × δL_relación / Σ peso_referencia
```

El peso controla frecuencia; no representa exposición monetaria. La cobertura por importe se mide aparte.

| Lado | Sociedad-mes comparables | Sociedades | Grupos |
|---|---:|---:|---:|
| AP | 5.011 | 490 | 143 |
| AR | 2.496 | 286 | 113 |

Una contracción AP se definió como cambio ponderado ≤−7 días y reducción ≥7 días en al menos la mitad de las relaciones comparables:

- **74 sociedad-mes, 45 sociedades, 30 grupos**.
- Exigiendo cobertura de esas relaciones ≥50% del importe AP elegible reciente: **28 sociedad-mes de 18 sociedades**.

No son retiradas de confianza demostradas. Son cambios registrados con esa geometría.

### Versión conservadora

Añadiendo `invoice` únicamente, medianas de plazo entre 7 y 120 días, ticket mediano reciente entre la mitad y el doble del anterior, ≥3 contrapartes y cobertura ≥30% del importe AP elegible:

| Patrón | Sociedad-mes | Sociedades | Grupos |
|---|---:|---:|---:|
| Contracción ≥7 días y amplitud ≥50% | 16 | 14 | 10 |
| Expansión ≥7 días y amplitud ≥50% | 10 | 8 | 8 |

El límite 7–120 afecta a las medianas de relación. Los documentos de partida siguen limitados a 0–180 días.

### Ejemplo: COMP_0817

Comparando abril–junio de 2026 con enero–marzo:

- seis proveedores comparables;
- todos reducen su mediana ≥7 días;
- cambio agregado **−28,94 días**;
- cobertura **67,4%** del importe AP elegible reciente.

| Contraparte | Documentos antes / después | Plazo antes | Después |
|---|---:|---:|---:|
| COUNTERPARTY_01323 | 3 / 4 | 57 | 44 |
| COUNTERPARTY_02245 | 9 / 4 | 95 | 35,5 |
| COUNTERPARTY_02544 | 6 / 3 | 68 | 43 |
| COUNTERPARTY_13574 | 3 / 3 | 67 | 60 |
| COUNTERPARTY_19182 | 5 / 4 | 44 | 23,5 |
| COUNTERPARTY_24223 | 6 / 5 | 62 | 49 |

Todas tienen al menos dos fechas distintas de emisión por ventana. Sin embargo, una contraparte concentra **551.879,11 €** del importe reciente emparejado. Seis proveedores no son seis exposiciones equilibradas.

Además, en junio las seis sociedades de GROUP_0070 con cobertura en la variante amplia contraen su plazo ≥7 días. Puede haber política de grupo, ERP o un patrón sintético común. No se debe interpretar como evidencia independiente de seis mercados.

Excluyendo GROUP_0070 quedan **11 ventanas de 10 sociedades y 9 grupos** en la contracción conservadora.

### Ejemplo de ambas direcciones: COMP_0521

Sociedad en **USD**, sin convertir sus importes a euros:

- Septiembre de 2025: ampliación **+25,87 días**, ocho proveedores, cobertura 53,3%.
- Agosto de 2026: contracción **−13,92 días**, cuatro proveedores, cobertura 72,2%.

Describe margen contractual que se amplía y después se estrecha. No demuestra por sí solo recuperación y posterior deterioro económico.

---

## 8. Qué dicen las pruebas predictivas

Se contrastó la contracción de plazo AP con un resultado futuro de caja clasificada, no con quiebra ni con las etiquetas oficiales del reto:

```text
Margen mensual = (entradas_operativas − salidas_operativas)
                 / (entradas_operativas + salidas_operativas)

Futuro = media del margen de t+1, t+2 y t+3
Actual_3m = media del margen de t, t−1 y t−2

Deterioro = Futuro < −10% y Futuro − Actual_3m < −15 puntos
Recuperación = Futuro > +10% y Futuro − Actual_3m > +15 puntos
```

El panel auxiliar separaba circulación bancaria identificada antes de calcular operación. Este proxy no es EBITDA ni un estado auditado de flujos de efectivo.

### Particiones y calidad

- Desarrollo hasta noviembre de 2025, excluyendo los grupos reservados.
- Validación temporal de marzo a mayo de 2026.
- Reserva de grupos completos cuyo número identificador es múltiplo de cinco.
- Evaluación con margen reciente disponible, al menos seis meses observados y calidad suficiente en el mes analizado y los tres futuros.
- Calidad bancaria del panel: ≥20 transacciones seleccionadas, ≥80% de filas en moneda nativa/FX=1, ≤40% de importe absoluto sin categoría, ≤10% de filas candidatas de resincronización y ninguna observación superior al umbral de 100 millones nominales.

Los umbrales son convenciones exploratorias, no fronteras económicas calibradas. Las particiones se han inspeccionado durante la investigación y no son un test externo intacto. Los IDs de grupo sirven para la partición, no como feature de salud.

### Resultado para contracción AP

| Partición | Filas | Grupos | Deterioros | AUC deterioro | AUC recuperación, orientación inversa |
|---|---:|---:|---:|---:|---:|
| Desarrollo | 822 | 52 | 154 | 0,498 | 0,518 |
| Temporal | 432 | 57 | 39 | 0,592 | 0,487 |
| Temporal + grupos reservados | 101 | 21 | 11 | 0,592 | 0,375 |

Bootstrap por grupos, 600 remuestreos y semilla 73:

- AUC temporal, intervalo exploratorio 95%: **0,481–0,685**.
- AUC temporal + grupos: **0,371–0,831**.
- Los positivos pertenecen a 21 y 6 grupos, respectivamente.

No hay precisión extraordinaria ni evidencia de una señal simétrica potente de recuperación.

### ¿Añade valor frente a un baseline de caja?

Se comparó una ridge para margen futuro con y sin cambio de plazo:

- baseline: margen reciente, cambio de margen y volatilidad de seis meses;
- normalización y recorte 1%–99% aprendidos solo en desarrollo;
- penalización 10 e intercepto sin penalizar;
- comparación sobre exactamente las mismas filas.

| Partición | Train / test | MAE baseline | MAE con plazo |
|---|---:|---:|---:|
| Temporal | 815 / 432 | 0,156814 | 0,157165 |
| Temporal + grupos | 815 / 100 | 0,148867 | 0,148291 |

Empeora ligeramente en una partición y mejora muy poco en la otra. **No hay ganancia consistente que justifique un peso importante en el score.**

La expansión AR también se exploró: AUC de deterioro 0,493 en desarrollo, 0,462 temporal y 0,696 en temporal + grupos. Ese último resultado tiene solo siete filas positivas; no debe seleccionarse aisladamente como prueba de éxito.

### Decisión derivada

- Construir la explicación y la medición de exposición comercial.
- Mantener la hipótesis predictiva como experimental.
- Reproducir la depuración y las métricas con el pipeline que se construya.
- Exigir mejora incremental frente a objetivos oficiales antes de modificar el score por esta señal.
- No prometer meses de anticipación a partir de ejemplos elegidos retrospectivamente.

---

## 9. Qué construir: un motor mínimo, no solo esta señal

El reto exige un score de salud financiera para el conjunto de empresas. Una feature contractual con cobertura parcial no basta.

La arquitectura propuesta sería:

```text
CSV originales
    ↓
Validación, moneda, dirección, cobertura y fechas
    ↓
Clasificación de movimientos y separación de circulación de liquidez
    ↓
Panel sociedad–mes + relaciones locales de clientes y proveedores
    ↓
Features de generación, obligaciones, trayectoria y crédito comercial
    ↓
Score de salud + dirección + estabilidad + cobertura
    ↓
Explicaciones, alertas y pantalla de decisiones para el CFO
```

Todos esos componentes son **trabajo propuesto**, no entregables incluidos en este documento.

### A. Separar dinero generado de dinero que circula

Antes de puntuar, habría que distinguir:

- cobros y pagos operativos identificados;
- transferencias entre cuentas propias;
- circulación automática de tesorería o cash pooling;
- transferencias intragrupo identificables;
- financiación e inversión;
- movimientos inciertos.

Un cash pool puede vaciar y reponer una cuenta automáticamente. Contar cada retorno como un gasto nuevo fabricaría actividad o deterioro. A la inversa, una transferencia entrante no prueba ventas ni generación propia.

La detección de esos mecanismos requeriría evidencia de cuenta, moneda, importe, fecha y secuencia. No bastaría una etiqueta ni una palabra en la descripción. Donde no hubiera evidencia, el sistema debería abstenerse.

Este es un requisito de medición para construir el motor, no una funcionalidad que se presuponga disponible.

### B. Baseline de salud

Empezaría por un modelo simple y explicable con:

- generación operativa normalizada por actividad;
- evolución de cobros y pagos depurados;
- obligaciones registradas y cohortes de liquidación;
- persistencia de deterioro o mejora;
- variabilidad adversa, no castigo indiscriminado a toda volatilidad;
- concentración de relaciones cuando exista cobertura;
- dependencia observada de financiación o apoyo;
- calidad de observación por dimensión.

Separaría **nivel**, **dirección**, **estabilidad** y **cobertura**. Una empresa puede mejorar y seguir débil; otra puede estar fuerte y empezar a deteriorarse.

No asignaría aquí pesos supuestamente óptimos ni una probabilidad de insolvencia. Primero hay que conocer la salida y métrica oficiales y validar el baseline.

### C. La capa diferencial: tiempo prestado

| Feature propuesta | Definición | Uso inicial |
|---|---|---|
| `matched_ap_term_change` | Cambio de plazo recibido en relaciones comparables | Diagnóstico; predictor experimental |
| `matched_ar_term_change` | Cambio de plazo concedido a clientes | Diagnóstico y exposición comercial |
| `settlement_clock_decomposition` | Δduración = Δplazo + Δretraso, misma población | Explicación |
| `term_change_amount_days` | Importe × diferencia de plazo frente a referencia explícita | Materialidad de la condición comercial |
| `unsettled_at_fixed_age` | Sin liquidación registrada a 60/90 días desde emisión | Conversión a edad comparable |
| `contractual_maturity_scenario` | Calendario observado frente a un escenario explícito de plazos | Apoyo a decisiones, no predicción causal |

Inicialmente estas features explicarían el número y sus límites. Su incorporación como predictores dependería de validación incremental.

---

## 10. El detalle de diseño más importante: dos anclas para las cohortes

Medir una factura a «vencimiento +30 días» sirve para puntualidad. Pero el instante de evaluación cambia cuando cambia el plazo:

- factura a 30 días: vencimiento +30 se alcanza a los **60 días de emisión**;
- factura a 120 días: el mismo horizonte se alcanza a los **150 días de emisión**.

No representan el mismo tiempo de financiación.

Por eso se propone combinar:

```text
Disciplina: ¿se liquidó antes de vencimiento +30?
Conversión: ¿se liquidó antes de emisión +60 o emisión +90?
Condición: ¿qué plazo tenía y cómo cambió en esa relación?
```

Una factura a 120 días abierta a los 90 **no es morosa por ese motivo**. Sigue dentro de plazo, pero mantiene dinero financiando al cliente.

Cada cohorte solo puede evaluarse cuando alcanza su horizonte al corte analizado. Las facturas jóvenes no son ni aciertos ni impagos. Para pagos parciales, la limitación del histórico debe mostrarse expresamente.

### Condiciones de activación propuestas

- Mínimo de documentos y de fechas distintas por relación.
- Separación por dirección, moneda y tipo documental.
- Cobertura por importe y número de relaciones.
- Concentración del principal cliente o proveedor visible.
- Contraste interanual cuando haya datos.
- Alerta local de condición comercial separada de alerta de deterioro empresarial.
- Confirmación en dos cierres para elevar una tendencia; el segundo sería la fecha de confirmación.
- Advertencia de cambio común de ERP o política cuando varias filiales cambien a la vez.
- Abstención si variantes razonables de población invierten la conclusión.

Son reglas a implementar y probar, no umbrales comerciales validados.

---

## 11. Producto propuesto: Tiempo prestado

### Comprador

**CFO o responsable de tesorería de la empresa o grupo que conecta sus datos.** Embat podría ser canal, integrador o comprador de la capacidad. No hay todavía validación de disposición a pagar.

### Problema concreto

> «Dime qué condiciones comerciales están cambiando mi necesidad de financiación aunque mi saldo o mi ratio de morosidad parezcan normales.»

### Pantalla mínima a construir

Para cada señal:

1. **Qué cambió:** relación, dirección AR/AP, periodo y plazos.
2. **Cuánto representa:** importe y días, sin confundir euro-días con pérdidas.
3. **Qué sostiene la conclusión:** documentos, fechas y alternativas de ponderación.
4. **Qué puede explicarla:** negociación, estacionalidad, tipo de operación o registro; hipótesis, no causas afirmadas.
5. **Qué falta:** cobertura, revisiones, conciliación, precio o contrato.
6. **Qué decisión estudiar:** próxima negociación, anticipo, hitos, descuento o alternativa de circulante.

Para el caso principal: cuatro facturas por 19.519,91 € a 120 días, referencia reciente 61,5 y referencia interanual 93. La pantalla debería enseñar ambas referencias, no ocultar la menos espectacular.

### Qué no debería hacer

- Llamar «mal cliente» a alguien solo por tener plazo largo.
- Recomendar retrasar pagos fuera de contrato.
- Ejecutar cambios de ERP, correos o movimientos de dinero automáticamente.
- Afirmar ahorro anual, pérdida esperada o aprobación de financiación sin datos adicionales.
- Usar un LLM para inventar explicaciones financieras.

Un LLM podría redactar a partir de evidencia estructurada, pero no es necesario para detectar ni calcular el patrón.

### Escenario comercial honesto

Comparar las mismas emisiones e importes bajo:

- fechas de vencimiento observadas;
- una referencia de plazo seleccionada y visible.

Para documentos abiertos al corte, mostrar los importes que caen dentro de cada horizonte en ambos escenarios. No utilizar pagos posteriores ni pendientes finales como si fueran históricos.

No es una predicción causal: se desconoce si el cliente aceptaría otra condición, si se perdería una venta o si existe un descuento. Para convertir tiempo en coste financiero se necesita un tipo y una convención explícitos.

### Cómo comprobar el valor comercial

Enseñar alertas trazables a un tesorero y medir:

- cuántas merecen revisión;
- si ya conocía los cambios;
- qué trabajo de búsqueda o conciliación evitan;
- qué decisiones producen;
- qué condiciones se obtienen después;
- y si ese valor justifica la suscripción.

La unidad de valor sería una **decisión concreta sobre una relación y un importe**, no un semáforo genérico.

---

## 12. Demo que habría que construir

### 1. Pregunta inicial

> «El retraso de esta relación baja de veinte días a cero. ¿Eso significa que estamos cobrando antes?»

### 2. Mostrar los tres relojes

COMP_1171 / COUNTERPARTY_06105:

- duración: 81 → 102 días;
- plazo: 62 → 102;
- retraso: 20 → 0.

> «Ha mejorado la puntualidad, pero la duración hasta liquidación ha aumentado. Son dos cosas distintas.»

Permitir alternar media, ponderación por importe y mediana.

### 3. Abrir la evidencia

Mostrar las cuatro facturas de septiembre a 120 días, junto con las referencias reciente e interanual.

> «Esta condición permite revisar la financiación concedida antes de esperar al pago, siempre que se conozca a emisión y no haya sido revisada después.»

### 4. Terminar en una decisión

> «El CFO necesita saber qué financiación está concediendo y qué relación conviene revisar, no que le prometamos una quiebra que no podemos demostrar.»

La demo debería incluir también el score general y su trayectoria para cumplir el reto. El ejemplo de facturas es una explicación diferencial, no un sustituto del motor.

**No afirmar:** «Predijimos la caída cuatro meses antes». Este caso no lo demuestra.

---

## 13. Errores que debemos evitar al construir desde cero

### Confundir foto final con historia

No distribuir la deuda final, el saldo final o un flag de vencimiento calculado al final por todos los meses históricos. Cada feature necesita una fecha de disponibilidad coherente.

### Confundir tamaño con salud

Más euros de cobro no hacen automáticamente más sana a una empresa grande. Usar ratios y escalas razonables, con cobertura y denominadores explícitos.

### Fabricar trayectoria con rankings

Si A no cambia y B empeora, A puede subir en un ranking relativo sin haber mejorado su negocio. No explicarlo como mejora propia. Definir referencias estables para que un score absoluto no dependa arbitrariamente de las empresas incluidas en la petición.

Tratar empates de forma neutral: una serie constante no debe recibir sistemáticamente el máximo de su percentil propio.

### Explicar cambios con signos incorrectos

Las contribuciones deben conservar la dirección real del cambio. Si se muestran como puntos aditivos, deben reconciliar con el cambio del score. Una aproximación narrativa no debe presentarse como descomposición exacta.

### Confundir financiación con generación

Un plazo AP más largo puede mejorar liquidez y disciplina sin aumentar generación. Una entrada de apoyo tampoco es automáticamente una venta. Mantener separados ambos juicios.

### Interpretar fecha valor como confianza del banco

En la exploración bancaria, **293.464 transacciones de 1.161 sociedades** tienen distinta fecha contable y valor. La diferencia depende de categoría; las devoluciones de cobros tienen mediana de −4 días.

Eso no demuestra retención de fondos por desconfianza. Fecha valor no equivale a disponibilidad. Sin reglas de producto y banco, no se propone como rating implícito del financiador.

### Interpretar pagos anticipados como caja sobrante

Pueden responder a descuento, domiciliación, condiciones o registro del ERP. No prueban liquidez libre ni capacidad de pago sin conocer alternativas.

### Afirmar manipulación del vencimiento

Se observan condiciones distintas en documentos distintos. No existe historial suficiente para afirmar que se reescribió una misma factura, que se ocultó mora o que hubo maquillaje contable.

### Construir complejidad antes de tener un baseline

Grafos globales, modelos profundos o muchas señales nuevas no sustituyen cobertura, etiquetas y validación. Para esta propuesta bastan inicialmente relaciones locales y cálculos explicables.

---

## 14. Plan de construcción desde cero

| Orden | Trabajo | Entregable esperado |
|---|---|---|
| 1 | Aclarar unidad y métrica oficiales | Contrato de salida del score y evaluación |
| 2 | Ingestar los CSV sin alterar originales | Tablas tipadas, controles y reporte de cobertura |
| 3 | Definir qué se conoce en cada fecha | Política temporal y tratamiento de snapshots |
| 4 | Separar operación, circulación, apoyo e incertidumbre | Flujos interpretables por sociedad–mes |
| 5 | Construir un baseline sencillo | Salud, dirección, estabilidad y cobertura |
| 6 | Calcular los tres relojes | Explicaciones por relación con documentos trazables |
| 7 | Comparar condiciones y cohortes | Señales locales y materialidad comercial |
| 8 | Construir una pantalla de decisión | Demo navegable con el caso principal y sus límites |
| 9 | Evaluar temporalmente y por grupos | Métricas, falsas alarmas e incremento sobre baseline |
| 10 | Preparar entrega y pitch | Predicciones oficiales y demostración comercial honesta |

### Preguntas que hay que resolver antes de programar el score

- ¿La unidad evaluada es `group_id`, `company_id` o ambas? El reto menciona 250 empresas, pero los datos contienen 250 grupos y 1.286 sociedades.
- ¿Qué escala, meses y horizonte exige el script oficial?
- ¿Qué representa exactamente `due_date`: condición original o última revisión?
- ¿Cómo se relacionan `invoice` e `invoiceGroup`?
- ¿La fecha de pago es económica o administrativa?
- ¿Qué garantías hay sobre la dirección por signo y las monedas?

No promediar sin más scores de filiales para inventar salud de grupo. Al consolidar, los traspasos internos no generan caja externa y la cobertura del perímetro importa.

### Qué priorizar

Primero, un score general válido. Después, una explicación diferencial pequeña y verificable. Solo tras medir incremento predictivo, incorporar los nuevos plazos con peso en el motor.

No hace falta construir seis productos. Una pantalla que ayuda a una decisión real puede ser suficiente como producto sobre el score.

---

## 15. Validación necesaria para la entrega

### Temporal

- Construir cada mes con lo conocido al corte.
- Truncar datos y comprobar que no cambia el pasado.
- No usar vencimientos revisados como originales sin avisar.
- No adelantar retrospectivamente la fecha de confirmación de una alerta.
- Evaluar cohortes solo cuando maduran.

### Generalización

- Separar grupos completos, no filas o filiales hermanas.
- Mantener separación temporal compatible con el horizonte futuro.
- Aprender escalas en desarrollo, no con el lote oculto.
- Evaluar sensibilidad a ERP, moneda, tamaño y relaciones dominantes.
- No usar identificadores o ausencia de datos como atajos de salud.

### Utilidad de las alertas

Registrar todos los episodios y su seguimiento, no solo los aciertos. Informar precisión, sensibilidad, falsas alarmas por empresa-año, cobertura y anticipación. Una mediana de lead time entre aciertos no resume por sí sola utilidad.

Separar tres cosas:

1. observar un cambio de condiciones antes de su vencimiento;
2. predecir un deterioro futuro;
3. ayudar al CFO a tomar una decisión útil.

Son objetivos diferentes y requieren métricas diferentes.

### Coherencia

- Un traspaso propio no crea ventas.
- Un cambio de unidad monetaria equivalente no cambia salud.
- Un dato desconocido produce «no observable», no una cifra tranquilizadora.
- Una empresa constante no mejora solo porque empeoren otras, salvo en una vista relativa explícita.
- Las explicaciones no contradicen los documentos ni el signo de las features.

No convertir el índice de cobertura en una supuesta probabilidad de acierto.

---

## 16. Trazabilidad de las conclusiones

Las evidencias de facturas proceden de los CSV completos facilitados para el reto, no de las pequeñas muestras del repositorio. Los identificadores incluidos permiten localizar los documentos en cualquier copia de esos originales.

### Huellas de los dos CSV principales analizados

```text
invoices.csv
6686bd878244881bac78348a108852f3f30713ef244267f1fa3754b9be619c53

transactions.csv
000a6820a7500c66aa70a17b3e813d0c57a8270b3c58f6f2f006708a20228f2b
```

El CSV bancario contiene 25 bytes NUL, sustituidos solo en el buffer de lectura en memoria para la exploración de fechas. Los originales no se reescribieron.

### Cómo verificar el caso principal

1. Aplicar la selección de facturas del apartado 3.
2. Filtrar COMP_1171, COUNTERPARTY_06105, `invoice`, AR y EUR.
3. Mantener plazos 0–180 días.
4. Aceptar liquidación solo con estado `paid`, fecha no anterior a emisión y anterior a 2026-09-01.
5. Para el cuadro de liquidaciones, limitar duración a 0–180 y comparar `[2025-08-01, 2025-11-01)` con `[2025-11-01, 2026-02-01)`.
6. Calcular L, A y D sobre las mismas filas y usar `abs(amount)` para ponderar.
7. Para la condición a emisión, no limitarse a pagadas: comparar emisiones de junio–agosto de 2025 con las cuatro del 26 de septiembre.
8. Contrastar emisiones de septiembre–noviembre de 2024 y 2025 para estacionalidad.
9. Aplicar las sensibilidades del apartado 6 sin cambiar ventanas.

Los apartados 6–8 describen el protocolo de los otros contrastes. Las métricas predictivas dependen también del panel bancario auxiliar descrito en el apartado 3 y deben reproducirse al construir el proyecto. Este Markdown no es una entrega de código de reproducción ni un test automatizado.

Excluir facturas finalmente canceladas y utilizar estados finales bajo fechas de evento requiere supuestos. Sin ingestión ni versiones no se puede certificar qué información estaba disponible históricamente.

No se ha evaluado esta propuesta en el test oculto ni se ha validado comercialmente el producto.

---

## 17. Decisión recomendada

**Construir un score sencillo, temporalmente válido y explicable; encima, un producto que muestre financiación comercial escondida en los plazos.**

La idea diferencial no sería «sabemos lo que piensan tus proveedores». Sería:

> **Distinguimos si estás generando mejor caja, cumpliendo mejor tus compromisos o simplemente financiándote —o financiando a otros— durante más tiempo.**

El patrón de los tres relojes tiene evidencia concreta. La capacidad de anticipar deterioro general todavía no está demostrada. Esa frontera debe mantenerse visible en el producto y en el pitch.

**Punto de partida para el equipo:** los datos, estas conclusiones y el plan anterior. El motor, las features, la validación y la demo son el trabajo que queda por construir.
