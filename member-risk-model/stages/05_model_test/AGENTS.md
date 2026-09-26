# 05_model_test: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Score every candidate and the current champion on the LOCKED evaluation protocol (MRS-001 section 2A and M14), including CMS comparison, bootstrap intervals and the golden test.
- Spec: `specs/005-model-test/` · MRS-001 modules: M14 evaluation vs CMS (Model Gate), champion vs challenger comparison
- Local skill: `skills/cms-risk-comparison/`. Registry: `config/evaluation.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/model-owner. Gate at the end of this stage: Model Gate.
- `config/evaluation.yaml` is LOCKED. Never edit it.
