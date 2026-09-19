"""
Phase 2 -- the member-month spine.

One row per member per ENROLLED month, with that month's dollars, utilisation counts and
the member-year's MOR attached. This is the ONLY place the three raw tables get joined;
target.py, features.py and everything downstream read the spine and nothing else.

Two columns exist purely for the leakage machinery in features.py:
    month_start      -- the date the MMR record is known (first of the month)
    max_claim_date   -- the latest service_date among that month's claims (NaT if none)
    mor_source_date  -- the date the member-year's MOR sweep is known
Every feature block records the max of one of these as its "source date", and
assert_no_future_leakage refuses anything dated on or after the as_of_date.
"""

import numpy as np
import pandas as pd

import config


def build_spine(mmr, claims, mor):
    """Join mmr + claims + mor into one member-month table."""
    spine = mmr.copy()

    # ---- claims -> one row per (member, month), wide by category -----------
    monthly = claims.groupby(["member_id", "year", "month", "category"], as_index=False).agg(
        cost=("allowed_amount", "sum"),
        n_claims=("claim_id", "size"),
    )
    costs = monthly.pivot_table(index=["member_id", "year", "month"], columns="category",
                                values="cost", fill_value=0.0)
    counts = monthly.pivot_table(index=["member_id", "year", "month"], columns="category",
                                 values="n_claims", fill_value=0)
    # A category with no claims anywhere would be missing from the pivot; add it as zero
    # so the spine always has the same columns regardless of the data drawn.
    costs = costs.reindex(columns=config.COST_CATEGORIES, fill_value=0.0)
    counts = counts.reindex(columns=config.COST_CATEGORIES, fill_value=0)
    costs.columns = [f"cost_{c}" for c in costs.columns]
    counts.columns = [f"claims_{c}" for c in counts.columns]

    last_service = claims.groupby(["member_id", "year", "month"])["service_date"].max()
    last_service.name = "max_claim_date"

    spine = (spine
             .merge(costs, on=["member_id", "year", "month"], how="left")
             .merge(counts, on=["member_id", "year", "month"], how="left")
             .merge(last_service, on=["member_id", "year", "month"], how="left"))

    # A month with no claims is a real $0 month, not a missing value.
    cost_cols = [f"cost_{c}" for c in config.COST_CATEGORIES]
    claim_cols = [f"claims_{c}" for c in config.COST_CATEGORIES]
    spine[cost_cols] = spine[cost_cols].fillna(0.0)
    spine[claim_cols] = spine[claim_cols].fillna(0).astype(int)

    # Part A+B is what the target is built from; rx (Part D) is a feature only.
    spine["cost_part_ab"] = spine[[f"cost_{c}" for c in config.PART_AB_CATEGORIES]].sum(axis=1)
    spine["cost_total"] = spine[cost_cols].sum(axis=1)
    spine["claims_total"] = spine[claim_cols].sum(axis=1)

    # ---- mor -> attached at the member-YEAR grain --------------------------
    spine = spine.merge(mor, on=["member_id", "year"], how="left", suffixes=("", "_mor"))
    spine = spine.rename(columns={"source_date": "mor_source_date"})

    spine = spine.sort_values(["member_id", "year", "month"], ignore_index=True)
    _validate_spine(spine)
    return spine


def _validate_spine(spine):
    """Cheap structural checks -- a broken spine poisons every later phase silently."""
    key = ["member_id", "year", "month"]
    assert not spine.duplicated(key).any(), "spine must be one row per member-month"
    assert spine["cost_part_ab"].min() >= 0, "negative Part A+B dollars in the spine"
    assert spine["month_start"].notna().all(), "every spine row needs a month_start"
    # Claim dollars must never be attributed to a month the member was not enrolled in:
    # the merge is a LEFT join from mmr, so this holds by construction -- assert it anyway.
    claimed = spine.loc[spine["cost_total"] > 0, "max_claim_date"]
    assert claimed.notna().all(), "a month has dollars but no claim date"


def population_pmpm(spine, year):
    """
    Population PMPM for one calendar year, on Part A+B dollars.

        population_pmpm = sum(actual_cost over all members) / sum(exposure over all members)

    Note this is the exposure-WEIGHTED figure (sum over sum), not the average of member
    PMPMs. It is used twice: as the denominator of the target (target.py) and as the
    denominator that puts the base-year cost features on a relative basis (features.py).
    """
    year_rows = spine[spine["year"] == year]
    if len(year_rows) == 0:
        raise ValueError(f"no spine rows for year {year}")
    # Hospice months are excluded from dollars but still count as exposure -- see target.py.
    dollars = year_rows.loc[year_rows["hospice"] == 0, "cost_part_ab"].sum()
    exposure = len(year_rows)
    return float(dollars / exposure)


def population_pmpm_history(spine, years=None):
    """{year: population_pmpm} for every year present in the spine."""
    years = years if years is not None else sorted(spine["year"].unique())
    return {int(y): population_pmpm(spine, y) for y in years}
