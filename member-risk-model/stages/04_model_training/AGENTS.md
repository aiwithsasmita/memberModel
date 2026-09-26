# 04_model_training: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Train baselines and candidate models from the model registry with hyperparameter search, then calibrate per cutoff. Every algorithm is a plugin.
- Spec: `specs/004-model-training/` · MRS-001 modules: M9 baselines, M10 main model, M11 high-cost classifier, M12 excess layer, M13 calibration
- Local skill: `skills/add-model/`. Registry: `config/models.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/ml-owners.
