"""Marcas de calidad de `balances` (D38). Solo marcan: el saldo original se conserva."""
import pandas as pd

from xray.fx import to_eur

SENTINEL_MIN_EUR = 1e8        # D38: solo saldos de al menos 100 M€ equivalentes
SENTINEL_ACTIVITY_RATIO = 1000  # ... que superan en 1.000× el mayor movimiento de su propia cuenta
TECHNICAL_PLACEHOLDER = 999_999_999.0  # importe de relleno de ajustes técnicos del banco


def sentinel_balances(balances: pd.DataFrame, products: pd.DataFrame, transactions: pd.DataFrame) -> pd.Series:
    """True para saldos de cuenta bancaria imposibles de explicar con la actividad de la propia cuenta.

    Un saldo es centinela si pertenece a una cuenta bancaria (no a deuda), vale al menos 100 M€ en valor
    absoluto y, o bien supera en más de 1.000 veces el mayor movimiento de esa cuenta, o bien la cuenta
    tiene ajustes técnicos de 999.999.999. Sirven de ejemplo +99.999.990.000 € en una cuenta con
    movimientos de pocos euros, o −999.999.999 € exactos.
    """
    info = products.set_index("product_id")
    bank = balances.product_id.map(info.kind).eq("banking")
    eur = to_eur(pd.to_numeric(balances.balance), balances.product_id.map(info.currency)).abs()
    moves = transactions.groupby("product_id").amount.apply(lambda s: s.abs().max())
    largest = balances.product_id.map(moves).fillna(0.)
    technical = balances.product_id.isin(
        transactions.loc[transactions.amount.abs().eq(TECHNICAL_PLACEHOLDER), "product_id"])
    unexplained = pd.to_numeric(balances.balance).abs() > SENTINEL_ACTIVITY_RATIO * largest
    return (bank & eur.ge(SENTINEL_MIN_EUR) & (unexplained | technical)).fillna(False).astype(bool)
