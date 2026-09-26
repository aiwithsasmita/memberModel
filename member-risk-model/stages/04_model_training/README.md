# 04 · Model training

Train baselines and candidate models from the model registry with hyperparameter search, then calibrate per cutoff. Every algorithm is a plugin.

| | |
| --- | --- |
| Spec | `specs/004-model-training/` |
| MRS-001 modules | M9 baselines, M10 main model, M11 high-cost classifier, M12 excess layer, M13 calibration |
| Reads | `model_dataset`, `selected_features` |
| Writes | `candidate_models`, `pred_candidates` |
| Registry | `config/models.yaml` |
| Local skill | `skills/add-model/` |
| Gate | none |
| Owners | @org/ml-owners |

**Extend:** add an entry to `config/models.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_04_model_training` · **Test:** `pytest -q stages/04_model_training/tests`
