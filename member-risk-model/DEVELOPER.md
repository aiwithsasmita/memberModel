# DEVELOPER.md: how we work

## The change flow
| # | Step | Who | How |
| --- | --- | --- | --- |
| 1 | Log the change request | Anyone | Row in `aidlc_change_requests` (gets CR-NNN) |
| 2 | Branch | Developer | `feature/NNN-short-name` from `main` |
| 3 | Spec | Developer + agent | `/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` in `specs/NNN-short-name/` |
| 4 | Check | Automatic | `/speckit.analyze` must show no critical issues |
| 5 | **Approve spec** | Tech lead | Reviews the spec PR; fills `gates/NNN-short-name/SPEC_APPROVAL.md` (name, date, time); merge locks the spec |
| 6 | Implement | Code owner + agent | `/speckit.implement` with global + stage skills |
| 7 | Review | Automatic | Code review agent on the PR (traced tasks, exact FRs, no assumptions, no leakage/PHI) |
| 8 | **Approve code** | Stage code owner | PR approval; CI green |
| 9 | Rebuild | Automatic | Pipeline reruns from the earliest changed stage (`tools/rerun_from_changes.py`) |
| 10 | Compete | Automatic | Challenger vs champion on the locked evaluation |
| 11 | **Promote** | Approvers | MLflow deployment job approval |

## Rules
- One change = one branch = one spec folder. Keep PRs small (one stage where possible).
- **Tasks must name their files and FR IDs:** `- [ ] T014 [US1] (FR-003) Build ER features in stages/02_feature_engineering/src/plugins/utilization.py`
- **Changing an approved spec** needs the tech lead again (CODEOWNERS on `specs/`) and restarts the flow from step 4.
- **Only code owners** of a stage can approve changes to it. Nobody pushes to `main`.
- Log each finished task to `aidlc_task_metrics` (`tools/log_task_metrics.py`): it powers the leadership dashboard.

## Common changes
| Change | Where | New spec? |
| --- | --- | --- |
| New data source | `stages/01_feature_creation/config/sources.yaml` + plugin | Yes |
| New feature | `stages/02_feature_engineering/config/features.yaml` + plugin + tests | Yes |
| Feature logic change | the feature's plugin + tests | Yes (spec change) |
| Selection rule | `stages/03_feature_selection/config/selection.yaml` | Only for a new method |
| New algorithm | `stages/04_model_training/config/models.yaml` + plugin + tests | Yes |
| Training window / params | `stages/04_model_training/config/models.yaml` | No |
| Evaluation protocol | `stages/05_model_test/config/evaluation.yaml` (locked) | Yes + model owner |
| Scoring schedule | `stages/07_deployment/config/scoring.yaml` | No |
| Monitor threshold | `stages/08_aiops/config/monitors.yaml` | No |
