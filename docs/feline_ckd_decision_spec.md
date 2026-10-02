# Feline Kidney Flag: Does It Pay? Decision-Curve Analysis (pre-registered)

Written 2026-10-02, before the code below was run. Code: `src/tailsignal/models/feline_ckd_decision.py`. Outputs: `reports/feline_ckd/decision/`. Uses the 10× network and the cross-validated predictions from [feline_ckd_spec.md](feline_ckd_spec.md).

## Question

If a clinic rechecks every flagged cat (a repeat panel with SDMA and urinalysis in 3–6 months), is the flag worth it compared with rechecking every senior cat, or none? At what flag threshold?

## Method

- **Net benefit** (Vickers and Elkin, 2006): at a threshold probability *p*, net benefit = true flags / N − false flags / N × *p* / (1 − *p*). The threshold encodes the trade-off: flagging at *p* = 20% says one early catch is worth 4 unnecessary rechecks. Compared against "recheck all" and "recheck none" over thresholds 2–60%.
- **Cost per early catch:** at each threshold, rechecks per true early catch = 1 / PPV. No dollar figures are assumed. A clinic can multiply by its own recheck price and compare with what an early catch is worth to it.
- **Prevalence:** this cohort is enriched (24% diagnosed within two years). Results are repeated after reweighting negatives to a 10% two-year rate, closer to a general senior-cat population.
- Models compared: M0 (latest creatinine, scaled to a probability by isotonic calibration within each fold), M3 (no SDMA) and M5 (with SDMA); plus M5 on the confounded labs from the stress test.

## Pre-stated expectations

1. M5's net benefit beats both "recheck all" and "recheck none" at every threshold from 5% to 50%.
2. M5's net benefit is at least M3's at every threshold from 5% to 50%.
3. At a 10% prevalence, rechecks per early catch at M5's 95%-specificity threshold are at least double what they are at 24% prevalence.

## Limits stated up front

Net benefit treats every true flag as equally valuable; a cat flagged 23 months before diagnosis gains more than one flagged 2 months before. The model's probabilities come from the simulation, so absolute values are optimistic.
