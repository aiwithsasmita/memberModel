# 06_mlops: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Register models in Unity Catalog with full lineage, manage @champion / @challenger aliases, and run the MLflow 3 deployment job (evaluate, human approval, promote).
- Spec: `specs/006-mlops/` · MRS-001 modules: Registry, aliases, promotion rules, MLflow deployment job
- Local skill: `skills/model-promotion/`. Registry: `config/promotion.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/ml-owners. Gate at the end of this stage: Promotion.
