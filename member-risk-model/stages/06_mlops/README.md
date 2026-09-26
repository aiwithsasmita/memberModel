# 06 · MLOps

Register models in Unity Catalog with full lineage, manage @champion / @challenger aliases, and run the MLflow 3 deployment job (evaluate, human approval, promote).

| | |
| --- | --- |
| Spec | `specs/006-mlops/` |
| MRS-001 modules | Registry, aliases, promotion rules, MLflow deployment job |
| Reads | `candidate_models`, `comparison_verdicts` |
| Writes | `model_registry_events` |
| Registry | `config/promotion.yaml` |
| Local skill | `skills/model-promotion/` |
| Gate | Promotion |
| Owners | @org/ml-owners |

**Extend:** add an entry to `config/promotion.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_06_mlops` · **Test:** `pytest -q stages/06_mlops/tests`
