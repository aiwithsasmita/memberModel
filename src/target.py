"""
The training target -- non-negotiable rule #1.

    actual_cost_T(m)  = sum of allowed$ for m in year T, Part A+B categories,
                        EXCLUDING any month m was in hospice status
    exposure_T(m)     = enrolled months for m in year T  (drop m if this is 0)
    member_pmpm(m)    = actual_cost_T(m) / exposure_T(m)

    population_pmpm_T = sum(actual_cost_T) / sum(exposure_T)   over ALL members with exposure

    relative_target(m)        = member_pmpm(m) / population_pmpm_T
    relative_target_capped(m) = min(relative_target(m), P99.5 of relative_target in year T)

Why a ratio and not dollars: pooling raw dollars across years lets the model absorb
medical trend as if it were member risk. Dividing by that year's population PMPM removes
the year's cost level, and dividing by the member's own exposure removes partial-year
enrolment -- which is also why no separate LightGBM exposure offset is needed on top.

Train on relative_target_capped. Keep relative_target (uncapped) for reporting only.
"""

import numpy as np
import pandas as pd

import config


def build_target(spine, target_year):
    """
    Build the target for one calendar year.

    Returns (target_df, population_pmpm_T). population_pmpm_T is returned alongside
    because Phase 7 needs the history of it to project dollars for a future year.
    """
    year_rows = spine[spine["year"] == target_year]
    if len(year_rows) == 0:
        raise ValueError(f"no spine rows for target year {target_year}")

    # Exposure counts EVERY enrolled month, including hospice months. Dollars exclude
    # hospice months. That is the formula as written: hospice care is carved out of the
    # cost we are predicting, but the member was still a member those months.
    exposure = year_rows.groupby("member_id").size().rename("exposure_months")
    non_hospice = year_rows[year_rows["hospice"] == 0]
    actual_cost = (non_hospice.groupby("member_id")["cost_part_ab"].sum()
                   .reindex(exposure.index, fill_value=0.0)
                   .rename("actual_cost"))

    tgt = pd.concat([exposure, actual_cost], axis=1).reset_index()

    # A member with zero exposure has no rows here at all, so this is belt-and-braces.
    tgt = tgt[tgt["exposure_months"] > 0].copy()

    tgt["member_pmpm"] = tgt["actual_cost"] / tgt["exposure_months"]

    # Exposure-weighted population reference: sum of dollars over sum of months.
    # NOT the mean of member_pmpm -- that would over-weight one-month members.
    population_pmpm_T = float(tgt["actual_cost"].sum() / tgt["exposure_months"].sum())

    tgt["relative_target"] = tgt["member_pmpm"] / population_pmpm_T

    cap = float(tgt["relative_target"].quantile(config.CAP_PERCENTILE))
    tgt["relative_target_capped"] = tgt["relative_target"].clip(upper=cap)

    tgt.insert(1, "target_year", target_year)
    tgt.attrs["population_pmpm"] = population_pmpm_T
    tgt.attrs["cap_value"] = cap
    return tgt, population_pmpm_T


def build_targets_for_years(spine, years):
    """{year: target_df} plus {year: population_pmpm} for every requested year."""
    targets, pmpms = {}, {}
    for year in years:
        targets[year], pmpms[year] = build_target(spine, year)
    return targets, pmpms
