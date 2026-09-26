---
name: aidlc-constitution
description: Use before any change in this repo: how to apply the AI-DLC constitution, which approvals are needed, and when to stop and ask a person.
---

# Applying the AI-DLC constitution

Read `.specify/memory/constitution.md` first. These rules are not optional.

## Before you write code
1. Find the spec folder for this change (`specs/NNN-*/`). If there is none, stop: the change needs a spec approved by the tech lead.
2. Check the spec has no `NEEDS CLARIFICATION`. If it has, stop and ask for `/speckit.clarify`.
3. Check `gates/NNN-*/SPEC_APPROVAL.md` exists with an approver name and timestamp. If not, stop.
4. Only change files named by a task in `specs/NNN-*/tasks.md`. If you need another file, stop and ask for the tasks to be updated.

## While you work
- Change one stage at a time. Stages never import each other; they read and write tables declared in `contract.yaml`.
- Put every tunable value in the stage's `config/`. Never hardcode years, cutoffs, caps, thresholds or table names.
- Log every MLflow run with the standard tags (see the `mlflow-traceability` skill).
- Write tests that would fail if the logic were wrong.

## Stop and ask a person when
- the spec is ambiguous or silent about something the code must decide (never assume),
- a change touches `stages/05_model_test/config/evaluation.yaml` (locked),
- you would need to write outside the dev catalog, merge, promote or deploy.

## After you finish a task
- Tick the task in tasks.md, keeping its FR IDs.
- Add a row to `aidlc_task_metrics` (`python tools/log_task_metrics.py ...`).
- Open the PR; the code review agent runs automatically.
