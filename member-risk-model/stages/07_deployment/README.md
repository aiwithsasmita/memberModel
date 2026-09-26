# 07 · Deployment

Batch-score all active members with @champion at each cutoff and publish scores with model version and run date.

| | |
| --- | --- |
| Spec | `specs/007-deployment/` |
| MRS-001 modules | M16 scoring workflow, bundle targets |
| Reads | `feature_store`, `selected_features` |
| Writes | `member_risk_scores` |
| Registry | `config/scoring.yaml` |
| Local skill | `skills/deployment/` |
| Gate | Production deploy |
| Owners | @org/platform-owners |

**Extend:** add an entry to `config/scoring.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_07_deployment` · **Test:** `pytest -q stages/07_deployment/tests`
