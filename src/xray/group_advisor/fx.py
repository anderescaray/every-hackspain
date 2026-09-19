"""Tabla FX fija del advisor: unidades de moneda por 1 EUR, solo para importes (spec §7).

`default_fx_table()` devuelve la tabla del proyecto `xray.fx.FX_TO_EUR` (decisión D32: BCE
2026-09-18 más open.er-api.com para las monedas sin referencia BCE; paridades fijas para
BAM y XOF) cuando `xray.fx` se importa y expone `FX_TO_EUR`, `FX_SOURCE` y `FX_ASOF`;
`FX_SOURCE` y `FX_ASOF` de este módulo reflejan entonces las suyas. Si no está disponible,
cae a la tabla de trabajo `APPROXIMATE_FX_TO_EUR` de WP1 (valores aproximados de orden de
magnitud de 2025 para las 39 monedas de `companies.currency` ∪ `banking_products.currency`
del dataset limpio) con `FX_SOURCE = "approximate"`.

Como el panel de features D32 es 100 % EUR (todas las cuentas se convierten en features con
`xray.fx`), la tabla no afecta hoy a ningún importe del advisor: solo importaría si volvieran
filiales declaradas en otras monedas (acciones cruzadas con supuesto `fx_fixed_rate`).

Convención: `fx(x, c_from → c_to) = x / rate[c_from] · rate[c_to]`. Nunca se usa
`transactions.exchange_rate` (ambiguo, decisiones D07).
"""

APPROXIMATE_FX_SOURCE = "approximate"
APPROXIMATE_FX_ASOF = "2026-09-01"

APPROXIMATE_FX_TO_EUR = {
    "EUR": 1.0,
    "USD": 1.10, "GBP": 0.85, "CHF": 0.94, "JPY": 165.0,
    "AUD": 1.70, "CAD": 1.52, "NZD": 1.85, "SGD": 1.45, "HKD": 8.58,
    "SEK": 11.2, "NOK": 11.6, "DKK": 7.46, "PLN": 4.28, "CZK": 24.8, "HUF": 400.0, "RON": 5.0,
    "BAM": 1.95583, "TRY": 40.0, "RUB": 95.0, "ILS": 4.0, "AED": 4.04,
    "INR": 94.0, "MYR": 4.8, "THB": 37.0, "PHP": 62.0, "VND": 28500.0,
    "MXN": 20.5, "BRL": 6.2, "ARS": 1300.0, "CLP": 1030.0, "COP": 4500.0, "PEN": 4.0,
    "AOA": 1000.0, "GHS": 12.0, "NAD": 19.5, "ZAR": 19.5, "XOF": 655.957, "MZN": 70.0,
}

try:
    from xray import fx as _project_fx

    DEFAULT_FX_TO_EUR = {str(k): float(v) for k, v in _project_fx.FX_TO_EUR.items()}
    FX_SOURCE = str(_project_fx.FX_SOURCE)
    FX_ASOF = str(_project_fx.FX_ASOF)
except (ImportError, AttributeError):
    DEFAULT_FX_TO_EUR = dict(APPROXIMATE_FX_TO_EUR)
    FX_SOURCE = APPROXIMATE_FX_SOURCE
    FX_ASOF = APPROXIMATE_FX_ASOF


class MissingFXRateError(ValueError):
    """Moneda sin tipo en la tabla FX: las acciones cruzadas con ella son infactibles (`fx_rate_unavailable`)."""

    def __init__(self, currency, message=None):
        self.currency = currency
        super().__init__(message or f"Moneda sin tipo de cambio en la tabla FX: {currency!r}")


def default_fx_table():
    """Copia de la tabla vigente (unidades por 1 EUR): la de `xray.fx` si existe, si no la aproximada."""
    return dict(DEFAULT_FX_TO_EUR)


def convert(amount, from_ccy, to_ccy, table):
    """Convierte `amount` de `from_ccy` a `to_ccy`; devuelve `(importe_convertido, tipo_aplicado)`.

    El tipo aplicado son unidades de `to_ccy` por unidad de `from_ccy`. Misma moneda →
    identidad sin consultar la tabla. Moneda ausente o tabla `None` → `MissingFXRateError`.
    """
    if from_ccy == to_ccy:
        return amount, 1.0
    if table is None:
        raise MissingFXRateError(from_ccy, f"Sin tabla FX: no se puede convertir {from_ccy} → {to_ccy}")
    for currency in (from_ccy, to_ccy):
        if currency not in table:
            raise MissingFXRateError(currency)
    rate = table[to_ccy] / table[from_ccy]
    return amount * rate, rate
