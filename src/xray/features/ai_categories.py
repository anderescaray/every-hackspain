"""Compatibility API for the canonical ledger's static D31 enrichment.

The cache is research evidence generated offline, never a second classifier or
an API call during feature generation. Economic decisions live in xray.ledger.
"""
from xray.ledger.enrichment import (
    BLOCK_TO_CATEGORY,
    NONOPERATING,
    apply_ai_categories,
    load_template_categories,
    template,
)

__all__ = ["BLOCK_TO_CATEGORY", "NONOPERATING", "apply_ai_categories", "load_template_categories", "template"]
