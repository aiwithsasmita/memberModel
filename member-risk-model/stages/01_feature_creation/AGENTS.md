# 01_feature_creation: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Turn raw source data into clean, conformed tables: eligibility spine, standardized claims, Rx, MMR/MOR, diagnosis mapping (V28 HCC, CCSR).
- Spec: `specs/001-feature-creation/` · MRS-001 modules: M1 source profiling (Data Gate), M2 eligibility spine, M3 claims standardization, M4 diagnosis mapping
- Local skill: `skills/add-source/`. Registry: `config/sources.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/feature-creation-owners. Gate at the end of this stage: Data Gate.
