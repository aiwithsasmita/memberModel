"""
Leakage and split discipline -- rules #2, #3, #4 and #7, plus the #8 switch.

The strongest test here is the canary: features built from the full spine must be
IDENTICAL to features built from a spine with everything on or after the as_of_date
deleted. If a feature could see the future, deleting the future would change it.
"""

import numpy as np
import pandas as pd
import pytest

import config
import embeddings_stub
import encoding as encoding_module
import features as features_module
import model as model_module
import splits as splits_module

TARGET = model_module.TARGET


# ---------------------------------------------------------------------------
# Rule #2 -- assert_no_future_leakage, on hand-built ledgers
# ---------------------------------------------------------------------------

AS_OF = pd.Timestamp("2023-12-31")


def ledgered_frame(max_source_date, columns=("f1",), claimed=("f1",)):
    df = pd.DataFrame({"member_id": [1, 2], **{c: [0.0, 1.0] for c in columns}})
    df.attrs["source_max_dates"] = {
        "block": {"max_source_date": max_source_date, "columns": list(claimed)}}
    return df


def test_assertion_passes_when_sources_are_strictly_before():
    features_module.assert_no_future_leakage(ledgered_frame(pd.Timestamp("2023-12-30")), AS_OF)


@pytest.mark.parametrize("source_date", ["2023-12-31", "2024-01-15"])
def test_assertion_raises_on_or_after_as_of_date(source_date):
    # On the as_of_date itself is a failure too: "strictly before" is the rule.
    with pytest.raises(AssertionError, match="LEAKAGE"):
        features_module.assert_no_future_leakage(ledgered_frame(pd.Timestamp(source_date)),
                                                 AS_OF)


def test_assertion_raises_on_a_feature_no_block_registered():
    df = ledgered_frame(pd.Timestamp("2023-06-01"), columns=("f1", "sneaky"))
    with pytest.raises(AssertionError, match="no registered source date"):
        features_module.assert_no_future_leakage(df, AS_OF)


def test_assertion_raises_without_a_ledger():
    df = pd.DataFrame({"member_id": [1], "f1": [0.0]})
    with pytest.raises(AssertionError, match="ledger"):
        features_module.assert_no_future_leakage(df, AS_OF)


# ---------------------------------------------------------------------------
# Rule #2 -- on real feature frames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["A", "B", "C", "D"])
def test_every_established_frame_passes_the_assertion(row_sets, name):
    frame = row_sets[name].established
    as_of = features_module.as_of_date_for(row_sets[name].base_year)
    assert (pd.to_datetime(frame["as_of_date"]) == as_of).all()
    features_module.assert_no_future_leakage(frame, as_of)


@pytest.mark.parametrize("base_year", [2022, 2023, 2024, 2026])
def test_canary_features_unchanged_when_the_future_is_deleted(spine, base_year):
    as_of = features_module.as_of_date_for(base_year)
    universe = spine.loc[spine["year"] == base_year, "member_id"].unique()

    full, _ = features_module.build_features(spine, base_year, universe, new_enrollee_year=None)
    past_only = spine[spine["month_start"] < as_of]
    truncated, _ = features_module.build_features(past_only, base_year, universe,
                                                  new_enrollee_year=None)

    assert len(full) > 0
    pd.testing.assert_frame_equal(full, truncated)


def test_canary_features_unchanged_when_the_future_is_scrambled(spine):
    # Same idea, harder: keep the future rows but make them nonsense.
    base_year = 2023
    as_of = features_module.as_of_date_for(base_year)
    universe = spine.loc[spine["year"] == base_year, "member_id"].unique()

    scrambled = spine.copy()
    future = scrambled["month_start"] >= as_of
    for col in [c for c in scrambled.columns if c.startswith(("cost_", "claims_", "hcc_"))]:
        scrambled.loc[future, col] = scrambled.loc[future, col] * 7 + 3
    scrambled.loc[future, "raf_score"] = 99.0

    full, _ = features_module.build_features(spine, base_year, universe, None)
    other, _ = features_module.build_features(scrambled, base_year, universe, None)
    pd.testing.assert_frame_equal(full, other)


def test_a_members_features_do_not_depend_on_who_else_is_in_the_universe(spine, targets):
    # The universe of a training set is "who has exposure in the target year" -- future
    # information. It may decide WHICH rows exist, never what a row's features are.
    base_year, target_year = 2022, 2023
    universe = targets[target_year]["member_id"].to_numpy()
    half = universe[: len(universe) // 2]

    full, _ = features_module.build_features(spine, base_year, universe, None)
    part, _ = features_module.build_features(spine, base_year, half, None)

    shared = full[full["member_id"].isin(part["member_id"])].reset_index(drop=True)
    pd.testing.assert_frame_equal(shared, part.reset_index(drop=True), check_like=True)


@pytest.mark.parametrize("late_by_days", [0, 5])
def test_a_claim_dated_on_or_after_as_of_date_is_a_hard_stop(spine, late_by_days):
    base_year = 2023
    as_of = features_module.as_of_date_for(base_year)
    universe = spine.loc[spine["year"] == base_year, "member_id"].unique()

    tampered = spine.copy()
    december = tampered.index[(tampered["year"] == base_year) & (tampered["month"] == 12)
                              & tampered["max_claim_date"].notna()][0]
    tampered.loc[december, "max_claim_date"] = as_of + pd.Timedelta(days=late_by_days)

    with pytest.raises(AssertionError, match="at/after as_of_date"):
        features_module.build_features(tampered, base_year, universe, None)


def test_mor_source_is_before_the_as_of_date(row_sets):
    ledger = row_sets["A"].established.attrs["source_max_dates"]
    assert ledger["mor"]["max_source_date"] < features_module.as_of_date_for(2022)


# ---------------------------------------------------------------------------
# Rule #3 -- out-of-fold target encoding
# ---------------------------------------------------------------------------

def encoding_inputs(n=600, seed=0):
    rng = np.random.default_rng(seed)
    return (pd.Series(rng.integers(0, 12, n)),       # categories
            pd.Series(rng.gamma(0.5, 2.0, n)),       # target
            pd.Series(np.arange(n) % 5))             # folds


def test_oof_encoding_never_sees_its_own_fold():
    categories, target, folds = encoding_inputs()
    before = encoding_module.out_of_fold_target_encode(categories, target, folds)

    changed = target.copy()
    changed[folds == 0] = 1_000.0   # blow up fold 0's targets
    after = encoding_module.out_of_fold_target_encode(categories, changed, folds)

    fold0 = (folds == 0).to_numpy()
    # Fold 0's own encodings are unaffected by fold 0's targets...
    np.testing.assert_allclose(after[fold0], before[fold0])
    # ...while every other fold's encoding does move (so the test can fail).
    assert not np.allclose(after[~fold0], before[~fold0])


def test_oof_encoding_matches_the_formula_for_one_row():
    categories, target, folds = encoding_inputs()
    smoothing = 200.0
    enc = encoding_module.out_of_fold_target_encode(categories, target, folds, smoothing)

    i = 17
    other_folds = folds != folds[i]
    same_category = (categories == categories[i]) & other_folds
    prior = target[other_folds].mean()    # the prior leaves the own fold out too
    expected = (target[same_category].sum() + smoothing * prior) / (same_category.sum() + smoothing)
    assert enc[i] == pytest.approx(expected)


def test_scoring_rows_get_the_full_training_corpus_encoding():
    categories, target, folds = encoding_inputs()
    train = pd.DataFrame({"county_id": categories, "pcp_provider_id": categories,
                          TARGET: target, "fold": folds})
    score = pd.DataFrame({"county_id": [0, 5, 999], "pcp_provider_id": [0, 5, 999]})
    encoding_module.attach_target_encodings([train], [score], TARGET)

    mapping, global_mean = encoding_module.fit_target_encoding(categories, target)
    assert score["county_id_te"].tolist() == pytest.approx(
        [mapping[0], mapping[5], global_mean])   # 999 is unseen -> global mean


def test_cv_split_features_do_not_depend_on_held_out_targets(row_sets):
    # The encodings on a CV split must not move when the held-out fold's targets change --
    # neither the held-out rows' own encodings nor the training rows' encodings.
    # Each corpus gets its encodings attached the way the pipeline does it, i.e. AFTER the
    # targets are what they are -- so the tampered corpus carries tampered encodings in.
    train = row_sets["A"].established.copy()
    tampered = train.copy()
    tampered.loc[tampered["fold"] == 0, TARGET] *= 50.0
    for corpus in (train, tampered):
        encoding_module.attach_target_encodings([corpus], [], TARGET)

    fit_before, hold_before = model_module.split_fold(train, fold=0)
    fit_after, hold_after = model_module.split_fold(tampered, fold=0)

    te_columns = [f"{c}_te" for c in config.TARGET_ENCODE_COLUMNS]
    pd.testing.assert_frame_equal(fit_before[te_columns], fit_after[te_columns])
    pd.testing.assert_frame_equal(hold_before[te_columns], hold_after[te_columns])


# ---------------------------------------------------------------------------
# Rule #4 -- member-grouped splits
# ---------------------------------------------------------------------------

def test_every_member_has_exactly_one_fold(member_folds):
    assert member_folds.index.is_unique
    assert set(member_folds.unique()) == set(range(config.CV_FOLDS))
    sizes = member_folds.value_counts()
    assert sizes.max() - sizes.min() <= 1


@pytest.mark.parametrize("name", ["A", "B", "C", "D"])
def test_row_sets_are_member_grouped(row_sets, name):
    splits_module.assert_member_grouped(row_sets[name])


def test_a_member_keeps_its_fold_across_sets(row_sets):
    # So a refit corpus (A+B, A+B+C) is still member-grouped.
    corpus = pd.concat([row_sets[n].established for n in "ABC"], ignore_index=True)
    assert (corpus.groupby("member_id")["fold"].nunique() == 1).all()
    assert corpus["member_id"].duplicated().any(), "fixture should have repeat members"


def test_member_grouping_check_catches_a_straddling_member(row_sets):
    broken = row_sets["A"].established.copy()
    member = broken["member_id"].iloc[0]
    duplicate = broken[broken["member_id"] == member].assign(
        fold=lambda d: (d["fold"] + 1) % config.CV_FOLDS)
    bad_set = splits_module.RowSet(
        name="X", base_year=2022, target_year=2023, role="test",
        established=pd.concat([broken, duplicate], ignore_index=True),
        new_enrollees=row_sets["A"].new_enrollees)
    with pytest.raises(AssertionError, match="appear in both"):
        splits_module.assert_member_grouped(bad_set)


# ---------------------------------------------------------------------------
# Rule #7 -- new enrollees are their own code path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_new_enrollees_are_separate_and_demographics_only(spine, row_sets, name):
    row_set = row_sets[name]
    new = row_set.new_enrollees
    assert len(new) > 0, "fixture should contain new enrollees"

    # Nobody is on both paths.
    assert not set(new["member_id"]) & set(row_set.established["member_id"])

    # Nobody on the new path has any base-year history.
    base_rows = spine[(spine["year"] == row_set.base_year)
                      & spine["member_id"].isin(new["member_id"])]
    assert base_rows.empty

    # Demographics only -- no history column was imputed onto them.
    allowed = set(features_module.NEW_ENROLLEE_FEATURES)
    assert set(config.feature_columns(new)) <= allowed
    history_like = [c for c in new.columns if c.startswith(("cost_", "claims_", "hcc_", "raf"))]
    assert history_like == []

    # Each is scored strictly after the source record it was built from.
    first_month = (spine[spine["member_id"].isin(new["member_id"])
                         & (spine["year"] == row_set.target_year)]
                   .groupby("member_id")["month_start"].min())
    as_of = new.set_index("member_id")["as_of_date"]
    assert (pd.to_datetime(as_of) > first_month.reindex(as_of.index)).all()


def test_new_enrollee_row_with_history_column_is_rejected(row_sets):
    new = row_sets["A"].new_enrollees.copy()
    new["cost_total_12m_ratio"] = 0.0   # "just fill the history with zeros"
    with pytest.raises(AssertionError, match="history-derived"):
        features_module.assert_new_enrollee_features(new, base_year=2022)


def test_new_enrollee_reading_a_record_on_its_as_of_date_is_rejected(row_sets):
    new = row_sets["A"].new_enrollees
    same_day = pd.to_datetime(new["as_of_date"]).to_numpy()
    with pytest.raises(AssertionError, match="LEAKAGE"):
        features_module.assert_new_enrollee_features(new, base_year=2022,
                                                     source_dates=same_day)


# ---------------------------------------------------------------------------
# Set D -- the score set has no target and only uses the past
# ---------------------------------------------------------------------------

def test_score_set_has_no_target(row_sets):
    d = row_sets["D"]
    assert d.target_year is None
    for frame in (d.established, d.new_enrollees):
        present = [c for c in config.TARGET_COLUMNS if c in frame.columns]
        assert all(frame[c].isna().all() for c in present)


def test_score_set_is_members_enrolled_at_the_as_of_date(spine, row_sets):
    base_year = row_sets["D"].base_year
    active = spine.loc[(spine["year"] == base_year) & (spine["month"] == 12), "member_id"]
    assert set(row_sets["D"].established["member_id"]) == set(active)


# ---------------------------------------------------------------------------
# Rule #8 -- the Optum BERT switch
# ---------------------------------------------------------------------------

def test_embeddings_are_off_by_default_and_not_faked(monkeypatch):
    assert config.USE_BERT_EMBEDDINGS is False
    assert embeddings_stub.get_member_embeddings([1, 2], AS_OF) is None

    monkeypatch.setattr(config, "USE_BERT_EMBEDDINGS", True)
    with pytest.raises(NotImplementedError):
        embeddings_stub.get_member_embeddings([1, 2], AS_OF)
