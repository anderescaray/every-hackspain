# La fórmula del score, en una página

El score es un número de 0 a 100 por empresa y mes. Combina **dónde está** la empresa (nivel) con **hacia dónde va** (momentum). Implementación: `src/xray/score_v2/` (`financial_smoothed_v2`); detalle completo en [scoring-v2.md](./scoring-v2.md).

**Es el score oficial de la web** desde el PR #3 (`frontend_export.py`, `MODEL_VERSION = financial_smoothed_v2+frontend-export-1`). PulseFourPillars (`src/xray/pulse/`) se conserva como experimento y no alimenta la web. Estado a 2026-09-19 (agosto de 2026, último mes completo): **1.011 empresas con score** (284 `scored`, 727 `provisional`) y 275 sin score, tras D39.

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

`N(·)` convierte cada magnitud en una nota 0–100 con **anclas financieras fijas** (interpolación lineal):

| Señal | Anclas (valor → puntos) |
|---|---|
| Margen | −100 % → 0 · −25 % → 20 · 0 % → 55 · +10 % → 75 · +25 % → 90 · ≥+50 % → 100 |
| Servicio de deuda | 0 % → 100 · 5 % → 90 · 15 % → 70 · 30 % → 40 · 50 % → 15 · 100 % → 0 |
| Retraso cobros y pagos | 0 días → 100 · 7 → 85 · 15 → 65 · 30 → 40 · 60 → 15 · ≥90 → 0 |

Esa nota se mezcla al **70/30** con la posición de la empresa respecto al resto de la cartera (percentiles 10–90 de los grupos de referencia), para corregir lo que las anclas no capten. La parte empírica solo se usa si la referencia tiene al menos 100 observaciones de 20 grupos; si no, cuenta solo la ancla. La referencia se construye con los 24 meses anteriores, reservando un 20 % de grupos como holdout, y cada grupo pesa igual.

Si una dimensión no existe (p. ej. la empresa no tiene ERP conectado y no hay facturas), su peso se reparte entre las demás y el score queda marcado como `provisional`. Nunca se inventa una nota "sana" por falta de datos. El nivel necesita al menos **3 meses con calidad** dentro de la ventana de 6.

### Qué entra en cada magnitud (datos)

| Magnitud | Origen |
|---|---|
| Entradas y salidas operativas | **Libro de caja canónico** (`xray.ledger.classify`): una sola interpretación económica por movimiento, compartida con el resto del proyecto. Cobros (`collection`, TPV, efectivo, devoluciones recibidas) y pagos (proveedores, suministros, nóminas, Seguridad Social, impuestos). Traspasos entre cuentas propias e intragrupo, financiación, inversión y movimientos inciertos **no** son operativos |
| Categorías | Los movimientos sin categoría bancaria se completan con un **artefacto estático de categorías AI** (D31, confianza ≥ 0,7), activo por defecto. No es una llamada a un modelo en tiempo real |
| Servicio de deuda | Principal (`debt_repayment`) e intereses financieros observados en el banco. Las **comisiones de pasarela** (Stripe, network cost) salen del servicio de deuda (van a operativas). No se usa `debt_products`: no tener productos registrados no significa no tener deuda (D36) |
| Retrasos de cobro y pago | Solo facturas estándar (`invoice`) pagadas con vencimiento válido; exige al menos **5 pagos** en el mes para usar el retraso actual. **Fechas de pago de relleno (D39):** si el historial de la empresa en esa dirección hasta el mes tiene ≥30 pagos y ≥95% exactamente al vencimiento (típico de Business Central, que pone el vencimiento como fecha de pago), el retraso es **no medible** (vacío, como sin ERP), nunca un 0 perfecto falso |
| Moneda | **Todo en EUR** con un tipo fijo por moneda (`xray.fx`, D32). Cada empresa suma todas sus cuentas y facturas; ningún movimiento se descarta por su tamaño |
| Primer mes | El primer mes con actividad real de quien entra a mitad de ventana está incompleto (empieza a mitad de mes, ~60 % de actividad) y **sus importes no cuentan** (D33) |
| Mes con calidad | Al menos 5 movimientos utilizables, ≥ 80 % de filas utilizables, ≥ 10 % del importe operativo y todas las empresas del panel informadas |

## Momentum: hacia dónde va (último trimestre frente al anterior)

```
momentum = 50 + 50 · tanh( z̄ / 2 )

z̄  = ( 0,35·z_margen + 0,25·z_crecimiento + 0,20·z_deuda + 0,10·z_cobros + 0,10·z_pagos ) / √(Σ pesos²)

z_i = ( valor del último trimestre − valor del trimestre anterior )_i  /  σ_i
```

- Se usan las mismas cuatro magnitudes del nivel, calculadas por trimestre, más el **crecimiento de las entradas** en las mismas cuentas bancarias (suma de log(1+g) de tres meses, que no tiene sesgo alcista).
- **σ_i es la volatilidad mensual habitual de esa misma empresa** (12 meses anteriores al trimestre reciente). Así el cambio se mide en "cuántas veces su ruido normal": una empresa que oscila mucho necesita un cambio grande para que cuente; una muy estable, uno pequeño. Es lo que separa un mes malo de una tendencia.
- La combinación `Σ w·z / √Σ w²` (Z de Stouffer) hace que, si todo es ruido, z̄ se comporte como una normal estándar con cualquier número de señales disponibles: el umbral no depende de si la empresa tiene ERP o no.
- `tanh(z̄/2)` lo lleva a 0–100: z̄ = 0 → 50 (neutral), z̄ = +1,5 → 82, z̄ = −1,5 → 18, saturando en los extremos. Cada z_i se recorta a ±4.
- **Ajuste estacional del crecimiento:** a cada crecimiento mensual se le resta el típico de ese mes del año (agosto y enero muy negativos, diciembre positivo), estimado solo con la referencia anterior al mes puntuado. Así un agosto flojo no se lee como deterioro. Medido: la mediana del momentum de la cartera oscila unos 4 puntos a lo largo del año, frente a 12,5 en un momentum sin ajustar.
- **Cobertura:** el crecimiento no se mide hacia ni desde un mes de alta (`onboarding`), para no confundir conectar cuentas con crecer.
- El momentum exige al menos **7 meses de historia útil**, 2 meses con calidad por trimestre y señales que sumen al menos el 50 % del peso; la volatilidad propia necesita al menos 4 de los 12 meses. Si no llega, el momentum queda vacío (no se imputa 50) y el score es el nivel.

## De momentum a etiqueta (bache o tendencia)

| Condición | Etiqueta |
|---|---|
| \|z̄\| < 1,5 | `stable` (o `mixed_signals` si unas señales suben y otras bajan) |
| \|z̄\| ≥ 1,5 un mes | `emerging_improvement` / `emerging_deterioration` |
| \|z̄\| ≥ 1,5 **dos meses seguidos y el mes actual sigue del mismo lado de su nivel de seis meses** | `improving` / `deteriorating` (confirmado) |
| Mes actual a más de 2σ de su nivel sin tendencia confirmada | episodio `one_off_dip` / `one_off_spike` (bache) |
| Sin momentum disponible | `insufficient_history` |

Una dirección confirmada se mantiene mientras \|z̄\| no baje de la mitad del umbral (histéresis 0,5 · 1,5 = 0,75), para que la etiqueta no parpadee. Nunca se mira el mes siguiente.

Reparto en agosto de 2026 (tras D39): `stable` 598, `insufficient_history` 509, `emerging_deterioration` 73, `emerging_improvement` 56, `improving` 19, `deteriorating` 17, `mixed_signals` 14.

## Cuándo se puntúa y cuándo queda `provisional`

| Situación | Resultado |
|---|---|
| Sin movimientos utilizables, cobertura de grupo incompleta o menos de 3 meses con calidad en la ventana | `not_scored` (sin score) |
| Mes actual con poca actividad (`thin_current_month`), historia corta, sin momentum, faltan dimensiones opcionales o hay movimientos sin moneda conocida | `provisional` con su motivo |
| Mes de alta (`coverage_onboarding`) o cambio material de cuentas (`coverage_account_change`) | `provisional`: el nivel es válido, la trayectoria hay que leerla con cautela |
| Todo lo anterior en orden | `scored` |

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
