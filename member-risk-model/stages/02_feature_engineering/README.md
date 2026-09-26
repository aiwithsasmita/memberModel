# 02 · Feature engineering

Build the member x target_year x cutoff_month snapshot, the target, and all feature tables. Your existing feature engineering code lives here.

| | |
| --- | --- |
| Spec | `specs/002-feature-engineering/` |
| MRS-001 modules | M5 snapshot builder, M6 target builder (Target Gate), M7a-M7h feature modules |
| Reads | `member_month_spine`, `claims_std`, `member_dx_events` |
| Writes | `snapshot`, `target`, `feature_store` |
| Registry | `config/features.yaml` |
| Local skill | `skills/add-feature/` |
| Gate | Target Gate |
| Owners | @org/feature-engineering-owners |

**Extend:** add an entry to `config/features.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_02_feature_engineering` · **Test:** `pytest -q stages/02_feature_engineering/tests`
