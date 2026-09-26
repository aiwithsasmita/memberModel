---
name: add-selection-method
description: Use when adding a feature selection method to 03_feature_selection.
---

# Add a selection method
1. Add the method to `config/selection.yaml` with params.
2. Implement `src/plugins/<method>.py` from the template: input feature list + stats, output kept list + reasons.
3. Log kept/dropped features and reasons to MLflow.
4. Tests on a small synthetic table.
