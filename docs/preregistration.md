# Pre-Registered Analysis Plan

Committed before any model is fit. Changes after this commit are logged in the amendment table at the bottom with a reason, so readers can separate confirmatory from exploratory results.

## Data used for each claim

| Claim type | Data | Why |
|---|---|---|
| Novel-method claims (Models A, B) | Real public data only | A model trained on simulated data only recovers the simulator's assumptions |
| Pipeline, linkage, privacy, forecasting method | Simulated multi-channel data with known ground truth | Ground truth allows exact measurement of linkage and recovery |
| Cross-channel value (Model C) | Simulation study, reported as a power analysis | Answers "how much partner data is needed to detect the effect," not "the effect exists" |

## Hypotheses

### Organize
- **H1 – Entity resolution.** Probabilistic linkage (Splink) achieves pairwise F1 ≥ 0.95 on cross-channel pet records and beats a deterministic rule (exact owner phone + pet name) on recall by ≥ 10 points at equal or better precision.
- **H2 – De-identification.** The released cohort table meets k ≥ 10 on quasi-identifiers (species, breed group, birth year, 3-digit ZIP, sex) with ≤ 5% of records suppressed.

### Predict
- **H3 – Model A, breed-stratified pharmacovigilance (openFDA).** Empirical-Bayes shrinkage (EBGM lower bound) with breed hierarchy pooling detects more positive-control drug–event–breed signals than PRR/ROR at a matched false-signal rate on negative controls, and detects them earlier relative to the public alert date.
  - Positive controls: isoxazoline class × neurologic events (FDA alert, Sept 2018); macrocyclic lactones × neurologic events in herding breeds associated with MDR1/ABCB1 variants.
  - Negative controls: drug–event pairs without a plausible mechanism, selected before looking at signal scores.
  - Primary metric: recall at the false-signal rate observed for PRR ≥ 2, n ≥ 3; secondary: months of lead time before alert.
- **H4 – Model B, hierarchical breed-condition risk.** Partial pooling across breed → breed group → size class yields better calibration (lower Brier score, calibration slope closer to 1) than unpooled breed-frequency estimates for breeds with < 50 dogs, with no loss for common breeds. Data: Dog Aging Project if access is granted; otherwise reported on simulated data and labeled as such.
- **H5 – Model C, cross-channel early warning (simulation).** Adding non-veterinary channel features (daycare attendance change, boarding and grooming notes) to a vet-only model raises 60-day vet-visit AUC. Reported as the minimum number of linked pets needed to detect a lift of 0.02, 0.05, and 0.10 AUC with 80% power.
- **H6 – Model D, uplift.** Targeting wellness-plan reminders by modeled uplift retains more members per 1,000 contacts than targeting by lapse risk alone (Qini coefficient, randomized holdout).

### Segment and forecast
- **H7 – Segmentation.** A stable segmentation exists: bootstrap mean Jaccard ≥ 0.75 per segment at the chosen k, with k selected by BIC and business usability (no segment < 5% of pets).
- **H8 – Forecasting.** Hierarchically reconciled forecasts beat seasonal-naive on MASE at site × service level across a 12-month rolling-origin backtest, with 80% intervals covering 75–85% of actuals.

## Validation rules
- Time-based holdouts: train through 2024-06-30, evaluate after; no random row splits for temporal models.
- Splits by household, so the same household never appears in train and test.
- Bootstrap 95% CIs (1,000 resamples, household-level) on every headline metric.
- Every model is compared with a simple baseline that a skeptical reviewer would propose first.
- Results that fail a hypothesis are reported, not dropped.

## Amendments

| Date | Change | Reason |
|---|---|---|
| 2026-10-01 | H3 negative controls replaced by (a) a permutation null for false-signal rates and (b) an extended reference set of label-listed reactions, in `docs/model_a_spec.md` | A hand-picked list of "no plausible mechanism" pairs is weak and easy to bias. A permutation null measures each method's false-signal rate directly. Made before the full FDA data was downloaded; no results seen. |
| 2026-10-01 | H3 adds a breed-specific positive control test: macrocyclic lactones × neurologic events, MDR1 high-frequency breeds vs. other dogs | Tests the claim that matters for a breed-stratified method: finding a signal that pooled all-dog analysis dilutes. |
| 2026-10-02 | Adds a **fixed review-budget comparison**: each quarter, every method ranks all drug–event cells (n ≥ 3) by its own score (PRR, ROR lower bound, EB05; for breed excess: interaction-ROR lower bound vs. hierarchical ratio 5th percentile). A method "detects" a control when it ranks in the top K (K = 10, 50, 100, 500, 1,000). Equal K means equal alert volume, so methods are compared like for like. Isoxazolines × Seizure NOS is added as a secondary target in all runs. A second, **within-product** ranking (where does the target rank among that drug's own reaction terms; K = 1, 3, 5, 10, 20; counted only when the target has n ≥ 3 and the product has ≥ 20 reviewable terms) was added after the cat global ranks showed every method's database-wide top list is filled with expected and labeled associations. | Default thresholds give PRR/ROR far more alerts than MGPS, so the first comparison was not like for like. Made after the default-threshold results were seen (section 3 of `model_a_results.md`), before any ranks were computed. |
| 2026-10-02 | Cat analysis (secondary in spec): pooled analysis only. Breed strata are not used for cats (no MDR1-type breed marker; most reports are domestic short/longhair). Control: isoxazolines × neurologic events. | The spec listed cats as secondary without a breed hypothesis. |
| 2026-10-02 | Adds a confirmatory analysis on 2020+ reports with a seizure/tremor composite and predictions P1–P5 (`docs/model_a_confirmatory_2020.md`). | The narrower event definition was chosen from 2013–2019 results; testing it on a later period that played no part in choosing it keeps the claim honest. Written before the 2020+ period was analyzed on its own. |
| 2026-10-02 | H7 exploratory revision after the pre-registered segmentation failed stability (min Jaccard 0.36): cluster on behavioral rates only (vet visits, wellness share, daycare days, boarding nights, grooming appointments); household attributes become descriptors; covariance regularization 0.1; diagonal covariance for a top level and full covariance for a finer level, both with k chosen by the pre-registered BIC + 5% rule. | Binary and near-constant attributes made the mixture spend components on exact-0/1 spikes. Reported alongside the failed pre-registered result, not instead of it. |
| 2026-10-02 | H8 adds an equal-weight average of the two base models (seasonal naive + MSTL) as an exploratory forecaster, reconciled with MinT. | Added after a one-origin smoke test showed neither base model wins in every service. The pre-registered comparison (MSTL + MinT vs. seasonal naive) is reported unchanged. |
| 2026-10-02 | H5 exploratory ablation: vet + engagement features (uses other channels) vs. vet + engagement + warning-signal features (attendance drop, concerning notes), on the platform data and on simulations with 0–100% warning signal. | The power study showed the pre-registered contrast lifts AUC even with no planted signal, so it cannot distinguish engagement from early warning. Added after seeing that result. |
