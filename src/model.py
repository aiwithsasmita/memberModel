"""
Phase 6 -- LightGBM with a Tweedie objective, a small Optuna study, MLflow logging.

Non-negotiable rule #5: the objective is Tweedie, not squared error on log(cost). The
target is zero-inflated with a heavy right tail by construction (Phase 1: ~10% of members
have a zero-cost year, 0.3% of member-years are catastrophic). Squared error on a log
transform has to invent something for the zeros and systematically under-predicts the
tail; Tweedie models the zero mass and the positive tail in one likelihood.

Tuning discipline: the Optuna study only ever sees Set A. Sets B, C and D are never
touched during tuning -- that is the whole point of holding them out of time.

One subtlety worth knowing about: tweedie_variance_power is itself a tuned parameter, so
the Tweedie deviance LightGBM reports is measured in different units from trial to trial
and is NOT comparable across them. The Optuna objective therefore re-scores every trial's
out-of-fold predictions with ONE fixed deviance power (config.EVAL_TWEEDIE_POWER). The
tuned power is still used for training and for each fold's early stopping.
"""

import os

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import mean_tweedie_deviance

import config
import encoding as encoding_module

# MLflow >= 3.16 refuses the plain-folder tracking backend unless you opt in. We want the
# folder backend here precisely because it needs no server and no database -- the whole
# rehearsal has to run on a laptop with nothing else installed. In production this whole
# block goes away and MLFLOW_TRACKING_URI points at the Databricks-managed tracking server
# instead (see README, "Porting to Databricks").
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
# Silences a local MLflow CLI hint; harmless everywhere else.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
import mlflow  # noqa: E402

TARGET = "relative_target_capped"

optuna.logging.set_verbosity(optuna.logging.WARNING)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

def setup_mlflow():
    """Local file-based tracking. No server, no network -- mlruns/ in the repo root."""
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT)


def align_features(df, feature_columns):
    """Pull the feature matrix out of a frame in a fixed column order."""
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise KeyError(f"frame is missing feature columns: {missing}")
    return df[feature_columns].astype(float)


def scoring_deviance(y_true, y_pred):
    """Tweedie deviance at one FIXED power, so numbers are comparable across trials."""
    y_pred = np.clip(y_pred, 1e-6, None)   # the Tweedie deviance is undefined at 0
    return float(mean_tweedie_deviance(y_true, y_pred, power=config.EVAL_TWEEDIE_POWER))


def _base_params(params):
    merged = {
        "objective": config.LGB_OBJECTIVE,
        "metric": "tweedie",
        "verbosity": -1,
        "seed": config.RANDOM_SEED,
        "bagging_seed": config.RANDOM_SEED,
        "feature_fraction_seed": config.RANDOM_SEED,
        "deterministic": True,
        "bagging_freq": 1,
        "num_threads": config.LGB_NUM_THREADS,
    }
    merged.update(params)
    return merged


# ---------------------------------------------------------------------------
# Cross-validation (member-grouped: the `fold` column comes from splits.py)
# ---------------------------------------------------------------------------

def split_fold(train_df, fold):
    """
    (fit_rows, holdout_rows) for one CV split, with the target encodings refitted.

    Rule #3 applied to CV itself: the encodings already on train_df were fitted on ALL of
    its folds, so the rows this split trains on would carry the held-out fold's targets in
    their features. Here the held-out fold gets an encoding fitted on the training folds
    only -- exactly what an out-of-time set gets -- and the training folds get their own
    out-of-fold one. Nothing the split sees depends on a held-out target.
    """
    is_holdout = train_df["fold"].to_numpy() == fold
    fit_rows, holdout_rows = train_df[~is_holdout].copy(), train_df[is_holdout].copy()
    encoding_module.attach_target_encodings(
        train_frames=[fit_rows], other_frames=[holdout_rows], target_column=TARGET)
    return fit_rows, holdout_rows


def cross_validate(train_df, feature_columns, params):
    """
    Out-of-fold predictions over the member-grouped folds already on the frame.

    Returns (mean deviance at the fixed scoring power, mean best iteration).
    """
    params = _base_params(params)
    oof_pred = np.zeros(len(train_df))
    best_iterations = []

    for fold in sorted(train_df["fold"].unique()):
        is_holdout = train_df["fold"].to_numpy() == fold
        fit_rows, holdout_rows = split_fold(train_df, fold)

        train_set = lgb.Dataset(align_features(fit_rows, feature_columns),
                                label=fit_rows[TARGET])
        valid_set = lgb.Dataset(align_features(holdout_rows, feature_columns),
                                label=holdout_rows[TARGET], reference=train_set)

        booster = lgb.train(
            params, train_set,
            num_boost_round=config.LGB_MAX_ROUNDS,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(config.LGB_EARLY_STOPPING_ROUNDS, verbose=False)],
        )
        oof_pred[is_holdout] = booster.predict(
            align_features(holdout_rows, feature_columns), num_iteration=booster.best_iteration
        )
        best_iterations.append(booster.best_iteration)

    deviance = scoring_deviance(train_df[TARGET].to_numpy(), oof_pred)
    return deviance, int(np.mean(best_iterations))


# ---------------------------------------------------------------------------
# Optuna
# ---------------------------------------------------------------------------

def tune(train_df, feature_columns, n_trials=config.OPTUNA_TRIALS, run_name="optuna_search"):
    """
    Small TPE search over the Phase 6 space, scored on mean CV Tweedie deviance.

    Every trial's parameters and score go to MLflow as a nested run.
    Returns (best_params, best_num_boost_round, best_deviance).
    """
    space = config.OPTUNA_SEARCH_SPACE
    results = {}

    def objective(trial):
        params = {
            "tweedie_variance_power": trial.suggest_float(
                "tweedie_variance_power", *space["tweedie_variance_power"]),
            "learning_rate": trial.suggest_float(
                "learning_rate", *space["learning_rate"], log=True),
            "num_leaves": trial.suggest_int("num_leaves", *space["num_leaves"]),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", *space["min_data_in_leaf"]),
            "feature_fraction": trial.suggest_float("feature_fraction", *space["feature_fraction"]),
            "bagging_fraction": trial.suggest_float("bagging_fraction", *space["bagging_fraction"]),
        }
        deviance, best_iteration = cross_validate(train_df, feature_columns, params)
        results[trial.number] = best_iteration

        with mlflow.start_run(run_name=f"trial_{trial.number:02d}", nested=True):
            mlflow.log_params(params)
            mlflow.log_metric("cv_tweedie_deviance", deviance)
            mlflow.log_metric("cv_best_iteration", best_iteration)
        return deviance

    sampler = optuna.samplers.TPESampler(seed=config.RANDOM_SEED)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    with mlflow.start_run(run_name=run_name):
        mlflow.log_param("n_trials", n_trials)
        mlflow.log_param("n_train_rows", len(train_df))
        mlflow.log_param("n_features", len(feature_columns))
        mlflow.log_param("scoring_tweedie_power", config.EVAL_TWEEDIE_POWER)
        study.optimize(objective, n_trials=n_trials)

        mlflow.log_params({f"best_{k}": v for k, v in study.best_params.items()})
        mlflow.log_metric("best_cv_tweedie_deviance", study.best_value)

    return study.best_params, results[study.best_trial.number], study.best_value


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def fit(train_df, feature_columns, params, num_boost_round, model_path=None,
        run_name=None, extra_metrics=None):
    """Train one booster on the whole corpus and optionally save + log it."""
    params = _base_params(params)
    train_set = lgb.Dataset(align_features(train_df, feature_columns), label=train_df[TARGET])
    booster = lgb.train(params, train_set, num_boost_round=num_boost_round)

    if model_path is not None:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        booster.save_model(str(model_path))

    if run_name is not None:
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(params)
            mlflow.log_param("num_boost_round", num_boost_round)
            mlflow.log_param("n_train_rows", len(train_df))
            mlflow.log_param("n_features", len(feature_columns))
            for name, value in (extra_metrics or {}).items():
                mlflow.log_metric(name, value)
            if model_path is not None:
                mlflow.log_artifact(str(model_path))
    return booster


def fit_new_enrollee_model(train_df, feature_columns, model_path=None, run_name=None):
    """
    The second, smaller model -- rule #7.

    New enrollees have demographics and nothing else, and there are only ~80-100 of them
    per set, so they get fixed conservative parameters rather than their own Optuna study
    (Phase 6 says tuning happens on Set A's established rows and nowhere else). Returns
    None if there is nothing to train on, and callers fall back to predicting 1.0 --
    "exactly the population average" -- which is the honest prior for a member we know
    nothing about.
    """
    if len(train_df) == 0:
        return None

    params = dict(config.NEW_ENROLLEE_LGB_PARAMS)
    num_boost_round = params.pop("num_boost_round")
    return fit(train_df, feature_columns, params, num_boost_round,
               model_path=model_path, run_name=run_name)


def predict(booster, df, feature_columns, fallback=1.0):
    """Predict a relative risk score. An empty frame or a missing model yields nothing."""
    if len(df) == 0:
        return np.array([], dtype=float)
    if booster is None:
        return np.full(len(df), fallback, dtype=float)
    return booster.predict(align_features(df, feature_columns))
