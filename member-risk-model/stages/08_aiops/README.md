# 08 · AI Ops

Monitor data and model drift, alert, and run the agents: AI Ops (triage, retrain as challenger, change requests), deployment agent (readiness, post-deploy checks), change agent (config-only changes). Code review agent lives in tools/.

| | |
| --- | --- |
| Spec | `specs/008-aiops/` |
| MRS-001 modules | M16 monitoring, AI Ops agent, deployment agent, change agent |
| Reads | `member_risk_scores`, `feature_store`, `eval_pr` |
| Writes | `monitor_metrics` |
| Registry | `config/monitors.yaml` |
| Local skill | `skills/drift-triage/` |
| Gate | none |
| Owners | @org/aiops-owners |

**Extend:** add an entry to `config/monitors.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_08_aiops` · **Test:** `pytest -q stages/08_aiops/tests`
