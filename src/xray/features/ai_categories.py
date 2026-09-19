"""Categorías AI (TypeSafe Jev) para movimientos `uncategorized` — decisión D31.

El artefacto `template_categories.parquet` se generó UNA vez con `scripts/experimental/jev_categorize_all.py`
y es estático: aquí no se llama a ninguna API. Se aplica solo a filas cuya categoría bancaria es
`uncategorized`; la categoría del banco nunca se sobreescribe. La columna original se conserva
como `category_bank` y `category_source` indica bank / ai / none.
"""
import numpy as np
import pandas as pd

# Bloque Jev -> categoría equivalente del banco (misma semántica que FE03). `None` = no se usa.
BLOCK_TO_CATEGORY = {
    "operating_inflow": "collection", "supplier_payment": "payment", "utility": "utility",
    "salary": "salary", "social_security": "social_security", "tax": "tax", "bank_fee": "fee",
    "internal_transfer": "ai_nonoperating", "cash": "ai_nonoperating", "bank_adjustment": "ai_nonoperating",
    "interest_or_debt": None,  # acuerdo débil con el banco en el control; no se usa para servicio de deuda
    "unknown": None,
}
NONOPERATING = "ai_nonoperating"


def template(description: pd.Series) -> pd.Series:
    """Normaliza el texto a una plantilla estable (misma función usada al generar el artefacto)."""
    return (
        description.fillna("").str.upper()
        .str.replace(r"COUNTERPARTY_\d+", "CP", regex=True)
        .str.replace(r"\[[A-Z]+\]", "T", regex=True)
        .str.replace(r"\d+", "#", regex=True)
        .str.replace(r"[^A-Z#ÑÇÁÉÍÓÚÀÈÒÜ ]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def load_template_categories(path) -> pd.DataFrame:
    m = pd.read_parquet(path, columns=["tpl", "sign", "jev_block", "jev_confidence", "sign_conflict"])
    m = m.loc[m.jev_block.notna() & ~m.sign_conflict, ["tpl", "sign", "jev_block", "jev_confidence"]]
    m["sign"] = m.sign.astype(int)
    return m.drop_duplicates(["tpl", "sign"]).reset_index(drop=True)


def apply_ai_categories(t: pd.DataFrame, mapping: pd.DataFrame, min_confidence: float) -> pd.DataFrame:
    """Rellena `category` de filas `uncategorized` con la categoría AI si supera el umbral.

    Añade `category_bank`, `category_source`, `category_ai_confidence`.
    """
    t = t.copy()
    t["category_bank"] = t.category
    t["category_source"] = np.where(t.category.eq("uncategorized"), "none", "bank")
    t["category_ai_confidence"] = np.nan
    target = t.category.eq("uncategorized")
    if not target.any():
        return t
    keys = pd.DataFrame({"tpl": template(t.loc[target, "description"]),
                         "sign": np.sign(t.loc[target, "amount"]).astype(int)}, index=t.index[target])
    joined = keys.merge(mapping, on=["tpl", "sign"], how="left").set_index(keys.index)
    category = joined.jev_block.map(BLOCK_TO_CATEGORY)
    # Impuesto con signo positivo = devolución fiscal, como en FE03.
    category = category.where(~(category.eq("tax") & joined.sign.gt(0)), "tax_refund")
    accept = category.notna() & joined.jev_confidence.ge(min_confidence)
    idx = accept[accept].index
    t.loc[idx, "category"] = category[idx]
    t.loc[idx, "category_source"] = "ai"
    t.loc[idx, "category_ai_confidence"] = joined.loc[idx, "jev_confidence"]
    return t
