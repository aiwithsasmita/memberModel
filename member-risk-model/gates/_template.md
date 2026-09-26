# Gate: <Spec approval | Data Gate | Target Gate | Feature Gate | Model Gate | Production deploy>

| Field | Value |
| --- | --- |
| Spec | specs/NNN-name |
| Change request | CR-NNN |
| Stage | NN_stage |
| Evidence | links to evidence tables, MLflow runs, review IDs |
| Checks | pass/fail summary |
| **Decision** | approved / rejected (approver fills) |
| **Approver** | name (approver fills) |
| **Approved at** | YYYY-MM-DD HH:MM in UTC (approver fills) |

File name = gate name: `SPEC_APPROVAL.md`, `DATA_GATE.md`, `TARGET_GATE.md`, `FEATURE_GATE.md`, `MODEL_GATE.md`,
`PRODUCTION_DEPLOY.md`, inside `gates/NNN-name/`.

Agents may draft this file. Only the named approver fills Decision, Approver and Approved at, in the PR.
On merge, CI writes the row to `aidlc_platform.aidlc_gates`.
