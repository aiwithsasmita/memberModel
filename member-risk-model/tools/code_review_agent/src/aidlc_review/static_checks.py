"""Deterministic checks ("computational sensors"): regex rules on added lines and PR-level structure."""
from __future__ import annotations

import re
from typing import List

from .config import ReviewConfig, path_matches
from .diff_parser import FileDiff
from .models import Finding


def run_static_checks(files: List[FileDiff], cfg: ReviewConfig) -> List[Finding]:
    findings: List[Finding] = []
    for rule in cfg.rules.get("static", []):
        rx = re.compile(rule["pattern"])
        must = re.compile(rule["file_must_also_contain"]) if rule.get("file_must_also_contain") else None
        for fd in files:
            if not path_matches(fd.path, rule.get("files", ["**/*"])):
                continue
            if must is not None:
                full = cfg.read_repo_file(fd.path)
                haystack = full if full is not None else "\n".join(t for _, t in fd.added_lines)
                if must.search(haystack):
                    continue
            for line_no, text in fd.added_lines:
                if text.lstrip().startswith("#"):
                    continue
                if rx.search(text):
                    findings.append(Finding(
                        rule_id=rule["id"], severity=rule["severity"], file=fd.path, line=line_no,
                        title=rule["title"], explanation=f"Matched rule {rule['id']} on an added line.",
                        suggested_fix=rule.get("fix", ""), evidence=text.strip()[:300],
                        source="static", verified=True,
                    ))
    return findings


def run_structural_checks(files: List[FileDiff], cfg: ReviewConfig) -> List[Finding]:
    findings: List[Finding] = []
    changed = [f.path for f in files]
    for rule in cfg.rules.get("structural", []):
        triggered = [p for p in changed if path_matches(p, rule.get("when_changed", []))]
        if not triggered:
            continue
        satisfied = any(path_matches(p, rule.get("requires_changed", [])) for p in changed)
        if satisfied:
            continue
        findings.append(Finding(
            rule_id=rule["id"], severity=rule["severity"], file=triggered[0], line=None,
            title=rule["title"],
            explanation="Changed: " + ", ".join(triggered[:5]) + ". Required companion change not found in this PR.",
            suggested_fix=rule.get("fix", ""), source="structural", verified=True,
        ))
    return findings
