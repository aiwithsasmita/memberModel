"""Standard MLflow run with required lineage tags (constitution rule 5)."""
from __future__ import annotations

import contextlib
import os
import subprocess
from typing import Dict, Mapping, Optional

REQUIRED_TAGS = ("spec_id", "task_id", "change_request_id", "git_commit")


def git_info() -> Dict[str, str]:
    def run(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""
    return {"git_commit": os.environ.get("GIT_COMMIT") or run("rev-parse", "HEAD"),
            "git_branch": os.environ.get("GIT_BRANCH") or run("rev-parse", "--abbrev-ref", "HEAD")}


def build_tags(spec_id: str, task_id: str, change_request_id: str, stage: str, extra: Optional[Mapping] = None) -> Dict[str, str]:
    tags = {"spec_id": spec_id, "task_id": task_id, "change_request_id": change_request_id, "stage": stage, **git_info()}
    tags.update(extra or {})
    missing = [t for t in REQUIRED_TAGS if not tags.get(t)]
    if missing:
        raise ValueError(f"MLflow run is missing required lineage tags: {missing}")
    return {k: str(v) for k, v in tags.items()}


@contextlib.contextmanager
def start_traced_run(spec_id: str, task_id: str, change_request_id: str, stage: str, config: Mapping,
                     inputs: Optional[Mapping[str, int]] = None, run_name: Optional[str] = None, extra_tags=None):
    """Start an MLflow run with lineage tags, the stage config and the Delta versions of every input."""
    import mlflow

    tags = build_tags(spec_id, task_id, change_request_id, stage, extra_tags)
    with mlflow.start_run(run_name=run_name, tags=tags) as run:
        mlflow.log_dict(dict(config), "config/stage_config.json")
        for table, version in (inputs or {}).items():
            mlflow.log_param(f"input_version__{table.split('.')[-1]}", version)
        yield run
