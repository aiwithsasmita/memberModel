"""
Phase 7 -- evaluation against a baseline, and the dollar conversion for 2027.

Non-negotiable rule #6: every result is reported against a baseline. The synthetic
raf_score stands in for the real CMS RAF. An R2 on its own means nothing here -- synthetic
data has no real signal ceiling, so the only claim worth making is "better than baseline".

The baseline is put on the same relative-to-population-mean basis as the target before
anything is compared: each member's base-year raf_score is divided by the mean raf_score
of the population being scored, so 1.0 means "exactly the population average", the same
meaning 1.0 has for the target. The rescaling uses the baseline's own population only --
never the actual outcome -- so the baseline, like the model, is scored without having
seen the answer.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

import config


# ---------------------------------------------------------------------------
# The dollar trend -- READ THIS BEFORE PORTING
# ---------------------------------------------------------------------------

def trend_project(pmpm_history, target_year):
    """
    Project population PMPM into a future year by fitting a log-linear (geometric) trend
    to the known history. `pmpm_history` is {year: population_pmpm}.

    ### THIS IS THE SWAP POINT. ###
    In production this function is replaced by the actuarial trend assumption supplied by
    the actuarial team, cross-checked against the published FFS trend rate. It must NEVER
    be the CMS county benchmark rate: the benchmark is a payment policy parameter, not a
    forecast of what care will cost, and using it here would quietly bake a rate-setting
    decision into a cost model. What is here is a deliberately simple extrapolation whose
    only job is to prove the plumbing works end to end.
    """
    years = np.array(sorted(pmpm_history))
    values = np.array([pmpm_history[int(y)] for y in years], dtype=float)
    if len(years) < 2:
        return float(values[-1])

    slope, intercept = np.polyfit(years, np.log(values), 1)
    projected = float(np.exp(intercept + slope * target_year))
    return projected


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def rescale_baseline(raw_baseline):
    """
    Put the raw raf_score on the target's relative-to-population-mean basis:
    member raf / population mean raf. Uses no outcome data.
    """
    raw_baseline = np.asarray(raw_baseline, dtype=float)
    return raw_baseline / float(np.mean(raw_baseline))


def decile_table(predicted, actual, n_deciles=config.N_DECILES):
    """
    Predictive ratio by decile: sort members by PREDICTED value into equal groups, then
    within each group divide the sum of predictions by the sum of actuals.

    1.00 means the group's total prediction matched its total actual. Above 1.00 is
    over-prediction, below is under-prediction. A well-behaved model sits near 1.00 across
    every decile; the classic failure is a bottom decile far above 1 and a top decile far
    below it, which is what squared-error-on-log looks like on a tail like this one.
    """
    frame = pd.DataFrame({"predicted": np.asarray(predicted, dtype=float),
                          "actual": np.asarray(actual, dtype=float)})
    order = frame["predicted"].rank(method="first")
    frame["decile"] = pd.qcut(order, n_deciles, labels=False) + 1

    grouped = frame.groupby("decile").agg(
        n=("actual", "size"),
        sum_predicted=("predicted", "sum"),
        sum_actual=("actual", "sum"),
        mean_actual=("actual", "mean"),
    )
    grouped["predictive_ratio"] = grouped["sum_predicted"] / grouped["sum_actual"].replace(0, np.nan)
    return grouped.reset_index()


def top_pct_capture(predicted, actual, pct=config.TOP_PCT):
    """
    Of the members who were ACTUALLY in the top `pct` of cost, what fraction did the
    model's own top-`pct` predicted group catch?
    """
    predicted = np.asarray(predicted, dtype=float)
    actual = np.asarray(actual, dtype=float)
    k = max(1, int(round(len(actual) * pct)))

    actual_top = set(np.argsort(-actual, kind="stable")[:k])
    predicted_top = set(np.argsort(-predicted, kind="stable")[:k])
    return len(actual_top & predicted_top) / len(actual_top)


def evaluate_set(name, frame, predicted_column="predicted", baseline_column="baseline_raw"):
    """
    Score one backtest: model vs baseline, on the same members, with the same metrics.

    `frame` needs: predicted, baseline_raw, relative_target, relative_target_capped.
    """
    actual_capped = frame["relative_target_capped"].to_numpy(dtype=float)
    actual_uncapped = frame["relative_target"].to_numpy(dtype=float)
    predicted = frame[predicted_column].to_numpy(dtype=float)
    baseline = rescale_baseline(frame[baseline_column])

    result = {
        "name": name,
        "n_members": len(frame),
        "model_r2_capped": r2_score(actual_capped, predicted),
        "model_r2_uncapped": r2_score(actual_uncapped, predicted),
        "baseline_r2_capped": r2_score(actual_capped, baseline),
        "baseline_r2_uncapped": r2_score(actual_uncapped, baseline),
        "model_top_capture": top_pct_capture(predicted, actual_uncapped),
        "baseline_top_capture": top_pct_capture(baseline, actual_uncapped),
        "model_deciles": decile_table(predicted, actual_capped),
        "baseline_deciles": decile_table(baseline, actual_capped),
    }
    result["beats_baseline"] = result["model_r2_capped"] > result["baseline_r2_capped"]
    return result


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def _combined_decile_markdown(result):
    model = result["model_deciles"]
    baseline = result["baseline_deciles"]
    lines = [
        "| decile | n | model sum pred | model sum actual | model PR | "
        "baseline sum pred | baseline sum actual | baseline PR |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i in range(len(model)):
        m, b = model.iloc[i], baseline.iloc[i]
        lines.append(
            f"| {int(m['decile'])} | {int(m['n'])} | {m['sum_predicted']:.1f} | "
            f"{m['sum_actual']:.1f} | {m['predictive_ratio']:.3f} | "
            f"{b['sum_predicted']:.1f} | {b['sum_actual']:.1f} | {b['predictive_ratio']:.3f} |"
        )
    return "\n".join(lines)


def _backtest_section(result, description):
    verdict = "yes" if result["beats_baseline"] else "no"
    return f"""
## {result['name']}

{description}

Members scored: **{result['n_members']:,}**

| metric | model | baseline (raf_score) |
|---|---:|---:|
| R2 vs capped relative target | {result['model_r2_capped']:.4f} | {result['baseline_r2_capped']:.4f} |
| R2 vs uncapped relative target | {result['model_r2_uncapped']:.4f} | {result['baseline_r2_uncapped']:.4f} |
| top-{int(config.TOP_PCT * 100)}% capture | {result['model_top_capture']:.1%} | {result['baseline_top_capture']:.1%} |

**beats baseline: {verdict}**  (on R2 against the capped relative target, the trained target)

### Predictive ratio by decile

Members are sorted into deciles by each column's OWN predicted value, so the two halves of
this table are ordered differently on purpose. Decile 1 is the lowest predicted risk.

{_combined_decile_markdown(result)}
"""


def write_report(results, pmpm_history, projected_pmpm, score_summary, path=None):
    """Write outputs/eval_report.md."""
    path = path or (config.OUTPUT_DIR / "eval_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    history_rows = "\n".join(
        f"| {year} | ${value:,.2f} |" for year, value in sorted(pmpm_history.items())
    )

    sections = [
        "# MA member cost/risk rehearsal -- evaluation report",
        "",
        "Synthetic data. The metric VALUES here mean nothing on their own -- synthetic data",
        "has no real signal ceiling. What matters is that the model beats the baseline on the",
        "same members with the same metrics, and that the decile tables are well behaved.",
        "",
        "Target: `relative_target_capped` = member PMPM / population PMPM for the target year,",
        f"capped at the P{config.CAP_PERCENTILE * 100:g} of that year's relative target.",
        "Baseline: the synthetic `raf_score` from the base year, divided by the mean raf_score",
        "of the scored population, so 1.0 means population average on both sides. No outcome",
        "data is used to rescale it.",
        "",
        "New enrollees have no base-year MOR, so they enter the baseline at the population",
        "average. They are predicted by the separate demographics-only model (rule #7).",
    ]

    for result, description in results:
        sections.append(_backtest_section(result, description))

    sections.append(f"""
## 2027 rehearsal

Model refit on A+B+C, applied to Set D (features as of 2026-12-31). There is no ground
truth here and there never will be at this point in the real calendar either, so this
section reports inputs and distribution, not accuracy.

Known population PMPM history (Part A+B, exposure-weighted):

| year | population PMPM |
|---|---:|
{history_rows}

Projected {config.SCORE_YEAR} population PMPM: **${projected_pmpm:,.2f}**
(log-linear extrapolation -- `evaluate.trend_project`, the swap point for the real
actuarial trend assumption. Not a benchmark rate.)

{score_summary}
""")

    path.write_text("\n".join(sections), encoding="utf-8")
    return path


def write_predictions(frame, projected_pmpm, path=None,
                      expected_exposure_months=config.ASSUMED_FUTURE_EXPOSURE_MONTHS):
    """
    Convert relative risk scores to dollar estimates and write the score file.

        predicted_pmpm(m)   = relative_risk_score(m) * projected_population_pmpm(year)
        predicted_annual(m) = predicted_pmpm(m) * expected_exposure_months(m)

    The file has no actual/target column, because in real life it does not exist yet at
    this point in the calendar.
    """
    path = path or (config.OUTPUT_DIR / f"predictions_{config.SCORE_YEAR}.csv")
    path.parent.mkdir(parents=True, exist_ok=True)

    predicted_pmpm = frame["predicted"].to_numpy(dtype=float) * projected_pmpm
    out = pd.DataFrame({
        "member_id": frame["member_id"].to_numpy(),
        "relative_risk_score": np.round(frame["predicted"].to_numpy(dtype=float), 6),
        "predicted_annual_dollar_estimate": np.round(predicted_pmpm * expected_exposure_months, 2),
    }).sort_values("member_id", ignore_index=True)

    out.to_csv(path, index=False)
    return path, out
