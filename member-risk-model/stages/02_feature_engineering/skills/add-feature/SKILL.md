---
name: add-feature
description: Use when adding or changing a feature group in 02_feature_engineering.
---

# Add a feature group
1. The spec must define the feature: sources, exact logic, as-of rule, grain, FR ID, and the keep rule (for example R² gain ≥ 0.005).
2. Add an entry to `config/features.yaml` with `plugin`, `sources`, `params`, `owner`, `spec`.
3. Copy `src/plugins/_template.py` to `src/plugins/<name>.py`. Output keyed on (member_id, target_year, cutoff_month).
4. Tests: as-of leakage test (skill `leakage-checks`), nulls, duplicate keys.
5. Output columns are prefixed with the group name; add them to `contract.yaml` under `feature_store`.
6. After merge, 03_feature_selection runs the ablation for this group automatically.
