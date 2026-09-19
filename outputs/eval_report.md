# MA member cost/risk rehearsal -- evaluation report

Synthetic data. The metric VALUES here mean nothing on their own -- synthetic data
has no real signal ceiling. What matters is that the model beats the baseline on the
same members with the same metrics, and that the decile tables are well behaved.

Target: `relative_target_capped` = member PMPM / population PMPM for the target year,
capped at the P99.5 of that year's relative target.
Baseline: the synthetic `raf_score` from the base year, divided by the mean raf_score
of the scored population, so 1.0 means population average on both sides. No outcome
data is used to rescale it.

New enrollees have no base-year MOR, so they enter the baseline at the population
average. They are predicted by the separate demographics-only model (rule #7).

## Backtest 1 -- Set B (2023 features -> 2024 cost)

Model trained on Set A only (features as of 2022-12-31, target 2023), then applied out of time to Set B.

Members scored: **1,872**

| metric | model | baseline (raf_score) |
|---|---:|---:|
| R2 vs capped relative target | 0.3813 | 0.2650 |
| R2 vs uncapped relative target | 0.2297 | 0.1599 |
| top-5% capture | 43.6% | 45.7% |

**beats baseline: yes**  (on R2 against the capped relative target, the trained target)

### Predictive ratio by decile

Members are sorted into deciles by each column's OWN predicted value, so the two halves of
this table are ordered differently on purpose. Decile 1 is the lowest predicted risk.

| decile | n | model sum pred | model sum actual | model PR | baseline sum pred | baseline sum actual | baseline PR |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 188 | 32.1 | 27.7 | 1.159 | 92.9 | 22.5 | 4.130 |
| 2 | 187 | 45.7 | 41.0 | 1.113 | 111.0 | 48.4 | 2.293 |
| 3 | 187 | 63.9 | 100.2 | 0.637 | 125.4 | 74.0 | 1.694 |
| 4 | 187 | 82.7 | 73.8 | 1.121 | 141.2 | 99.7 | 1.416 |
| 5 | 187 | 105.3 | 100.1 | 1.052 | 157.2 | 105.1 | 1.495 |
| 6 | 187 | 135.5 | 141.8 | 0.956 | 175.9 | 160.7 | 1.095 |
| 7 | 187 | 169.1 | 177.0 | 0.955 | 191.0 | 142.0 | 1.345 |
| 8 | 187 | 209.1 | 183.3 | 1.141 | 216.4 | 232.4 | 0.931 |
| 9 | 187 | 277.3 | 281.7 | 0.984 | 260.9 | 284.6 | 0.917 |
| 10 | 188 | 602.0 | 644.0 | 0.935 | 400.2 | 601.2 | 0.666 |


## Backtest 2 -- Set C (2024 features -> 2025 cost)

Model refit on Sets A+B with the SAME hyperparameters, then applied out of time to Set C.

Members scored: **1,932**

| metric | model | baseline (raf_score) |
|---|---:|---:|
| R2 vs capped relative target | 0.3905 | 0.2638 |
| R2 vs uncapped relative target | 0.1778 | 0.1185 |
| top-5% capture | 45.4% | 44.3% |

**beats baseline: yes**  (on R2 against the capped relative target, the trained target)

### Predictive ratio by decile

Members are sorted into deciles by each column's OWN predicted value, so the two halves of
this table are ordered differently on purpose. Decile 1 is the lowest predicted risk.

| decile | n | model sum pred | model sum actual | model PR | baseline sum pred | baseline sum actual | baseline PR |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 194 | 27.1 | 16.8 | 1.607 | 93.9 | 20.1 | 4.666 |
| 2 | 193 | 47.1 | 44.3 | 1.062 | 113.3 | 36.6 | 3.098 |
| 3 | 193 | 65.1 | 63.1 | 1.032 | 129.2 | 65.3 | 1.978 |
| 4 | 193 | 82.9 | 72.3 | 1.148 | 143.9 | 73.7 | 1.953 |
| 5 | 193 | 108.2 | 111.1 | 0.974 | 160.6 | 106.4 | 1.509 |
| 6 | 193 | 138.4 | 106.0 | 1.306 | 179.6 | 109.9 | 1.634 |
| 7 | 193 | 172.7 | 164.1 | 1.053 | 195.5 | 174.0 | 1.123 |
| 8 | 193 | 212.2 | 220.4 | 0.963 | 221.4 | 179.2 | 1.235 |
| 9 | 193 | 287.6 | 272.2 | 1.057 | 273.7 | 331.9 | 0.825 |
| 10 | 194 | 641.2 | 697.7 | 0.919 | 420.7 | 670.6 | 0.627 |


## 2027 rehearsal

Model refit on A+B+C, applied to Set D (features as of 2026-12-31). There is no ground
truth here and there never will be at this point in the real calendar either, so this
section reports inputs and distribution, not accuracy.

Known population PMPM history (Part A+B, exposure-weighted):

| year | population PMPM |
|---|---:|
| 2022 | $347.80 |
| 2023 | $379.19 |
| 2024 | $372.16 |
| 2025 | $408.92 |
| 2026 | $436.93 |

Projected 2027 population PMPM: **$454.86**
(log-linear extrapolation -- `evaluate.trend_project`, the swap point for the real
actuarial trend assumption. Not a benchmark rate.)

Members scored: **1,835** (1,835 established, 0 new enrollees)

Assumed exposure for each member in 2027: **12 months** (see README, Assumptions).

| statistic | relative risk score | predicted annual dollars |
|---|---:|---:|
| mean | 0.959 | $5,233 |
| median | 0.574 | $3,130 |
| p95 | 3.051 | $16,651 |
| max | 7.948 | $43,380 |

