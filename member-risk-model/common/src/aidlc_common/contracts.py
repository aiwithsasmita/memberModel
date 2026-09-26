"""Data contracts between stages: declared tables, keys and required columns."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .config import load_config


@dataclass
class TableContract:
    name: str
    table: str
    keys: List[str]
    required_columns: List[str] = field(default_factory=list)


@dataclass
class Contract:
    stage: str
    inputs: Dict[str, TableContract]
    outputs: Dict[str, TableContract]

    def check_columns(self, name: str, columns: List[str], side: str = "outputs") -> List[str]:
        """Return a list of problems (empty = OK) for a table's columns against the contract."""
        tc = getattr(self, side)[name]
        missing = [c for c in tc.keys + tc.required_columns if c not in columns]
        return [f"{name}: missing column {c}" for c in missing]


def _tables(section) -> Dict[str, TableContract]:
    out = {}
    for name, spec in (section or {}).items():
        out[name] = TableContract(name=name, table=spec.get("table", ""), keys=spec.get("keys", []),
                                  required_columns=spec.get("required_columns", []))
    return out


def load_contract(path: str | Path, variables=None) -> Contract:
    c = load_config(path, variables)
    return Contract(stage=c.get("stage", ""), inputs=_tables(c.get("inputs")), outputs=_tables(c.get("outputs")))


def check_unique_keys(df, keys: List[str]) -> int:
    """Spark: number of duplicate key rows (0 = OK)."""
    return df.groupBy(*keys).count().filter("count > 1").count()
