"""Evaluate the reviewer on known-bad and known-clean diffs, and log results to MLflow.

Each case folder under eval/cases/ holds:
  diff.patch      the change
  expected.yaml   expected_rules: [...]   should_block: true|false

Metrics
  rule_recall       share of expected rule IDs the reviewer reported
  block_accuracy    share of cases where the block / no-block decision was right
  clean_false_alarm share of clean cases (no expected rules) with any high or critical finding

Run in Databricks (uses the real endpoint) or locally with --no-llm (static checks only).
Rerun whenever the prompt, rules or model endpoint changes; grow the set to 25+ cases.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidlc_review.config import ReviewConfig  # noqa: E402
from aidlc_review.reviewer import CodeReviewer  # noqa: E402


def run(cases_dir: Path, cfg: ReviewConfig, llm) -> dict:
    reviewer = CodeReviewer(cfg, llm)
    rows, hit, expected_total, block_ok, clean, clean_fp = [], 0, 0, 0, 0, 0
    for case in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        exp = yaml.safe_load((case / "expected.yaml").read_text())
        res = reviewer.review_diff((case / "diff.patch").read_text())
        found = {f.rule_id for f in res.findings}
        want = set(exp.get("expected_rules", []))
        hit += len(want & found)
        expected_total += len(want)
        blocked = res.verdict == "block"
        block_ok += int(blocked == bool(exp.get("should_block")))
        if not want:
            clean += 1
            clean_fp += int(any(f.severity in ("high", "critical") for f in res.findings))
        rows.append({"case": case.name, "expected": sorted(want), "found": sorted(found),
                     "missed": sorted(want - found), "verdict": res.verdict,
                     "tokens": res.input_tokens + res.output_tokens})
    n = len(rows) or 1
    return {
        "rule_recall": hit / expected_total if expected_total else 1.0,
        "block_accuracy": block_ok / n,
        "clean_false_alarm": clean_fp / clean if clean else 0.0,
        "cases": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/cases")
    ap.add_argument("--config", default="config/review_config.yaml")
    ap.add_argument("--rules", default="config/rules.yaml")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--mlflow-experiment", default=None)
    args = ap.parse_args()

    cfg = ReviewConfig(args.config, args.rules)
    llm = None
    if not args.no_llm:
        from aidlc_review.llm_client import DatabricksLLMClient
        llm = DatabricksLLMClient()
    out = run(Path(args.cases), cfg, llm)
    print(json.dumps(out, indent=2))

    if args.mlflow_experiment:
        import mlflow
        mlflow.set_experiment(args.mlflow_experiment)
        with mlflow.start_run(run_name=f"review-eval-v{cfg.get('prompt_version')}"):
            mlflow.set_tags({"agent": "aidlc_code_review", "prompt_version": cfg.get("prompt_version"),
                             "endpoint": cfg.get("llm", "endpoint"), "llm": str(not args.no_llm)})
            mlflow.log_metrics({k: v for k, v in out.items() if isinstance(v, float)})
            mlflow.log_dict(out, "eval_results.json")


if __name__ == "__main__":
    main()
