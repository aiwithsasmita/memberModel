# Intent: MA Member Cost/Risk Pipeline — Synthetic Rehearsal

## What this is

A small, correct, end-to-end rehearsal of a Medicare Advantage member cost/risk pipeline,
built on tiny **synthetic** data. The real target is production year **2027**, on real
claims + MMR + MOR data, on Databricks/Spark with a serverless GPU. This repo is not that —
it is a fast, local dry run of the exact same logic, so the person running it can verify the
pipeline is *structured correctly* before pointing it at real data on a company laptop.

**Priority order: correctness of target/leakage/split logic > code cleanliness > model
accuracy.** Synthetic data has no real signal ceiling — do not tune for a better R² on it.
If every phase's acceptance check passes, this is done, regardless of the metric values.

Do not ask clarifying questions. Use the defaults in `config.py`. If you must deviate,
write the deviation and why in `README.md` under "Assumptions" and keep going.

## Non-negotiable rules

These encode mistakes that are easy to make and expensive to find later. Follow them exactly.

1. **Target = a PMPM ratio to the population mean, capped — never raw dollars pooled across years.** See the formula below. Training on raw dollars mixed across years lets the model absorb medical trend as if it were risk.
2. **Every feature row has an explicit `as_of_date`.** A feature may only use source rows dated strictly before it. Enforce this with a callable assertion in code, not a comment — see Phase 3.
3. **Any mean/target encoding of a categorical column must be out-of-fold.** Fit-and-transform on the same rows it trains on is leakage, full stop.
4. **Splits are member-grouped.** A `member_id` never appears in both a training fold and its held-out fold.
5. **Model objective is Tweedie**, not squared error on log(cost). This dataset is zero-inflated with a heavy right tail by construction (see Phase 1) — squared-error-on-log will visibly mis-calibrate the tail; that's intentional, it's the point of the rehearsal.
6. **Every result is reported against a baseline**, never in a vacuum. The synthetic `raf_score` (Phase 1) stands in for the real CMS RAF. "Better than baseline" is the only claim that means anything here.
7. **New enrollees (no base-year history) are a separate code path**, not a row with nulls filled in.
8. **Do not fabricate a working Optum-BERT integration.** No public model may stand in for it. Build the interface only (Phase 8); leave it unimplemented and switched off by default.
9. **Do not use a benchmark-rate as the dollar-trend factor.** Use a simple, clearly-swappable trend function (Phase 7). The real trend assumption is an actuarial input to be supplied later, not a policy rate.
10. **Only real, pip-installable, production-grade libraries**: pandas, numpy, lightgbm, optuna, scikit-learn, mlflow, pyarrow. No PySpark for this rehearsal — see "Porting to Databricks" for why and what changes.
11. Fix `RANDOM_SEED = 42` everywhere (numpy, LightGBM, Optuna sampler). The whole run should finish in well under two minutes.

## The target formula (implement exactly this)

```
For member m, target year T:
  actual_cost_T(m)  = sum of allowed$ for m in year T, Part A+B categories, excluding any
                       month m was in hospice status
  exposure_T(m)     = enrolled months for m in year T   (drop m from the target if this is 0)
  member_pmpm(m)    = actual_cost_T(m) / exposure_T(m)

Population reference, computed over ALL members with exposure in year T:
  population_pmpm_T = sum(actual_cost_T over all members) / sum(exposure_T over all members)

Training target:
  relative_target(m)        = member_pmpm(m) / population_pmpm_T
  relative_target_capped(m) = min(relative_target(m), P99.5 of relative_target within year T)
```

Train on `relative_target_capped`. Keep `relative_target` (uncapped) for reporting only.
This single ratio already accounts for both a member's own exposure and that year's cost
level — no separate LightGBM exposure offset is needed on top of it.

To convert a prediction back to a dollar estimate for a future year (Phase 7):

```
projected_population_pmpm(year) = trend_project(known population_pmpm_T history, year)
predicted_pmpm(m)  = model.predict(features(m)) * projected_population_pmpm(year)
predicted_annual(m) = predicted_pmpm(m) * expected_exposure_months(m)
```

## Repo layout to create

```
ma_risk_pipeline/
  README.md
  requirements.txt
  config.py                 # every constant lives here — see Phase 0
  data/make_synthetic_data.py
  src/
    spine.py                # member-month spine from the raw synthetic tables
    target.py                # the formula above, per (base_year, target_year) pair
    features.py              # feature table for one as_of_date + leakage assertion
    encoding.py               # generic out-of-fold target encoder
    splits.py                 # assembles the row sets in Phase 5
    model.py                  # LightGBM + Tweedie + small Optuna search + MLflow logging
    evaluate.py                # decile / predictive-ratio / top-5% capture report vs baseline
    embeddings_stub.py         # Optum-BERT interface — not implemented, see Phase 8
  pipeline.py                 # runs everything end to end with one command
  tests/
    test_leakage.py
    test_target.py
  outputs/                    # run artifacts land here
```

## Phase 0 — config.py

```
N_MEMBERS = 2000
YEARS = [2022, 2023, 2024, 2025, 2026]     # 2027 is scored later with no ground truth
CAP_PERCENTILE = 0.995
N_DECILES = 10
N_HCC_FLAGS = 15
N_COUNTIES = 20
N_PROVIDERS = 100
OPTUNA_TRIALS = 20
CV_FOLDS = 5
RANDOM_SEED = 42
```

## Phase 1 — synthetic data (`make_synthetic_data.py`)

Give every member a fixed latent `true_risk` (draw once, lognormal), nudged slightly year
to year to imitate disease progression. `true_risk` drives four things, so the pipeline has
real (if simple) signal to recover:

- **Monthly cost.** Each member-month: with a probability that increases with `true_risk`
  (baseline ~25%), draw a claim amount from a right-skewed distribution (lognormal or gamma)
  scaled by `true_risk`; otherwise $0. Split the drawn amount across categories (inpatient,
  outpatient, ER, professional, Rx) with fixed rough proportions. Separately, give ~0.3% of
  member-years a catastrophic multiplier (20–50x that year's cost) — this is what makes the
  tail fat, matching the real book's shape (most members cheap, a few very expensive).
- **Synthetic HCC flags** (`N_HCC_FLAGS` binary columns per member-year): each flag's
  probability increases with `true_risk`, so they're correlated with cost the way real HCCs are.
- **Synthetic `raf_score`**: a noisy monotonic function of `true_risk` (add real noise — it
  should be a decent but imperfect predictor, the same way the real RAF is).
- **Demographics/MMR-like fields**: age, sex, dual flag, OREC, hospice flag (rare), ESRD flag
  (rare), `county_id` (1 of `N_COUNTIES`), enrolled months per member-year (mostly 12, some
  partial-year to exercise the exposure logic). Also assign each member a `pcp_provider_id`
  (1 of `N_PROVIDERS`) to exercise high-cardinality encoding.

Write three raw tables to `data/raw/` (parquet): `mmr` (member × year × month demographics),
`claims` (member × month × category $ amounts), `mor` (member × year × HCC flags + raf_score).
Print row counts and the cost distribution's zero-rate and percentiles — confirm by eye that
it's skewed (mostly zero/low, long tail), not roughly normal.

## Phase 2 — spine (`spine.py`)

Join `mmr` + `claims` + `mor` into one member-month table. One row per member per
enrolled month. This is the only place raw tables get joined; everything downstream reads
from the spine.

## Phase 3 — features (`features.py`)

For a given `as_of_date` (Dec 31 of a base year), build a modest feature set — this is a
rehearsal, not the full production catalog:

- Cost by category at 6- and 12-month trailing windows, each expressed as a ratio to that
  base year's population PMPM (same normalization idea as the target, applied to the
  base-year side).
- Utilization counts (claim counts by category) over the same windows.
- HCC flags + HCC count from `mor`.
- Demographics from `mmr`: age, sex, dual, OREC, ESRD, hospice.
- `county_id` and `pcp_provider_id` encoded via `encoding.py` (out-of-fold target encoding —
  see Phase 4) plus a raw frequency count for each.
- `months_history_available` and `has_any_claim` (claims-derived numerics fill 0; MMR fields
  keep nulls).

Write `assert_no_future_leakage(df, as_of_date)` in `features.py`: it re-derives the max
source date touched by every column-building step and raises if any of them is `>= as_of_date`.
Call it at the end of feature building — a failure here is a hard stop, not a warning.

## Phase 4 — out-of-fold encoding (`encoding.py`)

One reusable function: given a categorical column, a target column, and a fold assignment,
return the leave-own-fold-out mean-encoded column (smoothed toward the global mean with a
configurable weight, default 200). Training rows never see their own fold's contribution;
non-training rows (OOT/score) get the encoding computed from all training rows.

## Phase 5 — splits (`splits.py`)

Build these four row sets from the spine + target(Phase 2) + features(Phase 3):

| Set | Base year (features) | Target year | Role |
|---|---|---|---|
| A | 2022 | 2023 | Train — 5-fold CV, grouped by `member_id` |
| B | 2023 | 2024 | Backtest 1 (out-of-time) |
| C | 2024 | 2025 | Backtest 2 (out-of-time, after refit on A+B) |
| D | 2026 | — (none) | Score — the "2027" rehearsal, no target column populated |

New enrollees (no base-year history) are routed to a separate, smaller feature set
(demographics only) in every set above — do not let them fall through with imputed history.

## Phase 6 — model (`model.py`)

LightGBM, `objective="tweedie"`. Small Optuna study (`OPTUNA_TRIALS` trials, TPE sampler,
seeded) over: `tweedie_variance_power` [1.1–1.9], `learning_rate` [0.01–0.1, log], `num_leaves`
[15–127], `min_data_in_leaf` [20–200], `feature_fraction` [0.5–1.0], `bagging_fraction`
[0.5–1.0]. Optimize mean CV Tweedie deviance on Set A only — never let B, C, or D touch
tuning. Log every trial's params and the chosen model's params/metrics to MLflow using a
local file-based tracking URI (`mlruns/` in the repo root — no server needed). Save the
final model to `outputs/model_backtest1.txt` (trained on A only) and, after refit,
`outputs/model_final.txt` (trained on A+B).

## Phase 7 — evaluate (`evaluate.py`)

For Backtest 1 (model from A, applied to B) and Backtest 2 (model from A+B, applied to C),
each against that set's actual outcome and against the synthetic `raf_score` baseline
(rescaled to the same relative-to-population-mean basis), compute and write to
`outputs/eval_report.md`:

- R² (both capped and uncapped relative target)
- A predictive-ratio-by-decile table: sort members by *predicted* value into 10 equal groups,
  sum predicted ÷ sum actual within each group — model's column next to baseline's column
- Top-5% capture: of members who were actually in the top 5% of cost, what fraction did the
  model's top-5%-predicted group catch, versus the baseline's
- One printed line per backtest: `"beats baseline: yes/no"` based on whether model R² >
  baseline R²

Then run the **2027 rehearsal**: refit on A+B+C, score Set D, apply the Phase-7 dollar
conversion (`trend_project` — a simple linear or geometric extrapolation over the known
`population_pmpm_T` history; comment clearly that this is the swap point for a real
actuarial trend assumption, not a benchmark rate). Write `outputs/predictions_2027.csv`
with `member_id, relative_risk_score, predicted_annual_dollar_estimate` — no actual/target
column, because in real life it doesn't exist yet at this point either.

## Phase 8 — embeddings stub (`embeddings_stub.py`)

```
def get_member_embeddings(member_ids, as_of_date) -> pd.DataFrame:
    """
    Production: frozen Optum BERT, mean-pooled over each member's token sequence
    truncated at as_of_date, reduced to ~32 dims via a PCA fit on training rows.
    Not implemented here — no substitute model is used. Controlled by
    config.USE_BERT_EMBEDDINGS (default False).
    """
```

Behind `USE_BERT_EMBEDDINGS=False`, return `None` (features.py must not require it). The
default pipeline run must complete with this off.

## Phase 9 — pipeline.py + README.md

`pipeline.py` runs Phases 1–7 with one command (`python pipeline.py`) and prints a short
summary: row counts per table, both backtests' headline R² and win/loss vs. baseline, and
the list of files written to `outputs/`.

`README.md` (short): what this is, how to run it, what each output file means, an
"Assumptions" section for anything you had to decide, and this **Porting to Databricks**
section:

- Swap `pandas` frames for Spark DataFrames in `spine.py`/`features.py` only — the module
  boundaries (spine/target/features/splits/model/evaluate) are deliberately pure functions
  so this stays localized; pandas itself is a legitimate production choice too (e.g. a
  single-node Databricks cluster), this swap is about scaling to 5M+ members, not correctness.
- Point the MLflow tracking URI at the Databricks-managed tracking server instead of the
  local `mlruns/` folder — one line.
- Replace `make_synthetic_data.py`'s output with real reads from the MMR/claims/MOR Delta
  tables in Unity Catalog, keeping the same column contracts `spine.py` expects.
- Implement `embeddings_stub.get_member_embeddings` against the real Optum BERT endpoint on
  the serverless GPU.
- Replace `trend_project` with the real actuarial trend assumption, cross-checked against
  the published FFS trend rate — never the CMS county benchmark rate.
- Expand `config.py`'s feature list and Optuna budget once this runs correctly at small
  scale — this repo intentionally uses a fraction of the real feature catalog.

## Definition of done

- [ ] `python pipeline.py` completes with no errors in well under two minutes
- [ ] `tests/test_leakage.py` and `tests/test_target.py` both pass
- [ ] `outputs/eval_report.md` shows both backtests' decile tables and a beats-baseline verdict
- [ ] `outputs/predictions_2027.csv` exists, has no actual/target column, and row count
      matches Set D's member count
- [ ] `USE_BERT_EMBEDDINGS=False` by default and the pipeline does not import/require any
      embedding model to complete
- [ ] `README.md`'s Porting section is filled in, not a placeholder

## Optional background

If `ma_member_cost_risk_model_playbook.md` is present alongside this file, it has the fuller
production design (complete feature catalog, full Optuna ranges, the 5-stage feature-selection
funnel, Optum BERT levels 1–4) for when this rehearsal is scaled up on real data — useful
context, not a dependency for this build.
