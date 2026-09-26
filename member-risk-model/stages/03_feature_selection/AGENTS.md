# 03_feature_selection: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Assemble the model dataset, run the leakage audit, and choose the feature set with configured methods (constant/null filters, correlation, importance, ablation).
- Spec: `specs/003-feature-selection/` · MRS-001 modules: M8 feature assembly and leakage audit (Feature Gate), feature selection
- Local skill: `skills/add-selection-method/`. Registry: `config/selection.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/feature-engineering-owners. Gate at the end of this stage: Feature Gate.
