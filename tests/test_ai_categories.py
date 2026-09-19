import pandas as pd
import pytest

from test_features import build, company, fixture_tables
from test_clean import row
from xray.features import FeatureConfig
from xray.features.ai_categories import apply_ai_categories, template


def mapping(**rows):
    return pd.DataFrame([{"tpl": template(pd.Series([text])).iat[0], "sign": sign, "jev_block": block, "jev_confidence": conf}
                         for text, (sign, block, conf) in rows.items()])


def test_template_is_stable_to_ids_numbers_and_case():
    a = template(pd.Series(["Adeudo recibo COUNTERPARTY_92069 Nº 0049 [NUM]"]))
    b = template(pd.Series(["ADEUDO RECIBO counterparty_00001 nº 7 [REF]"]))
    assert a.iat[0] == b.iat[0] == "ADEUDO RECIBO CP N # T"


def test_only_uncategorized_rows_change_and_threshold_applies():
    t = pd.DataFrame({"amount": [100., -50., -30., 200.],
                      "category": ["uncategorized", "uncategorized", "utility", "uncategorized"],
                      "description": ["PAYOUT STRIPE 1", "SEPA Overboeking Naam: X", "PAYOUT STRIPE 1", "SCF-AJUS.SALDO C., DC: 1"]})
    m = mapping(**{"PAYOUT STRIPE 1": (1, "operating_inflow", 0.95),
                   "SEPA Overboeking Naam: X": (-1, "supplier_payment", 0.55),
                   "SCF-AJUS.SALDO C., DC: 1": (1, "bank_adjustment", 0.9)})
    out = apply_ai_categories(t, m, 0.7)
    assert out.category.tolist() == ["collection", "uncategorized", "utility", "ai_nonoperating"]
    assert out.category_source.tolist() == ["ai", "none", "bank", "ai"]
    assert out.category_bank.tolist() == t.category.tolist()
    assert out.category_ai_confidence.iloc[0] == 0.95 and pd.isna(out.category_ai_confidence.iloc[1])


def test_tax_with_positive_sign_becomes_refund_and_debt_is_ignored():
    t = pd.DataFrame({"amount": [300., -300.], "category": ["uncategorized"] * 2,
                      "description": ["DEVOLUCION IVA", "CUOTA PRESTAMO"]})
    m = mapping(**{"DEVOLUCION IVA": (1, "tax", 0.99), "CUOTA PRESTAMO": (-1, "interest_or_debt", 0.99)})
    out = apply_ai_categories(t, m, 0.7)
    assert out.category.tolist() == ["tax_refund", "uncategorized"]


def test_features_use_ai_categories_when_configured(tmp_path):
    rows = [row(0, date="2025-01-20", amount=5000),   # enero: primer mes, parcial (D33); febrero ya es comparable
            row(1, date="2025-02-01", amount=100),
            row(2, date="2025-02-05", amount=80, category="-", description="PAYOUT STRIPE 1"),
            row(3, date="2025-02-06", amount=-40, category="-", description="SEPA Overboeking Naam: X"),
            row(4, date="2025-02-07", amount=-500, category="-", description="SCF-AJUS.SALDO C., DC: 1"),
            row(5, date="2025-02-08", amount=-10)]
    tables = fixture_tables(rows)
    m = mapping(**{"PAYOUT STRIPE 1": (1, "operating_inflow", 0.95),
                   "SEPA Overboeking Naam: X": (-1, "supplier_payment", 0.9),
                   "SCF-AJUS.SALDO C., DC: 1": (-1, "bank_adjustment", 0.9)}).assign(sign_conflict=False)
    path = tmp_path / "template_categories.parquet"
    m.to_parquet(path, index=False)
    base = company(build(tables)).loc["2025-02-01"]
    ai = company(build_ai(tables, path)).loc["2025-02-01"]
    assert base.tx_uncategorized_amount == 620 and base.tx_ai_categorized_amount == 0
    assert ai.tx_uncategorized_amount == 0 and ai.tx_ai_categorized_amount == 620 and ai.tx_ai_nonoperating_amount == 500
    assert ai.tx_inflow == base.tx_inflow + 80 and ai.tx_outflow == base.tx_outflow + 40
    assert ai.tx_cash_inflow == base.tx_cash_inflow  # el efectivo total no cambia, solo su clasificación


def build_ai(tables, path):
    from xray.features import build_features
    return build_features(tables, FeatureConfig(start_month="2025-01-01", end_month="2025-06-01",
                                                ai_categories_path=str(path), ai_min_confidence=0.7))


def test_invalid_confidence_rejected():
    with pytest.raises(ValueError):
        FeatureConfig(ai_min_confidence=1.5)
