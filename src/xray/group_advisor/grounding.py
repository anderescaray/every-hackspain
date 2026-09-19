"""Validador de anclaje (spec §9.3): todo número e identificador del texto debe existir en el JSON.

Se aplica tanto a las plantillas deterministas como a cualquier paráfrasis de un LLM. Un número
del texto está anclado si coincide con un valor numérico del documento tras redondear ambos a un
decimal, si (mostrado como porcentaje) coincide con `valor / 100` a tres decimales, o si coincide
con `fracción * 100` de algún valor del documento en [-1, 1]. Los ids `COMP_xxxx` / `GROUP_xxxx` y
los nombres de palanca del texto deben aparecer como cadenas en el documento.
"""
import math
import re
from dataclasses import dataclass, field

LEVER_IDS = ("D1", "P", "cut_outflow", "raise_inflow", "debt_service_cut", "ap_on_time", "ar_faster")

# Números de las frases fijas que no dependen del documento y se aceptan siempre:
#   1 y 6   -> los k reportados («k=1» próximo cierre, «k=6» régimen, «6 meses») y el «por 1 %» de los rankings;
#   10000   -> normalización fija de la eficiencia y del ranking por caja («por cada 10.000»);
#   100     -> escala 0–100 del nivel y de G, y el «100 %» de una fracción completa;
#   40 y 70 -> fronteras de tramo (`tramo_bounds`) citadas al hablar de cambio de tramo.
# Suelen estar en `config`, pero la sensibilidad no serializa la configuración y el texto no debe
# depender de ello.
ALWAYS_ALLOWED = frozenset({1, 6, 10000, 100, 40, 70})

_ISO_DATE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?")
_NUMBER = re.compile(r"(?<![\w.,])([-−])?(\d{1,3}(?:\.\d{3})+|\d+)(,\d+)?(\s?%)?(?!\w)")
_ENTITY_ID = re.compile(r"\b(?:COMP|GROUP)_\d+\b")
_LEVER_ID = re.compile(r"(?<![\w])(" + "|".join(re.escape(l) for l in LEVER_IDS) + r")(?![\w])")


@dataclass
class GroundingResult:
    ok: bool
    unmatched_numbers: list = field(default_factory=list)
    unmatched_ids: list = field(default_factory=list)


def _tokens(text):
    """Pares (valor, es_porcentaje) de los números del texto en formato castellano; ignora fechas ISO."""
    out = []
    for match in _NUMBER.finditer(_ISO_DATE.sub(" ", text)):
        sign, integer, decimal, pct = match.groups()
        value = float(integer.replace(".", "") + (decimal.replace(",", ".") if decimal else ""))
        out.append((-value if sign else value, pct is not None))
    return out


def extract_numbers(text):
    """Números del texto («1.234,5», «42 %», «−0,80», «7.020 EUR», «0,078», enteros) como floats."""
    return [value for value, _ in _tokens(text)]


def collect_numbers(doc):
    """Valores numéricos finitos (int/float, no bool) de un dict/list anidado."""
    found = set()

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            if math.isfinite(node):
                found.add(float(node))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(doc)
    return found


def collect_ids(doc):
    """Ids `COMP_/GROUP_` contenidos en cualquier cadena del documento más los nombres de palanca presentes."""
    found = set()

    def walk(node):
        if isinstance(node, str):
            found.update(_ENTITY_ID.findall(node))
            if node in LEVER_IDS:
                found.add(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(doc)
    return found


def _close(a, b):
    return round(a, 1) == round(b, 1) or abs(a - b) <= 0.05


def _grounded(value, is_pct, numbers, fractions):
    if value in ALWAYS_ALLOWED:
        return True
    if any(_close(value, n) for n in numbers) or any(_close(value, f) for f in fractions):
        return True
    return is_pct and any(round(value / 100, 3) == round(n, 3) for n in numbers)


def validate_grounding(text, doc):
    """Comprueba que cada número e id del texto existe en `doc`; devuelve `GroundingResult`."""
    numbers = collect_numbers(doc)
    fractions = {n * 100 for n in numbers if abs(n) <= 1}
    ids = collect_ids(doc)
    unmatched_numbers, unmatched_ids = [], []
    for value, is_pct in _tokens(text):
        if not _grounded(value, is_pct, numbers, fractions) and value not in unmatched_numbers:
            unmatched_numbers.append(value)
    for token in _ENTITY_ID.findall(text) + _LEVER_ID.findall(text):
        if token not in ids and token not in unmatched_ids:
            unmatched_ids.append(token)
    return GroundingResult(ok=not unmatched_numbers and not unmatched_ids,
                           unmatched_numbers=unmatched_numbers, unmatched_ids=unmatched_ids)
