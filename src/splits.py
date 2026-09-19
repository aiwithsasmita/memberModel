"""
Phase 5 -- the four row sets.

    Set | base year (features) | target year | role
    ----+----------------------+-------------+--------------------------------------------
     A  | 2022                 | 2023        | train, 5-fold CV grouped by member_id
     B  | 2023                 | 2024        | backtest 1 (out of time)
     C  | 2024                 | 2025        | backtest 2 (out of time, after refit on A+B)
     D  | 2026                 | none        | score -- the "2027" rehearsal, no target

Non-negotiable rule #4: splits are member-grouped -- a member_id never appears in both a
training fold and its held-out fold. Folds are assigned ONCE per member_id for the whole
run (see assign_member_folds), so a member keeps the same fold in every set. That makes
the guarantee structural rather than something each split has to remember to re-derive.

Non-negotiable rule #7: new enrollees are carried in their own frame, never merged into
the established frame with imputed history.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config
import features as features_module


@dataclass
class RowSet:
    """One of the four sets above, with its two populations kept apart."""
    name: str
    base_year: int
    target_year: "int | None"
    role: str
    established: pd.DataFrame
    new_enrollees: pd.DataFrame

    @property
    def n_rows(self):
        return len(self.established) + len(self.new_enrollees)

    def has_target(self):
        return self.target_year is not None

    def describe(self):
        return (f"Set {self.name}: base {self.base_year} -> target {self.target_year}  "
                f"{self.n_rows:>5,} members "
                f"({len(self.established):,} established, {len(self.new_enrollees):,} new)")


def assign_member_folds(member_ids, n_folds=config.CV_FOLDS, seed=config.RANDOM_SEED):
    """
    member_id -> fold, assigned once for the whole run.

    Shuffle the member list with a fixed seed and deal folds round-robin. Grouping is by
    member, so every row a member ever produces lands in the same fold -- in Set A, in a
    refit on A+B, and in the target encoding of Phase 4, which reuses this same column.
    """
    members = np.array(sorted(pd.unique(np.asarray(member_ids))))
    rng = np.random.default_rng(seed)
    rng.shuffle(members)
    folds = np.arange(len(members)) % n_folds
    return pd.Series(folds, index=pd.Index(members, name="member_id"), name="fold")


def build_row_sets(spine, targets, member_folds):
    """
    Build all four sets.

    targets -- {year: target_df} from target.build_targets_for_years.
    """
    row_sets = {}
    for name, spec in config.SPLITS.items():
        base_year = spec["base_year"]
        target_year = spec["target_year"]

        if target_year is not None:
            # Universe = everyone with exposure in the target year. Members who left
            # mid-year are in, with their partial exposure -- that is what PMPM is for.
            target_df = targets[target_year]
            universe = target_df["member_id"]
        else:
            # Score set: members still enrolled at the as_of_date (active in December of the
            # base year). Someone who left mid-year has no next year to project, and someone
            # joining next year is not known yet -- in production they are scored by the
            # new-enrollee model when they enrol. Only data before as_of_date decides this.
            target_df = None
            active = (spine["year"] == base_year) & (spine["month"] == 12)
            universe = spine.loc[active, "member_id"].unique()

        established, new_enrollees = features_module.build_features(
            spine, base_year=base_year, member_universe=universe,
            new_enrollee_year=target_year,
        )

        established = _attach_target_and_fold(established, target_df, member_folds, target_year)
        new_enrollees = _attach_target_and_fold(new_enrollees, target_df, member_folds, target_year)
        # Re-check the finished frame, not just the one features.py returned: attaching the
        # target must not have smuggled in a column the model would treat as a feature.
        features_module.assert_no_future_leakage(
            established, features_module.as_of_date_for(base_year))

        row_sets[name] = RowSet(
            name=name, base_year=base_year, target_year=target_year, role=spec["role"],
            established=established, new_enrollees=new_enrollees,
        )
    return row_sets


def _attach_target_and_fold(frame, target_df, member_folds, target_year):
    # pandas does not carry .attrs through a merge, and the leakage ledger lives there.
    ledger = frame.attrs.get("source_max_dates", {})
    frame = _attach(frame.copy(), target_df, member_folds, target_year)
    frame.attrs["source_max_dates"] = ledger
    return frame


def _attach(frame, target_df, member_folds, target_year):
    if len(frame) == 0:
        for column in config.TARGET_COLUMNS:
            frame[column] = pd.Series(dtype=float)
        frame["fold"] = pd.Series(dtype=int)
        frame["target_year"] = pd.Series(dtype="Int64")
        return frame

    if target_df is not None:
        keep = ["member_id", "target_year"] + config.TARGET_COLUMNS
        frame = frame.merge(target_df[keep], on="member_id", how="left")
        missing = frame["relative_target_capped"].isna().sum()
        assert missing == 0, f"{missing} feature rows have no target for year {target_year}"
    else:
        frame["target_year"] = pd.NA

    frame["fold"] = frame["member_id"].map(member_folds).astype(int)
    return frame


def assert_member_grouped(row_set):
    """
    Rule #4, checked rather than assumed: for every fold, the member ids used for training
    and the member ids held out share nobody.
    """
    frames = [f for f in (row_set.established, row_set.new_enrollees) if len(f) > 0]
    if not frames:
        return
    everything = pd.concat(frames, ignore_index=True)

    for fold in sorted(everything["fold"].unique()):
        holdout = set(everything.loc[everything["fold"] == fold, "member_id"])
        train = set(everything.loc[everything["fold"] != fold, "member_id"])
        overlap = holdout & train
        if overlap:
            raise AssertionError(
                f"Set {row_set.name}: {len(overlap)} member_id(s) appear in both the "
                f"training folds and held-out fold {fold}, e.g. {sorted(overlap)[:5]}"
            )


def training_corpus(row_sets, names):
    """
    Concatenate the established frames of several sets into one training corpus.

    Used for the refits: A alone -> backtest 1, A+B -> backtest 2, A+B+C -> the 2027 score.
    Folds come along unchanged, so CV on a multi-set corpus is still member-grouped.
    """
    frames = [row_sets[n].established for n in names]
    return pd.concat(frames, ignore_index=True)


def new_enrollee_corpus(row_sets, names):
    """The same, for the new-enrollee frames."""
    frames = [row_sets[n].new_enrollees for n in names if len(row_sets[n].new_enrollees) > 0]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
