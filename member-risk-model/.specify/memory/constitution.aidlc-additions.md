# AI-DLC additions to the constitution

Merge these articles into `.specify/memory/constitution.md` (keep your existing articles). Changes to the
constitution need the tech lead's approval.

## Data and modeling
1. **Time-based splits only.** Train, validation and test are separated by target year. No random splits across years.
2. **No leakage.** Features use only claims with `paid_date <= cutoff_date - claims_lag_days` and `service_date < cutoff_date`.
3. **One formula library.** Shared calculations (weights, risk score, rescaling, metrics) live in shared code, never inline.
4. **Locked evaluation.** `stages/05_model_test/config/evaluation.yaml` and the test year change only through an approved
   spec change signed by the model owner. Changing it re-scores the champion and all challengers.
5. **Traceability.** Every MLflow run logs spec_id, task_id, change_request_id, git commit, input Delta versions and full
   config. Runs without these are invalid.
6. **Champion/challenger.** A model is promoted only if it beats the current champion on the locked evaluation.
7. **Reproducible.** Seeds and library versions pinned; reruns give identical results.
8. **No PHI** in logs, prints, prompts or MLflow artifacts.

## Architecture
9. **Modular stages.** The eight stages never import each other; they exchange data only through tables declared in
   `contract.yaml`.
10. **Config-driven.** Every tunable value lives in the stage's `config/`. Capabilities are added through registries
    and plugins.

## Process and governance
11. **Spec before code.** No code task starts until its spec is approved by the tech lead (name and timestamp in `gates/`).
12. **No assumptions.** Code implements the spec exactly. If the spec is silent or ambiguous, stop and clarify.
13. **Traceable tasks.** Every changed file is named by a task that lists the FR IDs it implements.
14. **Owners decide.** Only CODEOWNERS approve changes to their area. Agents never merge, promote, approve gates, or
    write outside the dev catalog.
15. **Measured.** Every task is logged to `aidlc_task_metrics`.
