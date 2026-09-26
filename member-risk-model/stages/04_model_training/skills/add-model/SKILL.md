---
name: add-model
description: Use when adding a modeling algorithm to 04_model_training.
---

# Add an algorithm
1. The spec must say why this algorithm, its search space, trial budget and the acceptance rule.
2. Create `src/plugins/<algo>.py` implementing `ModelPlugin` (fit, predict, get_params, log_model) from `src/plugins/base.py`.
3. Add an entry to `config/models.yaml` with `plugin`, `role: candidate`, and `search`.
4. Tests: trains on a 1,000-row synthetic sample, predictions non-negative, logs with required tags.
5. Do not touch splits, evaluation or the pipeline. 05_model_test scores it; it becomes challenger only if it wins.
