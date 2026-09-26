# SPEC: Member Risk Score Model (Multi-Horizon, Beats CMS-HCC)

**Spec ID:** MRS-001 | **Owner:** Aiwithsasmita | **Platform:** Databricks (Unity Catalog, MLflow, DABs) | **Status:** Draft v1.1 (adds Section 2A formulas, M14 comparison protocol, Appendix A golden test)

---

## 1. Goal

Predict each member's **relative risk score** for the rest of the calendar year at four cutoffs, and beat the CMS-HCC risk score on the same members.

| Horizon | Cutoff date | Months observed in the target year | Months predicted |
|---|---|---|---|
| 0+12 | Jan 1 | 0 | Jan–Dec |
| 2+10 | Mar 1 | 2 | Mar–Dec |
| 5+7 | Jun 1 | 5 | Jun–Dec |
| 8+4 | Sep 1 | 8 | Sep–Dec |

**Definitions**
- **Target:** annualized allowed cost for the predicted months = total allowed cost ÷ eligible member-months × 12, capped per member.
- **Risk score:** predicted dollars converted to a relative score where 1.0 = average. **Use only the formulas in Section 2A.**
- **Data profile:** zero-inflated and heavy-tailed. About 70% of members spend under $10k; the tail is mostly cancer, cardiac and renal members above $100k.

**Out of scope for V1:** clinical outcome prediction (progression, admission, death), monthly cost paths, and real-time scoring.

---

## 2. Global rules (every module must follow)

1. **No leakage.** Every feature must use only records with `paid_date <= cutoff_date - claims_lag_days`, and service dates before the cutoff. Anything on or after the cutoff belongs to the target only.
2. **Time-based splits only.** Split data by target year. Never use random member splits across years.
3. **One HCC version.** Map every year to CMS-HCC **V28**. Never mix V24 and V28.
4. **Configurable parameters.** All constants live in module M0; nothing is hardcoded.
5. **Unity Catalog tables.** Every module writes a Delta table under `{catalog}.{schema}`, with partitioning noted.
6. **Module isolation.** Each module is one notebook or job task with its own tests, runnable alone once its upstream tables exist.
7. **MLflow tracking.** Log every model run with its parameters, metrics, feature list and data version.
8. **PHI.** No member identifiers in logs or MLflow artifacts; use hashed `member_id` only.
9. **One formula library.** Implement every formula in Section 2A **once**, in a shared module (`mrs_formulas`), and import it everywhere. Never re-implement a formula inside a notebook.

---

## 2A. Canonical formulas (single source of truth)

All formulas are computed **separately for each (`target_year`, `cutoff_month`) group**, called a *scoring group* below. Σ means sum over all members in that scoring group. `i` = one member.

**F1. Weight**
`w_i = remaining_member_months_i / 12`

**F2. Weighted mean**
`wmean(x) = Σ(x_i × w_i) / Σ(w_i)`

**F3. Risk score (two versions; store both)**
- **F3a `risk_score_relative`** (default): `pred_i / wmean(pred)` for the same scoring group. The weighted average always equals 1.0. Use it for ranking and care management.
- **F3b `risk_score_base`**: `pred_i / base_mean`. Here `base_mean` = `wmean(actual y_annualized)` for `base_year` (config) at the same `cutoff_month`, computed once and frozen. Use it for trend and pricing: if the population gets sicker, the average goes above 1.0.

**F4. Convert the CMS RAF to dollars (evaluation only)**
- `k_cms = Σ(y_eval_i × w_i) / Σ(RAF_i × w_i)`, the dollars per CMS point
- `cms_pred_i = RAF_i × k_cms`
- `RAF_i` is the final RAF on the member's MMR record for the target year (community, institutional, new-enrollee or ESRD score as CMS assigned it). Do **not** remove the normalization factor or the coding adjustment: they are constant multipliers, and `k_cms` cancels them.

**F5. Rescale any model to the actual total (evaluation only)**
- `k_model = Σ(y_eval_i × w_i) / Σ(pred_i × w_i)`, then `pred_eval_i = pred_i × k_model`
- Apply F5 to **every** model in the comparison (our model and baselines B2 and B3), so all models have the same total and only the ranking and spread differ.
- Log `k_model` in MLflow. If it's outside 0.95–1.05 for our model, raise a calibration warning.

**F6. `y_eval`, the actual used for scoring**
- `y_eval = y_capped` for the **capped** evaluation (headline).
- `y_eval = y_annualized` for the **uncapped** evaluation.
- For the capped evaluation, cap the predictions at the same `cost_cap` before F5.

**F7. Metrics** (all weighted by `w_i`; `p` = rescaled prediction, `a` = `y_eval`)
| Metric | Formula | Better when |
|---|---|---|
| MAE | `Σ(w_i × |a_i − p_i|) / Σ w_i` | lower |
| MAE % | `MAE / wmean(a)` | lower |
| R² | `1 − Σ w_i(a_i − p_i)² / Σ w_i(a_i − wmean(a))²` | higher |
| CPM (Cumming's prediction measure) | `1 − Σ w_i|a_i − p_i| / Σ w_i|a_i − wmean(a)|` | higher |
| Predictive ratio for group G | `Σ_G(w_i × p_i) / Σ_G(w_i × a_i)` | closer to 1.00 |
| Top-k% capture | share of the actual top-k% members (by `a`) who are also in the predicted top-k% (by `p`), for k = 1 and 5 | higher |
| Gini | `2 × AUC_lorenz − 1`, with members sorted by `p` and cumulative share of `a` | higher |

**F8. Evaluation groups (for predictive ratios)**
- `decile`: 10 equal-weight groups by **predicted** risk (F3a) of **that model**
- `condition_group` (one per member, first match wins): ESRD → cancer_metastatic → cancer_active → renal_ckd4plus → heart_failure → other_cardiac → diabetes → other_chronic → zero_spend_prior12 → other. Codes come from M7e/M7g; the group is **fixed at the cutoff**, never taken from the target period.
- `age_band`: <65, 65–69, 70–74, 75–79, 80–84, 85+
- `new_member_flag`: 0 or 1
- `actual_cost_band` (report only): $0, <$1k, $1–10k, $10–50k, $50–100k, $100–250k, >$250k

---

## 3. Data split (configurable)

| Split | Target year | History window | Purpose |
|---|---|---|---|
| Train | 2023 | 2022 (12 months) | Fit models |
| Validation | 2024 | 2022–2023 (up to 24 months) | Tuning, early stopping, calibration |
| Test / backtest | 2025 | 2023–2024 | Final comparison with CMS, sign-off by actuarial |

- Set the lookback to a fixed **24 months** and add `hist_months_available`. The train year only has 12 months of history, so the model must learn to handle short history.
- When a later year's actuals arrive, roll the window forward one year.

---

## 4. Module map and gates

```
M0 Config
 └─ M1 Source profiling ............ [DATA GATE]
     ├─ M2 Eligibility spine
     ├─ M3 Claims standardization
     └─ M4 Diagnosis mapping (HCC V28, CCSR)
         └─ M5 Snapshot builder (member × year × cutoff)
             ├─ M6 Target builder ...... [TARGET GATE]
             └─ M7a–M7h Feature modules
                 └─ M8 Feature assembly + leakage audit .. [FEATURE GATE]
                     ├─ M9  Baselines (CMS RAF, HCC-only refit)
                     ├─ M10 Main model (LightGBM Tweedie)
                     ├─ M11 High-cost classifier            (V1.1)
                     ├─ M12 Excess layer + final score      (V1.1)
                     ├─ M13 Calibration
                     ├─ M14 Evaluation report ... [MODEL GATE]
                     ├─ M15 Explainability (SHAP)           (V1.1)
                     └─ M16 Scoring + monitoring            (V2)
```

A gate must pass before any module downstream of it starts.

---

## 5. Module specifications

### M0 — Config
- **Output:** `config.yaml` (versioned in the repo), loaded by every module.
- **Keys:**
  - `catalog`, `schema`
  - `target_years: [2023, 2024, 2025]`
  - `cutoff_months: [0, 2, 5, 8]`
  - `claims_lag_days: 30` (confirm against the production paid-through lag)
  - `lookback_months: 24`
  - `cost_cap: 250000`, `cost_cap_alt: 500000`
  - `high_cost_threshold: 100000`
  - `hcc_version: V28`
  - `min_member_months: 1`
  - `random_seed: 42`
  - `base_year: 2023` (the frozen denominator year for F3b)
  - `eval_split: test` (the split used for the Model Gate)
  - `bootstrap_n: 200`, `bootstrap_sample_frac: 0.2`
  - `pr_min_group_weight: 1000` (minimum total `w` for a group to count toward gate checks)
- **Tests:** the config loads, every key exists, and the types are valid.
- **Also build in M0:** the shared `mrs_formulas` module (Section 2A), with unit tests that pass the **golden test in Appendix A**. No other module starts until the golden test passes.

### M1 — Source profiling [DATA GATE]
- **Input:** raw claims (medical and Rx), eligibility, MMR and MOR tables.
- **Output:** `dq_source_profile` (row counts, null rates, date ranges, value distributions by year and month).
- **Checks (the gate fails if any fails):**
  - Monthly claim volume and allowed cost have no gap or spike larger than ±30% month over month without a known reason.
  - `paid_date >= service_date` on at least 99.5% of rows.
  - Allowed amount is non-null on at least 99% of rows; the rate of negative amounts (reversals) is reported.
  - MMR covers every eligible member-month, with at least 98% match to eligibility.
  - ICD-10 codes are valid for at least 99% of diagnosis rows.
- **Deliverable:** a one-page data quality summary, attached to the gate review.

### M2 — Eligibility spine
- **Output:** `member_month_spine` (`member_id`, `year_month`, `eligible_flag`, `plan_type`, `death_flag`, `disenroll_flag`), partitioned by year.
- **Logic:** one row per member per eligible month. Death and disenrollment flags come from MMR/eligibility.
- **Tests:**
  - No duplicate (`member_id`, `year_month`) pairs.
  - Member counts per year are within 1% of the official enrollment report.

### M3 — Claims standardization
- **Output:** `claims_std` with these columns:
  - `member_id`, `claim_id`, `service_date`, `paid_date`, `allowed_amt`
  - `setting`: IP, OP, ER, PROF, SNF, HH, DME, RX, RX_SPEC or OTHER
  - `dx_codes` (array), `cpt_hcpcs`, `ndc`, `pos`, `provider_specialty`
- **Logic:**
  - Net reversals and adjustments to the final claim.
  - Assign the setting from bill type, place of service and revenue codes.
  - Specialty Rx means a specialty-drug flag, or a single fill above $1,000 (configurable).
- **Tests:**
  - Total allowed cost per year matches finance totals within 1%.
  - No duplicate final `claim_id`.
  - Every row has a `setting`.

### M4 — Diagnosis mapping
- **Output:**
  - `member_dx_events` (`member_id`, `service_date`, `paid_date`, `icd10`, `hcc_v28`, `ccsr`)
  - `ref_icd_hcc_v28`
  - `ref_icd_ccsr`
- **Logic:**
  - Map each ICD-10 code to a V28 HCC. Store the mapping before the hierarchy is applied; the hierarchy is applied later, in M7e.
  - Map each ICD-10 code to AHRQ CCSR (default category plus all categories).
  - Only use diagnoses from claim types CMS accepts for risk adjustment for the HCC features. Keep all diagnoses for CCSR.
- **Tests:**
  - At least 98% of ICD codes map to CCSR.
  - The HCC mapping reproduces the MOR HCCs for a sample of 1,000 members with at least 95% agreement (differences explained).

### M5 — Snapshot builder
- **Output:** `snapshot` (`member_id`, `target_year`, `cutoff_month`, `cutoff_date`, `feature_asof_date`, `remaining_member_months`, `hist_months_available`, `new_member_flag`), partitioned by target year and cutoff month.
- **Logic:**
  - Build one row per member × target year × cutoff month where the member is eligible for at least 1 month from the cutoff to Dec 31.
  - `cutoff_date` = the first day of month (cutoff_month + 1). `feature_asof_date` = `cutoff_date` − `claims_lag_days`.
  - `remaining_member_months` = eligible months from the cutoff to Dec 31.
- **Tests:**
  - Row counts per cutoff match the eligibility spine.
  - `remaining_member_months` is between 1 and (12 − cutoff_month).

### M6 — Target builder [TARGET GATE]
- **Output:** `target` (`member_id`, `target_year`, `cutoff_month`, `allowed_remaining`, `y_annualized`, `y_capped`, `y_excess`, `y_highcost_flag`, `weight`).
- **Logic:**
  - `allowed_remaining` = allowed cost with service date from the cutoff to Dec 31, using fully run-out claims (at least 3 months of run-out).
  - `y_annualized` = `allowed_remaining` ÷ `remaining_member_months` × 12.
  - `y_capped` = min(`y_annualized`, `cost_cap`).
  - `y_excess` = max(0, `y_annualized` − `cost_cap`).
  - `y_highcost_flag` = `y_annualized` > `high_cost_threshold`.
  - `weight` = `remaining_member_months` ÷ 12.
- **Gate checks:**
  - The weighted mean of `y_annualized` matches actual per-member-per-month cost × 12 within 1%.
  - The share of zero-cost members and the 50th, 90th, 99th and 99.9th percentiles are reported for each year and cutoff.
  - Decedents and disenrolled members are kept, with exposure-weighted targets.

### M7 — Feature modules
Each submodule writes its own table keyed on (`member_id`, `target_year`, `cutoff_month`) and only reads data where `paid_date <= feature_asof_date` and `service_date < cutoff_date`.

| Module | Table | Features | Version |
|---|---|---|---|
| **M7a Demographics and MMR** | `feat_demo` | Age, sex, original reason for entitlement, dual status, LIS, ESRD, hospice, institutional, community or institutional segment, latest RAF (V28), `new_member_flag` | V1 |
| **M7b Cost history** | `feat_cost` | Allowed cost for the last 3, 6, 12 and 24 months, in total and by setting; zero-cost months count; cost slope over the last 6 months; maximum single month | V1 |
| **M7c Current year to date** | `feat_ytd` | Year-to-date allowed cost by setting, YTD admissions and ER visits, new diagnoses this year (count and CCSR flags), months since last admission. **All zero or null when cutoff = 0** | V1 |
| **M7d Utilization** | `feat_util` | Admissions, inpatient days, ER visits, SNF days, home health, DME and distinct provider count, over the last 6 and 12 months | V1 |
| **M7e Diagnoses** | `feat_dx` | V28 HCC flags after the hierarchy, HCC flags before the hierarchy, HCC count, CCSR flags over the last 12 and 24 months, months since first and last occurrence for the top 50 CCSR categories | V1 |
| **M7f Rx** | `feat_rx` | Drug-class flags (ATC level 3 or USP), specialty Rx cost, count of distinct drug classes, adherence gaps for chronic drug classes | V1 |
| **M7g Clinical states** | `feat_clin` | **Renal:** latest CKD stage, stage change in the last 12 months, fistula or graft creation flag, dialysis start and months on dialysis, transplant. **Cancer:** site group, metastatic flag, phase (new, active treatment, maintenance, remission or end of life), line of therapy, hospice or palliative flag. **Cardiac:** heart failure type, heart failure admissions in the last 6 and 12 months, devices (ICD, CRT, LVAD), recent MI or stroke, guideline therapy flags | Renal V1.1, cancer and cardiac V2 |
| **M7h History flags** | `feat_hist` | `hist_months_available`, `cutoff_month`, gap months in enrollment | V1 |

**Tests for every submodule:**
- One row per key, and the row count equals the `snapshot` row count.
- A leakage test: the max `paid_date` used is on or before `feature_asof_date`. Assert it on a 1% sample by recomputing from raw data.
- Null and zero rates are logged; any feature that is 100% constant is dropped.

### M8 — Feature assembly and leakage audit [FEATURE GATE]
- **Output:** `model_dataset` (the snapshot joined with the M6 target and all M7 features), plus `feature_dictionary` (name, source module, definition, data type, version).
- **Gate checks:**
  - The join keeps every snapshot row.
  - **Target-shuffle test:** a quick LightGBM model on shuffled targets must reach R² ≤ 0.01.
  - **Leakage sniff test:** no single feature has correlation above 0.9 with the target at cutoff 0.
  - The feature dictionary covers 100% of the columns.

### M9 — Baselines
- **Output:** one table, `pred_baselines` (`member_id`, `target_year`, `cutoff_month`, `model_name`, `pred_raw`), with `model_name` ∈ {`B1_CMS`, `B2_HCC_REFIT`, `B3_PRIOR_COST`}.
- **B1_CMS:**
  - `pred_raw` = the member's final RAF for the target year, from MMR. Store the RAF itself here; it is converted to dollars only inside M14 with F4.
  - Use the **same RAF for all four cutoffs** of a year. CMS does not update for claims in the current year, and that's intended.
  - Members with no RAF get null here, and are handled by the M14 population rule.
- **B2_HCC_REFIT:** a weighted linear regression (weight `w`) of `y_capped` on age/sex bands, the MMR status flags from M7a and V28 HCC flags after the hierarchy. Fit on the train split only, one model per `cutoff_month`. `pred_raw` = the prediction, floored at 0.
- **B3_PRIOR_COST:** `pred_raw` = allowed cost over the 12 months before `feature_asof_date` (from M7b, which includes year-to-date cost at later cutoffs) ÷ eligible months in that window × 12. Floor at 0.
- **Tests:**
  - At least 95% of eval rows have a non-null `B1_CMS`; the null count is logged.
  - B2 and B3 are non-null for 100% of rows.
  - For B1, `pred_raw` is identical across the four cutoffs for each member and year.

### M10 — Main model: LightGBM Tweedie
- **Output:** MLflow model `mrs_tweedie`, and the table `pred_main`.
- **Setup:**
  - `objective = tweedie`, `tweedie_variance_power` tuned in [1.1, 1.8]
  - Label `y_capped`, sample weight `weight`
  - **One model across all cutoffs**, with `cutoff_month` as a feature
  - Early stopping on validation Tweedie deviance
  - Tune with Hyperopt or Optuna for at most 50 trials: `num_leaves`, `learning_rate`, `min_data_in_leaf`, `feature_fraction`, `lambda_l2`
- **Training compute:** distributed LightGBM (SynapseML) or a single large node on a sample of at least 20% of members, then retrain on the full data.
- **Tests:**
  - Predictions are never negative.
  - The weighted mean prediction is within ±2% of the actual mean in validation, for each cutoff.
  - Training is reproducible with the fixed seed.

### M11 — High-cost classifier (V1.1)
- **Output:** `pred_highcost` (`p_highcost`).
- **Setup:** LightGBM binary model on `y_highcost_flag` with the same features, evaluated with AUPRC.
- **Use:** a care-management flag and a check on the tail. It doesn't change the risk score in V1.1.
- **Test:** AUPRC on validation is above the prevalence rate × 5.

### M12 — Excess layer and final score (V1.1)
- **Output:** `pred_final` (`pred_capped`, `pred_excess`, `pred_total`, `risk_score_relative`, `risk_score_base`).
- **Logic:**
  - `pred_excess` = `p_exceed_cap` × average excess for the member's condition group (cancer, cardiac, renal, ESRD, other), estimated on the train year. `p_exceed_cap` comes from a small classifier or from M11 rescaled to the cap.
  - `pred_total` = `pred_capped` + `pred_excess`.
  - `risk_score_relative` = F3a applied to `pred_total`.
  - `risk_score_base` = F3b applied to `pred_total`.
  - **In V1, before M12 exists:** write `pred_final` from M13's calibrated output, with `pred_total = pred_capped`, `pred_excess = 0`, and both risk scores computed from it.
- **Tests:**
  - The weighted mean of `pred_total` is within ±2% of the uncapped actual mean in validation.
  - The weighted mean of `risk_score_relative` equals 1.0 (±0.0001) in every scoring group.

### M13 — Calibration
- **Output:** `calibrator_{cutoff}` in MLflow, and calibrated predictions.
- **Logic:** fit isotonic regression per cutoff month on validation, from predicted to actual on the capped scale. If isotonic overfits the tail, fall back to a single scaling factor per cutoff.
- **Test:** predicted-to-actual ratio between 0.95 and 1.05 for each decile in validation, for each cutoff.

### M14 — Evaluation report [MODEL GATE]
**Purpose:** prove, with one fixed procedure, whether our model predicts member cost better than CMS. Follow the steps **in this order**. Do not add or skip steps.

**Inputs:**
- `pred_final` (our model = `OURS`)
- `pred_baselines` (`B1_CMS`, `B2_HCC_REFIT`, `B3_PRIOR_COST`)
- `target` (M6) and `snapshot` (M5)
- Condition groups (F8)

**Step 1 — Build the evaluation population**
- Take every row of `snapshot` for the split being evaluated (validation or test). **Never evaluate on the train year.**
- Keep a row only if **all four** models have a non-null prediction. This gives the same members for every model.
- Put members with MMR status ESRD or hospice in a **separate population** (`pop = ESRD_HOSPICE`); everyone else is `pop = MAIN`. The Model Gate is judged on `MAIN`; `ESRD_HOSPICE` is reported only.
- Log the row counts: total, dropped for a null RAF, and in each population.

**Step 2 — Choose the actual (run twice)**
- Run A, **capped (headline):** `y_eval = y_capped`, and cap every model's prediction at `cost_cap` first.
- Run B, **uncapped:** `y_eval = y_annualized`, with predictions uncapped (`OURS` uses `pred_total`).

**Step 3 — Put every model in dollars on the same total** (per scoring group and population)
- `B1_CMS`: apply **F4** (RAF → dollars).
- `OURS`, `B2`, `B3`: apply **F5** (rescale to the actual total). Log each `k`.
- After this step, check: `Σ(w × pred_eval) = Σ(w × y_eval)` for every model, within 0.01%.

**Step 4 — Compute the metrics** (F7) for each model × scoring group × population × run
- Overall: MAE, MAE %, R², CPM, top-1% and top-5% capture, Gini.
- Predictive ratio by each F8 grouping: decile, condition group, age band, new-member flag and actual cost band.

**Step 5 — Bootstrap confidence intervals** (Run A, `MAIN` only)
- Repeat `bootstrap_n` times: sample `bootstrap_sample_frac` of **members** with replacement (all of a member's rows together), redo Steps 3–4, and record `R²(OURS) − R²(B1_CMS)` and `MAE(B1_CMS) − MAE(OURS)`.
- Report the 2.5th and 97.5th percentiles. A win counts only if the whole interval is above 0.

**Step 6 — Show where the gain comes from** (Run A, `MAIN`, per cutoff)
- Report the R² row by row, in this order: `B1_CMS` → `B2_HCC_REFIT` → `OURS`, plus `B3_PRIOR_COST` for reference.
- B1 → B2 = gain from recalibrating HCCs to our population.
- B2 → OURS = gain from extra data and machine learning.

**Step 7 — Write the outputs**
- `eval_metrics` (`split`, `target_year`, `cutoff_month`, `pop`, `run` [capped|uncapped], `model_name`, `metric`, `value`, `ci_low`, `ci_high`)
- `eval_pr` (`split`, `target_year`, `cutoff_month`, `pop`, `run`, `model_name`, `group_type`, `group_value`, `sum_w`, `sum_pred`, `sum_actual`, `pr`)
- `eval_scaling` (`split`, `target_year`, `cutoff_month`, `pop`, `run`, `model_name`, `k`)
- A notebook report with exactly these sections:
  1. Population counts
  2. Headline table: R², MAE and CPM by cutoff, one column per model
  3. Gain breakdown from Step 6
  4. Decile predictive-ratio chart (OURS against B1)
  5. Condition-group predictive ratios
  6. Bootstrap CIs
  7. ESRD and hospice appendix

**How to read the in-year horizons** (state this in the report): B1_CMS uses the same RAF at every cutoff, while OURS uses claims from the current year. A larger win at 2+10, 5+7 and 8+4 is expected and legitimate. B3_PRIOR_COST is included so the win isn't only against an out-of-date score.

**Gate criteria** (Run A, `pop = MAIN`, `eval_split`; thresholds proposed, confirm with actuarial):
1. At 0+12: `R²(OURS) ≥ R²(B1_CMS) + 0.08` **and** `R²(OURS) ≥ R²(B2_HCC_REFIT)`, with the bootstrap CI of the R² difference above 0.
2. At every cutoff: `MAE(OURS) < MAE(B1_CMS)`, with the bootstrap CI above 0.
3. At 2+10, 5+7 and 8+4: the R² gain over B1 is at least the 0+12 gain.
4. Predictive ratio for OURS is between 0.90 and 1.10 in every decile, and in every condition group with `sum_w ≥ pr_min_group_weight`.
5. Top-1% capture for OURS is at least 1.3 × that of B1_CMS.

**Tests:**
- The `mrs_formulas` golden test (Appendix A) passes.
- The Step 3 total check passes for every model.
- Every combination of (split, year, cutoff, pop, run, model) has all the metrics in `eval_metrics`.

### M15 — Explainability (V1.1)
- **Output:** `shap_global` and `shap_member_top5` (the top 5 reasons per member, for the top 5% of risk only).
- **Logic:** TreeSHAP on a stratified sample of 200k rows for global importance; per-member SHAP for high-risk members. Map each feature to a readable label through `feature_dictionary`.
- **Test:** the top 20 global features are reviewed by a clinician or actuary, and no leaky feature appears.

### M16 — Scoring and monitoring (V2)
- **Output:** a Databricks Workflow (DAB) that scores all active members at each cutoff, plus the `monitor_metrics` table.
- **Monitoring:**
  - Population stability index (PSI) per feature
  - Mean risk score by segment
  - Predicted-to-actual ratio by cohort once actuals mature
  - Share of HCC and CCSR codes (coding drift)
- **Alerts:** any PSI above 0.2, or a segment predicted-to-actual ratio outside 0.9–1.1.

---

## 6. Version roadmap

### V1 — MVP: beat CMS on the risk score
**Modules:** M0–M6, M7a–f and M7h, M8, M9, M10, M13, M14.
**Done when:** the Model Gate passes on the validation year for all four cutoffs.

### V1.1 — Tail and explanations
- M11 high-cost classifier, M12 excess layer (uncapped `risk_score`)
- M15 SHAP reasons
- M7g clinical states for **renal only**
- Tuning: compare cost caps of $250k and $500k
**Done when:** the Model Gate passes on the **test** year, the renal-segment predicted-to-actual ratio improves, and actuarial signs off.

### V2 — Clinical depth and production
- M7g cancer and cardiac clinical states
- Separate calibration (or small separate models) for ESRD, hospice and institutional members
- Compare one hurdle model (classifier plus severity model) against Tweedie for the top 5%
- M16 scoring workflow, monitoring and yearly retraining
- Condition-group predicted-to-actual ratio tables for pricing and care management

### V3 — Research extensions (each needs its own spec)
- **Event-sequence embeddings:** pretrain a small generative transformer (Delphi or ReClaim style, 10–100M parameters) on member code sequences (ICD, CPT, NDC classes, time encoding) using serverless GPU. Feed the member embeddings into M10 as features. Keep only if the test-year R² gain is at least 0.02.
- **Clinical outcome risk:** 12-month probabilities of progression, admission and death, using a discrete-time competing-risk model in LightGBM, reported next to the cost-based risk score.
- **Multi-state progression model** for renal (CKD 3 → 4 → 5 → dialysis → transplant or death).

---

## 7. Implementation order and test plan

| Sprint | Modules | What you test |
|---|---|---|
| 1 | M0 (incl. `mrs_formulas` + golden test), M1, M2, M3 | Golden test passes; Data Gate: totals reconcile with finance and enrollment |
| 2 | M4, M5, M6 | Target Gate: target distribution and means are correct |
| 3 | M7a–M7d | Leakage tests and row counts for each feature table |
| 4 | M7e, M7f, M7h, M8 | Feature Gate: shuffle and leakage tests pass |
| 5 | M9, M10 | First comparison: M10 against CMS on validation |
| 6 | M13, M14 | Model Gate on validation; V1 done |
| 7–8 | M11, M12, M15, M7g renal | V1.1 on the test year; actuarial sign-off |

---

## 8. Open decisions (confirm before Sprint 1)
1. The real claims lag in production (sets `claims_lag_days`).
2. Cost basis: allowed or paid amount, and whether Rx rebates are included.
3. The population in scope: Medicare Advantage only, or other lines of business too.
4. Whether to include the MMR RAF as a feature. It improves accuracy but makes the model partly depend on CMS coding.
5. Gate thresholds in M14, to be signed off by actuarial.
6. Which RAF B1_CMS uses: the final reconciled RAF (default) or the initial one available on Jan 1.
7. `base_year` for `risk_score_base` (default 2023).

---

## Appendix A — Golden test for `mrs_formulas` (must pass before any other module)

Ten members in one scoring group. All weights `w = 1` (12 remaining months). No cap applied.

| member | RAF | pred_ours | y_eval |
|---|---|---|---|
| A | 0.35 | 1000 | 0 |
| B | 0.40 | 1500 | 300 |
| C | 0.45 | 1000 | 900 |
| D | 0.50 | 3000 | 1500 |
| E | 0.90 | 7000 | 6000 |
| F | 1.10 | 8000 | 9000 |
| G | 1.40 | 12000 | 14000 |
| H | 2.10 | 35000 | 38000 |
| I | 1.80 | 85000 | 95000 |
| J | 2.60 | 171200 | 160000 |

**Expected results** (tolerance ±0.01 for dollars, ±0.0001 for ratios):

| Check | Expected |
|---|---|
| F4 `k_cms` | 27991.38 |
| F4 `cms_pred` for A, E, J | 9796.98, 25192.24, 72777.59 |
| F5 `k_model` for OURS | 1.0000 (totals already equal: 324,700) |
| MAE: CMS / OURS | 26367.59 / 3200.00 |
| R²: CMS / OURS | 0.5350 / 0.9905 |
| CPM: CMS / OURS | 0.3259 / 0.9182 |
| Predictive ratio, members A–D: CMS / OURS | 17.6242 / 2.4074 |
| Predictive ratio, members E–G: CMS / OURS | 3.2817 / 0.9310 |
| Predictive ratio, members H–J: CMS / OURS | 0.6210 / 0.9939 |
| F3a `risk_score_relative` (OURS) for A, H, J | 0.0308, 1.0779, 5.2726 |
| Weighted mean of `risk_score_relative` | 1.0000 |

This example is only a test of the formulas. It doesn't represent expected real-world performance.
