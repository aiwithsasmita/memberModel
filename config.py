"""
Every constant for the rehearsal lives in this file.

Read this first. If you want to change how the pipeline behaves, change it here --
none of the modules in src/ hard-code a number that belongs in this file.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
RAW_DIR = REPO_ROOT / "data" / "raw"
OUTPUT_DIR = REPO_ROOT / "outputs"
MLFLOW_TRACKING_URI = (REPO_ROOT / "mlruns").as_uri()  # local file store; no server needed
MLFLOW_EXPERIMENT = "ma_risk_pipeline_rehearsal"

# ---------------------------------------------------------------------------
# Phase 0 constants (exactly as specified in intent.md)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Cost categories
# ---------------------------------------------------------------------------
# The target is Part A + Part B allowed dollars only. Rx is Part D: it is generated
# and used as a *feature*, but it never enters the target. See README "Assumptions".
COST_CATEGORIES = ["inpatient", "outpatient", "er", "professional", "rx"]
PART_AB_CATEGORIES = ["inpatient", "outpatient", "er", "professional"]

# Rough share of a member-month's drawn dollars that lands in each category.
CATEGORY_SHARES = {
    "inpatient": 0.35,
    "outpatient": 0.22,
    "er": 0.08,
    "professional": 0.20,
    "rx": 0.15,
}

# ---------------------------------------------------------------------------
# Phase 1: synthetic data generation knobs
# ---------------------------------------------------------------------------
TRUE_RISK_SIGMA = 0.60            # lognormal sigma for the latent per-member risk
TRUE_RISK_DRIFT_SIGMA = 0.15      # year-over-year nudge (disease progression)
BASE_MONTHLY_CLAIM_PROB = 0.25    # a mean-risk member has a claim ~25% of months
CLAIM_AMOUNT_LOG_MU = 6.5         # lognormal mu for a month's drawn dollars
CLAIM_AMOUNT_LOG_SIGMA = 1.10     # lognormal sigma -> right-skewed, long tail
CATASTROPHIC_RATE = 0.003         # ~0.3% of member-years blow up
CATASTROPHIC_MULTIPLIER = (20.0, 50.0)
LATE_ENROLLMENT_RATE = 0.18       # share of members who start after Jan 2022 (-> new enrollees)
DISENROLLMENT_RATE = 0.10         # share of members who leave before Dec 2026
DUAL_RATE = 0.20
ESRD_RATE = 0.01
HOSPICE_MEMBER_YEAR_RATE = 0.005

# ---------------------------------------------------------------------------
# Phase 3: features
# ---------------------------------------------------------------------------
TRAILING_WINDOWS_MONTHS = [6, 12]  # trailing cost/utilization windows ending at as_of_date

# ---------------------------------------------------------------------------
# Phase 4: out-of-fold target encoding
# ---------------------------------------------------------------------------
TARGET_ENCODE_COLUMNS = ["county_id", "pcp_provider_id"]
TARGET_ENCODE_SMOOTHING = 200.0    # pulls small categories toward the global mean

# ---------------------------------------------------------------------------
# Phase 5: the four row sets
# ---------------------------------------------------------------------------
# base_year -> features are built as of Dec 31 of this year
# target_year -> the year whose PMPM ratio we are trying to predict (None = score only)
SPLITS = {
    "A": {"base_year": 2022, "target_year": 2023, "role": "train (5-fold CV, grouped by member_id)"},
    "B": {"base_year": 2023, "target_year": 2024, "role": "backtest 1 (out-of-time)"},
    "C": {"base_year": 2024, "target_year": 2025, "role": "backtest 2 (out-of-time, after refit on A+B)"},
    "D": {"base_year": 2026, "target_year": None, "role": "score (the 2027 rehearsal)"},
}
SCORE_YEAR = 2027                      # the year Set D is projected into
ASSUMED_FUTURE_EXPOSURE_MONTHS = 12    # see README "Assumptions"

# ---------------------------------------------------------------------------
# Phase 6: model
# ---------------------------------------------------------------------------
LGB_OBJECTIVE = "tweedie"
# Optuna tunes tweedie_variance_power, so the Tweedie deviance *reported by LightGBM*
# changes units between trials and is not comparable across them. The Optuna objective
# therefore scores every trial with one fixed deviance power. See README "Assumptions".
EVAL_TWEEDIE_POWER = 1.5
LGB_MAX_ROUNDS = 2000
LGB_EARLY_STOPPING_ROUNDS = 50
# Fixed, small thread count. At ~2,000 rows extra threads only add overhead, and a fixed
# count keeps `deterministic=True` results identical across laptops with different core
# counts. Raise it on a real cluster.
LGB_NUM_THREADS = 4
OPTUNA_SEARCH_SPACE = {
    "tweedie_variance_power": (1.1, 1.9),
    "learning_rate": (0.01, 0.1),      # sampled log-uniform
    "num_leaves": (15, 127),
    "min_data_in_leaf": (20, 200),
    "feature_fraction": (0.5, 1.0),
    "bagging_fraction": (0.5, 1.0),
}
# New enrollees have demographics only and there are few of them, so they get a small,
# deliberately under-fit model with fixed params rather than their own Optuna study.
NEW_ENROLLEE_LGB_PARAMS = {
    "objective": "tweedie",
    "tweedie_variance_power": 1.5,
    "learning_rate": 0.05,
    "num_leaves": 7,
    "min_data_in_leaf": 25,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "num_boost_round": 150,
}

# ---------------------------------------------------------------------------
# Phase 7: evaluation
# ---------------------------------------------------------------------------
TOP_PCT = 0.05   # "top 5% capture"

# ---------------------------------------------------------------------------
# Phase 8: embeddings
# ---------------------------------------------------------------------------
USE_BERT_EMBEDDINGS = False   # Optum BERT is interface-only here. Do not flip this on.
BERT_EMBEDDING_DIMS = 32

# ---------------------------------------------------------------------------
# Column bookkeeping -- used to separate "features" from everything else
# ---------------------------------------------------------------------------
ID_COLUMNS = [
    "member_id", "base_year", "target_year", "as_of_date",
    "county_id", "pcp_provider_id", "fold", "row_kind",
]
TARGET_COLUMNS = [
    "exposure_months", "actual_cost", "member_pmpm",
    "relative_target", "relative_target_capped",
]


def feature_columns(df):
    """Every column of `df` that the model is allowed to see."""
    blocked = set(ID_COLUMNS) | set(TARGET_COLUMNS)
    return [c for c in df.columns if c not in blocked]


# ---------------------------------------------------------------------------
# Medical trend baked into the synthetic dollars
# ---------------------------------------------------------------------------
# Costs are inflated by this factor each year, so population PMPM genuinely rises
# year over year. That is exactly what rule #1 is about: a model trained on raw
# pooled dollars would learn this trend and call it "risk". The relative-to-
# population-mean target divides it straight back out.
ANNUAL_COST_TREND = 1.05
