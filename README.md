# MA member cost/risk pipeline — synthetic rehearsal

A small, end-to-end dry run of a Medicare Advantage member cost/risk pipeline on tiny
**synthetic** data. The real target is production year 2027 on real claims + MMR + MOR on
Databricks. This repo checks that the pipeline is *structured correctly*: target,
leakage, splits, baseline. Only then does it get pointed at real data.

The metric values mean nothing. Synthetic data has no real signal ceiling, so nothing here
is tuned for R². The claims that matter are:

- the model beats the `raf_score` baseline on the same members
- the leakage and split checks hold

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python pipeline.py                # Phases 1-7, ~10 seconds
python -m pytest tests            # 50 tests, ~3 seconds
```

**Use a plain pip venv, not the Anaconda base environment.** Anaconda's numpy is linked
against MKL, which loads Intel's OpenMP runtime (`libiomp5md.dll`). LightGBM uses
Microsoft's (`vcomp140.dll`). With both loaded in one process, LightGBM crashes at random
mid-training with `Windows fatal exception: access violation`. PyPI wheels load a single
OpenMP runtime, so a venv avoids the problem.

## What each output means

| path | what it is |
|---|---|
| `outputs/eval_report.md` | Both backtests vs the baseline: R² (capped and uncapped), predictive-ratio-by-decile tables, top-5% capture, a `beats baseline` verdict. Also the 2027 trend projection and score distribution. |
| `outputs/predictions_2027.csv` | `member_id, relative_risk_score, predicted_annual_dollar_estimate` for every Set D member. No actual/target column, because at this point in the calendar there isn't one. |
| `outputs/model_backtest1.txt` | LightGBM model trained on Set A only. Produces backtest 1. |
| `outputs/model_final.txt` | Same hyperparameters, refit on A+B. Produces backtest 2. |
| `outputs/model_2027.txt` | Same hyperparameters, refit on A+B+C. Scores Set D. |
| `outputs/model_new_enrollee_2027.txt` | Demographics-only model for members who join in 2027 (see Assumptions). |
| `mlruns/` | Local MLflow store: the Optuna parent run, one nested run per trial, one run per fitted model. Browse with `set MLFLOW_ALLOW_FILE_STORE=true` (bash: `export ...`) then `mlflow ui --backend-store-uri mlruns`. |
| `data/raw/*.parquet` | The three synthetic source tables: `mmr`, `claims`, `mor`. |

## Where each rule is enforced

| rule | enforced in |
|---|---|
| 1. Target is a capped PMPM ratio | `src/target.py`; `tests/test_target.py` (includes "inflate every dollar 37%, the target must not move") |
| 2. Strictly-before `as_of_date` | `features._source_slice` (every source read), `features.assert_no_future_leakage` (ledger per feature block, re-run in `splits.py`); canary tests delete/scramble the future and require identical features |
| 3. Out-of-fold encoding | `src/encoding.py`; also re-fitted inside every CV split (`model.split_fold`) |
| 4. Member-grouped splits | `splits.assign_member_folds` (one fold per member for the whole run) + `splits.assert_member_grouped` |
| 5. Tweedie objective | `config.LGB_OBJECTIVE`, `src/model.py` |
| 6. Always vs a baseline | `src/evaluate.py`: every metric is computed for model and `raf_score` side by side |
| 7. New enrollees separate | `features._build_new_enrollee_features` + `assert_new_enrollee_features`; a second model in `model.fit_new_enrollee_model` |
| 8. No fake Optum BERT | `src/embeddings_stub.py`: returns `None` when off, raises `NotImplementedError` when on |
| 9. Swappable trend | `evaluate.trend_project` |
| 10–11. Libraries, seed | `requirements.txt`; `config.RANDOM_SEED` in numpy, LightGBM and the Optuna sampler. Two runs produce byte-identical outputs. |

The tests were checked by breaking the code on purpose. Ten realistic bugs were
re-introduced one at a time, and the suite caught all ten. Examples: reading one year
into the future, a pooled-year cap, hospice dollars kept, per-row random folds, an
un-refitted CV encoding.

## Assumptions

Anything intent.md left open, and what was decided:

- **Rx is Part D.** It is generated and used as a feature (`cost_rx_*`, `claims_rx_*`) but
  never enters the target, which is Part A+B only.
- **Hospice months** are excluded from dollars but still count as exposure, exactly as the
  formula is written.
- **MOR timing.** The synthetic MOR for year Y is dated Dec 1 of Y, so base-year HCCs and
  raf are usable at the Dec 31 `as_of_date`. The real MOR for Y lands partway through Y+1.
  See Porting.
- **Claim dates.** Synthetic service days are capped at the 28th, so every December
  claim is strictly before Dec 31.
- **Established vs new enrollee.** Established means at least one enrolled month in the
  base year; `months_history_available` records how many. New enrollee means zero
  base-year months. New enrollees get demographics only.
- **New enrollees are scored when they join.** Each one's `as_of_date` is the day after
  their first MMR record. It is set per row, and the one record they read is strictly
  before it.
- **The new-enrollee model** uses fixed, conservative parameters rather than its own
  Optuna study, because tuning happens on Set A's established rows only. If there are no
  training rows, it predicts 1.0 (population average).
- **Set D** is the members still enrolled at 2026-12-31 (active in December). It has no
  new enrollees by construction, because 2027 joiners are not known yet.
  `model_new_enrollee_2027.txt` is saved for scoring them as they enroll.
- **Expected 2027 exposure** is 12 months for every member.
- **The baseline** is base-year `raf_score` divided by the mean `raf_score` of the scored
  population, so 1.0 means population average, as it does for the target. No outcome
  data is used to rescale it. New enrollees have no base-year raf, so they enter the
  baseline at 1.0.
- **The beats-baseline verdict** is R² against the capped target (the trained target), as
  specified. Top-5% capture is reported but is not part of the verdict. In backtest 1 the
  baseline actually wins on capture (45.7% vs 43.6%). That is reported as-is.
- **`raf_score_base` is also a model feature.** Production risk models use RAF as an
  input. It is base-year data, so it is leak-safe.
- **Optuna scoring.** `tweedie_variance_power` is tuned, which changes the deviance's
  units between trials. Every trial is therefore scored at one fixed power
  (`config.EVAL_TWEEDIE_POWER = 1.5`). The tuned power is still what trains the model.
  Boosting rounds are the mean early-stopped best iteration across the CV folds.
- **Refits reuse Set A's hyperparameters.** B and C never influence tuning.
- **Target encoding.** Smoothing weight is 200, and the smoothing prior leaves the own
  fold out too. Unseen categories get the global mean. Raw `county_id` and
  `pcp_provider_id` are identifiers, never features. Frequency counts are taken over every
  base-year member, not just the ones who turn out to have target-year exposure.
- **The synthetic dollars carry a 5%/yr medical trend** (`config.ANNUAL_COST_TREND`), so
  population PMPM genuinely rises. That is what the relative target has to divide out.
- **LightGBM runs with 4 threads** (`config.LGB_NUM_THREADS`) and `deterministic=True`.
- **MLflow ≥ 3.16 refuses the plain-folder store** unless `MLFLOW_ALLOW_FILE_STORE=true`.
  `src/model.py` sets it.

## Porting to Databricks

- Swap `pandas` frames for Spark DataFrames in `spine.py`/`features.py` only. The module
  boundaries (spine/target/features/splits/model/evaluate) are deliberately pure functions,
  so the change stays localized. pandas itself is a legitimate production choice too (e.g.
  a single-node Databricks cluster). This swap is about scaling to 5M+ members, not
  correctness.
- Point the MLflow tracking URI at the Databricks-managed tracking server instead of the
  local `mlruns/` folder. That is one line, `config.MLFLOW_TRACKING_URI`, and the
  `MLFLOW_ALLOW_FILE_STORE` block in `model.py` goes away.
- Replace `make_synthetic_data.py`'s output with real reads from the MMR/claims/MOR Delta
  tables in Unity Catalog, keeping the same column contracts `spine.py` expects:
  - `mmr`: `member_id, year, month, month_start`, demographics, `hospice, county_id, pcp_provider_id`
  - `claims`: `claim_id, member_id, year, month, service_date, category, allowed_amount`
  - `mor`: `member_id, year, hcc_*, hcc_count, raf_score, source_date`
- Implement `embeddings_stub.get_member_embeddings` against the real Optum BERT endpoint on
  the serverless GPU. Honour its contract, including `.attrs["max_source_date"]` so the
  leakage assertion can check it.
- Replace `trend_project` with the real actuarial trend assumption, cross-checked against
  the published FFS trend rate. Never use the CMS county benchmark rate.
- Expand `config.py`'s feature list and Optuna budget once this runs correctly at small
  scale. This repo intentionally uses a fraction of the real feature catalog.

Two real-data differences the leakage checks will surface. Both are hard stops, by design:

- **Real claims include Dec 29–31 service dates.** These are not strictly before a Dec 31
  `as_of_date`, so `_source_slice` will stop the run. Either filter claims at claim grain
  before building the spine, or define `as_of_date` as Jan 1 of Y+1. Do not loosen the
  check.
- **Real MOR for year Y arrives in Y+1.** Set `mor.source_date` to the actual file date.
  If that lands after the `as_of_date`, use the prior year's MOR in the features rather
  than moving the date.
