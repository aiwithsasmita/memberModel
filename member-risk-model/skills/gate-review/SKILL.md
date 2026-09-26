---
name: gate-review
description: Use when a stage is ready for a gate (Data, Target, Feature, Model, Promotion): collect evidence and draft the gate record for a person to sign.
---

# Preparing a gate

1. Run the stage's checks and write results to Delta (evidence tables).
2. Draft `gates/NNN-*/<GATE>.md` from `gates/_template.md`: gate, stage, spec ID, change request, evidence links, check results.
3. Leave **Approver**, **Decision** and **Approved at** empty. Only the named approver fills them, in the PR.
4. On merge, CI writes the approval row to `aidlc_gates` (gate, approver, timestamp, commit).
5. Never mark a gate approved yourself.
