# Feline Kidney Disease Early Prediction: Specification (pre-registered)

Written 2026-10-02, before the model code was run. Data: simulated clinic records (EHR layer), actual network (1×) and 10× scenario. Code: `src/tailsignal/models/feline_ckd.py`. Outputs: `reports/feline_ckd/`.

## Question

From routine lab panels, can we flag cats that will be diagnosed with chronic kidney disease (CKD) in the next two years, earlier and more accurately than the latest creatinine result alone?

## Published reference

Bradley et al. (2019, *JVIM*) trained a recurrent neural network on 106,251 Banfield cats using creatinine, BUN, urine specific gravity (USG) and age. Sensitivity at about 99% specificity was 90.7% at diagnosis, 63.0% one year before and 44.2% two years before ([abstract](https://escholarship.org/uc/item/7f38t7mc)). This became Antech's RenalTech.

## Cohort

- **Unit:** a cat's lab panel (index) that has at least one earlier panel 90–900 days before it (two time points).
- **Outcome:** first recorded CKD diagnosis 30–730 days after the index panel. Diagnoses within 30 days count as "already diagnosable" and are excluded, not used as positives.
- **Exclusions:** cats with a CKD diagnosis on or before the index; index panels without 730 days of follow-up unless the outcome occurred.
- **Cats are identified by their clinic record** (no cross-clinic linkage); splits keep all of a cat's panels together.

## Models

| | Inputs | Purpose |
|---|---|---|
| M0 | Latest creatinine | The usual practice baseline |
| M1 | IRIS-style rule: creatinine ≥ 1.6 mg/dL or SDMA ≥ 18 µg/dL | A rule clinics already use |
| M2 | Bradley's four features (creatinine, BUN, USG, age) at the index only; logistic regression | Published feature set, one time point |
| M3 | The same four features at both time points plus change per year; gradient boosting | Two time points (RenalTech-style) |
| M4 | M3 plus urine protein:creatinine, urine pH, WBC | The wider panel |
| M5 | M4 plus SDMA | Value of SDMA |

## Evaluation

- Five-fold cross-validation grouped by cat; the 10× network is primary for precision, 1× is reported.
- Area under the ROC curve and average precision, each with a 95% bootstrap interval resampling cats.
- Sensitivity at 95% and 99% specificity, overall and by lead time (diagnosis 1–12 months vs 12–24 months after the index), for comparison with Bradley et al.
- Calibration: Brier score and a decile calibration table for the chosen model.

## Pre-stated expectations

1. Two time points (M3) beat the latest creatinine (M0), because single creatinine values are noisy in this simulation (19% of panels from cats never diagnosed exceed 1.6).
2. SDMA (M5) adds over M4, because simulated SDMA rises earlier than creatinine.
3. Sensitivity at 99% specificity for diagnoses 12–24 months ahead stays below 60%, in line with the published 44%.

## Limits stated up front

The simulated kidney decline was generated from these same lab values, so absolute performance is optimistic; the comparisons between models are the point. The simulation has no hyperthyroidism, dehydration or diet effects, which confound creatinine and USG in real cats.
