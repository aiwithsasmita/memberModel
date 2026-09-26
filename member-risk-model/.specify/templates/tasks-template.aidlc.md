# Tasks: [FEATURE NAME]

**Spec**: specs/[NNN-name]/spec.md · **Plan**: specs/[NNN-name]/plan.md · **Change request**: CR-[NNN]

## Format (required by the code review agent)
`- [ ] T### [P?] [US#] (FR-###, FR-###) Description with the exact file path`

- `[P]` only when the task touches different files with no dependencies.
- `(FR-###)` lists every requirement the task implements. Tasks with no FR (setup) may omit it.
- The path must be the real file, e.g. `stages/02_feature_engineering/src/plugins/renal.py`.

## Phase 1: Setup
- [ ] T001 Add registry entry in stages/NN_stage/config/<registry>.yaml

## Phase 2: User Story 1 (P1)
- [ ] T002 [US1] (FR-001) Implement ... in stages/NN_stage/src/plugins/<name>.py
- [ ] T003 [P] [US1] (FR-001) Tests in stages/NN_stage/tests/test_<name>.py

## Phase N: Gate and metrics
- [ ] T0NN Prepare gate evidence (skill gate-review) in gates/NNN-name/<GATE>.md
