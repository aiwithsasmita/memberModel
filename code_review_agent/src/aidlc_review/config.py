"""Config loading and path-glob helpers."""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Iterable

import yaml


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@functools.lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern:
    i, out = 0, ["^"]
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(_glob_regex(p).match(path) for p in patterns)


class ReviewConfig:
    def __init__(self, config_path: str | Path, rules_path: str | Path, repo_root: str | Path = "."):
        self.cfg = load_yaml(config_path)
        self.rules = load_yaml(rules_path)
        self.repo_root = Path(repo_root)
        self._expand_placeholders()

    def _expand_placeholders(self):
        cats = self.cfg.get("forbidden_write_catalogs", []) or ["__none__"]
        cat_alt = "(?:" + "|".join(re.escape(c) for c in cats) + ")"
        for r in self.rules.get("static", []):
            r["pattern"] = r["pattern"].replace("{forbidden_catalogs}", cat_alt)
        protected = self.cfg.get("protected_paths", [])
        for r in self.rules.get("structural", []):
            expanded = []
            for p in r.get("when_changed", []):
                expanded.extend(protected if p == "{protected_paths}" else [p])
            r["when_changed"] = expanded

    # convenience accessors
    def get(self, *keys, default=None):
        node = self.cfg
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def reviewable(self, path: str) -> bool:
        inc = self.get("files", "include", default=["**/*"])
        exc = self.get("files", "exclude", default=[])
        return path_matches(path, inc) and not path_matches(path, exc)

    def spec_for(self, path: str) -> str | None:
        for entry in self.get("spec_map", default=[]) or []:
            if path_matches(path, entry.get("paths", [])):
                return entry.get("spec")
        return None

    def read_repo_file(self, rel: str) -> str | None:
        p = self.repo_root / rel
        try:
            return p.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
            return None
