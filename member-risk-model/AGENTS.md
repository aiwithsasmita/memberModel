# AGENTS.md: rules for every coding agent

You are working in a spec-driven, governed data science repo. Follow these rules exactly.

## Before any change
1. Find the spec folder `specs/NNN-*/` for this change. No approved spec → stop and ask.
2. The spec must have no `NEEDS CLARIFICATION`, and `gates/NNN-*/SPEC_APPROVAL.md` must show an approver and timestamp.
3. Only edit files named by a task in `specs/NNN-*/tasks.md`. Need another file? Stop and ask for the tasks to be updated.
4. Load skills: global ones in `skills/`, plus the local ones in the stage you are editing (`stages/<stage>/skills/`).
   Read the stage's own `AGENTS.md` too.

## How code is organized
- Eight stages under `stages/`. **A stage never imports another stage.** Stages exchange data only through the tables
  declared in each `contract.yaml`, via `aidlc_common.io`.
- Shared code goes in `common/` only if every stage can use it.
- Capabilities are added through registries (`config/*.yaml`) + `src/plugins/`, not by editing `src/run.py`.
- Every tunable value lives in the stage's `config/`. No hardcoded years, cutoffs, caps, thresholds or table names.

## Non-negotiable rules (see the constitution)
- Time-based splits only. No leakage: `paid_date <= cutoff_date - claims_lag_days`, `service_date < cutoff_date`.
- `stages/05_model_test/config/evaluation.yaml` is locked. Never edit it.
- MLflow runs only through `aidlc_common.mlflow_utils.start_traced_run` (spec_id, task_id, change_request_id, git_commit).
- No PHI in logs, prints, prompts or MLflow.
- Write only to the dev catalog. Never merge, promote a model, approve a gate or deploy beyond dev.
- Never assume. If the spec is silent, stop and ask.

## When a task is done
- Tick it in tasks.md (keep its FR IDs), run the stage tests and the code review agent (`request-code-review` skill),
  log the task to `aidlc_task_metrics`, then open the PR.
