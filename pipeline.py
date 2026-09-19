"""
Phase 9 -- the whole rehearsal, end to end.

    python pipeline.py

Read this file top to bottom to understand the pipeline. It is deliberately linear: each
block is one phase, in order, with no indirection. Everything it calls lives in src/ and
every constant it uses lives in config.py.

    Phase 1   synthetic raw tables                data/make_synthetic_data.py
    Phase 2   member-month spine                  src/spine.py
    Phase 3   the PMPM-ratio target               src/target.py
    Phase 3   features + leakage assertion        src/features.py
    Phase 4   out-of-fold target encoding         src/encoding.py
    Phase 5   the four row sets                   src/splits.py
    Phase 6   LightGBM + Tweedie + Optuna         src/model.py
    Phase 7   evaluation vs baseline, 2027        src/evaluate.py
    Phase 8   Optum BERT interface (off)          src/embeddings_stub.py

Three models get trained, on growing corpora, so that each backtest is genuinely out of
time with respect to the data that trained it:

    trained on A      -> scores B   (backtest 1)
    trained on A+B    -> scores C   (backtest 2)
    trained on A+B+C  -> scores D   (the 2027 rehearsal, no ground truth)
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "data"))

import numpy as np
import pandas as pd

import config
import make_synthetic_data
import spine as spine_module
import target as target_module
import features as features_module
import encoding as encoding_module
import splits as splits_module
import model as model_module
import evaluate as evaluate_module

TARGET = model_module.TARGET   # "relative_target_capped"


def banner(text):
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


# ---------------------------------------------------------------------------
# One training stage: encode -> train -> predict
# ---------------------------------------------------------------------------

def prepare_stage(row_sets, train_names, other_names):
    """
    Take fresh copies of the frames for this stage and attach the target encodings.

    Copies matter: the encoding of county_id / pcp_provider_id depends on WHICH sets are
    in the training corpus, so stage 2 (A+B) must not inherit stage 1's (A-only) numbers.
    Recomputing per stage is the honest thing to do and costs nothing at this size.
    """
    train_frames, other_frames = [], []
    frames = {}
    for name in train_names + other_names:
        row_set = row_sets[name]
        pair = (row_set.established.copy(), row_set.new_enrollees.copy())
        frames[name] = pair
        (train_frames if name in train_names else other_frames).extend(pair)

    encoding_module.attach_target_encodings(
        train_frames=train_frames, other_frames=other_frames, target_column=TARGET,
    )
    return frames


def predict_row_set(established, new_enrollees, main_model, new_model,
                    est_features, new_features):
    """
    Score both populations and stack them back together.

    Rule #7 in action: established members go through the full-feature model, new enrollees
    through the demographics-only one. They are never mixed, and a new enrollee is never
    handed to the main model with its history columns filled with zeros.
    """
    est = established[["member_id"]].copy()
    est["predicted"] = model_module.predict(main_model, established, est_features)
    est["baseline_raw"] = established["raf_score_base"].to_numpy(dtype=float)
    est["row_kind"] = "established"

    new = new_enrollees[["member_id"]].copy()
    new["predicted"] = model_module.predict(new_model, new_enrollees, new_features)
    # A new enrollee has no base-year MOR, so the raf baseline has nothing to say about
    # them: they enter the baseline at the population average of the established members.
    new["baseline_raw"] = est["baseline_raw"].mean() if len(est) else 1.0
    new["row_kind"] = "new_enrollee"

    for source, frame in ((established, est), (new_enrollees, new)):
        for column in ("relative_target", "relative_target_capped", "exposure_months"):
            frame[column] = source[column].to_numpy() if column in source.columns else np.nan

    return pd.concat([est, new], ignore_index=True)


def main():
    started = time.time()
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_module.setup_mlflow()

    # ---------------------------------------------------------------- Phase 1
    banner("Phase 1 -- synthetic raw data")
    make_synthetic_data.generate()
    mmr, claims, mor = make_synthetic_data.load_raw()

    # ---------------------------------------------------------------- Phase 2
    banner("Phase 2 -- member-month spine")
    spine = spine_module.build_spine(mmr, claims, mor)
    pmpm_history = spine_module.population_pmpm_history(spine, config.YEARS)
    print(f"spine rows: {len(spine):,}  ({spine['member_id'].nunique():,} members, "
          f"{len(config.YEARS)} years)")
    print("population PMPM (Part A+B, exposure-weighted) by year:")
    for year, value in sorted(pmpm_history.items()):
        print(f"   {year}: ${value:,.2f}")
    print("   ^ this rises over time. That trend is exactly what the relative target")
    print("     divides out, so the model never learns to call inflation 'risk'.")

    # ---------------------------------------------------------------- Phase 3
    banner("Phase 3 -- targets, features, leakage assertion")
    target_years = [spec["target_year"] for spec in config.SPLITS.values()
                    if spec["target_year"] is not None]
    targets, target_pmpms = target_module.build_targets_for_years(spine, target_years)
    for year in target_years:
        frame = targets[year]
        print(f"target {year}: {len(frame):,} members  "
              f"population PMPM ${frame.attrs['population_pmpm']:,.2f}  "
              f"P{config.CAP_PERCENTILE * 100:g} cap {frame.attrs['cap_value']:.2f}x  "
              f"zero-cost members {(frame['relative_target'] == 0).mean():.1%}")

    # ------------------------------------------------------------ Phases 4+5
    banner("Phase 5 -- row sets (features built here; leakage assertion runs per set)")
    member_folds = splits_module.assign_member_folds(spine["member_id"].unique())
    row_sets = splits_module.build_row_sets(spine, targets, member_folds)
    for row_set in row_sets.values():
        splits_module.assert_member_grouped(row_set)
        print(f"{row_set.describe()}   [{row_set.role}]")
    print("member-grouped fold check passed for every set (rule #4)")
    print("no-future-leakage assertion passed for every feature frame (rule #2)")

    # ---------------------------------------------------------------- Phase 6
    banner("Phase 6 -- tuning on Set A only")
    stage1 = prepare_stage(row_sets, ["A"], ["B"])
    a_established, a_new = stage1["A"]
    b_established, b_new = stage1["B"]

    est_features = config.feature_columns(a_established)
    new_features = config.feature_columns(a_new)
    print(f"{len(est_features)} features for established members, "
          f"{len(new_features)} for new enrollees")

    best_params, best_rounds, best_deviance = model_module.tune(
        a_established, est_features, run_name="optuna_setA")
    print(f"best CV Tweedie deviance (power {config.EVAL_TWEEDIE_POWER}): {best_deviance:.5f}"
          f"   at {best_rounds} rounds")
    for key, value in best_params.items():
        print(f"   {key:<24} {value:.4f}" if isinstance(value, float) else
              f"   {key:<24} {value}")

    # ------------------------------------------------- backtest 1: A -> B
    banner("Phase 7 -- backtest 1: trained on A (2022->2023), scored on B (2023->2024)")
    model_backtest1 = model_module.fit(
        a_established, est_features, best_params, best_rounds,
        model_path=config.OUTPUT_DIR / "model_backtest1.txt",
        run_name="final_model_A", extra_metrics={"cv_tweedie_deviance": best_deviance})
    new_model_1 = model_module.fit_new_enrollee_model(
        a_new, new_features, run_name="new_enrollee_model_A")

    predictions_b = predict_row_set(b_established, b_new, model_backtest1, new_model_1,
                                    est_features, new_features)
    backtest1 = evaluate_module.evaluate_set("Backtest 1 -- Set B (2023 features -> 2024 cost)",
                                             predictions_b)
    print_backtest(backtest1)

    # ------------------------------------------------- backtest 2: A+B -> C
    banner("Phase 7 -- backtest 2: refit on A+B, scored on C (2024->2025)")
    stage2 = prepare_stage(row_sets, ["A", "B"], ["C"])
    corpus2 = pd.concat([stage2["A"][0], stage2["B"][0]], ignore_index=True)
    corpus2_new = pd.concat([stage2["A"][1], stage2["B"][1]], ignore_index=True)
    c_established, c_new = stage2["C"]

    model_final = model_module.fit(
        corpus2, est_features, best_params, best_rounds,
        model_path=config.OUTPUT_DIR / "model_final.txt",
        run_name="final_model_AB")
    new_model_2 = model_module.fit_new_enrollee_model(
        corpus2_new, new_features, run_name="new_enrollee_model_AB")

    predictions_c = predict_row_set(c_established, c_new, model_final, new_model_2,
                                    est_features, new_features)
    backtest2 = evaluate_module.evaluate_set("Backtest 2 -- Set C (2024 features -> 2025 cost)",
                                             predictions_c)
    print_backtest(backtest2)
    print("\nHyperparameters are reused from the Set A study, not re-tuned -- B and C must")
    print("never influence tuning, or they stop being out-of-time (rule: Phase 6).")

    # --------------------------------------------- the 2027 rehearsal: A+B+C -> D
    banner(f"Phase 7 -- the {config.SCORE_YEAR} rehearsal: refit on A+B+C, score D")
    stage3 = prepare_stage(row_sets, ["A", "B", "C"], ["D"])
    corpus3 = pd.concat([stage3[n][0] for n in ("A", "B", "C")], ignore_index=True)
    corpus3_new = pd.concat([stage3[n][1] for n in ("A", "B", "C")], ignore_index=True)
    d_established, d_new = stage3["D"]

    model_score = model_module.fit(
        corpus3, est_features, best_params, best_rounds,
        model_path=config.OUTPUT_DIR / f"model_{config.SCORE_YEAR}.txt",
        run_name="final_model_ABC")
    # Set D holds only members enrolled at 2026-12-31, so it has no new enrollees: anyone
    # joining in 2027 is not known yet. This model is saved for scoring them as they enrol.
    new_model_3 = model_module.fit_new_enrollee_model(
        corpus3_new, new_features,
        model_path=config.OUTPUT_DIR / f"model_new_enrollee_{config.SCORE_YEAR}.txt",
        run_name="new_enrollee_model_ABC")

    predictions_d = predict_row_set(d_established, d_new, model_score, new_model_3,
                                    est_features, new_features)

    projected_pmpm = evaluate_module.trend_project(pmpm_history, config.SCORE_YEAR)
    predictions_path, prediction_frame = evaluate_module.write_predictions(
        predictions_d, projected_pmpm)

    print(f"projected {config.SCORE_YEAR} population PMPM: ${projected_pmpm:,.2f}   "
          f"(last known {max(pmpm_history)}: ${pmpm_history[max(pmpm_history)]:,.2f})")
    print(f"scored members: {len(prediction_frame):,}")
    dollars = prediction_frame["predicted_annual_dollar_estimate"]
    print(f"predicted annual dollars: mean ${dollars.mean():,.0f}   "
          f"median ${dollars.median():,.0f}   max ${dollars.max():,.0f}")

    score_summary = (
        f"Members scored: **{len(prediction_frame):,}** "
        f"({len(d_established):,} established, {len(d_new):,} new enrollees)\n\n"
        f"Assumed exposure for each member in {config.SCORE_YEAR}: "
        f"**{config.ASSUMED_FUTURE_EXPOSURE_MONTHS} months** (see README, Assumptions).\n\n"
        f"| statistic | relative risk score | predicted annual dollars |\n"
        f"|---|---:|---:|\n"
        f"| mean | {prediction_frame['relative_risk_score'].mean():.3f} | "
        f"${dollars.mean():,.0f} |\n"
        f"| median | {prediction_frame['relative_risk_score'].median():.3f} | "
        f"${dollars.median():,.0f} |\n"
        f"| p95 | {prediction_frame['relative_risk_score'].quantile(0.95):.3f} | "
        f"${dollars.quantile(0.95):,.0f} |\n"
        f"| max | {prediction_frame['relative_risk_score'].max():.3f} | "
        f"${dollars.max():,.0f} |\n"
    )

    # ---------------------------------------------------------------- report
    report_path = evaluate_module.write_report(
        results=[
            (backtest1, "Model trained on Set A only (features as of 2022-12-31, target 2023), "
                        "then applied out of time to Set B."),
            (backtest2, "Model refit on Sets A+B with the SAME hyperparameters, then applied "
                        "out of time to Set C."),
        ],
        pmpm_history=pmpm_history,
        projected_pmpm=projected_pmpm,
        score_summary=score_summary,
    )

    # --------------------------------------------------------------- summary
    banner("Summary")
    print(f"raw tables      mmr {len(mmr):>8,}   claims {len(claims):>8,}   mor {len(mor):>8,}")
    print(f"spine           {len(spine):>8,} member-months")
    for row_set in row_sets.values():
        print(f"                {row_set.describe()}")
    print()
    for result in (backtest1, backtest2):
        verdict = "YES" if result["beats_baseline"] else "NO "
        print(f"{result['name']}")
        print(f"   R2 model {result['model_r2_capped']:.4f}   "
              f"baseline {result['baseline_r2_capped']:.4f}   "
              f"top-5% capture {result['model_top_capture']:.1%} vs "
              f"{result['baseline_top_capture']:.1%}")
        print(f"   beats baseline: {verdict}")
    print()
    print("files written to outputs/:")
    for path in sorted(config.OUTPUT_DIR.iterdir()):
        print(f"   {path.name:<28} {path.stat().st_size / 1024:>8,.1f} KB")
    print(f"\nMLflow runs: {config.MLFLOW_TRACKING_URI}")
    print(f"report:      {report_path}")
    print(f"predictions: {predictions_path}")
    print(f"\nelapsed: {time.time() - started:.1f}s")


def print_backtest(result):
    print(f"members scored: {result['n_members']:,}")
    print(f"   R2 (capped target)     model {result['model_r2_capped']:>8.4f}   "
          f"baseline {result['baseline_r2_capped']:>8.4f}")
    print(f"   R2 (uncapped target)   model {result['model_r2_uncapped']:>8.4f}   "
          f"baseline {result['baseline_r2_uncapped']:>8.4f}")
    print(f"   top-5% capture         model {result['model_top_capture']:>8.1%}   "
          f"baseline {result['baseline_top_capture']:>8.1%}")
    print(f"   beats baseline: {'yes' if result['beats_baseline'] else 'no'}")


if __name__ == "__main__":
    main()
