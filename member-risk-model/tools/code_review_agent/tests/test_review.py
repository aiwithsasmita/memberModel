"""Unit tests. Run: pytest -q   (no Databricks or network needed; the LLM is faked)."""
from pathlib import Path

import pytest

from aidlc_review.config import ReviewConfig, path_matches
from aidlc_review.diff_parser import parse_unified_diff
from aidlc_review.llm_client import LLMResponse, _extract_json
from aidlc_review.reviewer import CodeReviewer
from aidlc_review.spec_trace import load_features, parse_spec, parse_tasks, spec_context, trace

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "eval" / "cases"

SPEC_MD = """# Feature Specification: Feature engineering

## User Scenarios & Testing

### User Story 1 - Cost history features (Priority: P1)

Actuaries need 12-month cost history per member at each cutoff.

**Acceptance Scenarios**:

1. **Given** claims paid after the as-of date, **When** cost history is built, **Then** those claims are excluded.
2. **Given** a member with no claims, **When** cost history is built, **Then** cost_12m is 0.

## Requirements

### Functional Requirements

- **FR-001**: System MUST include only claims with paid_date <= feature_asof_date.
- **FR-002**: System MUST sum allowed_amt over the 12 months before cutoff_date into cost_12m.

## Success Criteria

- **SC-001**: Leakage test passes on a 1% sample.
"""

TASKS_MD = """# Tasks: Feature engineering

## Phase 3: User Story 1
- [X] T010 [US1] (FR-001, FR-002) Build cost history in stages/02_feature_engineering/src/plugins/cost_history.py
- [ ] T011 [P] [US1] Leakage test in tests/test_cost_history.py
"""


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "specs" / "001-feature-engineering"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC_MD)
    (d / "tasks.md").write_text(TASKS_MD)
    return tmp_path


@pytest.fixture
def cfg(tmp_path):
    return ReviewConfig(ROOT / "config/review_config.yaml", ROOT / "config/rules.yaml", tmp_path)


@pytest.fixture
def spec_cfg(repo):
    return ReviewConfig(ROOT / "config/review_config.yaml", ROOT / "config/rules.yaml", repo)


def diff(name):
    return (CASES / name / "diff.patch").read_text()


class FakeLLM:
    """Scripted model. `by_lens` maps a lens keyword in the system prompt to a findings payload."""

    def __init__(self, by_lens=None, verify=None, conformance=None):
        self.by_lens, self.verify, self.conformance, self.calls = by_lens or {}, verify, conformance, []

    def complete_json(self, endpoint, system, user, schema, temperature, max_tokens):
        name = schema["name"]
        self.calls.append(name)
        if name == "verify_findings":
            data = self.verify or {"decisions": []}
        elif name == "requirement_conformance":
            data = self.conformance or {"requirements": []}
        else:
            data = {"summary": "", "findings": []}
            for key, payload in self.by_lens.items():
                if key in system:
                    data = payload
        return LLMResponse(data=data, input_tokens=100, output_tokens=50)


SPEC_LENS = "SPEC CONFORMANCE"
BUG_LENS = "CORRECTNESS AND DATA SCIENCE RISK"


# ---------------------------------------------------------------- helpers
def test_glob_matching():
    assert path_matches("src/a.py", ["src/**/*.py"])
    assert path_matches("src/x/y/a.py", ["src/**/*.py"])
    assert not path_matches("tests/a.py", ["src/**/*.py"])
    assert path_matches("a.py", ["**/*.py"])


def test_diff_line_numbers():
    fd = parse_unified_diff(diff("leakage_paid_date"))[0]
    assert fd.path == "stages/02_feature_engineering/src/plugins/cost_history.py"
    assert 13 in fd.added and "service_date" in fd.added[14]


def test_extract_json_from_fenced_text():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


# ---------------------------------------------------------------- static rules
@pytest.mark.parametrize("case,rule", [
    ("random_split", "RANDOM-SPLIT"), ("phi_logging", "PHI-LOG"), ("hardcoded_year", "HARDCODED-PERIOD"),
    ("prod_write", "PROD-WRITE"), ("mlflow_untagged", "MLFLOW-UNTAGGED"),
])
def test_static_rules_fire(cfg, case, rule):
    res = CodeReviewer(cfg, None).review_diff(diff(case))
    assert rule in {f.rule_id for f in res.findings}


def test_critical_static_blocks(cfg):
    assert CodeReviewer(cfg, None).review_diff(diff("prod_write")).verdict == "block"


def test_clean_change_passes_static(cfg):
    res = CodeReviewer(cfg, None).review_diff(diff("clean_feature"))
    assert res.verdict == "pass", res.findings


def test_structural_no_tests(cfg):
    res = CodeReviewer(cfg, None).review_diff(diff("leakage_paid_date"))
    assert "NO-TESTS" in {f.rule_id for f in res.findings}


# ---------------------------------------------------------------- Spec Kit parsing + tracing
def test_parse_spec_and_tasks():
    s = parse_spec(SPEC_MD)
    assert set(s["requirements"]) == {"FR-001", "FR-002"}
    assert "paid_date <= feature_asof_date" in s["requirements"]["FR-001"]
    assert len(s["stories"]["US1"]["scenarios"]) == 2 and "SC-001" in s["success_criteria"]
    t = parse_tasks(TASKS_MD)
    assert t[0].id == "T010" and t[0].done and t[0].story == "US1"
    assert t[0].fr_refs == ["FR-001", "FR-002"] and t[0].paths == ["stages/02_feature_engineering/src/plugins/cost_history.py"]
    assert t[1].parallel and not t[1].done


def test_traced_file_has_no_untraced_finding(spec_cfg):
    res = CodeReviewer(spec_cfg, None).review_diff(diff("leakage_paid_date"))
    assert "UNTRACED-CHANGE" not in {f.rule_id for f in res.findings}


def test_untraced_change_flagged(spec_cfg):
    res = CodeReviewer(spec_cfg, None).review_diff(diff("random_split"))   # stages/04_model_training/src/plugins/split.py: no task
    assert "UNTRACED-CHANGE" in {f.rule_id for f in res.findings}


def test_open_clarification_blocks(repo):
    spec = repo / "specs/001-feature-engineering/spec.md"
    spec.write_text(SPEC_MD + "\n- **FR-003**: Claims lag is [NEEDS CLARIFICATION: 30 or 45 days?]\n")
    c = ReviewConfig(ROOT / "config/review_config.yaml", ROOT / "config/rules.yaml", repo)
    res = CodeReviewer(c, None).review_diff(diff("leakage_paid_date"))
    assert "OPEN-CLARIFICATION" in {f.rule_id for f in res.findings} and res.verdict == "block"


def test_spec_context_is_exact(spec_cfg):
    files = parse_unified_diff(diff("leakage_paid_date"))
    tr = trace(files, spec_cfg)
    feat = load_features(spec_cfg)[0]
    ctx = spec_context(feat, files, tr, 8000)
    for must in ("FR-001", "FR-002", "SC-001", "US1", "T010", "claims paid after the as-of date"):
        assert must in ctx


# ---------------------------------------------------------------- LLM passes: grounding, verify, conformance
def _leak_finding(line=13, evidence='window = joined.filter(F.col("service_date") <= F.last_day(F.col("cutoff_date")))'):
    return {"rule_id": "LEAKAGE", "severity": "critical", "file": "stages/02_feature_engineering/src/plugins/cost_history.py", "line": line,
            "title": "Uses claims after the cutoff", "explanation": "Filter reaches the end of the cutoff month and drops the paid_date lag.",
            "suggested_fix": "Filter paid_date <= feature_asof_date and service_date < cutoff_date.", "evidence": evidence}


KEEP = {"decisions": [{"index": 0, "keep": True, "confidence": 95, "severity": "critical", "reason": "real"}]}


def test_llm_finding_verified_blocks(cfg):
    llm = FakeLLM({BUG_LENS: {"summary": "Leakage.", "findings": [_leak_finding()]}}, KEEP)
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert res.verdict == "block"
    leak = [f for f in res.findings if f.rule_id == "LEAKAGE"][0]
    assert leak.verified and leak.line == 13 and leak.confidence == 95 and leak.lens == "correctness"
    assert llm.calls.count("code_review_findings") == 3          # one call per lens


def test_duplicate_findings_across_lenses_merged(cfg):
    payload = {"summary": "", "findings": [_leak_finding()]}
    llm = FakeLLM({SPEC_LENS: payload, BUG_LENS: payload}, KEEP)
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert len([f for f in res.findings if f.rule_id == "LEAKAGE"]) == 1


def test_hallucinated_finding_is_dropped(cfg):
    fake = _leak_finding(line=99, evidence="df.crossJoin(other)")   # code not in the diff
    llm = FakeLLM({BUG_LENS: {"summary": "", "findings": [fake]}})
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert "LEAKAGE" not in {f.rule_id for f in res.findings}
    assert res.dropped_findings == 1


def test_wrong_line_is_snapped_to_evidence(cfg):
    llm = FakeLLM({BUG_LENS: {"summary": "", "findings": [_leak_finding(line=3)]}}, KEEP)
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert [f.line for f in res.findings if f.rule_id == "LEAKAGE"] == [13]


def test_low_confidence_is_dropped(cfg):
    low = {"decisions": [{"index": 0, "keep": True, "confidence": 60, "severity": "critical", "reason": "maybe"}]}
    llm = FakeLLM({BUG_LENS: {"summary": "", "findings": [_leak_finding()]}}, low)
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert "LEAKAGE" not in {f.rule_id for f in res.findings}


def test_verifier_can_reject(cfg):
    rej = {"decisions": [{"index": 0, "keep": False, "confidence": 10, "severity": "critical", "reason": "no"}]}
    llm = FakeLLM({BUG_LENS: {"summary": "", "findings": [_leak_finding()]}}, rej)
    res = CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))
    assert "LEAKAGE" not in {f.rule_id for f in res.findings}
    assert res.verdict == "fix"          # NO-TESTS (medium) still applies


def test_requirement_contradicted_blocks(spec_cfg):
    conf = {"requirements": [
        {"id": "FR-001", "status": "contradicted", "file": "stages/02_feature_engineering/src/plugins/cost_history.py", "line": 13,
         "evidence": 'window = joined.filter(F.col("service_date") <= F.last_day(F.col("cutoff_date")))',
         "explanation": "Filters on service_date to month end instead of paid_date <= feature_asof_date."},
        {"id": "FR-002", "status": "implemented", "file": "stages/02_feature_engineering/src/plugins/cost_history.py", "line": 15,
         "evidence": "", "explanation": "ok"}]}
    llm = FakeLLM(verify=KEEP, conformance=conf)
    res = CodeReviewer(spec_cfg, llm).review_diff(diff("leakage_paid_date"))
    req = [f for f in res.findings if f.rule_id == "REQ-CONTRADICTED"]
    assert len(req) == 1 and req[0].requirement_id == "FR-001" and req[0].verified
    assert res.verdict == "block"
    assert "requirement_conformance" in llm.calls


def test_conformance_skipped_without_task_scope(cfg):
    llm = FakeLLM()
    CodeReviewer(cfg, llm).review_diff(diff("leakage_paid_date"))    # no specs/ in this repo
    assert "requirement_conformance" not in llm.calls
