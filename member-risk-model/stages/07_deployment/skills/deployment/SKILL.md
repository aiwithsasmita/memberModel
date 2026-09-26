---
name: deployment
description: Use when changing jobs, schedules, bundle targets or scoring in 07_deployment.
---

# Deployment conventions
- Every job is defined in its stage's `job.yml` and included by `databricks.yml`.
- dev/test/prod differ only by bundle variables (catalogs, endpoints). No environment logic in code.
- Scoring uses `@champion` only; schedules come from `config/scoring.yaml`.
- Prod deploys only through CI after environment approval.
