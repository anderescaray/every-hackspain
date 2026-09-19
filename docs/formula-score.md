# La fórmula del score, en una página

El score es un número de 0 a 100 por empresa y mes. Combina **dónde está** la empresa (nivel) con **hacia dónde va** (momentum). Implementación: `src/xray/score_v2/`; detalle completo en [scoring-v2.md](./scoring-v2.md).

```
score = clip( nivel + 0,20 · (momentum − 50) , 0, 100 )
```

- `nivel` va de 0 a 100 y pesa lo principal.
- `momentum` va de 0 a 100 con 50 como neutral; como mucho mueve el score ±10 puntos.
- `clip` solo evita salir del rango 0–100.

## Nivel: dónde está la empresa (últimos seis meses)

```
nivel = 0,45 · N(margen) + 0,25 · N(servicio de deuda) + 0,15 · N(retraso cobros) + 0,15 · N(retraso pagos)
```

| Señal | Qué es | Cómo se calcula (sumando los seis últimos meses, no promediando meses) |
|---|---|---|
| **Margen** (45 %) | Si genera más caja operativa de la que gasta | (Σ entradas operativas − Σ salidas operativas) / (Σ entradas + Σ salidas). Rango −1..+1 |
| **Servicio de deuda** (25 %) | Qué parte de lo que entra se va en devolver deuda | (Σ principal pagado + Σ intereses) / Σ entradas operativas |
| **Retraso cobros** (15 %) | Con cuántos días de retraso le pagan sus clientes | Mediana de (fecha de cobro − vencimiento) de las facturas emitidas, ponderada por número de pagos |
| **Retraso pagos** (15 %) | Con cuántos días de retraso paga a proveedores | Igual, con las facturas recibidas |

`N(·)` convierte cada magnitud en una nota 0–100 con **anclas financieras fijas** (interpolación lineal). Por ejemplo, margen −25 % → 20 puntos, 0 % → 55, +10 % → 75, +25 % → 90; servicio de deuda 5 % → 90, 30 % → 40, 50 % → 15; retraso 0 días → 100, 30 días → 40, 90 días → 0. Esa nota se mezcla al 70/30 con la posición de la empresa respecto al resto de la cartera (percentiles 10–90 de los grupos de referencia), para corregir lo que las anclas no capten.

Si una dimensión no existe (p. ej. la empresa no tiene ERP conectado y no hay facturas), su peso se reparte entre las demás y el score queda marcado como `provisional`. Nunca se inventa una nota "sana" por falta de datos.

## Momentum: hacia dónde va (último trimestre frente al anterior)

```
momentum = 50 + 50 · tanh( z̄ / 2 )

z̄  = ( 0,35·z_margen + 0,25·z_crecimiento + 0,20·z_deuda + 0,10·z_cobros + 0,10·z_pagos ) / √(Σ pesos²)

z_i = ( valor del último trimestre − valor del trimestre anterior )_i  /  σ_i
```

- Se usan las mismas cuatro magnitudes del nivel, calculadas por trimestre, más el **crecimiento de las entradas** en las mismas cuentas bancarias (suma de log(1+g) de tres meses, que no tiene sesgo alcista).
- **σ_i es la volatilidad mensual habitual de esa misma empresa** (12 meses anteriores al trimestre reciente). Así el cambio se mide en "cuántas veces su ruido normal": una empresa que oscila mucho necesita un cambio grande para que cuente; una muy estable, uno pequeño. Es lo que separa un mes malo de una tendencia.
- La combinación `Σ w·z / √Σ w²` (Z de Stouffer) hace que, si todo es ruido, z̄ se comporte como una normal estándar con cualquier número de señales disponibles: el umbral no depende de si la empresa tiene ERP o no.
- `tanh(z̄/2)` lo lleva a 0–100: z̄ = 0 → 50 (neutral), z̄ = +1,5 → 82, z̄ = −1,5 → 18, saturando en los extremos.

## De momentum a etiqueta (bache o tendencia)

| Condición | Etiqueta |
|---|---|
| \|z̄\| < 1,5 | `stable` (o `mixed_signals` si unas señales suben y otras bajan) |
| \|z̄\| ≥ 1,5 un mes | `emerging_improvement` / `emerging_deterioration` |
| \|z̄\| ≥ 1,5 **dos meses seguidos y el mes actual sigue del mismo lado de su nivel de seis meses** | `improving` / `deteriorating` (confirmado) |
| Mes actual a más de 2σ de su nivel sin tendencia confirmada | episodio `one_off_dip` / `one_off_spike` (bache) |

## ¿Por qué el momentum ajusta el nivel en vez de ser un porcentaje del score?

Hay dos formas de combinar las dos partes. La elegida (A) suma un ajuste centrado en 50; la alternativa (B) sería una media ponderada de dos notas 0–100, p. ej. `0,70·nivel + 0,30·momentum`.

**A · `nivel + 0,20·(momentum − 50)` (actual)**

| Ventajas | Desventajas |
|---|---|
| El número se lee como **estado de salud**: 80 es sano y 30 no, vaya la empresa a mejor o a peor. Es la lectura de un analista de riesgo | El peso de la tendencia es fijo y pequeño (±10): una empresa en caída fuerte pero con nivel alto sigue alta (82 → 74). Si el leaderboard premia la dirección, el compuesto la refleja poco y hay que apoyarse en la etiqueta |
| El momentum está centrado en cero: sin tendencia no aporta ni resta; si falta (empresa nueva), el score es el nivel sin inventar un 50 ni cambiar de escala | El 0,20 es una constante elegida a mano, explicable pero no calibrada |
| Dos empresas con el mismo nivel y sin tendencia sacan el mismo score; el nivel es comparable entre empresas y en el tiempo | Hace falta recortar a 0–100: nivel 97 con momentum alto se satura en 100 y pierde información |
| Tramos, límites de crédito y umbrales de producto cuelgan del nivel; la tendencia se muestra al lado, no los contamina | Quien solo mire el número puede no ver la tendencia: obliga a mostrar siempre nivel, momentum y etiqueta juntos |

**B · `α·nivel + (1−α)·momentum`**

| Ventajas | Desventajas |
|---|---|
| Da más protagonismo a la trayectoria: la que se tuerce baja antes, la que mejora sube antes | **Rompe la lectura del número como estado.** Con 70/30, una empresa excelente y estable (95, 50) saca 81,5 y una mediocre en racha (55, 95) saca 67; ninguna empresa estable puede superar `α·100 + (1−α)·50` = 85. La escala deja de significar salud |
| Fórmula aún más simple de contar ("70 % dónde está, 30 % hacia dónde va") y sin recorte: la media de dos notas 0–100 ya está en rango | Cuando falta el momentum hay que imputar 50 (inventar neutralidad) o renormalizar a nivel puro, con lo que empresas nuevas y con historia no comparten escala |
| Pesos como porcentajes explícitos, fáciles de negociar con negocio | Amplifica la parte más ruidosa: el momentum es por construcción la más volátil; darle un 30 % multiplica por 1,5 los saltos que acabamos de suavizar (el rebote tras un mes atípico pasaría de ±5 a ±15 puntos) |
| | Cuenta la tendencia dos veces: el nivel de seis meses ya va incorporando el deterioro; sumar además un 30 % de momentum lo dobla mientras dura y luego el score rebota al normalizarse el momentum aunque el nivel siga bajo |
| | Los tramos de producto cambiarían por una racha de dos trimestres sin cambio estructural |

**Decisión:** mantener A como número principal. Si hace falta dar más peso a la trayectoria, hacerlo sin cambiar de esquema: subir el coeficiente (0,20 → 0,30, ±15 puntos) conservando el centrado en 50, y entregar siempre las tres cosas (nivel, momentum, score compuesto) más la etiqueta, para que quien evalúe la dirección la tenga ya calculada. Si algún día se optara por B, las condiciones mínimas son no imputar 50 cuando falte el momentum y mantener su peso por debajo del 20 %.

## Explicación

Cada score se descompone exactamente en sumandos: la contribución de cada dimensión del nivel (`peso · nota`) más la contribución de cada señal del momentum (`0,20 · k(z̄) · w_i·z_i / √Σw²`, con `k` un factor común de saturación) más el recorte a 0–100. La suma coincide con el score con tolerancia numérica y se valida automáticamente. Por eso siempre se puede decir "saca 51 porque el margen de seis meses vale −12 % (+25 puntos), no paga deuda (+36) y el último trimestre es 4 desviaciones peor que el anterior (−10)".
