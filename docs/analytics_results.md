# Segmentation and Forecasting Results

Data: the resolved TailSignal platform (synthetic multi-channel data; 8,490 households, 12,666 pets, 2022–2025). Hypotheses H7 and H8 are in [`preregistration.md`](preregistration.md), along with the exploratory revisions logged on 2026-10-02. Because the data are simulated, these results demonstrate the method and the decisions it supports. They are not market estimates.

## Segmentation (H7)

Features are measured over the training window (through 2024-06-30), per household per year. Code: `src/tailsignal/models/segmentation.py`. Outputs: `reports/segmentation/`.

### Pre-registered specification: **fails**

Eleven features (behavior plus household attributes), Gaussian mixture, k by BIC with no segment under 5%. BIC chose k = 4, and bootstrap stability was poor: Jaccard 0.36–0.68 per segment against a 0.75 bar. The binary and near-constant attributes (all-dog vs. all-cat households, wellness-plan yes/no) pulled mixture components onto exact-0/1 spikes.

### Exploratory revision: **stable**

Clustering on five behavioral rates only, with household attributes kept as descriptors (amendment logged before rerunning).

| Top-level segment | Households | Revenue | Spend / yr | Daycare days / yr | Grooming / yr | Stability (Jaccard) |
|---|---|---|---|---|---|---|
| Daycare regulars | 22% | **64%** | $6,005 | 115 | 4.4 | 0.94 |
| Grooming-led | 17% | 13% | $1,513 | 0 | 7.0 | 0.76 |
| Vet-centric | 62% | 24% | $780 | 0 | 0 | 0.88 |

| Finer segment (k = 6) | Parent | Households | Revenue | Spend / yr | Stability |
|---|---|---|---|---|---|
| Daycare + grooming regulars | Daycare regulars | 934 (12%) | 40% | $6,747 | 0.84 |
| Daycare regulars, no grooming | Daycare regulars | 671 (9%) | 22% | $5,189 | 0.76 |
| Grooming-led | Grooming-led | 1,174 (15%) | 12% | $1,601 | 0.99 |
| Vet + boarding | Vet-centric | 1,334 (17%) | 10% | $1,221 | 0.89 |
| Vet only | Vet-centric | 3,220 (42%) | 13% | $617 | 0.94 |
| No partner-vet visits | Vet-centric | 396 (5%) | 2% | $959 | 0.77 |

Every segment at both levels clears the 0.75 stability bar with 50 bootstrap refits.

**Recovery check.** Agreement with the simulator's hidden segments is low (adjusted Rand 0.21). This is expected, not a failure. The simulator assigns behavior probabilistically, so households in different hidden segments often behave alike (for example, many "boarding travelers" never board in a given window). The segments describe what customers do, which is what a business can act on.

### Commercial opportunities (illustrative sizing)

| Opportunity | Who | Sizing logic | Annual value if 20% convert |
|---|---|---|---|
| Add grooming for daycare regulars | 671 households in "Daycare regulars, no grooming" | 5.6 appointments/yr (median groomer) × $95 | ≈ $71,000 |
| Bring daycare/grooming customers to partner vets | 396 "No partner-vet visits" households | 1.5 visits/yr × $288 | ≈ $34,000 |
| Protect the core | Daycare regulars: 22% of households, 64% of revenue | Retention priority; first audience for the wellness-plan uplift model (Model D) | — |

## Forecasting (H8)

Weekly demand per location for daycare visits, boarding stays, grooming appointments, and vet visits: 27 location series in a service → market → location hierarchy (43 series in total). Backtest: 12 forecast origins, 4 weeks apart, from 2024-07-01; 13-week horizon. Code: `src/tailsignal/models/forecasting.py`. Outputs: `reports/forecasting/`.

| Method | Mean MASE, location level (lower is better) | 80% interval coverage (target 75–85%) |
|---|---|---|
| Seasonal naive (baseline) | 0.889 | 85% |
| MSTL | 0.838 | 64% |
| MSTL + MinT reconciliation (pre-registered) | **0.828** | 64% |
| Average of seasonal naive and MSTL + MinT (exploratory) | **0.811** | **79%** |

**H8: fails on calibration.** The pre-registered forecaster beats the baseline on accuracy (MASE 0.83 vs. 0.89) but its 80% intervals cover only 64% of outcomes; MSTL intervals are too narrow. The exploratory average meets both bars (0.81, 79%) but was added after a smoke test, so it needs confirming on new data before it replaces the pre-registered method.

By service (mean MASE; pre-registered method vs. baseline): daycare 0.70 vs. 0.77, boarding 0.91 vs. 0.98, grooming 0.83 vs. 0.97, vet 0.86 vs. 0.85. Vet visits are the one place the seasonal baseline holds its own: annual wellness visits repeat on the pet's own anniversary, which last year's pattern already captures.

### Decision layer: daycare staffing

Rule: handlers per day = forecast daily dogs ÷ 15, rounded up. Costs are illustrative: $160 per handler-day, $40 per dog-day turned away over capacity. Backtest totals are summed across overlapping windows, so compare them relative to each other only.

| Staff to… | Over-staffing cost | Turned-away cost | Total |
|---|---|---|---|
| Seasonal naive, point forecast | $240,800 | $92,560 | $333,360 |
| MSTL + MinT, point | $195,200 | $185,320 | $380,520 |
| **Average + MinT, point** | $202,400 | $109,040 | **$311,440** (−7% vs. baseline) |
| Any method, upper 80% bound | | | $548,000–$1.7M |

Staffing to the upper bound is far too conservative at these costs. A handler covers 15 dogs, so one extra handler costs more than several turned-away visits. The forward 13-week staffing plan (`reports/forecasting/daycare_staffing_plan.csv`) uses the lowest-cost rule from the backtest.

## What carries forward

- The segments feed the partner portal ("your customer mix vs. your market") and target the uplift model.
- Forecasts and staffing plans are the first embedded-analytics feature for daycare partners.
- Next forecasting step: conformal prediction intervals to fix calibration, then confirm the average model on 2025 data.
