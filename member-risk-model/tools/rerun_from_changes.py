"""Find the earliest pipeline stage touched by a set of changed files, and (optionally) start the
pipeline from that stage. Used by CI after a merge to main.

  git diff --name-only HEAD~1 HEAD | python tools/rerun_from_changes.py            # print plan
  git diff --name-only HEAD~1 HEAD | python tools/rerun_from_changes.py --run --job-id 123
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _glob_to_regex(p: str) -> re.Pattern:
    return re.compile("^" + re.escape(p).replace(r"\*\*", ".*").replace(r"\*", "[^/]*") + "$")


def plan(changed: list[str], pipeline_cfg: dict) -> dict:
    order = pipeline_cfg["order"]
    mapping = [(_glob_to_regex(k), v) for k, v in pipeline_cfg["path_to_stage"].items()]
    hit = set()
    for f in changed:
        for rx, stage in mapping:
            if rx.match(f.strip()):
                hit.add(stage)
    in_order = [s for s in order if s in hit]
    if not in_order:
        return {"start_at": None, "tasks": [], "reason": "no pipeline stage changed"}
    start = in_order[0]
    tasks = order[order.index(start):]
    return {"start_at": start, "tasks": tasks, "reason": f"earliest changed stage: {start}"}


def task_key(stage: str) -> str:
    return "s" + stage.split("_", 1)[0] + "_" + stage.split("_", 1)[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--job-id", type=int)
    ap.add_argument("--spec-id", default="")
    ap.add_argument("--change-request-id", default="")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load((ROOT / "pipelines" / "pipeline.yaml").read_text())
    p = plan([l for l in sys.stdin.read().splitlines() if l.strip()], cfg)
    print(p)
    if a.run and p["start_at"]:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        # Runs only the affected tasks (gate check + earliest changed stage and everything after it).
        w.jobs.run_now(job_id=a.job_id, only=["gate_check"] + [task_key(s) for s in p["tasks"]],
                       job_parameters={"spec_id": a.spec_id, "change_request_id": a.change_request_id})


if __name__ == "__main__":
    main()
