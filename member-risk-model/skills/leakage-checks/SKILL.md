---
name: leakage-checks
description: Use when building or reviewing any feature, target or filter: how to prove no data from on or after the cutoff is used.
---

# Proving there is no leakage

Every feature table needs these tests (in the stage's `tests/`):

1. **As-of test:** on a 1% sample, recompute the feature from raw data and assert `max(paid_date) <= feature_asof_date` and `max(service_date) < cutoff_date` for every row used.
2. **Target isolation:** assert no feature column is computed from target-period rows (service_date >= cutoff_date).
3. **Shuffle test (Feature Gate):** a quick model on shuffled targets must reach R² ≤ 0.01.
4. **Sniff test:** no single feature correlates above 0.9 with the target at cutoff 0.

Common leakage patterns to look for:
- filtering on `service_date` only and forgetting `paid_date`,
- using month-end of the cutoff month instead of the cutoff date,
- window functions that look forward,
- joining tables that were refreshed after the cutoff (use Delta versions from the contract).
