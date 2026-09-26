"""Spec Kit traceability: tie every changed file to tasks (T###), user stories (US#) and requirements (FR-###).

Reads the standard Spec Kit artifacts in each feature folder (specs/NNN-name/):
  spec.md   -> FR-###, SC-###, user stories with Given/When/Then scenarios, NEEDS CLARIFICATION markers
  tasks.md  -> "- [ ] T012 [P] [US1] Description with src/path/file.py" lines (FR-### refs optional)
  plan.md   -> passed through as context

Nothing is inferred by keyword: scope comes from the task lines that name the changed files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import ReviewConfig, path_matches
from .diff_parser import FileDiff
from .models import Finding

FR_RX = re.compile(r"\b(FR-\d{3,})\b")
SC_RX = re.compile(r"\b(SC-\d{3,})\b")
TASK_RX = re.compile(r"^\s*-\s*\[(?P<done>[ xX])\]\s*(?P<id>T\d{3,})\b(?P<rest>.*)$")
STORY_TAG_RX = re.compile(r"\[(US\d+)\]")
PATH_RX = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.\w+|[\w.-]+\.(?:py|sql|yml|yaml|ipynb|md))")
STORY_HEAD_RX = re.compile(r"^#{2,4}\s*User Story\s+(\d+)\b(.*)$", re.I)


@dataclass
class Task:
    id: str
    done: bool
    story: Optional[str]
    parallel: bool
    text: str
    paths: List[str]
    fr_refs: List[str]


@dataclass
class Feature:
    folder: str
    spec_md: str = ""
    plan_md: str = ""
    requirements: Dict[str, str] = field(default_factory=dict)       # FR-001 -> text
    success_criteria: Dict[str, str] = field(default_factory=dict)   # SC-001 -> text
    stories: Dict[str, dict] = field(default_factory=dict)           # US1 -> {title, scenarios[]}
    clarifications: List[str] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)

    @property
    def spec_path(self) -> str:
        return f"{self.folder}/spec.md"


# ------------------------------------------------------------------ parsing
def parse_spec(md: str, marker: str = "NEEDS CLARIFICATION") -> dict:
    reqs, scs, stories, clar = {}, {}, {}, []
    current_story = None
    for line in md.splitlines():
        s = line.strip()
        m = STORY_HEAD_RX.match(s)
        if m:
            current_story = f"US{m.group(1)}"
            stories[current_story] = {"title": m.group(2).strip(" -:"), "scenarios": []}
            continue
        if s.startswith("#") and not STORY_HEAD_RX.match(s) and current_story and s.lstrip("#").strip().lower() \
                .startswith(("requirements", "success criteria", "edge cases", "functional requirements")):
            current_story = None
        fr = FR_RX.search(s)
        if fr and fr.group(1) not in reqs and (s.startswith("-") or s.startswith("*") or s.startswith(fr.group(1))
                                               or s.startswith("**")):
            reqs[fr.group(1)] = re.sub(r"^[-*\s]*(\*\*)?FR-\d+(\*\*)?[:.\s]*", "", s)
        sc = SC_RX.search(s)
        if sc and sc.group(1) not in scs and (s.startswith("-") or s.startswith("*") or s.startswith("**")):
            scs[sc.group(1)] = re.sub(r"^[-*\s]*(\*\*)?SC-\d+(\*\*)?[:.\s]*", "", s)
        if current_story and re.search(r"\bGiven\b", s) and re.search(r"\bThen\b", s):
            stories[current_story]["scenarios"].append(re.sub(r"^\d+\.\s*", "", s))
        if marker.lower() in s.lower():
            clar.append(s)
    return {"requirements": reqs, "success_criteria": scs, "stories": stories, "clarifications": clar}


def parse_tasks(md: str) -> List[Task]:
    tasks = []
    for line in md.splitlines():
        m = TASK_RX.match(line)
        if not m:
            continue
        rest = m.group("rest")
        story = STORY_TAG_RX.search(rest)
        paths = [p.strip("`'\".,;:()") for p in PATH_RX.findall(rest)]
        tasks.append(Task(id=m.group("id"), done=m.group("done").lower() == "x",
                          story=story.group(1) if story else None, parallel="[P]" in rest,
                          text=rest.strip(), paths=[p for p in paths if p], fr_refs=FR_RX.findall(rest)))
    return tasks


def load_features(cfg: ReviewConfig) -> List[Feature]:
    root = cfg.repo_root / cfg.get("spec_trace", "features_root", default="specs")
    marker = cfg.get("spec_trace", "clarification_marker", default="NEEDS CLARIFICATION")
    feats = []
    if not root.is_dir():
        return feats
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        spec, tasks, plan = d / "spec.md", d / "tasks.md", d / "plan.md"
        if not spec.exists() and not tasks.exists():
            continue
        f = Feature(folder=str(d.relative_to(cfg.repo_root)).replace("\\", "/"))
        if spec.exists():
            f.spec_md = spec.read_text(encoding="utf-8")
            parsed = parse_spec(f.spec_md, marker)
            f.requirements, f.success_criteria = parsed["requirements"], parsed["success_criteria"]
            f.stories, f.clarifications = parsed["stories"], parsed["clarifications"]
        if plan.exists():
            f.plan_md = plan.read_text(encoding="utf-8")
        if tasks.exists():
            f.tasks = parse_tasks(tasks.read_text(encoding="utf-8"))
        feats.append(f)
    return feats


# ------------------------------------------------------------------ tracing
def _task_touches(task: Task, path: str) -> bool:
    for p in task.paths:
        if "*" in p and path_matches(path, [p]):
            return True
        if path == p or path.endswith("/" + p) or p.endswith("/" + path):
            return True
    return False


@dataclass
class TraceResult:
    file_tasks: Dict[str, List[tuple]] = field(default_factory=dict)   # path -> [(feature, task)]
    features: Dict[str, Feature] = field(default_factory=dict)         # folder -> feature touched
    findings: List[Finding] = field(default_factory=list)

    def tasks_for(self, path: str) -> List[tuple]:
        return self.file_tasks.get(path, [])


def trace(files: List[FileDiff], cfg: ReviewConfig, features: Optional[List[Feature]] = None) -> TraceResult:
    features = load_features(cfg) if features is None else features
    res = TraceResult()
    if not features:              # repo has no Spec Kit features yet: nothing to trace against
        return res
    required = cfg.get("spec_trace", "require_task_for", default=["src/**"])
    for fd in files:
        hits = [(f, t) for f in features for t in f.tasks if _task_touches(t, fd.path)]
        res.file_tasks[fd.path] = hits
        for f, _ in hits:
            res.features[f.folder] = f
        if not hits and path_matches(fd.path, required):
            res.findings.append(Finding(
                rule_id="UNTRACED-CHANGE", severity="high", file=fd.path, line=None,
                title="Code change not traced to any Spec Kit task",
                explanation="No task in any specs/*/tasks.md names this file. Every code change must come from an "
                            "approved spec task; untraced code is an assumption.",
                suggested_fix="Add or update the spec and tasks.md (approved by the tech lead), or remove the change.",
                source="structural", verified=True))

    for f in res.features.values():
        if f.clarifications:
            res.findings.append(Finding(
                rule_id="OPEN-CLARIFICATION", severity="critical", file=f.spec_path, line=None,
                title="Spec still has unresolved NEEDS CLARIFICATION items",
                explanation="Code was written against a spec with open questions: " + " | ".join(f.clarifications[:3]),
                suggested_fix="Resolve with /speckit.clarify, get tech-lead approval of the spec, then implement.",
                source="structural", verified=True))
        for t in f.tasks:
            if not t.done:
                continue
            for p in t.paths:
                if "*" in p or not p.startswith(("stages/", "common/", "pipelines/", "tools/")):
                    continue
                if not (cfg.repo_root / p).exists() and p not in [x.path for x in files]:
                    res.findings.append(Finding(
                        rule_id="TASK-FILE-MISSING", severity="medium", file=f"{f.folder}/tasks.md", line=None,
                        title=f"{t.id} is marked done but {p} does not exist",
                        explanation=f"Task text: {t.text[:200]}",
                        suggested_fix="Implement the file or untick the task.", source="structural", verified=True))
    return res


def in_scope_requirements(res: TraceResult, files: List[FileDiff]) -> Dict[str, List[str]]:
    """FR IDs referenced by DONE tasks that touch the changed files: these must be fully implemented."""
    scope: Dict[str, List[str]] = {}
    for fd in files:
        for f, t in res.tasks_for(fd.path):
            if t.done and t.fr_refs:
                scope.setdefault(f.folder, [])
                for fr in t.fr_refs:
                    if fr not in scope[f.folder]:
                        scope[f.folder].append(fr)
    return scope


def spec_context(feature: Feature, files: List[FileDiff], res: TraceResult, max_chars: int) -> str:
    """Exact, structured spec context: every FR and SC, touched stories' scenarios, touched task lines, plan excerpt."""
    touched_tasks = [t for fd in files for (f, t) in res.tasks_for(fd.path) if f.folder == feature.folder]
    stories = sorted({t.story for t in touched_tasks if t.story})
    parts = [f"Feature folder: {feature.folder}"]
    if feature.requirements:
        parts.append("### Functional requirements (all)\n" +
                     "\n".join(f"- {k}: {v}" for k, v in feature.requirements.items()))
    if feature.success_criteria:
        parts.append("### Success criteria\n" + "\n".join(f"- {k}: {v}" for k, v in feature.success_criteria.items()))
    for s in stories:
        st = feature.stories.get(s)
        if st:
            parts.append(f"### {s}: {st['title']}\n" + "\n".join(f"- {sc}" for sc in st["scenarios"]))
    if touched_tasks:
        seen = set()
        lines = []
        for t in touched_tasks:
            if t.id in seen:
                continue
            seen.add(t.id)
            lines.append(f"- [{'X' if t.done else ' '}] {t.id} {t.text}")
        parts.append("### Tasks that touch these files\n" + "\n".join(lines))
    if feature.clarifications:
        parts.append("### OPEN CLARIFICATIONS\n" + "\n".join(feature.clarifications))
    text = "\n\n".join(parts)
    if not feature.requirements and feature.spec_md:     # not a Spec Kit-shaped spec: pass the raw spec
        text += "\n\n### Spec (raw)\n" + feature.spec_md
    if feature.plan_md and len(text) < max_chars:
        text += "\n\n### Plan excerpt\n" + feature.plan_md[: max_chars - len(text)]
    return text[:max_chars]


def feature_for_file(res: TraceResult, path: str) -> Optional[Feature]:
    hits = res.tasks_for(path)
    return hits[0][0] if hits else None

