# member-risk-model

Member risk score model (MRS-001), built the AI-DLC way on Databricks: Spec Kit specs, a governed agent harness,
and eight independent, config-driven lifecycle stages.

| Read first | Why |
| --- | --- |
| `AGENTS.md` | Rules for every coding agent (Genie Code, Codex) |
| `DEVELOPER.md` | How people work here: branches, specs, PRs, approvals |
| `.specify/memory/constitution.md` | Project rules (merge in `constitution.aidlc-additions.md`) |
| `docs/AIDLC_Implementation_Plan.md` | Step-by-step build plan |
| `docs/member_risk_model_spec.md` | MRS-001 model spec |

## Layout

```
AGENTS.md  DEVELOPER.md  CODEOWNERS  databricks.yml
.specify/          Spec Kit: constitution, templates (tasks carry FR IDs)
specs/             one folder per feature or change (spec.md, plan.md, tasks.md)
gates/             approval records: approver, timestamp, evidence
skills/            GLOBAL skills for every stage
common/            shared helpers only (config, contracts, IO, MLflow tags, gates, events)
pipelines/         orchestration only (stage order, gates, triggers)
stages/
  01_feature_creation/   02_feature_engineering/   03_feature_selection/   04_model_training/
  05_model_test/         06_mlops/                 07_deployment/          08_aiops/
    each: config/ (stage.yaml + registry) · contract.yaml · src/ (run.py, plugins/) · tests/
          skills/ (LOCAL) · AGENTS.md · job.yml · README.md
platform/sql/      platform tables, catalogs, grants
tools/             code review agent, rerun-from-changes, task metrics logger
ci/                GitHub Actions workflows (move to .github/workflows/)
```

## Quick start
1. Run `platform/sql/02_catalogs_and_grants.sql`, `platform/sql/01_create_platform_tables.sql` and
   `tools/code_review_agent/sql/create_aidlc_reviews.sql`.
2. Merge `.specify/memory/constitution.aidlc-additions.md` into your constitution; copy the tasks template.
3. Replace `@org/...` teams in `CODEOWNERS`; turn on branch protection for `main`.
4. Move `ci/*.yml` to `.github/workflows/` and add the secrets listed in each file.
5. Put your existing feature engineering code in `stages/02_feature_engineering/src/plugins/`
   and register each group in `stages/02_feature_engineering/config/features.yaml`.
6. `pip install -e common -e "tools/code_review_agent[ci,dev]" && pytest -q`
7. `databricks bundle deploy -t dev`
