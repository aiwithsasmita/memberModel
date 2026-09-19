"""
Phase 1 -- synthetic raw data.

Writes three parquet tables to data/raw/ that imitate the shape (not the scale) of the
real inputs:

    mmr.parquet     one row per member per ENROLLED month -- demographics
    claims.parquet  one row per (member, month, category) with dollars -- one "claim"
    mor.parquet     one row per member per year -- HCC flags + raf_score

Everything is driven by a single latent `true_risk` per member-year. That latent value
drives cost, HCC flags and raf_score together, so the pipeline has real (if simple)
signal to recover, and so raf_score is a *decent but imperfect* baseline -- the same
relationship the real CMS RAF has with next year's cost.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config


def _month_grid(years):
    """All (year, month) pairs across `years`, in calendar order."""
    return [(y, m) for y in years for m in range(1, 13)]


def _draw_true_risk(rng, n_members, n_years):
    """
    Latent risk: drawn once per member (lognormal), then nudged each year to imitate
    disease progression. Each year is renormalised to mean 1.0 so that *risk* carries
    no time trend -- the dollar trend is applied separately and explicitly below.
    """
    base = rng.lognormal(mean=0.0, sigma=config.TRUE_RISK_SIGMA, size=n_members)
    base /= base.mean()

    risk = np.empty((n_members, n_years))
    risk[:, 0] = base
    for j in range(1, n_years):
        nudge = rng.lognormal(mean=0.0, sigma=config.TRUE_RISK_DRIFT_SIGMA, size=n_members)
        risk[:, j] = risk[:, j - 1] * nudge
        risk[:, j] /= risk[:, j].mean()
    return risk


def _draw_enrollment(rng, n_members, n_months):
    """
    First and last enrolled month index for each member, on the 0..n_months-1 grid.

    Most members are enrolled for the whole window. A slice start late -- these become
    the NEW ENROLLEES that Phase 5 routes down a separate code path -- and a slice leave
    early, which exercises the partial-year exposure logic in the target formula.
    """
    first = np.zeros(n_members, dtype=int)
    late = rng.random(n_members) < config.LATE_ENROLLMENT_RATE
    # Late starters begin between Feb 2022 and Dec 2025, so every one of the target
    # years 2023 / 2024 / 2025 has a real population of new enrollees.
    first[late] = rng.integers(1, n_months - 12, size=int(late.sum()))

    last = np.full(n_members, n_months - 1, dtype=int)
    leaves = rng.random(n_members) < config.DISENROLLMENT_RATE
    for i in np.flatnonzero(leaves):
        earliest_exit = min(first[i] + 6, n_months - 1)
        last[i] = rng.integers(earliest_exit, n_months)
    return first, last


def generate(seed=config.RANDOM_SEED, verbose=True):
    rng = np.random.default_rng(seed)

    months = _month_grid(config.YEARS)
    n_months = len(months)
    n_members = config.N_MEMBERS
    member_ids = np.arange(1, n_members + 1)
    year_index = {y: j for j, y in enumerate(config.YEARS)}

    true_risk = _draw_true_risk(rng, n_members, len(config.YEARS))
    first_idx, last_idx = _draw_enrollment(rng, n_members, n_months)

    # ---- member-level fixed attributes ------------------------------------
    # Age is mildly correlated with risk, the way it is in a real book.
    base_age = np.clip(
        65 + rng.gamma(shape=3.0, scale=3.0, size=n_members) + 4.0 * np.log(true_risk[:, 0]),
        65, 99,
    ).astype(int)
    sex = rng.choice(["M", "F"], size=n_members, p=[0.45, 0.55])
    dual = (rng.random(n_members) < config.DUAL_RATE).astype(int)
    orec = rng.choice([0, 1, 2, 3], size=n_members, p=[0.72, 0.18, 0.06, 0.04])
    esrd = (rng.random(n_members) < config.ESRD_RATE).astype(int)
    county_id = rng.integers(1, config.N_COUNTIES + 1, size=n_members)
    pcp_provider_id = rng.integers(1, config.N_PROVIDERS + 1, size=n_members)

    # ---- the enrolled member-month grid -----------------------------------
    month_idx = np.arange(n_months)
    enrolled = (month_idx[None, :] >= first_idx[:, None]) & (month_idx[None, :] <= last_idx[:, None])
    mem_pos, mon_pos = np.nonzero(enrolled)          # one entry per enrolled member-month

    grid_year = np.array([months[k][0] for k in mon_pos])
    grid_month = np.array([months[k][1] for k in mon_pos])
    grid_member = member_ids[mem_pos]
    grid_risk = true_risk[mem_pos, [year_index[y] for y in grid_year]]

    # ---- hospice: rare, and concentrated at the end of a member-year -------
    hospice = np.zeros(len(mem_pos), dtype=int)
    member_years = pd.DataFrame({
        "pos": np.arange(len(mem_pos)),
        "member_id": grid_member,
        "year": grid_year,
    })
    my_groups = member_years.groupby(["member_id", "year"], sort=False)["pos"].apply(list)
    hospice_pick = rng.random(len(my_groups)) < config.HOSPICE_MEMBER_YEAR_RATE
    for positions in my_groups[hospice_pick]:
        n_hospice_months = min(len(positions), int(rng.integers(1, 4)))
        hospice[positions[-n_hospice_months:]] = 1

    # ---- monthly cost ------------------------------------------------------
    # Probability of having any claim rises with risk; the amount is right-skewed.
    claim_prob = np.clip(config.BASE_MONTHLY_CLAIM_PROB * grid_risk ** 0.7, 0.02, 0.95)
    has_claim = rng.random(len(mem_pos)) < claim_prob

    trend = config.ANNUAL_COST_TREND ** (grid_year - config.YEARS[0])
    raw_amount = rng.lognormal(config.CLAIM_AMOUNT_LOG_MU, config.CLAIM_AMOUNT_LOG_SIGMA,
                               size=len(mem_pos))
    month_amount = np.where(has_claim, raw_amount * grid_risk * trend, 0.0)

    # ---- catastrophic member-years (this is what makes the tail fat) -------
    cat_pick = rng.random(len(my_groups)) < config.CATASTROPHIC_RATE
    cat_multipliers = rng.uniform(*config.CATASTROPHIC_MULTIPLIER, size=int(cat_pick.sum()))
    for positions, mult in zip(my_groups[cat_pick], cat_multipliers):
        month_amount[positions] *= mult

    # ---- MMR table ---------------------------------------------------------
    mmr = pd.DataFrame({
        "member_id": grid_member,
        "year": grid_year,
        "month": grid_month,
        "month_start": pd.to_datetime(dict(year=grid_year, month=grid_month, day=1)),
        "age": base_age[mem_pos] + (grid_year - config.YEARS[0]),
        "sex": sex[mem_pos],
        "dual": dual[mem_pos],
        "orec": orec[mem_pos],
        "esrd": esrd[mem_pos],
        "hospice": hospice,
        "county_id": county_id[mem_pos],
        "pcp_provider_id": pcp_provider_id[mem_pos],
    }).sort_values(["member_id", "year", "month"], ignore_index=True)

    # ---- claims table ------------------------------------------------------
    # Split each claim-month's dollars across the five categories with roughly fixed
    # proportions (Dirichlet noise around CATEGORY_SHARES), one row per category.
    claim_pos = np.flatnonzero(month_amount > 0)
    n_claim_months = len(claim_pos)
    alpha = np.array([config.CATEGORY_SHARES[c] for c in config.COST_CATEGORIES]) * 20.0
    gammas = rng.gamma(shape=alpha, size=(n_claim_months, len(config.COST_CATEGORIES)))
    shares = gammas / gammas.sum(axis=1, keepdims=True)
    amounts = shares * month_amount[claim_pos][:, None]

    n_cat = len(config.COST_CATEGORIES)
    rep_member = np.repeat(grid_member[claim_pos], n_cat)
    rep_year = np.repeat(grid_year[claim_pos], n_cat)
    rep_month = np.repeat(grid_month[claim_pos], n_cat)
    rep_category = np.tile(np.array(config.COST_CATEGORIES), n_claim_months)
    rep_amount = amounts.ravel()

    keep = rep_amount >= 1.0   # drop trivial slivers
    # Service days are capped at 28 so that a December claim is always strictly before
    # an as_of_date of December 31 -- the leakage assertion in features.py is date-based.
    service_day = rng.integers(1, 29, size=int(keep.sum()))
    claims = pd.DataFrame({
        "member_id": rep_member[keep],
        "year": rep_year[keep],
        "month": rep_month[keep],
        "service_date": pd.to_datetime(dict(year=rep_year[keep], month=rep_month[keep],
                                            day=service_day)),
        "category": rep_category[keep],
        "allowed_amount": np.round(rep_amount[keep], 2),
    }).sort_values(["member_id", "service_date", "category"], ignore_index=True)
    claims.insert(0, "claim_id", np.arange(1, len(claims) + 1))

    # ---- MOR table ---------------------------------------------------------
    # One row per member-year the member was enrolled in at all. HCC flag probabilities
    # and raf_score both rise with true_risk, raf_score with real noise on top.
    mor_keys = member_years.drop_duplicates(["member_id", "year"]).reset_index(drop=True)
    mor_risk = true_risk[mor_keys["member_id"].values - 1,
                         [year_index[y] for y in mor_keys["year"].values]]

    flag_base_p = rng.uniform(0.02, 0.25, size=config.N_HCC_FLAGS)
    hcc_matrix = (
        rng.random((len(mor_keys), config.N_HCC_FLAGS))
        < np.clip(flag_base_p[None, :] * (mor_risk[:, None] ** 0.8), 0, 0.95)
    ).astype(int)
    hcc_cols = [f"hcc_{k + 1:02d}" for k in range(config.N_HCC_FLAGS)]

    raf_noise = rng.lognormal(0.0, 0.30, size=len(mor_keys))
    raf_score = np.clip(0.35 + 0.70 * mor_risk * raf_noise, 0.20, 8.0)

    mor = pd.DataFrame(hcc_matrix, columns=hcc_cols)
    mor.insert(0, "member_id", mor_keys["member_id"].values)
    mor.insert(1, "year", mor_keys["year"].values)
    mor["hcc_count"] = hcc_matrix.sum(axis=1)
    mor["raf_score"] = np.round(raf_score, 4)
    # Explicit source date for the leakage assertion. See README "Assumptions": the real
    # MOR for year Y lands partway through Y+1; here we treat the year's final sweep as
    # available on Dec 1 of the same year. Changing that assumption is this one line.
    mor["source_date"] = pd.to_datetime(dict(year=mor["year"], month=12, day=1))
    mor = mor.sort_values(["member_id", "year"], ignore_index=True)

    # ---- write -------------------------------------------------------------
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    mmr.to_parquet(config.RAW_DIR / "mmr.parquet", index=False)
    claims.to_parquet(config.RAW_DIR / "claims.parquet", index=False)
    mor.to_parquet(config.RAW_DIR / "mor.parquet", index=False)

    if verbose:
        _print_diagnostics(mmr, claims, mor, month_amount)
    return mmr, claims, mor


def load_raw():
    """Read the three raw tables back. Every later phase starts here."""
    mmr = pd.read_parquet(config.RAW_DIR / "mmr.parquet")
    claims = pd.read_parquet(config.RAW_DIR / "claims.parquet")
    mor = pd.read_parquet(config.RAW_DIR / "mor.parquet")
    return mmr, claims, mor


def _print_diagnostics(mmr, claims, mor, month_amount):
    """Confirm by eye that the cost distribution is skewed, not roughly normal."""
    print("\n--- Phase 1: synthetic data ------------------------------------")
    print(f"mmr     rows: {len(mmr):>8,}  (member-months enrolled)")
    print(f"claims  rows: {len(claims):>8,}  (member-month-category)")
    print(f"mor     rows: {len(mor):>8,}  (member-years)")

    zero_rate = float((month_amount == 0).mean())
    print(f"\nmember-month zero-cost rate  : {zero_rate:.1%}")

    levels = [50, 75, 90, 95, 99, 99.9]
    pct = np.percentile(month_amount, levels)
    print("member-month cost percentiles: "
          + "  ".join(f"p{p}=${v:,.0f}" for p, v in zip(levels, pct)))

    annual = claims.groupby(["member_id", "year"])["allowed_amount"].sum()
    pct = np.percentile(annual, levels)
    print("member-YEAR cost percentiles : "
          + "  ".join(f"p{p}=${v:,.0f}" for p, v in zip(levels, pct)))
    print(f"mean vs median member-year   : ${annual.mean():,.0f} vs ${annual.median():,.0f}"
          "   (mean >> median = right-skewed, as intended)")


if __name__ == "__main__":
    generate()
