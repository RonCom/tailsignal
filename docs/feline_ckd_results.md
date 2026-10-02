# Feline Kidney Disease Early Prediction — Results

Spec (pre-registered): [`feline_ckd_spec.md`](feline_ckd_spec.md). Code: `src/tailsignal/models/feline_ckd.py`. Outputs: `reports/feline_ckd/`. Data: simulated clinic lab panels, actual network (452 index panels, 337 cats, 106 future diagnoses) and 10× scenario (4,856 panels, 3,567 cats, 1,166 diagnoses).

![Sensitivity at 99% specificity by lead time](../reports/feline_ckd/sensitivity_by_lead.png)

## Headlines (10× network)

1. **Two visits beat one.** Bradley's four features (creatinine, BUN, urine specific gravity, age) from two visits plus their change reach AUC 0.894, against 0.861 from the latest visit alone and 0.787 from the latest creatinine alone. Change over time is what separates early kidney decline from a cat whose creatinine simply runs high.
2. **SDMA adds the most.** Adding SDMA lifts AUC from 0.918 to 0.965. At 95% specificity it catches 77% of cats diagnosed 12–24 months later, against 41% without it.
3. **Very early, high-confidence flags stay hard.** At 99% specificity the best model catches 23% of cats diagnosed 12–24 months ahead and 65% of those diagnosed within a year. Bradley et al. report 44% and 63% on real Banfield data. Within a year this simulation matches them; further out it falls short.
4. **The latest creatinine alone cannot be used at 99% specificity.** It flags no future cases, because healthy cats with naturally high readings occupy the top 1%. The IRIS-style rule (creatinine ≥ 1.6 or SDMA ≥ 18) catches 81% of future cases but wrongly flags 24% of cats who stay healthy.

| Model (10×) | AUC (95% CI) | Sensitivity at 95% specificity | At 99%, diagnosis 12–24 mo ahead |
|---|---|---|---|
| M0 Latest creatinine | 0.787 (0.769–0.802) | 41% | 0% |
| M1 IRIS-style rule | 0.784 (0.770–0.798) | 81% (specificity 76%) | n/a |
| M2 Four features, one visit | 0.861 (0.847–0.875) | 49% | 1% |
| M3 Four features, two visits | 0.894 (0.882–0.905) | 64% | 7% |
| M4 + urine protein, pH, WBC | 0.918 (0.908–0.928) | 72% | 15% |
| M5 + SDMA | **0.965** (0.957–0.972) | **91%** | **23%** |

Calibration (M5): Brier score 0.047; observed rates track predicted risk across deciles (`reports/feline_ckd/10x/summary.json`).

## Pre-stated expectations, scored

| Expectation | Result |
|---|---|
| Two time points beat the latest creatinine | Confirmed at both sizes (10×: 0.894 vs 0.787) |
| SDMA adds over the wider panel | Confirmed (0.965 vs 0.918) |
| Sensitivity at 99% specificity, 12–24 months ahead, below 60% | Confirmed (23%) |

At the actual network size, results are noisier. The single-visit model (M2) edges the two-visit model (0.939 vs 0.922), and 99%-specificity estimates rest on a handful of healthy cats. That size is too small for a model meant to run at 99% specificity.

## What it would be worth

- **Product:** a risk flag on each senior cat's lab report, embedded in the clinic's lab results or the partner portal. It would prompt a recheck in 3–6 months, or SDMA and urine tests now.
- **Operational value** (owned network such as Destination Pet's vet clinics): earlier renal diets and rechecks, and the follow-up visits they bring.
- **Partner value:** a lab-diagnostics partner gets RenalTech-style screening; a pet food company gets a cohort for renal-diet trials.

## Limits

- The simulated kidney decline was generated from these lab values. Absolute performance is optimistic; comparisons between models are the point.
- Real cats have confounders this simulation lacks: hyperthyroidism, dehydration, muscle loss and diet all move creatinine and urine concentration.
- Cats are tracked by clinic record only; a cat seen at two clinics appears as two cats.
- Before any clinical use, this needs validation on real lab histories. The Dog Aging Project does not cover cats, so this means a lab or clinic partner.

## Source

Bradley R. et al. (2019). [Predicting early risk of chronic kidney disease in cats using routine clinical laboratory tests and machine learning](https://escholarship.org/uc/item/7f38t7mc). *Journal of Veterinary Internal Medicine* 33:2644–2656. 106,251 Banfield cats; four features; recurrent neural network.
