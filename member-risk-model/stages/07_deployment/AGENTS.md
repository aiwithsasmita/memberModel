# 07_deployment: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Batch-score all active members with @champion at each cutoff and publish scores with model version and run date.
- Spec: `specs/007-deployment/` · MRS-001 modules: M16 scoring workflow, bundle targets
- Local skill: `skills/deployment/`. Registry: `config/scoring.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/platform-owners. Gate at the end of this stage: Production deploy.
