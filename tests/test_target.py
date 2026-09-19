"""
Rule #1: the target is a capped PMPM ratio to that year's population mean -- never raw
dollars pooled across years.

The first tests use hand-built spines small enough to check on paper. The later ones run
the same properties over the synthetic data.
"""

import numpy as np
import pandas as pd
import pytest

import config
import evaluate as evaluate_module
import spine as spine_module
import target as target_module


def tiny_spine(members):
    """
    members: {member_id: [(month, dollars, hospice), ...]} -- all in year 2023.
    Only the columns target.py reads.
    """
    rows = [
        {"member_id": m, "year": 2023, "month": month,
         "cost_part_ab": float(dollars), "hospice": int(hospice)}
        for m, months in members.items()
        for month, dollars, hospice in months
    ]
    return pd.DataFrame(rows)


def full_year(dollars_per_month, hospice_months=()):
    return [(mo, dollars_per_month, mo in hospice_months) for mo in range(1, 13)]


def by_member(tgt):
    return tgt.set_index("member_id")


# ---------------------------------------------------------------------------
# Hand-checked arithmetic
# ---------------------------------------------------------------------------

def test_formula_by_hand():
    # m1: 12 months x $100  -> $1,200 / 12 = $100 PMPM
    # m2:  6 months x $300  -> $1,800 /  6 = $300 PMPM   (partial year)
    # m3: 12 months x $0    -> $0
    # population PMPM = (1200 + 1800 + 0) / (12 + 6 + 12) = 3000 / 30 = $100
    spine = tiny_spine({
        1: full_year(100),
        2: [(mo, 300, False) for mo in range(7, 13)],
        3: full_year(0),
    })
    tgt, population_pmpm = target_module.build_target(spine, 2023)
    t = by_member(tgt)

    assert population_pmpm == pytest.approx(100.0)
    assert t.loc[1, "exposure_months"] == 12
    assert t.loc[2, "exposure_months"] == 6
    assert t.loc[1, "member_pmpm"] == pytest.approx(100.0)
    assert t.loc[2, "member_pmpm"] == pytest.approx(300.0)
    assert t.loc[[1, 2, 3], "relative_target"].tolist() == pytest.approx([1.0, 3.0, 0.0])

    # P99.5 of [0, 1, 3] with linear interpolation: 1 + 0.99 * (3 - 1) = 2.98
    assert tgt.attrs["cap_value"] == pytest.approx(2.98)
    assert t.loc[2, "relative_target_capped"] == pytest.approx(2.98)
    assert t.loc[2, "relative_target"] == pytest.approx(3.0)   # uncapped kept for reporting


def test_population_is_exposure_weighted_not_mean_of_member_pmpm():
    # m1: 1 month at $1,000. m2: 12 months at $100.
    # Exposure-weighted: (1000 + 1200) / 13 = 169.23. The mean of member PMPMs would be 550.
    spine = tiny_spine({1: [(12, 1000, False)], 2: full_year(100)})
    _, population_pmpm = target_module.build_target(spine, 2023)
    assert population_pmpm == pytest.approx(2200 / 13)


def test_hospice_months_excluded_from_dollars_but_not_exposure():
    # 10 ordinary months at $100 plus 2 hospice months at $5,000 each.
    spine = tiny_spine({1: full_year(100, hospice_months=(11, 12)), 2: full_year(100)})
    spine.loc[(spine["member_id"] == 1) & (spine["hospice"] == 1), "cost_part_ab"] = 5000.0

    t = by_member(target_module.build_target(spine, 2023)[0])
    assert t.loc[1, "actual_cost"] == pytest.approx(1000.0)
    assert t.loc[1, "exposure_months"] == 12
    assert t.loc[1, "member_pmpm"] == pytest.approx(1000 / 12)


def test_partial_year_member_is_not_penalised_for_exposure():
    # Same monthly cost rate, different exposure -> same relative target. This is why no
    # separate LightGBM exposure offset is needed on top of the ratio.
    spine = tiny_spine({
        1: full_year(250),
        2: [(mo, 250, False) for mo in range(1, 4)],
        3: full_year(50),
    })
    t = by_member(target_module.build_target(spine, 2023)[0])
    assert t.loc[1, "relative_target"] == pytest.approx(t.loc[2, "relative_target"])


def test_member_with_no_exposure_in_target_year_is_dropped():
    spine = tiny_spine({1: full_year(100), 2: full_year(100)})
    other_year = spine[spine["member_id"] == 2].assign(year=2022)
    spine = pd.concat([spine[spine["member_id"] == 1], other_year], ignore_index=True)

    tgt, _ = target_module.build_target(spine, 2023)
    assert tgt["member_id"].tolist() == [1]


def test_medical_trend_is_divided_out():
    # Rule #1 in one line: inflate every dollar by 37% and the relative target must not
    # move -- only the population PMPM does. A raw-dollar target would move with it.
    spine = tiny_spine({1: full_year(80), 2: full_year(120), 3: full_year(0),
                        4: [(mo, 900, False) for mo in range(1, 7)]})
    base, base_pmpm = target_module.build_target(spine, 2023)
    inflated_spine = spine.assign(cost_part_ab=spine["cost_part_ab"] * 1.37)
    inflated, inflated_pmpm = target_module.build_target(inflated_spine, 2023)

    assert inflated_pmpm == pytest.approx(base_pmpm * 1.37)
    np.testing.assert_allclose(inflated["relative_target"], base["relative_target"])
    np.testing.assert_allclose(inflated["relative_target_capped"],
                               base["relative_target_capped"])


# ---------------------------------------------------------------------------
# The same properties on the synthetic data
# ---------------------------------------------------------------------------

def test_exposure_weighted_mean_of_relative_target_is_one(targets):
    for year, tgt in targets.items():
        weighted = (tgt["relative_target"] * tgt["exposure_months"]).sum() / tgt["exposure_months"].sum()
        assert weighted == pytest.approx(1.0), f"year {year}"


def test_cap_is_p995_within_each_year(targets):
    for year, tgt in targets.items():
        cap = tgt["relative_target"].quantile(config.CAP_PERCENTILE)
        assert tgt.attrs["cap_value"] == pytest.approx(cap), f"year {year}"
        assert tgt["relative_target_capped"].max() == pytest.approx(cap)
        assert (tgt["relative_target_capped"] <= tgt["relative_target"] + 1e-12).all()
        untouched = tgt["relative_target"] <= cap
        np.testing.assert_allclose(tgt.loc[untouched, "relative_target_capped"],
                                   tgt.loc[untouched, "relative_target"])


def test_caps_differ_by_year(targets):
    # The cap is computed within year T, not once over the pooled years.
    caps = {year: tgt.attrs["cap_value"] for year, tgt in targets.items()}
    assert len(set(np.round(list(caps.values()), 6))) == len(caps)


def test_target_population_matches_spine_helper(spine, targets):
    # Two independent implementations of population_pmpm_T must agree.
    for year, tgt in targets.items():
        assert tgt.attrs["population_pmpm"] == pytest.approx(
            spine_module.population_pmpm(spine, year))


def test_target_uses_part_ab_only(spine, targets):
    # Rx (Part D) is a feature, never part of the target.
    year = min(targets)
    rows = spine[(spine["year"] == year) & (spine["hospice"] == 0)]
    expected = rows.groupby("member_id")["cost_part_ab"].sum()
    got = targets[year].set_index("member_id")["actual_cost"]
    np.testing.assert_allclose(got.reindex(expected.index), expected)
    assert (rows["cost_rx"] > 0).any(), "fixture should contain Rx dollars for this to mean anything"


# ---------------------------------------------------------------------------
# Converting a prediction back to dollars (the second formula in intent.md)
# ---------------------------------------------------------------------------

def test_trend_project_recovers_a_geometric_trend():
    history = {2022 + i: 100.0 * 1.05 ** i for i in range(5)}
    assert evaluate_module.trend_project(history, 2027) == pytest.approx(100.0 * 1.05 ** 5)


def test_dollar_conversion_and_no_target_column(tmp_path):
    frame = pd.DataFrame({
        "member_id": [3, 1, 2],
        "predicted": [0.5, 1.0, 2.0],
        # these must NOT reach the score file
        "relative_target": [np.nan] * 3,
        "relative_target_capped": [np.nan] * 3,
    })
    path, out = evaluate_module.write_predictions(frame, projected_pmpm=400.0,
                                                  path=tmp_path / "p.csv",
                                                  expected_exposure_months=12)
    written = pd.read_csv(path)
    assert list(written.columns) == ["member_id", "relative_risk_score",
                                     "predicted_annual_dollar_estimate"]
    by_id = written.set_index("member_id")
    # predicted_annual = score * projected population PMPM * expected exposure months
    assert by_id.loc[1, "predicted_annual_dollar_estimate"] == pytest.approx(1.0 * 400 * 12)
    assert by_id.loc[2, "predicted_annual_dollar_estimate"] == pytest.approx(2.0 * 400 * 12)
    assert by_id.loc[3, "predicted_annual_dollar_estimate"] == pytest.approx(0.5 * 400 * 12)
