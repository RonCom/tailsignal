# Feline Kidney Model: Stress Test (pre-registered)

Written 2026-10-02, before the stress-test code was run. Code: `src/tailsignal/models/feline_ckd_stress.py`. Outputs: `reports/feline_ckd/stress/`. Builds on [feline_ckd_spec.md](feline_ckd_spec.md); cohort, models and metrics are unchanged.

## Question

The first evaluation lists two weaknesses: the simulated cats have none of the conditions that make creatinine misleading in real cats, and models were scored by shuffled cross-validation rather than on later data. How much of the reported accuracy survives when both are fixed?

## Confounders added to the lab values

Applied to the existing simulated panels (10× network), each with a fixed seed. Disease status and diagnosis dates are unchanged; only what the lab reports changes.

| Confounder | Who | Effect on reported values | Basis |
|---|---|---|---|
| Untreated hyperthyroidism | 15% of cats, onset at a random age 10–16, untreated for 6–18 months | creatinine × 0.65, SDMA × 0.80, BUN × 0.85, USG − 0.008 | 19% of UK cats aged 8+ screened were hyperthyroid ([Bestwick et al. 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13446506/)). After radioiodine, median creatinine rose 1.0 → 1.5 mg/dL and SDMA 9 → 11 µg/dL in non-azotemic cats ([Peterson et al. 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC5787157)) |
| Dehydration at the visit | 10% of panels, at random | creatinine × 1.25, BUN × 1.40, SDMA × 1.15, USG + 0.008 | Assumed: prerenal azotemia raises BUN more than creatinine |
| Muscle loss with age | every cat from age 12 | creatinine × (1 − 0.02 per year over 12); SDMA unchanged | Assumed rate; SDMA is not affected by lean mass while creatinine is (Hall et al. 2014) |

## Evaluation

Four scenarios for models M0, M3, M4 and M5:

1. Original labs, five-fold cross-validation by cat (the published result).
2. Original labs, **time split**: train on index panels before the median index day, test on later panels from cats not seen in training.
3. Confounded labs, cross-validation.
4. Confounded labs, time split.

Metrics: AUC with cat-bootstrap 95% intervals, sensitivity at 95% specificity, and at 99% specificity for diagnoses 12–24 months ahead.

## Pre-stated expectations

1. Time split alone (scenario 2 vs 1) changes AUC by less than 0.02 for every model, because the simulation has no drift over time.
2. Confounders lower M0 (latest creatinine) AUC by at least 0.05.
3. M5 (with SDMA) loses less AUC than M3 (no SDMA) under confounders.
4. M5 keeps an AUC of at least 0.90 in scenario 4.

## Limits stated up front

The confounder sizes are partly assumed (dehydration and muscle loss). Hyperthyroidism here only masks values; it does not change who develops kidney disease or when it is diagnosed, although in real cats treatment often reveals hidden kidney disease.
