# AI-DLC Implementation Plan: Member Risk Model on Databricks

**Document ID:** AIDLC-PLAN-001 · **Version:** 1.1 (modular stages layout; starter repo) · **Owner:** Aiwithsasmita · **Related spec:** MRS-001 (member risk model)

---

## How to use this document (read first)

This is a **plan**, not code. Work through it **one step at a time, in order**.

**Rules for the implementing agent:**

1. Do only the current step. Don't start the next step until the current one meets its **Done when** checks.
2. Every step that produces code starts with Spec Kit: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`. Follow the project constitution.
3. Any step marked **🔒 Human approval** stops until a named person approves. Never approve on anyone's behalf.
4. Never write outside the `*_dev` catalog. Never merge pull requests. Never deploy to test or prod yourself; CI does that.
5. If something in this plan conflicts with the constitution or the MRS-001 spec, stop and ask. Don't guess.
6. For existing code (feature engineering is already built), **review it against the step's requirements and add only what's missing**. Don't rewrite working code.
7. After finishing each task, add a row to `aidlc_task_metrics` (Step 0.7). This feeds the leadership dashboard.

**Placeholders:** `{catalog_dev}`, `{catalog_test}`, `{catalog_prod}`, `{platform_schema}` (default `aidlc_platform`), `{gpt_endpoint}`, `{claude_endpoint}`.

---

## Stage overview

| Stage | Name | What it delivers | Who leads |
|---|---|---|---|
| 0 | Foundation and governance | Repo, permissions, catalogs, model endpoints, platform tables, metrics tracking | Platform + tech lead |
| 1 | Inception | Approved constitution and specs for every component | Tech lead approves |
| 2 | Construction (version 1) | Features, training, evaluation, MLflow traceability, deployment code, schedules | Data scientists with Spec Kit + skills |
| 3 | Harness and agents | Review, monitoring, AI Ops, change, deployment agents; observability | Data scientists + platform |
| 4 | Operations | Runbooks: data refresh, change requests, drift, incidents, rollback | Model owner |
| 5 | Measurement and dashboard | Vibe coding vs AI-DLC comparison, leadership dashboard | Model owner |

---

## Stage 0: Foundation and governance

### Step 0.1 Git repository and code ownership
- Create (or confirm) the Git repo `member-risk-model` and link it to a Databricks Git folder.
- **Start from the starter repo** `member-risk-model/` (already contains everything below). Folder layout:
  ```
  AGENTS.md  DEVELOPER.md  CODEOWNERS  databricks.yml  README.md
  .specify/            constitution (+ constitution.aidlc-additions.md), tasks template with FR IDs
  specs/               one folder per spec; later changes get the next number
  gates/               approval records (approver, timestamp, evidence)
  skills/              GLOBAL skills for every stage
  common/              shared helpers only: config, contracts, IO, MLflow tags, gates, events
  pipelines/           orchestration only: stage order, gates required, triggers
  stages/
    01_feature_creation/  02_feature_engineering/  03_feature_selection/  04_model_training/
    05_model_test/        06_mlops/                07_deployment/          08_aiops/
      each: config/stage.yaml + registry · contract.yaml · src/run.py + src/plugins/ · tests/
            skills/ (LOCAL) · AGENTS.md · job.yml · README.md
  platform/sql/        platform tables, catalogs, grants
  tools/               code review agent, rerun_from_changes, log_task_metrics, approval checks
  ci/                  workflows (move to .github/workflows/)
  docs/                this plan, MRS-001 spec, blueprint
  ```
- **Stage ↔ MRS-001 module map:** 01 = M1–M4 · 02 = M5–M7 · 03 = M8 + selection · 04 = M9–M13 · 05 = M14 · 06 = registry/promotion · 07 = M16 scoring · 08 = M16 monitoring + agents. M0 (config + formula library) lives in `common/`.
- **Stages never import each other**; they exchange data only through the tables in each `contract.yaml`.
- **CODEOWNERS:** one owner group per stage folder; tech lead owns `specs/`, `.specify/`, `gates/`, `skills/`; platform owns `pipelines/`, `databricks.yml`, `tools/` (starter `CODEOWNERS` provided).
- **Branch protection on `main`:** pull request required; code owner approval required; passing CI required; no direct pushes; no force pushes.

**Done when:** a test PR by a non-owner cannot merge without the owner's approval.

### Step 0.2 Spec approval flow
- Every new spec and every spec change lives in `specs/` and is merged by PR.
- `specs/` and `.specify/` are owned by the **tech lead** in CODEOWNERS, so no spec merges without tech-lead approval.
- Rule in the constitution: **no code task starts until its spec PR is merged.**

**Done when:** a spec PR cannot merge without tech-lead approval.

### Step 0.3 Catalogs and permissions
- Create catalogs `{catalog_dev}`, `{catalog_test}`, `{catalog_prod}` and schema `{platform_schema}`.
- Create service principals: `sp-aidlc-agents` (all agents) and `sp-aidlc-ci` (CI deploys).
- Grants:
  - Agents: read source data; write `{catalog_dev}` and `{platform_schema}` only.
  - CI: write `{catalog_test}` and `{catalog_prod}`.
  - People: developers write dev only; prod is changed only through CI.

**Done when:** `sp-aidlc-agents` gets a permission error writing to `{catalog_prod}`.

### Step 0.4 Model endpoints
- Create AI Gateway endpoints `{gpt_endpoint}` and `{claude_endpoint}` with usage logging and inference tables on, rate limits set, and guardrails for PII.

**Done when:** a test call from a notebook succeeds and appears in the usage table.

### Step 0.5 Platform tables (in `{platform_schema}`)
Create these Delta tables. Columns are the minimum; add more if needed.

| Table | Purpose | Key columns |
|---|---|---|
| `aidlc_gates` | Gate approvals | gate_name, module, spec_id, change_request_id, status (pending/approved/rejected), approver, approved_at, evidence_links |
| `aidlc_events` | Every agent and pipeline action | event_id, ts, actor (agent/person/job), action, module, change_request_id, run_id, details |
| `aidlc_reviews` | Code review results | review_id, pr_id, module, spec_section, verdict (pass/fix/block), findings_json, model_endpoint, override_reason |
| `aidlc_change_requests` | Every requested change | cr_id, created_at, source (person/alert), type, description, status, spec_pr, code_pr, champion_version, challenger_version, decision, decided_by |
| `aidlc_task_metrics` | Effort per task, for the dashboard | task_id, spec_id, arm (aidlc / vibe), start_ts, end_ts, tokens, messages, rework_rounds, defects_found, first_pass_tests |

- Only the named approver groups may insert `approved` rows into `aidlc_gates` (use a view or function with grants).

**Done when:** all five tables exist with grants, and a non-approver cannot insert an approved gate.

### Step 0.6 Agent context files
- `AGENTS.md`: the constitution's rules in short form, the folder map, and "read the matching spec before editing any module". Genie Code and Codex both read this file.
- Install the official Databricks agent skills and the Spec Kit skills in the workspace.
- Create our own skills folder (filled in Stage 3).

**Done when:** Genie Code, asked "what are this project's rules?", answers from `AGENTS.md`.

### Step 0.7 Start measuring from day one
- For every task in Stages 1–3, write one row to `aidlc_task_metrics` when the task finishes.
- Tag model-endpoint calls with the task ID where possible, so tokens can be joined.

**Done when:** the first task's row exists.

---

## Stage 1: Inception (specs and approvals)

### Step 1.1 Update the constitution
Add these rules to the existing constitution (keep existing rules):
1. Time-based splits only; never random splits across years.
2. No leakage: features use only data paid before the cutoff minus the claims lag.
3. One formula library (`common/`) for all shared calculations.
4. **The evaluation protocol and test year are locked.** Only the model owner may change them, through an approved spec change.
5. Every MLflow run logs spec ID, task ID, change request ID, Git commit, data versions and full config. Runs without these are invalid.
6. A model is promoted only if it beats the current champion on the locked evaluation.
7. Seeds and library versions are pinned; reruns give identical results.
8. No PHI in logs, prompts or MLflow artifacts.
9. All tunable settings live in each stage's `config/`; no hardcoded values in code. Stages never import each other.
10. Agents never merge, never deploy beyond dev, never approve gates.

🔒 **Human approval:** tech lead merges the constitution PR.

### Step 1.2 Write the specs
Create one spec per component with Spec Kit. The feature spec exists; confirm it matches the rules above.

| Spec | Covers |
|---|---|
| `001-feature-engineering` | Exists. Add: config-driven settings, feature registry, leakage tests, Delta versioning |
| `002-model-training` | Baselines, model plugin interface, LightGBM Tweedie, calibration, hyperparameter search |
| `003-evaluation` | Locked evaluation protocol: CMS comparison, metrics, groups, bootstrap, golden test |
| `004-mlflow-traceability` | What every run and model version must log; registry and aliases |
| `005-deployment` | Bundle, CI/CD, MLflow deployment job, batch scoring |
| `006-orchestration` | Pipeline job, schedules, triggers, rerun-from-step |
| `007-agents` | Review, monitoring, AI Ops, change and deployment agents; observability |
| `008-dashboard` | Metrics, sources, pages |

🔒 **Human approval:** tech lead merges each spec PR before its construction step starts.

---

## Stage 2: Construction (version 1, human-led with Spec Kit + skills)

### Step 2.1 Feature engineering (exists: review and harden)
Check the existing code against these requirements; add only what's missing:
- Code lives in `stages/02_feature_engineering/src/plugins/` (one file per feature group). All settings (cutoffs, lag days, lookback) read from `stages/02_feature_engineering/config/stage.yaml`.
- **Feature registry** `stages/02_feature_engineering/config/features.yaml`: one entry per feature group with name, description, source tables, owner, spec reference, enabled flag.
- Each feature table is Delta, keyed on (member_id, target_year, cutoff_month).
- A leakage test per feature table (max paid date used ≤ as-of date).
- Row-count and null-rate tests.
- Each run records the Delta version of every output table.

**Done when:** all tests pass and flipping a feature's `enabled` flag in the registry removes it from the output without code changes.

### Step 2.2 Model training
- **Model plugin interface** `stages/04_model_training/src/plugins/base.py`: every algorithm is a class with the same methods (fit, predict, get_params, log_to_mlflow). The stage picks algorithms from `stages/04_model_training/config/models.yaml`.
- Implement plugins: baseline B2 (HCC-only linear refit), B3 (prior cost), and the main LightGBM Tweedie model.
- Hyperparameter search with Optuna (search space in config, capped trials).
- Calibration per cutoff (isotonic, fallback to a scaling factor).
- Training reads features by table name and Delta version from config.

**Done when:** adding a new algorithm needs only a new plugin class plus one config entry; training runs end to end in dev.

### Step 2.3 Evaluation (locked protocol)
- Implement the MRS-001 evaluation exactly: formulas F1–F8, CMS conversion, rescaling, metrics, predictive ratios by decile and condition group, bootstrap intervals, gain breakdown.
- Golden test (MRS-001 Appendix A) must pass.
- Output tables `eval_metrics`, `eval_pr`, `eval_scaling`.
- **Champion vs challenger comparison** function: given two model versions, returns win / lose / tie using the locked rules (beats champion, bootstrap interval above zero, no condition group outside 0.90–1.10).

**Done when:** golden test passes; comparison returns a correct verdict on a test pair.

### Step 2.4 MLflow traceability
Every training run logs:

| Item | How |
|---|---|
| Spec, task, change request | Tags: spec_id, task_id, change_request_id |
| Code | Tags: git_commit, git_branch |
| Data | `mlflow.log_input` for each feature table with name and Delta version; split years as params |
| Settings | Full config files as params and as artifacts |
| Results | All evaluation metrics per cutoff; evaluation report and SHAP summary as artifacts |
| Model | Registered in Unity Catalog with a signature |

- Aliases: `@champion` (production) and `@challenger` (candidate).
- Model version tags: spec_id, change_request_id, evaluation verdict.

**Done when:** from any model version you can reach its run, code commit, data versions, config and change request in the UI.

### Step 2.5 Deployment code
- `databricks.yml` bundle with dev, test and prod targets; the pipeline job in `pipelines/pipeline_job.yml` and one standalone `job.yml` per stage.
- **CI/CD pipeline:**
  - On PR: run unit tests, leakage tests, golden test, and the code review (Step 3.1 once built).
  - On merge to `main`: deploy to test, run the pipeline on test data, then deploy to prod after a manual approval in CI.
- **MLflow 3 deployment job:** triggered by a new model version → run evaluation → 🔒 human approval on the model page → set `@champion` → deploy.
- **Batch scoring job:** scores all active members at each cutoff with `@champion`; writes scores with model version and run date.

**Done when:** a merged change reaches prod only through CI, and a model becomes champion only after approval.

### Step 2.6 Orchestration, schedules and triggers
- One pipeline job with dependent tasks: gate check → features → training → calibration → evaluation → register → (deployment job handles promotion).
- **Task 0 gate check:** reads `aidlc_gates`; fails the run if a required upstream gate isn't approved.
- **Schedules and triggers:**

| Trigger | Runs |
|---|---|
| Monthly schedule after claims close | Full pipeline (data refresh) |
| Scoring schedule at each cutoff (Jan 1, Mar 1, Jun 1, Sep 1) | Batch scoring |
| Table update on the claims source | Features → downstream |
| Merge to `main` touching a module | That module's task and everything after it |
| Drift alert (Stage 3) | Retrain as challenger + evaluation |

- The pipeline supports **starting from any task** and **repairing only failed tasks**.

**Done when:** changing one feature file and merging reruns features and all downstream steps automatically, and nothing upstream.

### Step 2.7 Version 1 sign-off
🔒 **Human approval (gates):**

| Gate | Approver | Evidence |
|---|---|---|
| Data Gate | Data engineering lead | Profiling and reconciliation results |
| Target Gate | Actuary | Target distribution and means |
| Feature Gate | ML lead | Leakage and shuffle tests |
| Model Gate | Actuary + ML lead | Evaluation vs CMS, bootstrap intervals |
| Production deploy | Platform owner | CI run, deployment job approval |

**Done when:** all five gates are approved in `aidlc_gates` and version 1 is champion in prod.

---

## Stage 3: Harness and agents (after version 1 is live)

All agents: run as Databricks jobs or a Databricks App, use AI Gateway endpoints, run as `sp-aidlc-agents`, are traced in MLflow, and write every action to `aidlc_events`.

### Step 3.1 Code review agent
- Function `aidlc_review(diff, spec_section, module)` calling `{gpt_endpoint}`.
- Checks: spec conformance, leakage, time splits, PHI, formula library use, config use (no hardcoding), test coverage, Spark anti-patterns.
- Output: verdict (pass / fix / block) and findings (severity, file, line, rule, suggested fix) written to `aidlc_reviews` and posted on the PR.
- Wired into CI on every PR; a `block` verdict fails CI unless a code owner overrides with a written reason.
- **Test set:** 25 known-bad diffs (planted defects + common bugs). Measure bug recall and false alarms with MLflow evaluation; rerun when the prompt or model changes.

**Done when:** it catches at least the 5 planted defects and runs on every PR.

### Step 3.2 Monitoring
- Data profiling monitors on the feature table and the scoring output (inference) table, with a baseline from the training period.
- Custom metrics: PSI per key feature, predicted ÷ actual by condition group (once actuals mature), score distribution by segment.
- SQL alerts: PSI > 0.2; predicted ÷ actual outside 0.95–1.05 for any group; freshness or row-count anomalies; job failures.
- Every alert writes an event and triggers the AI Ops agent.

**Done when:** a simulated drift (shifted test data) fires an alert within one scheduled run.

### Step 3.3 AI Ops agent
Triggered by alerts, job failures and schedules. For each trigger:
1. Read the alert, recent metrics and job logs.
2. Diagnose the likely cause (data change, coding change, pipeline failure, real population shift).
3. Act by type:

| Situation | Agent action | Human step |
|---|---|---|
| Job failed, transient | Repair run once; log it | None, unless the repair fails |
| Job failed, persistent | Summarize the error and cause; alert the owner | Owner fixes |
| New data arrived | Confirm the refresh ran; check data quality | None |
| Drift or calibration drop | Open a change request; start a **challenger** retrain in dev; attach the comparison | 🔒 Approve promotion in the deployment job |
| Needs a code change | Open a change request with a drafted spec delta | 🔒 Tech lead approves spec; developer implements |

- Uses LangGraph; state and memory in Lakebase so it can pause for approval and resume.

**Done when:** a simulated drift goes from alert → change request → challenger evaluation with no manual steps before the approval.

### Step 3.4 Change agent (configuration changes)
- Handles changes that only need edits in a stage's `config/`: retrain window, cost cap, feature on/off, calibration method, thresholds, adding a registered algorithm.
- Steps: edit config on a branch → open PR (reviewed by Step 3.1) → after merge, the pipeline reruns from the affected task → champion vs challenger comparison → result on the change request.
- Changes to the evaluation protocol or test year are **never** made by the agent (constitution rule 4).

**Done when:** a config-only change runs from request to challenger verdict with only the PR merge as a human step.

### Step 3.5 Deployment agent
- **Before release:** checks readiness (all gates approved, CI green, review verdict pass, challenger beats champion) and writes release notes from the change requests and runs.
- **After release:** runs smoke checks on the first scoring run (row counts, score distribution vs previous, nulls) and **recommends rollback** if checks fail.
- Never deploys or rolls back by itself; rollback = a person moves `@champion` back to the previous version.

**Done when:** release notes and post-deploy checks are produced for a real release.

### Step 3.6 Our skills (for coding agents)
Write these skills in the workspace skills folder, each with rules and examples from this project:

| Skill | Teaches |
|---|---|
| `claims-data-rules` | Claims lag, reversals, member-months, V28 mapping |
| `leakage-checks` | How to prove features respect the as-of date |
| `add-feature` | Feature registry entry → template code → tests → ablation |
| `add-model` | New plugin class → config entry → leaderboard |
| `mlflow-traceability` | What every run must log |
| `deployment` | Bundle, jobs, schedules, deployment job conventions |
| `gate-review` | Collect gate evidence and draft the gate record |
| `request-code-review` | Call `aidlc_review()` and act on findings |

**Done when:** a coding agent adds a new feature using `add-feature` without extra instructions.

### Step 3.7 Agent observability
- MLflow tracing on every agent and on `aidlc_review()`: prompts, tool calls, outputs, latency, cost.
- AI Gateway usage and inference tables joined to `aidlc_events` by change request and task.
- Weekly MLflow evaluation of agents: review agent on its test set; AI Ops agent on replayed past alerts.

**Done when:** any agent decision can be opened as a trace from its change request.

---

## Stage 4: Operations

### Step 4.1 Standard change flow (every change)
```
1. Request      form entry or alert → row in aidlc_change_requests
2. Spec delta   specs/changes/CR-xxx drafted (by person or agent)        🔒 tech lead approves
3. Implement    code owner (with Codex or Genie Code + skills), or change agent for config
4. Verify       CI: tests, leakage, golden test, review agent
5. Merge        🔒 code owner approves the PR
6. Rerun        pipeline reruns from the affected task
7. Compete      challenger vs champion on the locked evaluation (automatic accept/reject)
8. Promote      deployment job                                           🔒 approver clicks Approve
9. Verify live  deployment agent post-deploy checks
```

### Step 4.2 Playbook per change type

| Change | Where it's made | Automatic checks | Accept rule |
|---|---|---|---|
| Data refresh | Schedule or table trigger | Data quality, profiling | Runs automatically |
| Train or validation logic (window, weights, cap) | Config (change agent) | Rerun champion and challenger under the same setup | Beats champion; evaluation-protocol changes need model owner approval |
| Feature logic change | Feature code (code owner) | Leakage tests, feature diff report (old vs new distributions) | Beats champion; no group outside 0.90–1.10 |
| New feature | Feature registry + `add-feature` skill | Leakage and null tests, ablation (with vs without) | Keep only if gain ≥ threshold in config and no group worse |
| New algorithm | Model plugin + `add-model` skill | Same splits, same evaluation, leaderboard | Beats champion with bootstrap interval above zero |

### Step 4.3 Runbooks
Write short runbooks (in `docs/runbooks/`) for: monthly data refresh; drift alert; job failure; rollback; quarterly retrain; CMS model version change (for example a new HCC version).

**Done when:** each runbook has been run once in dev.

---

## Stage 5: Measurement and leadership dashboard

### Step 5.1 Comparison method (vibe coding vs AI-DLC + skills)
- **Arm A (vibe coding):** plain prompting, no spec, no skills, no gates.
- **Arm B (AI-DLC):** Spec Kit + constitution + skills + gates + review agent.
- Run **the same tasks** in both arms: at least 2 build tasks (for example one ML module) and the 4 standard changes (config change, feature logic change, new feature, new algorithm).
- Plant 5 known defects in the test data; keep the answer key sealed.
- Log every task in `aidlc_task_metrics` with its arm.

### Step 5.2 Metrics

| Group | Metric | Source |
|---|---|---|
| Speed | Hours per task; request-to-decision time per change | `aidlc_task_metrics`, `aidlc_change_requests` |
| Effort | Tokens, messages, human touches per change | AI Gateway usage, `system.access.assistant_events`, `aidlc_events` |
| Quality | Rework rounds, first-pass tests, defects caught before prod | `aidlc_task_metrics`, `aidlc_reviews`, answer key |
| Governance | Changes with approved spec, gates with named approver, full trace coverage | `aidlc_gates`, `aidlc_events`, MLflow |
| AI Ops | Alerts handled, time to detect, time to resolve, auto-rejected challengers | `aidlc_change_requests`, monitors |
| Model | R², MAE, predicted ÷ actual vs CMS by horizon | `eval_metrics`, `eval_pr` |
| Cost | Model spend and compute per change | AI Gateway usage, `system.billing.usage` |

### Step 5.3 Dashboard (Databricks AI/BI)
Pages:
1. **Overview:** headline comparison of the two arms and the lifecycle with gate status.
2. **Change timeline:** each change request end to end: steps, time per step, human touches, result.
3. **Build efficiency:** tokens, hours, rework per task, by arm.
4. **Governance:** gate register, review findings, trace coverage.
5. **AI Ops:** drift, alerts, change requests, time to resolve.
6. **Model impact:** champion vs CMS by horizon; champion history.

**Done when:** every number on the dashboard comes from the tables above, with no manual entries.

### Step 5.4 Leadership readout
- 30-minute demo: one change request live end to end, one rejected challenger, one blocked review, then the dashboard.

---

## Summary checklist

- [ ] Stage 0 — repo, CODEOWNERS, branch protection, catalogs, endpoints, platform tables, metrics tracking
- [ ] Stage 1 — constitution updated, 8 specs approved by tech lead
- [ ] Stage 2 — features hardened, training, evaluation, MLflow traceability, deployment, orchestration; 5 gates approved; version 1 live
- [ ] Stage 3 — review, monitoring, AI Ops, change, deployment agents; skills; observability
- [ ] Stage 4 — change flow, playbooks, runbooks tested
- [ ] Stage 5 — both arms measured, dashboard live, leadership readout
