"""
Phase 4 -- out-of-fold target encoding.

Non-negotiable rule #3: any mean/target encoding of a categorical column must be
out-of-fold. Fitting and transforming on the same rows is leakage, full stop -- a
high-cardinality column like pcp_provider_id would otherwise memorise each member's own
target and look spectacular in CV and worthless out of time.

The encoding is a smoothed mean:

    enc(c) = (sum_of_target_in_c + smoothing * global_mean) / (count_in_c + smoothing)

For a TRAINING row, the row's own fold is removed from both sums AND from the global mean
it is smoothed toward, so the row never contributes to -- and never sees -- its own fold's
signal. A category that appears in only one fold therefore falls all the way back to the
other folds' global mean for those rows, which is the honest answer: with that fold
removed there is no evidence left.

Non-training rows (out-of-time backtests, the score set) get the encoding fitted on ALL
training rows. They are not in the training corpus, so there is no own-fold to leave out.
"""

import numpy as np
import pandas as pd

import config


def out_of_fold_target_encode(categories, target, folds, smoothing=config.TARGET_ENCODE_SMOOTHING):
    """
    Leave-own-fold-out smoothed mean encoding for the training rows.

    categories / target / folds -- aligned Series of equal length.
    Returns a float Series aligned to the inputs.
    """
    frame = pd.DataFrame({
        "category": np.asarray(categories),
        "y": np.asarray(target, dtype=float),
        "fold": np.asarray(folds),
    })

    # The prior is left-own-fold-out too. A global mean over ALL rows would carry the row's
    # own fold back in through the smoothing term -- and with a smoothing weight of 200 the
    # prior dominates every small category, so that is not a rounding error.
    by_fold = frame.groupby("fold")["y"].agg(["sum", "count"])
    fold_sum = frame["fold"].map(by_fold["sum"]).to_numpy(dtype=float)
    fold_count = frame["fold"].map(by_fold["count"]).to_numpy(dtype=float)
    global_mean = (frame["y"].sum() - fold_sum) / (len(frame) - fold_count)

    by_category = frame.groupby("category")["y"].agg(["sum", "count"])
    by_category_fold = frame.groupby(["category", "fold"])["y"].agg(["sum", "count"])

    total_sum = frame["category"].map(by_category["sum"]).to_numpy(dtype=float)
    total_count = frame["category"].map(by_category["count"]).to_numpy(dtype=float)

    own_fold = pd.MultiIndex.from_arrays([frame["category"], frame["fold"]])
    own_sum = by_category_fold["sum"].reindex(own_fold).to_numpy(dtype=float)
    own_count = by_category_fold["count"].reindex(own_fold).to_numpy(dtype=float)

    # Remove the row's own fold, then smooth what is left toward the global mean.
    kept_sum = total_sum - own_sum
    kept_count = total_count - own_count
    encoded = (kept_sum + smoothing * global_mean) / (kept_count + smoothing)

    return pd.Series(encoded, index=pd.RangeIndex(len(frame)), name="encoded")


def fit_target_encoding(categories, target, smoothing=config.TARGET_ENCODE_SMOOTHING):
    """Fit the smoothed encoding on ALL training rows. Returns (mapping, global_mean)."""
    frame = pd.DataFrame({"category": np.asarray(categories),
                          "y": np.asarray(target, dtype=float)})
    global_mean = float(frame["y"].mean())
    stats = frame.groupby("category")["y"].agg(["sum", "count"])
    mapping = (stats["sum"] + smoothing * global_mean) / (stats["count"] + smoothing)
    return mapping, global_mean


def apply_target_encoding(categories, mapping, global_mean):
    """Apply a fitted encoding. Unseen categories fall back to the global mean."""
    return pd.Series(np.asarray(categories)).map(mapping).fillna(global_mean).to_numpy(dtype=float)


def attach_target_encodings(train_frames, other_frames, target_column,
                            columns=config.TARGET_ENCODE_COLUMNS,
                            smoothing=config.TARGET_ENCODE_SMOOTHING):
    """
    Convenience wrapper used once per training corpus.

    train_frames -- list of frames that together form the training corpus. They are
                    concatenated so the encoding is fitted on the whole corpus, then the
                    out-of-fold values are written back onto each frame.
    other_frames -- backtest / score frames. They get the full-corpus encoding.

    Frames are modified in place (callers pass copies), and every frame needs a `fold`
    column; folds are assigned per member_id in splits.py so a member's rows are always
    in the same fold and never straddle a train/holdout boundary.
    """
    corpus = pd.concat(train_frames, ignore_index=True) if train_frames else pd.DataFrame()

    for column in columns:
        encoded_name = f"{column}_te"

        if len(corpus) == 0:
            for frame in other_frames:
                frame[encoded_name] = np.nan
            continue

        oof = out_of_fold_target_encode(corpus[column], corpus[target_column],
                                        corpus["fold"], smoothing)
        # Split the corpus-level result back out to the frames it came from.
        cursor = 0
        for frame in train_frames:
            frame[encoded_name] = oof.iloc[cursor:cursor + len(frame)].to_numpy()
            cursor += len(frame)

        mapping, global_mean = fit_target_encoding(corpus[column], corpus[target_column],
                                                   smoothing)
        for frame in other_frames:
            if len(frame) == 0:
                frame[encoded_name] = np.nan
            else:
                frame[encoded_name] = apply_target_encoding(frame[column], mapping, global_mean)
