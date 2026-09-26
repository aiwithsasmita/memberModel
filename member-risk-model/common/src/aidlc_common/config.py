"""Load stage config with ${variable} substitution from bundle variables / environment."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute(node: Any, variables: Mapping[str, str]) -> Any:
    if isinstance(node, str):
        def repl(m):
            key = m.group(1)
            if key in variables:
                return str(variables[key])
            if key in os.environ:
                return os.environ[key]
            raise KeyError(f"Config variable ${{{key}}} is not set (bundle variable or environment)")
        return _VAR.sub(repl, node)
    if isinstance(node, list):
        return [_substitute(x, variables) for x in node]
    if isinstance(node, dict):
        return {k: _substitute(v, variables) for k, v in node.items()}
    return node


def load_config(path: str | Path, variables: Mapping[str, str] | None = None) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _substitute(raw, variables or {})


def load_stage(stage_dir: str | Path, variables: Mapping[str, str] | None = None) -> dict:
    """Return {'stage': stage.yaml, '<registry name>': registry, 'contract': contract.yaml} for a stage folder."""
    stage_dir = Path(stage_dir)
    out = {"stage": load_config(stage_dir / "config" / "stage.yaml", variables)}
    for p in sorted((stage_dir / "config").glob("*.yaml")):
        if p.name != "stage.yaml":
            out[p.stem] = load_config(p, variables)
    out["contract"] = load_config(stage_dir / "contract.yaml", variables)
    return out


def enabled(registry: Mapping[str, Mapping], section: str) -> dict:
    """Entries of a registry section with enabled: true (default true)."""
    return {k: v for k, v in (registry.get(section) or {}).items() if (v or {}).get("enabled", True)}
