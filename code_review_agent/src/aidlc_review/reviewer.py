"""The review pipeline: static checks -> LLM review per chunk -> grounding filter -> LLM verify -> verdict."""
from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional

from .config import ReviewConfig
from .context import Chunk, build_chunks, constitution_text, llm_rules_text
from .diff_parser import FileDiff, parse_unified_diff
from .llm_client import LLMClient
from .models import (CONFORMANCE_SCHEMA, FINDINGS_SCHEMA, SEVERITY_ORDER, VALID_SEVERITIES, VERIFY_SCHEMA,
                     Finding, ReviewResult)
from .prompts import (CONFORMANCE_SYSTEM, CONFORMANCE_USER, LENS_FOCUS, REVIEW_SYSTEM, REVIEW_USER,
                      VERIFY_SYSTEM, VERIFY_USER)
from .spec_trace import trace
from .static_checks import run_static_checks, run_structural_checks

try:  # MLflow tracing is optional so unit tests run anywhere
    import mlflow

    def _trace(name):
        return mlflow.trace(name=name)
except Exception:  # noqa: BLE001
    def _trace(name):
        def deco(fn):
            return fn
        return deco


def _norm(s: str) -> str:
    return " ".join((s or "").split())


class CodeReviewer:
    def __init__(self, cfg: ReviewConfig, llm: Optional[LLMClient]):
        self.cfg = cfg
        self.llm = llm
        self.known_rules = ({r["id"] for r in cfg.rules.get("llm", [])}
                            | {"CORRECTNESS", "REQ-MISSING", "REQ-PARTIAL", "REQ-CONTRADICTED"})
        self._tokens_in = 0
        self._tokens_out = 0

    # ------------------------------------------------------------------ public API
    @_trace("aidlc_review")
    def review_diff(self, diff_text: str, pr_id: str | None = None, change_request_id: str | None = None,
                    git_base: str | None = None, git_head: str | None = None) -> ReviewResult:
        t0 = time.time()
        files = parse_unified_diff(diff_text)
        reviewable = [f for f in files if self.cfg.reviewable(f.path)]

        findings = run_static_checks(reviewable, self.cfg) + run_structural_checks(files, self.cfg)

        trace_res = None
        if self.cfg.get("spec_trace", "enabled", default=True):
            trace_res = trace(reviewable, self.cfg)
            findings += trace_res.findings

        dropped, summaries, specs_used = 0, [], set()
        if self.llm is not None:
            constitution = constitution_text(self.cfg)
            lenses = self.cfg.get("llm", "lenses", default=["spec", "constitution", "correctness"])
            for chunk in build_chunks(reviewable, self.cfg, trace_res):
                if chunk.spec_path:
                    specs_used.add(chunk.spec_path)
                proposed = []
                for lens in lenses:
                    got, summary = self._review_chunk(chunk, constitution, lens)
                    proposed += got
                    if summary:
                        summaries.append(summary)
                proposed += self._conformance(chunk)
                grounded, n_ungrounded = self._ground(proposed, chunk.files)
                grounded = self._merge_duplicates(grounded)
                verified, n_rejected = self._verify(grounded, chunk, constitution)
                dropped += n_ungrounded + n_rejected
                findings.extend(verified)

        findings = self._dedupe_and_cap(findings)
        verdict = self._verdict(findings)
        return ReviewResult(
            review_id=str(uuid.uuid4()), verdict=verdict, findings=findings, dropped_findings=dropped,
            files_reviewed=[f.path for f in reviewable], specs_used=sorted(specs_used),
            model_endpoint=self.cfg.get("llm", "endpoint", default=""),
            prompt_version=str(self.cfg.get("prompt_version", default="")),
            input_tokens=self._tokens_in, output_tokens=self._tokens_out,
            duration_seconds=round(time.time() - t0, 2), pr_id=pr_id,
            change_request_id=change_request_id, git_base=git_base, git_head=git_head,
            summary=" ".join(summaries)[:2000],
        )

    # ------------------------------------------------------------------ LLM passes
    @_trace("review_chunk")
    def _review_chunk(self, chunk: Chunk, constitution: str, lens: str = "spec"):
        system = REVIEW_SYSTEM.format(focus=LENS_FOCUS.get(lens, lens), rules=llm_rules_text(self.cfg, lens))
        user = REVIEW_USER.format(constitution=constitution or "(none provided)",
                                  spec_path=chunk.spec_path or "(no spec mapped)",
                                  spec=chunk.spec_text or "(no spec text found)", code=chunk.code_text)
        resp = self.llm.complete_json(
            endpoint=self.cfg.get("llm", "endpoint"), system=system, user=user, schema=FINDINGS_SCHEMA,
            temperature=self.cfg.get("llm", "temperature", default=0.0),
            max_tokens=self.cfg.get("llm", "max_output_tokens", default=4000))
        self._tokens_in += resp.input_tokens
        self._tokens_out += resp.output_tokens
        out = []
        for f in resp.data.get("findings", []) or []:
            try:
                out.append(Finding(
                    rule_id=str(f.get("rule_id", "CORRECTNESS")).upper(),
                    severity=str(f.get("severity", "medium")).lower(),
                    file=str(f.get("file", "")), line=f.get("line"),
                    title=str(f.get("title", ""))[:200], explanation=str(f.get("explanation", ""))[:1200],
                    suggested_fix=str(f.get("suggested_fix", ""))[:1200],
                    evidence=str(f.get("evidence", ""))[:400], source="llm", lens=lens))
            except Exception:  # noqa: BLE001
                continue
        return out, str(resp.data.get("summary", ""))

    @_trace("requirement_conformance")
    def _conformance(self, chunk: Chunk) -> List[Finding]:
        """Requirement-by-requirement check for FRs referenced by completed tasks that touch these files."""
        if not chunk.requirements_in_scope:
            return []
        reqs = "\n".join(f"- {r}" for r in chunk.requirements_in_scope)
        user = CONFORMANCE_USER.format(requirements=reqs, spec_path=chunk.spec_path or "(none)",
                                       spec=chunk.spec_text, code=chunk.code_text)
        resp = self.llm.complete_json(
            endpoint=self.cfg.get("llm", "endpoint"), system=CONFORMANCE_SYSTEM, user=user,
            schema=CONFORMANCE_SCHEMA, temperature=0.0,
            max_tokens=self.cfg.get("llm", "max_output_tokens", default=4000))
        self._tokens_in += resp.input_tokens
        self._tokens_out += resp.output_tokens
        status_map = {"partial": ("REQ-PARTIAL", "high"), "missing": ("REQ-MISSING", "high"),
                      "contradicted": ("REQ-CONTRADICTED", "critical")}
        out, first_file = [], chunk.files[0].path
        for r in resp.data.get("requirements", []) or []:
            st = str(r.get("status", "")).lower()
            if st not in status_map or r.get("id") not in chunk.requirements_in_scope:
                continue
            rule, sev = status_map[st]
            f = Finding(rule_id=rule, severity=sev, file=str(r.get("file") or first_file), line=r.get("line"),
                        title=f"{r.get('id')}: requirement {st}", explanation=str(r.get("explanation", ""))[:1200],
                        suggested_fix=f"Implement {r.get('id')} exactly as written in {chunk.spec_path}.",
                        evidence=str(r.get("evidence", ""))[:400], source="llm", lens="conformance",
                        requirement_id=str(r.get("id")))
            if st == "missing" and not f.evidence:
                f.line = None          # nothing to quote: grounded by the task reference instead
            out.append(f)
        return out

    def _merge_duplicates(self, findings: List[Finding]) -> List[Finding]:
        """Several lenses may report the same issue: keep the most severe per (file, line, rule)."""
        best = {}
        for f in findings:
            k = (f.file, f.line, f.rule_id)
            if k not in best or SEVERITY_ORDER[f.severity] > SEVERITY_ORDER[best[k].severity]:
                best[k] = f
        return list(best.values())

    def _ground(self, proposed: List[Finding], files: List[FileDiff]):
        """Deterministic hallucination filter: the finding must cite real added code."""
        by_path: Dict[str, FileDiff] = {f.path: f for f in files}
        kept, dropped = [], 0
        for f in proposed:
            fd = by_path.get(f.file) or next((x for x in files if x.path.endswith(f.file) and f.file), None)
            if fd is None or f.severity not in VALID_SEVERITIES:
                dropped += 1
                continue
            if f.rule_id not in self.known_rules:
                f.rule_id = "CORRECTNESS"
            f.file = fd.path
            if f.rule_id == "REQ-MISSING" and f.line is None:
                kept.append(f)            # traced through tasks.md, not a code line
                continue
            ev = _norm(f.evidence)
            if isinstance(f.line, int) and f.line in fd.added and (not ev or ev in _norm(fd.added[f.line])
                                                                   or _norm(fd.added[f.line]) in ev):
                kept.append(f)
                continue
            # snap to the added line that actually contains the quoted evidence
            match = next((ln for ln, txt in fd.added_lines if ev and (ev in _norm(txt) or _norm(txt) in ev)
                          and len(_norm(txt)) > 3), None)
            if match is not None:
                f.line = match
                kept.append(f)
            else:
                dropped += 1
        return kept, dropped

    @_trace("verify_findings")
    def _verify(self, findings: List[Finding], chunk: Chunk, constitution: str):
        if not findings:
            return [], 0
        listing = "\n".join(
            f"[{i}] {f.rule_id} ({f.severity}) {f.file}:{f.line} | evidence: {f.evidence} | {f.title}: {f.explanation}"
            for i, f in enumerate(findings))
        user = VERIFY_USER.format(constitution=constitution or "(none)", spec_path=chunk.spec_path or "(none)",
                                  spec=chunk.spec_text or "(none)", code=chunk.code_text, findings=listing)
        endpoint = self.cfg.get("llm", "verifier_endpoint") or self.cfg.get("llm", "endpoint")
        try:
            resp = self.llm.complete_json(endpoint=endpoint, system=VERIFY_SYSTEM, user=user, schema=VERIFY_SCHEMA,
                                          temperature=0.0, max_tokens=2000)
        except Exception:  # noqa: BLE001  verify failure: keep findings, marked unverified
            return findings, 0
        self._tokens_in += resp.input_tokens
        self._tokens_out += resp.output_tokens
        decisions = {d.get("index"): d for d in resp.data.get("decisions", []) if isinstance(d, dict)}
        kept, rejected = [], 0
        for i, f in enumerate(findings):
            d = decisions.get(i)
            if d is None:                  # verifier silent: keep but unverified
                kept.append(f)
                continue
            conf = int(d.get("confidence", 100) or 0)
            if d.get("keep") and conf >= self.cfg.get("verify", "min_confidence", default=80):
                f.confidence = conf
                sev = str(d.get("severity", f.severity)).lower()
                f.severity = sev if sev in VALID_SEVERITIES else f.severity
                f.verified = True
                kept.append(f)
            else:
                rejected += 1
        return kept, rejected

    # ------------------------------------------------------------------ merge + verdict
    def _dedupe_and_cap(self, findings: List[Finding]) -> List[Finding]:
        priority = {"static": 0, "structural": 1, "llm": 2}
        findings.sort(key=lambda f: (priority.get(f.source, 3), -SEVERITY_ORDER.get(f.severity, 0)))
        seen, out, per_file = set(), [], {}
        cap = self.cfg.get("limits", "max_findings_per_file", default=15)
        for f in findings:
            k = (f.file, f.line, f.rule_id)
            if k in seen:
                continue
            seen.add(k)
            per_file[f.file] = per_file.get(f.file, 0) + 1
            if per_file[f.file] > cap:
                continue
            out.append(f)
        out.sort(key=lambda f: (-SEVERITY_ORDER.get(f.severity, 0), f.file, f.line or 0))
        return out

    def _verdict(self, findings: List[Finding]) -> str:
        block = set(self.cfg.get("verdict", "block_on_severity", default=["critical"]))
        fix = set(self.cfg.get("verdict", "fix_on_severity", default=["high", "medium"]))
        counted = [f for f in findings if f.verified or f.source != "llm"]
        if any(f.severity in block for f in counted):
            return "block"
        if any(f.severity in fix for f in findings):
            return "fix"
        return "pass"


def result_json(result: ReviewResult) -> str:
    return json.dumps(result.to_dict(), indent=2)
