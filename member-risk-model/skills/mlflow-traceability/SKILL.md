---
name: mlflow-traceability
description: Use whenever code starts an MLflow run or registers a model: the tags, inputs and artifacts every run must log.
---

# MLflow traceability

Always use `aidlc_common.mlflow_utils.start_traced_run(...)`, never `mlflow.start_run()` directly.
It sets and checks:

| Item | How |
| --- | --- |
| spec_id, task_id, change_request_id | run tags (required) |
| git_commit, git_branch | run tags (required) |
| input tables + Delta versions | `mlflow.log_input` per table from the contract |
| full stage config | params + artifact |
| metrics per cutoff | metrics named `<metric>__cutoff_<n>` |
| evaluation report, SHAP summary | artifacts |
| model | Unity Catalog registration with signature; version tags spec_id, change_request_id, evaluation verdict |

A run missing a required tag fails. Aliases: `@champion` is production, `@challenger` is the candidate.
