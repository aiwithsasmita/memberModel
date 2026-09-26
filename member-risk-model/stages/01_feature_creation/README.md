# 01 · Feature creation

Turn raw source data into clean, conformed tables: eligibility spine, standardized claims, Rx, MMR/MOR, diagnosis mapping (V28 HCC, CCSR).

| | |
| --- | --- |
| Spec | `specs/001-feature-creation/` |
| MRS-001 modules | M1 source profiling (Data Gate), M2 eligibility spine, M3 claims standardization, M4 diagnosis mapping |
| Reads | `raw_claims_medical`, `raw_claims_rx`, `raw_eligibility`, `raw_mmr`, `raw_mor` |
| Writes | `member_month_spine`, `claims_std`, `member_dx_events` |
| Registry | `config/sources.yaml` |
| Local skill | `skills/add-source/` |
| Gate | Data Gate |
| Owners | @org/feature-creation-owners |

**Extend:** add an entry to `config/sources.yaml` and a plugin in `src/plugins/` (see the local skill).
**Run alone:** `databricks bundle run mrs_01_feature_creation` · **Test:** `pytest -q stages/01_feature_creation/tests`
