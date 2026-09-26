"""Command line entry point, used by CI and by the Databricks job.

Examples
  aidlc-review --base origin/main --head HEAD                       # review local branch, print markdown
  aidlc-review --diff-file pr.diff --json out.json                  # review a saved diff
  aidlc-review --base origin/main --head HEAD --github-repo org/repo --pr 42 --write-delta sql
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import ReviewConfig
from .llm_client import DatabricksLLMClient
from .reviewer import CodeReviewer
from .sinks import post_github, to_markdown, write_delta_spark, write_delta_sql


def git_diff(base: str, head: str, context: int) -> str:
    return subprocess.run(["git", "diff", f"-U{context}", f"{base}...{head}"],
                          check=True, capture_output=True, text=True).stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AI-DLC code review agent (Databricks GPT endpoint)")
    ap.add_argument("--config", default="config/review_config.yaml")
    ap.add_argument("--rules", default="config/rules.yaml")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--diff-file")
    ap.add_argument("--pr")
    ap.add_argument("--change-request")
    ap.add_argument("--github-repo")
    ap.add_argument("--commit-sha")
    ap.add_argument("--write-delta", choices=["none", "spark", "sql"], default="none")
    ap.add_argument("--json", help="write the full result as JSON to this path")
    ap.add_argument("--no-llm", action="store_true", help="static and structural checks only")
    args = ap.parse_args(argv)

    cfg = ReviewConfig(args.config, args.rules, args.repo_root)

    if args.diff_file:
        diff = Path(args.diff_file).read_text(encoding="utf-8")
    elif args.base:
        diff = git_diff(args.base, args.head, cfg.get("limits", "context_lines", default=20))
    else:
        ap.error("give --diff-file or --base")

    try:
        import mlflow
        mlflow.openai.autolog()          # traces every LLM call (prompt, output, tokens)
        if mlflow.active_run():
            mlflow.set_tags({"agent": "aidlc_code_review", "prompt_version": cfg.get("prompt_version")})
    except Exception:  # noqa: BLE001
        pass

    llm = None if args.no_llm else DatabricksLLMClient(
        timeout=cfg.get("llm", "timeout_seconds", default=120),
        max_retries=cfg.get("llm", "max_retries", default=3))
    result = CodeReviewer(cfg, llm).review_diff(
        diff, pr_id=args.pr, change_request_id=args.change_request, git_base=args.base, git_head=args.head)

    md = to_markdown(result)
    print(md)
    if args.json:
        Path(args.json).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    table = cfg.get("output", "delta_table")
    if args.write_delta == "spark":
        write_delta_spark(result, table)
    elif args.write_delta == "sql":
        write_delta_sql(result, table)

    if args.github_repo and args.pr and cfg.get("output", "post_pr_summary", default=True):
        post_github(result, args.github_repo, int(args.pr), args.commit_sha or args.head,
                    inline=cfg.get("output", "post_inline_comments", default=True),
                    min_inline_severity=cfg.get("output", "min_inline_severity", default="medium"))

    return 2 if result.verdict in cfg.get("verdict", "ci_fail_on", default=["block"]) else 0


if __name__ == "__main__":
    sys.exit(main())
