# Forecast Intervals: Conformal Recalibration (pre-registered)

Written 2026-10-02, before the code below was run. Code: `src/tailsignal/models/forecasting_conformal.py`. Outputs: `reports/forecasting/conformal/summary.json`. Builds on the hierarchical demand forecast (pre-registered H8), whose 80% intervals covered only 64% of outcomes.

## Method

Keep the MSTL + MinT point forecasts from the existing 12-origin backtest and replace their intervals.

- For each location-level series, scale errors by that series' seasonal-naive error (the same scale used for MASE).
- For a forecast made at origin *k* for horizon *h* weeks, the interval is the point forecast ± *q* × scale. Here *q* is the 80th percentile of absolute scaled errors at horizon *h* from earlier origins. Only errors already observable at origin *k* count: their target week falls before origin *k*.
- Fewer than 30 earlier errors at that horizon: pool horizons within ±2 weeks. Still fewer than 30: no interval, and the origin is left out of scoring.

This is split conformal prediction applied sequentially, so no future data reaches any interval.

## Pre-stated expectations

1. Coverage of the conformal 80% intervals, over all scored forecasts, falls between 75% and 85% (the original H8 criterion).
2. Coverage within each horizon band (1–4, 5–8, 9–13 weeks) falls between 70% and 90%.
3. Conformal intervals are wider than the MinT intervals at every horizon band.
4. Daycare staffing from the conformal upper bound costs no more than staffing from the MinT upper bound, under the same illustrative cost assumptions, on the same scored weeks.

## Limits stated up front

Conformal coverage holds on average if errors behave like earlier errors. A shift in demand, such as a new location opening, breaks that. With 12 origins, early origins have little calibration data, so fewer forecasts are scored.
