"""Where review results go: PR comments (GitHub), the Delta audit table, and markdown."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List

from .models import SEVERITY_ORDER, Finding, ReviewResult

ICON = {"pass": "✅ PASS", "fix": "🟠 FIX NEEDED", "block": "⛔ BLOCKED"}


def to_markdown(r: ReviewResult) -> str:
    counts = {s: sum(1 for f in r.findings if f.severity == s) for s in SEVERITY_ORDER}
    lines = [
        f"## AI-DLC code review: {ICON.get(r.verdict, r.verdict)}",
        "",
        f"Critical {counts['critical']} · High {counts['high']} · Medium {counts['medium']} · Low {counts['low']}"
        f" · Files {len(r.files_reviewed)} · Specs: {', '.join(r.specs_used) or 'none mapped'}",
        "",
    ]
    if r.summary:
        lines += [r.summary, ""]
    if r.findings:
        lines += ["| Severity | Rule | Where | Finding | Fix |", "| --- | --- | --- | --- | --- |"]
        for f in r.findings:
            where = f"`{f.file}:{f.line}`" if f.line else f"`{f.file}`"
            lines.append(f"| {f.severity} | {f.rule_id} | {where} | {_cell(f.title)} | {_cell(f.suggested_fix)} |")
        lines.append("")
    else:
        lines += ["No problems found.", ""]
    lines.append(
        f"<sub>Review {r.review_id} · endpoint `{r.model_endpoint}` · prompt v{r.prompt_version} · "
        f"{r.input_tokens + r.output_tokens} tokens · {r.dropped_findings} unsupported findings filtered · "
        f"override: a code owner comments `/override-review <reason>`</sub>")
    return "\n".join(lines)


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")[:300]


# ---------------------------------------------------------------- GitHub
def post_github(r: ReviewResult, repo: str, pr_number: int, commit_sha: str, inline: bool = True,
                min_inline_severity: str = "medium") -> None:
    import requests  # only needed in CI

    token = os.environ["GITHUB_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"

    comments: List[dict] = []
    if inline:
        floor = SEVERITY_ORDER[min_inline_severity]
        for f in r.findings:
            if f.line and SEVERITY_ORDER.get(f.severity, 0) >= floor:
                comments.append({"path": f.file, "line": f.line, "side": "RIGHT",
                                 "body": _inline_body(f)})
    body = to_markdown(r)
    payload = {"commit_id": commit_sha, "body": body, "event": "COMMENT", "comments": comments}
    resp = requests.post(f"{api}/pulls/{pr_number}/reviews", headers=headers, json=payload, timeout=60)
    if resp.status_code >= 300:   # e.g. a line outside the diff: fall back to one summary comment
        requests.post(f"{api}/issues/{pr_number}/comments", headers=headers, json={"body": body}, timeout=60)


def _inline_body(f: Finding) -> str:
    return (f"**{f.severity.upper()} · {f.rule_id}: {f.title}**\n\n{f.explanation}\n\n"
            f"**Fix:** {f.suggested_fix}")


# ---------------------------------------------------------------- Delta audit table
def _row(r: ReviewResult) -> dict:
    return {
        "review_id": r.review_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "pr_id": r.pr_id, "change_request_id": r.change_request_id,
        "git_base": r.git_base, "git_head": r.git_head,
        "verdict": r.verdict,
        "n_critical": sum(f.severity == "critical" for f in r.findings),
        "n_high": sum(f.severity == "high" for f in r.findings),
        "n_medium": sum(f.severity == "medium" for f in r.findings),
        "n_low": sum(f.severity == "low" for f in r.findings),
        "findings_json": json.dumps([f.__dict__ for f in r.findings]),
        "files_reviewed": json.dumps(r.files_reviewed),
        "specs_used": json.dumps(r.specs_used),
        "model_endpoint": r.model_endpoint, "prompt_version": r.prompt_version,
        "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
        "dropped_findings": r.dropped_findings, "duration_seconds": r.duration_seconds,
        "override_reason": None,
    }


def write_delta_spark(r: ReviewResult, table: str) -> None:
    """Inside Databricks (job or notebook)."""
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    spark.createDataFrame([_row(r)]).write.mode("append").saveAsTable(table)


def write_delta_sql(r: ReviewResult, table: str) -> None:
    """From CI, through a SQL warehouse (DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_HTTP_PATH)."""
    from databricks import sql
    row = _row(r)
    cols = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    with sql.connect(server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/"),
                     http_path=os.environ["DATABRICKS_WAREHOUSE_HTTP_PATH"],
                     access_token=os.environ["DATABRICKS_TOKEN"]) as conn:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({params})", row)
