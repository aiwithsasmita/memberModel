"""Build the review context: governing spec sections, constitution, rules and code around each change."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .config import ReviewConfig
from .diff_parser import FileDiff, annotate_hunks

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


@dataclass
class Chunk:
    files: List[FileDiff]
    spec_path: str | None
    spec_text: str
    code_text: str
    feature_folder: str | None = None
    requirements_in_scope: List[str] = field(default_factory=list)


def _split_sections(md: str) -> List[str]:
    parts = re.split(r"(?m)^(?=#{1,4} )", md)
    return [p for p in parts if p.strip()]


def relevant_spec_text(spec_md: str, files: List[FileDiff], budget: int) -> str:
    """Keep the spec sections that share the most identifiers with the changed code."""
    if len(spec_md) <= budget:
        return spec_md
    tokens = set()
    for fd in files:
        tokens.update(w.lower() for w in _WORD.findall(fd.path))
        for _, t in fd.added_lines:
            tokens.update(w.lower() for w in _WORD.findall(t))
    sections = _split_sections(spec_md)
    scored = []
    for idx, sec in enumerate(sections):
        words = {w.lower() for w in _WORD.findall(sec)}
        score = len(words & tokens) + (5 if idx == 0 else 0)   # always favor the spec's intro
        scored.append((score, idx, sec))
    picked, used = [], 0
    for score, idx, sec in sorted(scored, key=lambda x: (-x[0], x[1])):
        if used + len(sec) > budget:
            continue
        picked.append((idx, sec))
        used += len(sec)
    return "\n".join(sec for _, sec in sorted(picked))


def constitution_text(cfg: ReviewConfig, budget: int = 6000) -> str:
    texts = []
    for p in cfg.get("constitution_paths", default=[]) or []:
        t = cfg.read_repo_file(p)
        if t:
            texts.append(f"--- {p} ---\n{t}")
    joined = "\n\n".join(texts)
    return joined[:budget]


def llm_rules_text(cfg: ReviewConfig, lens: str | None = None) -> str:
    lines = []
    for r in cfg.rules.get("llm", []):
        if lens and lens not in (r.get("lens") or [lens]):
            continue
        lines.append(f"- [{r['id']}] (default severity {r['severity']}) {r['description'].strip()}")
    return "\n".join(lines)


def build_chunks(files: List[FileDiff], cfg: ReviewConfig, trace_res=None) -> List[Chunk]:
    """Group changed files by Spec Kit feature (from tasks.md) or spec_map, then split to fit the call budget."""
    from .spec_trace import feature_for_file, in_scope_requirements, spec_context

    max_chars = cfg.get("limits", "max_chars_per_chunk", default=24000)
    spec_budget = cfg.get("limits", "max_spec_chars", default=8000)
    scope = in_scope_requirements(trace_res, files) if trace_res is not None else {}
    groups: dict = {}
    for fd in files:
        if not cfg.reviewable(fd.path) or not fd.added:
            continue
        feat = feature_for_file(trace_res, fd.path) if trace_res is not None else None
        key = ("feature", feat.folder) if feat else ("map", cfg.spec_for(fd.path))
        groups.setdefault(key, {"feature": feat, "files": []})["files"].append(fd)

    chunks: List[Chunk] = []
    for (kind, ref), g in groups.items():
        batch: List[FileDiff] = []
        size = 0
        for fd in g["files"]:
            rendered = f"### FILE: {fd.path}{' (new file)' if fd.is_new else ''}\n{annotate_hunks(fd)}\n"
            if batch and size + len(rendered) > max_chars:
                chunks.append(_make_chunk(batch, kind, ref, g["feature"], cfg, trace_res, spec_budget, scope))
                batch, size = [], 0
            batch.append(fd)
            size += len(rendered)
        if batch:
            chunks.append(_make_chunk(batch, kind, ref, g["feature"], cfg, trace_res, spec_budget, scope))
    return chunks


def _make_chunk(batch, kind, ref, feature, cfg, trace_res, spec_budget, scope) -> Chunk:
    from .spec_trace import spec_context

    code = "\n".join(
        f"### FILE: {fd.path}{' (new file)' if fd.is_new else ''}\n{annotate_hunks(fd)}" for fd in batch
    )
    if kind == "feature" and feature is not None:
        return Chunk(files=batch, spec_path=feature.spec_path,
                     spec_text=spec_context(feature, batch, trace_res, spec_budget), code_text=code,
                     feature_folder=feature.folder, requirements_in_scope=list(scope.get(feature.folder, [])))
    spec_md = (cfg.read_repo_file(ref) if ref else None) or ""
    spec = relevant_spec_text(spec_md, batch, spec_budget) if spec_md else ""
    return Chunk(files=batch, spec_path=ref, spec_text=spec, code_text=code)
