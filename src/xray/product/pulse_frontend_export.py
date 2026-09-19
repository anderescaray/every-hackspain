"""Compatibility import for the canonical Pulse web exporter.

The source of truth is :mod:`xray.product.frontend_export`; keeping this path
allows explicit Pulse invocations without maintaining a second score adapter.
"""
from xray.product.frontend_export import (  # noqa: F401
    FRONTEND_GENERATED,
    WebEnvelope,
    company_detail,
    group_detail,
    portfolio_export,
    run,
)
