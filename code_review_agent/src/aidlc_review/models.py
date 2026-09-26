"""Data structures for the AI-DLC code review agent."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
VALID_SEVERITIES = set(SEVERITY_ORDER)


@dataclass
class Finding:
    rule_id: str
    severity: str
    file: str
    line: Optional[int]
    title: str
    explanation: str
    suggested_fix: str
    evidence: str = ""          # the exact changed code the finding is about
    source: str = "llm"         # "static" | "structural" | "llm"
    verified: bool = False      # passed the grounding + verify steps
    confidence: int = 100       # 0-100 from the verify pass (static checks are 100)
    lens: str = ""              # which review pass produced it
    requirement_id: str = ""    # FR-### when the finding is about a spec requirement

    def key(self) -> tuple:
        return (self.rule_id, self.file, self.line)


@dataclass
class ReviewResult:
    review_id: str
    verdict: str                               # pass | fix | block
    findings: List[Finding] = field(default_factory=list)
    dropped_findings: int = 0                  # LLM findings removed by grounding / verify
    files_reviewed: List[str] = field(default_factory=list)
    specs_used: List[str] = field(default_factory=list)
    model_endpoint: str = ""
    prompt_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    pr_id: Optional[str] = None
    change_request_id: Optional[str] = None
    git_base: Optional[str] = None
    git_head: Optional[str] = None
    summary: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# JSON schema the LLM must return (used as structured output when the endpoint supports it).
FINDINGS_SCHEMA = {
    "name": "code_review_findings",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings", "summary"],
        "properties": {
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rule_id", "severity", "file", "line", "title",
                                 "explanation", "suggested_fix", "evidence"],
                    "properties": {
                        "rule_id": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "title": {"type": "string"},
                        "explanation": {"type": "string"},
                        "suggested_fix": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            },
        },
    },
}

VERIFY_SCHEMA = {
    "name": "verify_findings",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["decisions"],
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["index", "keep", "confidence", "severity", "reason"],
                    "properties": {
                        "index": {"type": "integer"},
                        "keep": {"type": "boolean"},
                        "confidence": {"type": "integer"},
                        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                        "reason": {"type": "string"},
                    },
                },
            }
        },
    },
}


CONFORMANCE_SCHEMA = {
    "name": "requirement_conformance",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["requirements"],
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "status", "file", "line", "evidence", "explanation"],
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"type": "string",
                                   "enum": ["implemented", "partial", "missing", "contradicted", "not_applicable"]},
                        "file": {"type": ["string", "null"]},
                        "line": {"type": ["integer", "null"]},
                        "evidence": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                },
            }
        },
    },
}
