"""Registro de lo que hace cada regla de limpieza."""
from dataclasses import asdict, dataclass, field

import pandas as pd

ACTIONS = ("drop_rows", "drop_column", "set_null", "normalize", "flag", "annotate")


@dataclass
class Entry:
    table: str
    rule: str          # ID de la regla (ver docs/decisiones.md)
    action: str        # una de ACTIONS
    rows: int          # filas afectadas (0 en drop_column)
    detail: str


@dataclass
class CleaningLog:
    entries: list[Entry] = field(default_factory=list)

    def add(self, table: str, rule: str, action: str, rows: int, detail: str) -> None:
        if action not in ACTIONS:
            raise ValueError(f"Acción desconocida: {action}")
        self.entries.append(Entry(table, rule, action, int(rows), detail))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(e) for e in self.entries], columns=list(Entry.__dataclass_fields__))
