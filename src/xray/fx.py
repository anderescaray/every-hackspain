"""Tipos de cambio fijos a EUR (decisión D32): una sola tasa por moneda para toda la ventana.

**Aproximación deliberada.** Todos los importes se pasan a EUR con el mismo tipo en los 24
meses, sin variación diaria. Es suficiente para comparar órdenes de magnitud y sumar
monedas, no para contabilidad. Mejora futura: tabla diaria por moneda (BCE histórico
u otra fuente) aplicada según la fecha de cada movimiento o factura.

Convención: unidades de moneda por 1 EUR, así que `importe_eur = importe / FX_TO_EUR[moneda]`.

Fuentes, consultadas el 2026-09-19:
- BCE, tipos de referencia del 2026-09-18 (eurofxref-daily.xml) para las 29 monedas que publica.
- open.er-api.com (actualización del 2026-09-19 00:02 UTC) para las que no publica el BCE:
  AED, AOA, ARS, CLP, COP, GHS, MAD, MZN, PEN, RUB, SAR, VND. BAM y XOF usan su paridad
  oficial fija con el euro; NAD la de er-api (paridad 1:1 con ZAR).

No se usa `transactions.exchange_rate`: su mediana coincide con cruces reales frente al
EUR en muchas monedas (DKK 7,47), pero en otras parece ir contra USD (HKD 7,83) o está
incompleta, y no cubre todas las monedas.
"""

import numpy as np
import pandas as pd

REPORTING_CURRENCY = "EUR"
FX_ASOF = "2026-09-18"
FX_SOURCE = "BCE 2026-09-18 + open.er-api.com 2026-09-19 (monedas sin referencia BCE)"

FX_TO_EUR = {
    "EUR": 1.0,
    # BCE, referencia 2026-09-18
    "USD": 1.1460, "JPY": 180.94, "CZK": 24.339, "DKK": 7.4754, "GBP": 0.85880,
    "HUF": 364.28, "PLN": 4.3635, "RON": 5.2647, "SEK": 11.2915, "CHF": 0.9462,
    "ISK": 139.40, "NOK": 10.8095, "TRY": 55.9077, "AUD": 1.6095, "BRL": 5.8857,
    "CAD": 1.6056, "CNY": 7.6755, "HKD": 8.9903, "IDR": 20424.81, "ILS": 3.4812,
    "INR": 109.8755, "KRW": 1590.76, "MXN": 19.6855, "MYR": 4.6763, "NZD": 2.0068,
    "PHP": 71.972, "SGD": 1.4651, "THB": 38.225, "ZAR": 18.6482,
    # open.er-api.com, 2026-09-19
    "AED": 4.215683, "AOA": 1098.243022, "ARS": 1736.015823, "CLP": 1101.636668,
    "COP": 3595.146407, "GHS": 13.248277, "MAD": 10.905906, "MZN": 73.243578,
    "PEN": 3.859993, "RUB": 96.911503, "SAR": 4.304646, "VND": 29874.47904,
    "NAD": 18.674043,
    # paridad oficial fija con el euro
    "BAM": 1.95583, "XOF": 655.957,
}


def to_eur(amount, currency):
    """Convierte importes a EUR con el tipo fijo de su moneda.

    `amount` y `currency` son escalares o Series alineadas. Una moneda nula o ausente de la
    tabla devuelve NaN: nunca se asume que ya estaba en EUR.
    """
    if isinstance(currency, pd.Series):
        rate = currency.map(FX_TO_EUR).astype(float)
        return amount / rate
    rate = FX_TO_EUR.get(currency, np.nan)
    return amount / rate
