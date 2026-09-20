"""Exact factor Shapley and V2 term deltas for small precomputed bundles."""

from __future__ import annotations

from itertools import combinations
from math import factorial


def exact_shapley(shocks, score_of_subset):
    """Exact (not sampled) Shapley over <=5 named shocks, in score points."""
    names = tuple(shock.factor for shock in shocks)
    if len(names) != len(set(names)) or not 1 <= len(names) <= 5:
        raise ValueError("Shapley requiere 1–5 factores distintos")
    n = len(names)
    empty = score_of_subset(frozenset())
    full = score_of_subset(frozenset(names))
    if empty is None or full is None:
        return None
    factors = []
    for name in names:
        others = [other for other in names if other != name]
        contribution = 0.0
        for count in range(n):
            weight = factorial(count) * factorial(n - count - 1) / factorial(n)
            for subset in combinations(others, count):
                absent = frozenset(subset)
                before, after = score_of_subset(absent), score_of_subset(absent | {name})
                if before is None or after is None:
                    return None
                contribution += weight * (after - before)
        factors.append({"factor": name, "points": contribution})
    residual = (full - empty) - sum(item["points"] for item in factors)
    return {"method": "exact_shapley", "factors": factors, "residual": residual}


def score_term_deltas(before, after):
    """Both are V2 `component -> final_contribution` mappings, including clipping."""
    return [{"component": key, "points": after.get(key, 0.0) - before.get(key, 0.0)}
            for key in sorted(set(before) | set(after))]
