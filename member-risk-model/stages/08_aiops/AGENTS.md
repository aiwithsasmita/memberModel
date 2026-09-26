# 08_aiops: local agent rules

Read the root `AGENTS.md` first. In this stage:
- Purpose: Monitor data and model drift, alert, and run the agents: AI Ops (triage, retrain as challenger, change requests), deployment agent (readiness, post-deploy checks), change agent (config-only changes). Code review agent lives in tools/.
- Spec: `specs/008-aiops/` · MRS-001 modules: M16 monitoring, AI Ops agent, deployment agent, change agent
- Local skill: `skills/drift-triage/`. Registry: `config/monitors.yaml`.
- Read and write only the tables in `contract.yaml`. Do not import from other stages.
- Code owners: @org/aiops-owners.
