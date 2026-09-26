---
name: drift-triage
description: Use when handling a monitor alert or job failure in 08_aiops.
---

# Drift triage
1. Read the alert, the last 3 monitor windows and the relevant job runs.
2. Classify: data change (source/schema), coding change (e.g. HCC mix shift), pipeline failure, or real population shift.
3. Act by class, following `config/agents.yaml` allowed actions: repair once, open a change request, or start a challenger retrain.
4. Write the diagnosis to the change request with evidence links. Never promote or deploy.
