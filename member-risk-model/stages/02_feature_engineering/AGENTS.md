# 02_feature_engineering: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Build the member x target_year x cutoff_month snapshot, the target, and all feature tables. Your existing feature engineering code lives here.
- Spec: `specs/002-feature-engineering/` · MRS-001 modules: M5 snapshot builder, M6 target builder (Target Gate), M7a-M7h feature modules
- Local skill: `skills/add-feature/`. Registry: `config/features.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/feature-engineering-owners. Gate at the end of this stage: Target Gate.
- Your existing feature engineering code goes in `src/plugins/`, one file per feature group, each registered in `config/features.yaml`.
