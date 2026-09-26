---
name: model-promotion
description: Use when working in 06_mlops: registry, aliases and the deployment job.
---

# Model promotion
- Register with lineage tags from `config/promotion.yaml`; registration fails if any is missing.
- A new version gets `@challenger` only when 05_model_test's verdict is `win`.
- Promotion to `@champion` only through the MLflow deployment job approval tasks. Never set the alias in code.
- Rollback = a person moves `@champion` back to the previous version.
