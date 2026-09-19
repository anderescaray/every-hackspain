# Embat Pulse — Propuesta de Producto Final y MVP

> **HackSpain 2026 · Reto Embat · X-Ray**  
> Documento de producto para alinear al equipo sobre **qué vamos a construir**, **qué enseñaremos en la demo** y **qué dejamos fuera del MVP**.

---

## 1. Producto en una frase

**Embat Pulse** es un sistema de **early warning y explicación de tesorería para CFOs** que no se limita a decir si una empresa está “bien” o “mal”, sino que muestra:

1. **cómo está hoy**;
2. **hacia dónde se está moviendo**;
3. **por qué está cambiando**;
4. **si su caja se genera realmente por la operación o depende de circulación/apoyo**;
5. **si clientes y proveedores están cambiando las condiciones que afectan a su liquidez**.

La idea central es:

> **Embat Pulse no solo mira cuánto dinero hay. Entiende qué dinero genera realmente la empresa, cuál simplemente circula y qué parte de su liquidez depende de tiempo o apoyo externo.**

---

## 2. Qué problema resolvemos

Un CFO puede ver un saldo aparentemente sano y aun así estar entrando en tensión financiera.

Un dashboard tradicional puede engañar por varios motivos:

- una empresa puede tener caja positiva gracias a transferencias intragrupo;
- movimientos de cash pooling pueden parecer gastos o ingresos operativos;
- un cliente puede pasar de pagar “20 días tarde” a pagar puntual, pero si ahora se le conceden 40 días más de plazo, la empresa tarda más en convertir la venta en caja;
- una empresa puede seguir teniendo buen nivel de caja mientras su tendencia operativa se deteriora;
- un único mes malo puede ser estacionalidad y no deterioro estructural.

Por tanto, el problema no es únicamente:

> “¿Cuánto dinero tiene esta empresa?”

Sino:

> **“¿Qué está ocurriendo realmente detrás de esa caja y está mejorando o empeorando?”**

---

## 3. Usuario y comprador

### Usuario principal

**CFO / responsable de tesorería** de una empresa o grupo empresarial.

Necesita responder rápidamente:

- ¿qué sociedades están deteriorándose?
- ¿cuáles están mejorando?
- ¿qué alertas requieren atención?
- ¿la caja viene de la actividad o de apoyo?
- ¿estamos financiando más a nuestros clientes?
- ¿nuestros proveedores nos están concediendo menos tiempo?
- ¿un deterioro es puntual o persistente?

### Encaje con Embat

Embat ya trabaja con información bancaria y de tesorería.

Pulse puede plantearse como una capa adicional de inteligencia:

> **de visualizar tesorería → a interpretar tesorería → a ayudar a decidir.**

---

## 4. Tesis del producto

El producto se apoya en cuatro preguntas.

### 1. Health — ¿Cómo estoy?

Mide la situación financiera actual de forma explicable.

### 2. Direction — ¿Hacia dónde voy?

Distingue entre:

- improving;
- stable;
- deteriorating.

Una empresa con 65 que viene de 45 puede estar en una historia mucho mejor que una empresa con 70 que viene de 85.

### 3. Cash Truth — ¿De dónde viene realmente mi caja?

Separa, cuando exista evidencia suficiente:

- operación;
- circulación propia / cash pooling;
- transferencias intragrupo;
- financiación/inversión;
- movimientos inciertos.

### 4. Time Borrowed — ¿Quién está financiando a quién y durante cuánto tiempo?

Separa tres conceptos que normalmente se mezclan:

- **plazo concedido/recibido**;
- **tiempo hasta liquidación**;
- **retraso sobre vencimiento**.

Esto permite detectar situaciones donde “la puntualidad mejora” pero la conversión a caja empeora.

---

# 5. MVP FINAL QUE QUEREMOS IMPLEMENTAR

Este es el núcleo. Todo lo demás es secundario.

## Pantalla 0 — Import Dataset

El usuario puede:

- arrastrar los CSV;
- seleccionar los archivos;
- usar un dataset ya procesado;
- entrar en demo.

Flujo:

```text
CSV
 ↓
Validación
 ↓
Cleaning
 ↓
Features
 ↓
Score
 ↓
Alerts
 ↓
Portfolio
```

La interfaz no procesa cientos de MB en navegador. El frontend únicamente sube los archivos al backend.

---

## Pantalla 1 — Portfolio

Objetivo:

> **En menos de 10 segundos el CFO debe saber dónde mirar.**

Tabla principal:

| Company | Pulse | Trajectory | Confidence | Main Signal | Alerts |
|---|---:|---|---:|---|---:|
| COMP_A | 72 | Deteriorating ↓ | 91% | Operating cash ↓ | 3 |
| COMP_B | 65 | Improving ↑ | 86% | Collections ↑ | 1 |
| COMP_C | 81 | Stable → | 74% | — | 0 |

Filtros:

- Improving
- Stable
- Deteriorating
- Active alerts
- Group
- Confidence

No queremos que el Portfolio sea otro dashboard lleno de gráficos. Debe contestar:

> **“¿Qué empresas necesitan mi atención?”**

---

## 6. Pulse Score

El score es la entrada al producto, no el producto entero.

Mostrar:

```text
Pulse Score      68 / 100
Health           72
Momentum         ↓ Deteriorating
Stability        61
Confidence       88%
```

### Health

Mide el nivel financiero actual.

Dimensiones iniciales:

- generación operativa;
- conversión de cobros/pagos;
- obligaciones;
- autonomía/dependencia de apoyo;
- resiliencia/downside.

### Momentum

Mide si las variables están mejorando, estables o deteriorándose.

Preferencia inicial:

- tendencia reciente;
- comparación 3 meses vs 3 meses anteriores;
- comparación interanual donde tenga sentido.

### Stability

Evita reaccionar de forma exagerada a un único mes y ayuda a distinguir **bache puntual vs cambio persistente**.

### Confidence

NO significa “88% de probabilidad de que tengamos razón”.

Significa:

> **“Tenemos buena cobertura y suficiente evidencia para calcular este diagnóstico.”**

Puede depender de:

- meses observados;
- nº de transacciones;
- nº de facturas;
- huecos;
- cobertura ERP;
- cobertura de counterparties;
- disponibilidad de cada dimensión.

---

## 7. Feature estrella #1 — Cash Truth

### Pregunta

> **¿Esta caja se genera, simplemente circula o viene de apoyo?**

Un dashboard tradicional puede sumar movimientos clasificados y concluir que una empresa tiene un enorme flujo operativo negativo, cuando parte de esos movimientos puede ser circulación automática de liquidez.

Cash Truth intenta separar:

```text
MOVIMIENTO BANCARIO TOTAL
          ↓
CIRCULACIÓN / CASH POOLING
          ↓
TRANSFERENCIAS IDENTIFICADAS
          ↓
OPERACIÓN IDENTIFICADA
          ↓
FINANCIACIÓN / INVERSIÓN
          ↓
INCIERTO
```

### Ejemplo visual

```text
Cash movement total             €4.8M

Generated by operations        +€320k
Treasury circulation             €870k
Group/internal support         +€3.4M
Other / uncertain                €210k
```

Y debajo:

> ⚠ **Liquidity dependency increasing**  
> La operación genera caja positiva, pero una parte relevante de la posición observada depende de apoyo identificado.

### Regla fundamental

No inventamos la clasificación. Cuando no exista suficiente evidencia:

> **“No identificable con suficiente confianza.”**

---

## 8. Feature estrella #2 — Time Borrowed

Nombre interno / comercial provisional: **Time Borrowed / Tiempo Prestado**.

### Problema

Pagar puntual no significa necesariamente cobrar antes.

Ejemplo:

```text
ANTES
Plazo concedido:       60 días
Retraso del cliente:   20 días
Cobro real:            día 80

DESPUÉS
Plazo concedido:      100 días
Retraso del cliente:    0 días
Cobro real:           día 100
```

Un dashboard normal podría decir:

> ✅ El retraso ha mejorado de 20 días a 0.

Pulse añade:

> ⚠ Sí, el cliente paga puntual, pero ahora tardamos más en convertir la venta en caja.

### Los tres relojes

Para cada relación comparable:

```text
L = fecha_vencimiento - fecha_emisión
A = fecha_liquidación - fecha_emisión
D = fecha_liquidación - fecha_vencimiento
```

Donde:

- **L — Plazo:** cuánto tiempo se concede.
- **A — Tiempo hasta liquidación:** cuánto tarda realmente en cerrarse.
- **D — Retraso:** cuánto se excede el vencimiento.

Esto permite distinguir situaciones como:

```text
Retraso ↓
pero
Tiempo hasta cobro ↑
```

### Lado cliente — AR

Pregunta:

> **¿Estamos financiando más tiempo a nuestros clientes?**

Mostrar:

```text
Customer: COUNTERPARTY_X

Payment term          62d → 102d
Late payment          20d →   0d
Time to cash          81d → 102d
```

Conclusión:

> La puntualidad mejora, pero la conversión a caja se ralentiza porque el plazo concedido aumenta.

### Lado proveedor — AP

Pregunta:

> **¿Nuestros proveedores nos están financiando durante más o menos tiempo?**

Ejemplo:

```text
Supplier payment term
90d → 52d
```

Significa:

> Ahora necesitamos caja antes para pagar.

NO significa automáticamente que el proveedor haya dejado de confiar en nosotros. Puede deberse a negociación, producto, estacionalidad, política del grupo, ERP, etc.

El sistema muestra **el cambio observado**, no inventa la intención.

---

## 9. Alerts — Qué debería mirar hoy el CFO

No queremos 200 señales en pantalla. Queremos un feed corto, trazable y útil.

Ejemplos:

### HIGH — Operating deterioration

```text
Operating cash generation has deteriorated
for 3 consecutive months.
```

### HIGH — Liquidity dependency

```text
A growing share of observed liquidity comes
from identified group/internal support.
```

### MEDIUM — Customer terms extended

```text
Top customer:
62 days → 102 days

Payment punctuality improved,
but time-to-cash increased.
```

### MEDIUM — Supplier terms compressed

```text
Comparable suppliers:
71 days → 49 days

Cash is required earlier than six months ago.
```

Cada alerta debe permitir abrir:

- evidencia;
- meses;
- facturas/transacciones;
- magnitud;
- cobertura;
- explicación.

---

## 10. Company Detail — Pantalla central de la demo

La página de una empresa debe quedar aproximadamente así:

```text
──────────────────────────────────────
COMP_XXXX
Pulse                                68
Deteriorating ↓          Confidence 88%
──────────────────────────────────────

WHY IS PULSE CHANGING?

↓ Operating generation              -8
↓ Working-capital conditions        -5
↑ Collections                        +2

──────────────────────────────────────
TRAJECTORY
24-month Pulse / Health / Momentum
──────────────────────────────────────

CASH TRUTH
Generated by operations        +€320k
Group/internal support         +€1.4M
Treasury circulation            €870k

⚠ Dependency increasing
──────────────────────────────────────

TIME BORROWED
CUSTOMERS
Time to cash              71d → 94d

SUPPLIERS
Payment window            63d → 48d

⚠ Working-capital pressure
──────────────────────────────────────

ACTIVE ALERTS
3
──────────────────────────────────────
WHAT-IF
```

---

## 11. What-if Simulator

El What-if se mantiene, pero NO es la tesis principal del producto.

Su objetivo es transformar diagnóstico en conversación de decisión.

Ejemplos:

```text
What if customer terms fall by 15 days?
What if collections improve by 10 days?
What if internal support is reduced?
```

Mostrar:

- escenario actual;
- escenario modificado;
- variables afectadas;
- Pulse estimado bajo ese escenario.

### Muy importante

No presentarlo como:

> “Esto es lo que va a pasar.”

Presentarlo como:

> **“Este sería el resultado mecánico bajo este escenario.”**

No sabemos si un cliente aceptaría nuevas condiciones, si cambiar condiciones afecta a ventas, si un proveedor reaccionaría o qué decisión tomaría finalmente la empresa.

Es una herramienta de análisis, no una predicción causal.

---

## 12. Vista de Grupo — escenario mecánico intragrupo (implementado el 19-09)

> **Actualización 19-09-2026.** Este apartado decía «no generar “transfiere 110.000 € de Filial B a Filial A”». Se ha sustituido por la fórmula del What-if (§11): el módulo `treasury_advisor_v1` (`src/xray/group_advisor/`, spec en `group-optimization.md`, decisiones §14) calcula **escenarios mecánicos bajo supuestos explícitos** sobre la función de nivel exacta de V2, con los supuestos en pantalla. No es una instrucción ejecutable ni una predicción. Decisión GA-00.

La vista de grupo aparece **solo si el grupo tiene ≥2 filiales puntuadas** (71 de 250 grupos son unipersonales y no la ven). Muestra:

```text
GROUP_0067                                   G (utilidad por tramos) 60,1 → 67,7 en régimen

COMP_1048   nivel 88  verde   donante
COMP_1275   nivel 31  rojo    receptora   → 66,7 en régimen (rojo → ámbar)
COMP_0216   nivel 32  rojo    receptora (25 %)
COMP_0407   nivel 48  ámbar   estructural: margen 6m −0,27
...

Paso 1 · COMP_1048 asume el 100 % de las cuotas de deuda de COMP_1275 (12.340 EUR/mes, 6 meses).
         El servicio externo del grupo no cambia; se traslada a quien puede llevarlo.
         Efecto k=1 / k=6 · evidencia ev_0019, ev_0026 · restricción activa · alternativas rechazadas
Supuestos: estacionariedad · crédito intragrupo no liquidado por banco · sin fiscalidad, legal, covenants ni precio intragrupo
```

Dos palancas, ambas con evidencia directa en los datos: **D1** (la filial fuerte asume el servicio de deuda de la débil; el nivel de la receptora sube por `debt_service_w`, el del donante baja algo, el consolidado no cambia) y **P** (financiar el pago a proveedores en plazo, solo si la receptora está restringida por liquidez; si paga tarde teniendo caja se etiqueta «retraso no explicado por liquidez» y no se propone nada). El objetivo es una utilidad cóncava por tramos (un punto en rojo vale tres en verde): «ayudar a la que se hunde» sale de la fórmula. Restricciones: caja reconstruida fiable, colchón del donante de dos meses, no sobrefinanciar, suelo de nivel del donante; lo no observable (fiscalidad, legal, covenants, precio intragrupo) se lista, no se modela.

### Lo que sigue sin hacerse

- Cancelación anticipada de deuda con caja del grupo (D2): V2 la penaliza seis meses aunque ahorre intereses; descartada y documentada.
- Recomendaciones ejecutables a un clic, contratos intercompany, ahorro en euros con tipos/comisiones inventados.
- Cobertura: en agosto 2026 solo 19 grupos tienen plan; 160 no tienen palanca factible (caja del donante no fiable, receptora sin deuda ni AP, colchón) y la vista lo dice filial por filial. Es un resultado honesto de palancas estrictas, no un fallo a esconder.

---

## 13. Arquitectura: números deterministas + IA opcional

```text
┌─────────────────────────────────────────────┐
│         FINANCIAL ENGINE — PYTHON           │
│ Cleaning · Features · Pulse                 │
│ Momentum · Stability · Confidence           │
│ Cash Truth · Time Borrowed                  │
│ Alerts · What-if                            │
└──────────────────┬──────────────────────────┘
                   │ JSON estructurado
                   ▼
┌─────────────────────────────────────────────┐
│              FRONTEND / COPILOT             │
│ Portfolio · Company detail                  │
│ Explanations · Evidence · Scenario UI       │
│ Narrativa opcional con LLM                  │
└─────────────────────────────────────────────┘
```

### Regla

> **El LLM nunca calcula los números financieros.**

El motor financiero determina importes, score, señales, días, dirección y alertas.

Un LLM, si se incorpora, puede transformar ese JSON en lenguaje natural, pero no inventa causas ni cifras.

Para el MVP, el LLM es opcional.

---

## 14. Qué cogemos de la idea “Group Co-Pilot”

La propuesta compartida por el equipo tiene ideas interesantes que podemos integrar sin desviar el MVP.

### Sí incorporar

- **Buyer claro:** CFO / tesorero de grupos.
- **Producto accionable:** no quedarnos en “Score = 63”; terminar cada análisis con “esto es lo que deberías revisar”.
- **Capa de grupo:** mostrar dependencia o soporte entre filiales cuando exista evidencia.
- **Copilot como interfaz:** evolución natural para preguntar “¿por qué está empeorando?” o “¿qué evidencia hay?”.

### Incorporado el 19-09 (ver §12 y `group-optimization.md`)

- **Capa de grupo con escenarios mecánicos** (D1, P) y **bloque «Qué mueve tu nivel» en la ficha de cada empresa**: pendiente por palanca, hasta dónde vale (siguiente nudo de las anclas) y cuánto hace falta para cambiar de tramo, con palancas de tesorería y de negocio etiquetadas (las de negocio son sensibilidad, nunca recomendación de recortar).
- **Copiloto determinista**: la narrativa sale de plantillas sobre el JSON del motor y un validador comprueba que cada número y cada id del texto existen en el JSON; hay nueve preguntas cerradas (`why_not_more`, `what_moves_most`, `how_to_reach_tramo`…). El LLM es opcional, parafrasea con temperatura 0 y cae a la plantilla si inventa un número. No hay proveedor conectado.

### Dejar para una fase posterior

- cash sweeping prescriptivo automático;
- ahorro exacto en euros sin datos de tipos/comisiones;
- contratos intragrupo automáticos;
- prometer “anticipamos 3 meses” de forma universal;
- recomendaciones financieras ejecutables a 1 click.

---

## 15. Diferenciación

| Dashboard típico | Embat Pulse |
|---|---|
| Saldo actual | Nivel + trayectoria |
| Cashflow bruto | Cash Truth |
| DSO/DPO | Plazo + tiempo a caja + retraso |
| Score opaco | Score + drivers + evidencia |
| Empresa aislada | Empresa + contexto de grupo |
| Gráfica | Alertas accionables |
| “Está peor” | “Está peor por estas razones” |
| Predicción sin trazabilidad | Evidencia hasta transacción/factura |

Nuestro mensaje no debería ser:

> “Tenemos un modelo más sofisticado.”

Sino:

> **“Interpretamos mejor el movimiento del dinero.”**

---

## 16. Demo propuesta

### Momento 1 — Portfolio

> “Pulse analiza todo el portfolio y me dice dónde mirar.”

Mostrar improving, deteriorating, confidence y alertas.

### Momento 2 — Cash Truth

Abrir una empresa donde un análisis simple de categorías se equivoque.

> “A simple vista parece que esta sociedad tiene un deterioro operativo enorme.”

Abrir Cash Truth.

> “Pero cuando seguimos el movimiento del dinero encontramos circulación recurrente de tesorería. No son nuevos gastos operativos.”

Después mostrar:

> “Eso tampoco significa que la empresa esté perfecta: podemos observar que parte de la posición depende de apoyo.”

Mensaje:

> **Mismo saldo aparente. Realidad financiera distinta.**

### Momento 3 — Time Borrowed

Abrir un caso como:

```text
Late payment       20d → 0d
```

Preguntar:

> “¿Esto significa que estamos cobrando antes?”

Mostrar:

```text
Payment term       62d → 102d
Time to cash       81d → 102d
```

Narrativa:

> “No. El cliente ahora paga puntual, pero hemos ampliado tanto el plazo que convertimos la venta en caja más tarde.”

### Momento 4 — Acción

Mostrar una alerta y el What-if:

```text
Scenario:
customer term -15 days
```

No prometemos que el cliente acepte. Mostramos cómo cambiaría el escenario si esa condición fuera distinta.

---

## 17. Pitch en una frase

> **“Embat Pulse no solo te dice cómo está una empresa. Te dice hacia dónde va, qué está ocurriendo realmente detrás de su caja y qué relación financiera deberías revisar antes de tomar una decisión.”**

Versión más agresiva:

> **“Otros dashboards cuentan dinero. Embat Pulse entiende qué dinero generas, cuál solo circula y cuánto tiempo estás financiando —o siendo financiado por— otros.”**

---

## 18. Alcance del MVP

### MUST HAVE

- Import CSV
- Portfolio
- Pulse Score
- Health
- Momentum
- Stability
- Confidence
- 24-month trajectory
- Explanations
- Alerts
- Cash Truth
- Time Borrowed
- Evidence drill-down
- What-if básico

### SHOULD HAVE

- **Bloque «Qué mueve tu nivel» en la ficha** (sensibilidad de empresa; motor implementado, `company_sensitivity/`)
- **Vista de grupo con plan mecánico** solo si ≥2 filiales puntuadas (motor implementado, `group_plans/`)
- Internal support dependency
- filtros y búsqueda
- casos demo seleccionados (`group-optimization.md` §15: GROUP_0067, GROUP_0022, GROUP_0064, COMP_0007, COMP_1275)

### NICE TO HAVE

- chat LLM sobre el JSON (interfaz `Completer` y validador de anclaje listos; falta proveedor)
- briefing ejecutivo generado
- export PDF
- escenarios más avanzados
- comparación entre filiales

### FUTURO

- optimización de cash pooling y palancas cruzadas de moneda con FX diario (hoy tipo fijo, panel 100 % EUR);
- cancelación anticipada de deuda (D2) si el score deja de penalizar el pico de principal;
- aceleración de cobros con coste de factoring observado;
- selección óptima de financiación;
- generación documental;
- acciones 1-click;
- integración operativa con Embat.

---

## 19. Qué NO debemos construir ahora

Para proteger tiempo y calidad:

- deep learning;
- grafos globales de contrapartes sin cobertura;
- predicción de quiebra;
- deuda histórica inventada a partir del snapshot final;
- reconstrucción de saldo presentada como verdad si no está validada;
- otro score semanal independiente;
- 20 features sin explicación;
- recomendaciones legales/fiscales;
- cash sweeps automáticos;
- contratos intercompany;
- seis productos diferentes.

El objetivo es que el jurado entienda **una gran idea muy bien**, no veinte ideas a medias.

---

## 20. Orden de implementación

1. **Asegurar score y temporalidad**: revisar leakage, snapshots finales, vencimientos, escalas, rankings y confidence.
2. **Cash Truth**: separar operación, circulación reconocida, apoyo identificado e incierto.
3. **Time Borrowed**: implementar plazo, tiempo a liquidación, retraso y cambio en relaciones comparables.
4. **Alerts**: generar alertas simples, trazables y priorizadas.
5. **Company Detail**: integrar Pulse, trajectory, Cash Truth, Time Borrowed y alerts.
6. **Evidence**: permitir ver qué movimientos o documentos justifican una conclusión.
7. **What-if**: conectar escenarios con el mismo motor de score.
8. **Demo**: elegir 2–3 empresas y ensayar una historia de 90 segundos.

---

## 21. Qué queremos que recuerde el jurado

No:

> “Tenían un score de 68.”

Sí:

> **“Eran los que descubrieron que una empresa podía parecer peor porque el mismo dinero estaba circulando, y que otra podía parecer cobrar mejor cuando en realidad tardaba más en convertir ventas en caja.”**

Ese es el producto.

---

## 22. Decisión final

| Elemento | Decisión |
|---|---|
| **Nombre** | Embat Pulse |
| **Categoría** | Treasury Early Warning & Decision Intelligence |
| **Buyer** | CFO / Treasury Manager |
| **Core** | Pulse + Trajectory + Explainability |
| **Diferenciadores** | Cash Truth + Time Borrowed |
| **Acción** | Alerts + What-if |
| **Visión futura** | Group Treasury Co-Pilot prescriptivo |

---

> ## Mensaje final
>
> **Embat Pulse convierte el rastro bancario y ERP en una explicación accionable de la salud financiera.**
>
> No se limita a mostrar cuánto dinero hay: distingue **qué dinero se genera**, **qué dinero circula**, **qué liquidez depende de apoyo** y **cómo clientes y proveedores están cambiando el tiempo necesario para convertir operaciones en caja**.
>
> El MVP debe demostrar eso de forma simple, trazable y visual.
