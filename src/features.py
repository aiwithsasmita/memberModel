"""
Phase 3 -- the feature table for one as_of_date, and the leakage assertion.

Non-negotiable rule #2: every feature row has an explicit as_of_date, and a feature may
only use source rows dated STRICTLY BEFORE it. That is enforced here in two independent
ways, not in a comment:

  1. _source_slice() is the only function that selects source rows. It filters on date and
     then re-asserts, on the rows it is about to hand back, that none of them carries a
     source date at or after the as_of_date.

  2. Every feature block registers the max source date it actually touched in a ledger,
     which rides along on the frame as `df.attrs["source_max_dates"]`.
     assert_no_future_leakage(df, as_of_date) then re-checks that ledger and also refuses
     a frame containing any feature column that no block claimed -- so a new feature added
     without registering its source raises instead of slipping through.

Two feature sets come out of here (rule #7):

  ESTABLISHED members -- have base-year history: cost/utilisation windows, MOR, demographics.
  NEW ENROLLEES       -- no base-year history at all: demographics only, as of their first
                         enrolled month. They are NOT established rows with nulls filled in.
"""

import numpy as np
import pandas as pd

import config
import embeddings_stub

HCC_COLUMNS = [f"hcc_{k + 1:02d}" for k in range(config.N_HCC_FLAGS)]

# The only feature columns a new-enrollee row is allowed to carry. Anything history-derived
# appearing here would mean the separate code path has quietly merged back into the main one.
NEW_ENROLLEE_FEATURES = [
    "age", "sex_male", "dual", "orec", "esrd",
    "enrollment_month", "county_freq", "pcp_freq",
]


def as_of_date_for(base_year):
    """Features for a base year are cut as of December 31 of that year."""
    return pd.Timestamp(year=base_year, month=12, day=31)


def _window_start(as_of_date, months):
    """Start of a trailing window of `months` ending the day before as_of_date."""
    return as_of_date - pd.DateOffset(months=months) + pd.DateOffset(days=1)


def _source_slice(spine, window_start, as_of_date):
    """
    The one and only place source rows are selected.

    Selects spine rows in [window_start, as_of_date) and then independently re-checks the
    rows it is returning. The re-check is deliberately redundant with the filter: if the
    filter above is ever edited to `<=`, or a row arrives carrying a claim dated after its
    own month, this raises instead of silently leaking.
    """
    rows = spine[(spine["month_start"] >= window_start) & (spine["month_start"] < as_of_date)]

    if not (rows["month_start"] < as_of_date).all():
        raise AssertionError(f"source slice contains an MMR month at/after {as_of_date.date()}")
    late_claims = rows["max_claim_date"].dropna()
    if (late_claims >= as_of_date).any():
        worst = late_claims.max()
        raise AssertionError(
            f"source slice contains a claim dated {worst.date()}, "
            f"at/after as_of_date {as_of_date.date()}"
        )
    return rows


def build_features(spine, base_year, member_universe, new_enrollee_year=None):
    """
    Build both feature sets for one base year.

    member_universe    -- the members we need a feature row for (usually: everyone with
                          exposure in the target year).
    new_enrollee_year  -- the year a new enrollee's first enrolled month is looked up in.
                          None means "no new-enrollee path for this set" (Set D).

    Returns (established_features, new_enrollee_features). Either may be empty.
    """
    as_of_date = as_of_date_for(base_year)
    universe = pd.Index(pd.unique(pd.Series(member_universe))).sort_values()

    # The 12-month window doubles as "all base-year history" and as the population the
    # base-year PMPM normaliser is computed over.
    w12_start = _window_start(as_of_date, 12)
    base_year_all = _source_slice(spine, w12_start, as_of_date)

    # Denominator for every cost feature: the base year's population PMPM, computed the
    # same way target.py computes the target year's (sum of dollars over sum of months).
    base_pop_pmpm = float(
        base_year_all.loc[base_year_all["hospice"] == 0, "cost_part_ab"].sum()
        / len(base_year_all)
    )

    in_universe = base_year_all[base_year_all["member_id"].isin(universe)]
    established_ids = pd.Index(np.sort(in_universe["member_id"].unique()))
    new_enrollee_ids = universe.difference(established_ids)

    # Category frequency counts: how many members sit in each county / with each PCP in the
    # base year. No target involved, so no fold machinery needed (unlike Phase 4). Counted
    # over EVERY base-year member, not just the universe: the universe is "who has exposure
    # in the target year", which is future information and must not shape a feature.
    county_freq = base_year_all.groupby("county_id")["member_id"].nunique()
    pcp_freq = base_year_all.groupby("pcp_provider_id")["member_id"].nunique()

    established = _build_established_features(
        spine, established_ids, base_year, as_of_date, base_pop_pmpm, county_freq, pcp_freq
    )
    new_enrollees = _build_new_enrollee_features(
        spine, new_enrollee_ids, base_year, new_enrollee_year, county_freq, pcp_freq
    )
    return established, new_enrollees


# ---------------------------------------------------------------------------
# Established members
# ---------------------------------------------------------------------------

def _build_established_features(spine, member_ids, base_year, as_of_date,
                                base_pop_pmpm, county_freq, pcp_freq):
    ledger = {}   # block name -> {"max_source_date": Timestamp, "columns": [...]}

    def register(block, columns, max_source_date):
        ledger[block] = {"max_source_date": max_source_date, "columns": list(columns)}

    out = pd.DataFrame(index=pd.Index(member_ids, name="member_id"))
    if len(member_ids) == 0:
        out = out.reset_index()
        out.attrs["source_max_dates"] = {}
        return out

    # ---- cost + utilisation over each trailing window ---------------------
    cost_cols, util_cols = [], []
    claim_source_dates, mmr_source_dates = [], []

    for months in config.TRAILING_WINDOWS_MONTHS:
        window = _source_slice(spine, _window_start(as_of_date, months), as_of_date)
        window = window[window["member_id"].isin(member_ids)]

        enrolled_months = window.groupby("member_id").size().reindex(member_ids)
        # Dollars are a rate, so they need a denominator. A member with no enrolled month
        # inside the window has an UNDEFINED rate, not a zero one -> NaN, which LightGBM
        # handles natively. Counts below are genuinely zero and are filled with 0.
        denom = enrolled_months.where(enrolled_months > 0)

        for category in config.COST_CATEGORIES + ["total"]:
            dollars = (window.groupby("member_id")[f"cost_{category}"].sum()
                       .reindex(member_ids, fill_value=0.0))
            name = f"cost_{category}_{months}m_ratio"
            out[name] = (dollars / denom) / base_pop_pmpm
            cost_cols.append(name)

            count = (window.groupby("member_id")[f"claims_{category}"].sum()
                     .reindex(member_ids, fill_value=0).astype(float))
            name = f"claims_{category}_{months}m"
            out[name] = count
            util_cols.append(name)

        if months == 6:
            out["months_enrolled_6m"] = enrolled_months.fillna(0).astype(int)
            util_cols.append("months_enrolled_6m")

        claim_source_dates.append(window["max_claim_date"].max())
        mmr_source_dates.append(window["month_start"].max())

    register("cost_windows", cost_cols, max(claim_source_dates))
    register("utilisation_windows", util_cols, max(claim_source_dates))

    # ---- base-year history summary ----------------------------------------
    base_year_rows = _source_slice(spine, _window_start(as_of_date, 12), as_of_date)
    base_year_rows = base_year_rows[base_year_rows["member_id"].isin(member_ids)]

    out["months_history_available"] = base_year_rows.groupby("member_id").size().reindex(member_ids)
    out["has_any_claim"] = ((base_year_rows.groupby("member_id")["cost_total"].sum()
                             .reindex(member_ids, fill_value=0.0) > 0).astype(int))
    register("history", ["months_history_available", "has_any_claim"],
             base_year_rows["month_start"].max())

    # ---- MOR: HCC flags, HCC count, raf_score -----------------------------
    # One MOR row per member-year, so any base-year spine row carries it; take the latest.
    latest = (base_year_rows.sort_values(["member_id", "month_start"])
              .groupby("member_id").tail(1).set_index("member_id"))

    for col in HCC_COLUMNS:
        out[col] = latest[col].reindex(member_ids)
    out["hcc_count"] = latest["hcc_count"].reindex(member_ids)
    # This is also the Phase 7 baseline: the synthetic stand-in for the real CMS RAF.
    out["raf_score_base"] = latest["raf_score"].reindex(member_ids)
    register("mor", HCC_COLUMNS + ["hcc_count", "raf_score_base"],
             base_year_rows["mor_source_date"].max())

    # ---- demographics, from the member's last enrolled month of the base year
    out["age"] = latest["age"].reindex(member_ids)
    out["sex_male"] = (latest["sex"] == "M").astype(int).reindex(member_ids)
    out["dual"] = latest["dual"].reindex(member_ids)
    out["orec"] = latest["orec"].reindex(member_ids)
    out["esrd"] = latest["esrd"].reindex(member_ids)
    out["hospice_any_base"] = base_year_rows.groupby("member_id")["hospice"].max().reindex(member_ids)
    register("demographics", ["age", "sex_male", "dual", "orec", "esrd", "hospice_any_base"],
             base_year_rows["month_start"].max())

    # ---- high-cardinality categoricals ------------------------------------
    # The raw ids are kept as IDENTIFIERS (config.ID_COLUMNS), not features: they are
    # consumed by encoding.py in Phase 4, which is the only leak-safe way to use them.
    out["county_id"] = latest["county_id"].reindex(member_ids)
    out["pcp_provider_id"] = latest["pcp_provider_id"].reindex(member_ids)
    out["county_freq"] = out["county_id"].map(county_freq).fillna(0).astype(int)
    out["pcp_freq"] = out["pcp_provider_id"].map(pcp_freq).fillna(0).astype(int)
    register("categorical_frequency", ["county_freq", "pcp_freq"],
             base_year_rows["month_start"].max())

    # ---- Phase 8: Optum BERT embeddings, off by default -------------------
    embeddings = embeddings_stub.get_member_embeddings(member_ids, as_of_date)
    if embeddings is not None:
        embeddings = embeddings.reindex(member_ids)
        for col in embeddings.columns:
            out[col] = embeddings[col]
        register("bert_embeddings", list(embeddings.columns),
                 embeddings.attrs["max_source_date"])

    out = out.reset_index()
    out.insert(1, "base_year", base_year)
    out.insert(2, "as_of_date", as_of_date)
    out.insert(3, "row_kind", "established")
    out.attrs["source_max_dates"] = ledger

    assert_no_future_leakage(out, as_of_date)
    return out


# ---------------------------------------------------------------------------
# New enrollees -- rule #7, a separate code path
# ---------------------------------------------------------------------------

def _build_new_enrollee_features(spine, member_ids, base_year, new_enrollee_year,
                                 county_freq, pcp_freq):
    """
    Members with NO base-year history. There is nothing to build a trailing window from,
    so they get demographics only, read from their first enrolled month in the year we are
    predicting. Their as_of_date is per-row, not the set's Dec 31, because in production
    you score a new enrollee when they join, not the previous winter: it is the day after
    their first MMR record, so the one source row they read is strictly before it (rule #2).
    """
    empty_columns = ["member_id", "base_year", "as_of_date", "row_kind",
                     "county_id", "pcp_provider_id"] + NEW_ENROLLEE_FEATURES
    if new_enrollee_year is None or len(member_ids) == 0:
        out = pd.DataFrame(columns=empty_columns)
        out.attrs["source_max_dates"] = {}
        return out

    rows = spine[(spine["year"] == new_enrollee_year) & (spine["member_id"].isin(member_ids))]
    first = (rows.sort_values(["member_id", "month_start"])
             .groupby("member_id").head(1).set_index("member_id"))

    out = pd.DataFrame(index=first.index)
    out["age"] = first["age"]
    out["sex_male"] = (first["sex"] == "M").astype(int)
    out["dual"] = first["dual"]
    out["orec"] = first["orec"]
    out["esrd"] = first["esrd"]
    out["enrollment_month"] = first["month"]
    out["county_id"] = first["county_id"]
    out["pcp_provider_id"] = first["pcp_provider_id"]
    out["county_freq"] = out["county_id"].map(county_freq).fillna(0).astype(int)
    out["pcp_freq"] = out["pcp_provider_id"].map(pcp_freq).fillna(0).astype(int)

    source_dates = first["month_start"].to_numpy()   # the one MMR row each member is read from

    out = out.reset_index()
    out.insert(1, "base_year", base_year)
    out.insert(2, "as_of_date", source_dates + np.timedelta64(1, "D"))   # per-row, see docstring
    out.insert(3, "row_kind", "new_enrollee")

    assert_new_enrollee_features(out, base_year, source_dates)
    return out


# ---------------------------------------------------------------------------
# The assertions
# ---------------------------------------------------------------------------

def assert_no_future_leakage(df, as_of_date):
    """
    Hard stop if any feature block touched a source row dated at or after as_of_date,
    or if any feature column is not claimed by a registered block.

    A failure here is a bug, not a warning -- it means a feature saw the future.
    """
    ledger = df.attrs.get("source_max_dates")
    features = config.feature_columns(df)

    if not features:
        return   # nothing to check (an empty set)
    if not ledger:
        raise AssertionError("feature frame carries no source-date ledger -- cannot verify")

    claimed = [c for block in ledger.values() for c in block["columns"]]
    duplicates = {c for c in claimed if claimed.count(c) > 1}
    if duplicates:
        raise AssertionError(f"columns registered by more than one block: {sorted(duplicates)}")

    unclaimed = sorted(set(features) - set(claimed))
    if unclaimed:
        raise AssertionError(
            f"feature columns with no registered source date: {unclaimed}. "
            "Every feature-building step must call register(...) so its source can be checked."
        )

    for block, info in ledger.items():
        max_date = info["max_source_date"]
        if pd.isna(max_date):
            continue     # block touched no dated source rows at all
        if pd.Timestamp(max_date) >= pd.Timestamp(as_of_date):
            raise AssertionError(
                f"LEAKAGE: feature block '{block}' used a source row dated "
                f"{pd.Timestamp(max_date).date()}, which is not strictly before "
                f"as_of_date {pd.Timestamp(as_of_date).date()}"
            )


def assert_new_enrollee_features(df, base_year, source_dates=None):
    """
    New-enrollee rows must be demographics-only, and each must be cut as of that member's
    own first enrolled month -- which is necessarily AFTER the base year ended, since
    having no base-year history is what put them on this path.

    source_dates -- per-row date of the source record each row was built from. When given,
    every one must be strictly before that row's as_of_date (rule #2, row by row, because
    new enrollees do not share one as_of_date).
    """
    if source_dates is not None:
        as_of = pd.to_datetime(df["as_of_date"]).to_numpy()
        late = np.asarray(source_dates, dtype="datetime64[ns]") >= as_of
        if late.any():
            raise AssertionError(
                f"LEAKAGE: {int(late.sum())} new-enrollee row(s) read a source record dated "
                "on or after their own as_of_date"
            )

    # The out-of-fold target encodings from Phase 4 are bolted on later, so allow them
    # here too -- this assertion stays usable after encoding.attach_target_encodings runs.
    allowed = set(NEW_ENROLLEE_FEATURES) | {f"{c}_te" for c in config.TARGET_ENCODE_COLUMNS}
    features = set(config.feature_columns(df))
    unexpected = sorted(features - allowed)
    if unexpected:
        raise AssertionError(
            f"new-enrollee rows carry history-derived columns {unexpected}; "
            "they must not fall through the established path with imputed history"
        )

    base_year_end = as_of_date_for(base_year)
    if (pd.to_datetime(df["as_of_date"]) <= base_year_end).any():
        raise AssertionError(
            "a new enrollee has an as_of_date inside the base year -- then they are not "
            "a new enrollee and belong on the established path"
        )
