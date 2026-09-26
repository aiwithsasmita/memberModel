---
name: claims-data-rules
description: Use when reading or transforming claims, eligibility, MMR/MOR or diagnosis data: claims lag, reversals, member-months, V28 HCC and CCSR mapping.
---

# Claims data rules

- **Allowed amount** is the cost basis unless the spec says paid.
- **Reversals and adjustments:** net to the final claim before any aggregation; one row per final claim.
- **Claims lag:** features may only use claims with `paid_date <= cutoff_date - claims_lag_days` (from config). Service dates must be before the cutoff.
- **Member-months:** exposure = eligible months; always weight annualized values by `remaining_member_months / 12`.
- **HCC version:** map every year to CMS-HCC **V28**; never mix V24 and V28. Keep pre-hierarchy flags as well as post-hierarchy.
- **CCSR:** map all diagnoses (not only payment HCCs); keep default and all categories.
- **Risk adjustment eligible diagnoses** only for HCC features; all diagnoses for CCSR.
- **PHI:** never print, log or send member identifiers to a model or MLflow. Use aggregates or hashed IDs.
- **Grain:** feature tables are keyed on (member_id, target_year, cutoff_month). Check for duplicate keys after every join.
