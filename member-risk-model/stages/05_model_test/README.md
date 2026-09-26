# 05 · Model test

Score every candidate and the current champion on the LOCKED evaluation protocol (MRS-001 section 2A and M14), including CMS comparison, bootstrap intervals and the golden test.

| | |
| --- | --- |
| Spec | `specs/005-model-test/` |
| MRS-001 modules | M14 evaluation vs CMS (Model Gate), champion vs challenger comparison |
| Reads | `pred_candidates`, `target` |
| Writes | `eval_metrics`, `eval_pr`, `comparison_verdicts` |
| Registry | `config/evaluation.yaml` |
| Local skill | `skills/cms-risk-comparison/` |
| Gate | Model Gate |
| Owners | @org/model-owner |

**Extend:** add an entry to `config/evaluation.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_05_model_test` · **Test:** `pytest -q stages/05_model_test/tests`
