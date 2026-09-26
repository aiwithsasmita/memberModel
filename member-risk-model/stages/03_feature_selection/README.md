# 03 · Feature selection

Assemble the model dataset, run the leakage audit, and choose the feature set with configured methods (constant/null filters, correlation, importance, ablation).

| | |
| --- | --- |
| Spec | `specs/003-feature-selection/` |
| MRS-001 modules | M8 feature assembly and leakage audit (Feature Gate), feature selection |
| Reads | `snapshot`, `target`, `feature_store` |
| Writes | `model_dataset`, `selected_features` |
| Registry | `config/selection.yaml` |
| Local skill | `skills/add-selection-method/` |
| Gate | Feature Gate |
| Owners | @org/feature-engineering-owners |

**Extend:** add an entry to `config/selection.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_03_feature_selection` · **Test:** `pytest -q stages/03_feature_selection/tests`
