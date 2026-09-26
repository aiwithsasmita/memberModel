"""Parse a unified git diff into files, added lines and hunks with new-file line numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    is_new: bool = False
    is_deleted: bool = False
    added: Dict[int, str] = field(default_factory=dict)   # new-file line number -> text
    hunks: List[str] = field(default_factory=list)        # raw hunk text, with headers

    @property
    def added_lines(self) -> List[Tuple[int, str]]:
        return sorted(self.added.items())

    def hunk_text(self) -> str:
        return "\n".join(self.hunks)


def parse_unified_diff(diff_text: str) -> List[FileDiff]:
    files: List[FileDiff] = []
    current: FileDiff | None = None
    new_line = 0
    hunk_lines: List[str] = []

    def close_hunk():
        nonlocal hunk_lines
        if current is not None and hunk_lines:
            current.hunks.append("\n".join(hunk_lines))
        hunk_lines = []

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            close_hunk()
            parts = raw.split(" b/", 1)
            path = parts[1] if len(parts) == 2 else raw.split()[-1]
            current = FileDiff(path=path)
            files.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.is_new = True
            continue
        if raw.startswith("deleted file mode"):
            current.is_deleted = True
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target.startswith("b/"):
                current.path = target[2:]
            continue
        if raw.startswith("--- ") or raw.startswith("index ") or raw.startswith("similarity") \
                or raw.startswith("rename ") or raw.startswith("Binary files"):
            continue
        m = _HUNK.match(raw)
        if m:
            close_hunk()
            new_line = int(m.group(3))
            hunk_lines.append(raw)
            continue
        if not hunk_lines:
            continue
        hunk_lines.append(raw)
        if raw.startswith("+"):
            current.added[new_line] = raw[1:]
            new_line += 1
        elif raw.startswith("-"):
            pass
        elif raw.startswith("\\"):
            pass
        else:
            new_line += 1
    close_hunk()
    return [f for f in files if not f.is_deleted]


def annotate_hunks(fd: FileDiff) -> str:
    """Render hunks with new-file line numbers so the LLM can cite exact lines."""
    out: List[str] = []
    for hunk in fd.hunks:
        lines = hunk.splitlines()
        m = _HUNK.match(lines[0])
        n = int(m.group(3)) if m else 1
        out.append(lines[0])
        for ln in lines[1:]:
            if ln.startswith("+"):
                out.append(f"{n:>5} + {ln[1:]}")
                n += 1
            elif ln.startswith("-"):
                out.append(f"      - {ln[1:]}")
            elif ln.startswith("\\"):
                continue
            else:
                out.append(f"{n:>5}   {ln[1:] if ln.startswith(' ') else ln}")
                n += 1
    return "\n".join(out)
