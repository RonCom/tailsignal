# Feline Kidney Disease Early Prediction — Results

Spec (pre-registered): [`feline_ckd_spec.md`](feline_ckd_spec.md). Code: `src/tailsignal/models/feline_ckd.py`. Outputs: `reports/feline_ckd/`. Data: simulated clinic lab panels, actual network (452 index panels, 337 cats, 106 future diagnoses) and 10× scenario (4,856 panels, 3,567 cats, 1,166 diagnoses).

![Sensitivity at 99% specificity by lead time](../reports/feline_ckd/sensitivity_by_lead.png)

## Headlines (10× network)

1. **Two visits beat one.** Bradley's four features (creatinine, BUN, urine specific gravity, age) from two visits plus their change reach AUC 0.894, against 0.861 from the latest visit alone and 0.787 from the latest creatinine alone. Change over time separates early kidney decline from a cat whose creatinine runs high.
2. **SDMA adds the most.** Adding SDMA lifts AUC from 0.918 to 0.965. At 95% specificity it catches 77% of cats diagnosed 12–24 months later, against 41% without it.
3. **Flags 12–24 months ahead at 99% specificity stay hard.** At 99% specificity the best model catches 23% of cats diagnosed 12–24 months ahead and 65% of those diagnosed within a year. Bradley et al. report 44% and 63% on real Banfield data. Within a year this simulation matches them; further out it falls short.
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

## Stress test: confounders and a time split (added 2026-10-02)

Spec, written before running: [`feline_ckd_stress_spec.md`](feline_ckd_stress_spec.md). Code: `src/tailsignal/models/feline_ckd_stress.py`. Untreated hyperthyroidism, dehydration at the visit and age-related muscle loss were added to the 10× network's lab values; models were also trained on earlier panels and tested on later ones from unseen cats.

| Model (10×) | AUC, original | Time split | + confounders | + confounders, time split | Heavier confounders* |
|---|---|---|---|---|---|
| M0 Latest creatinine | 0.787 | 0.795 | 0.731 | 0.739 | 0.698 |
| M3 Four features, two visits | 0.894 | 0.898 | 0.884 | 0.882 | 0.876 |
| M4 + urine panel, WBC | 0.918 | 0.921 | 0.913 | 0.912 | 0.909 |
| M5 + SDMA | 0.965 | 0.967 | 0.962 | 0.967 | 0.959 |

*Exploratory, chosen after seeing the pre-registered run: 40% of cats hyperthyroid, untreated for 1–3 years, and 25% of panels dehydrated. That puts 6.5% of panels in an untreated hyperthyroid cat, against 1.3% in the pre-registered run.

All four expectations were met:

| Expectation | Result |
|---|---|
| Time split changes AUC by less than 0.02 | Confirmed (largest change 0.008) |
| Confounders lower the latest-creatinine AUC by at least 0.05 | Confirmed (−0.056; −0.089 heavier) |
| The SDMA model loses less than the model without SDMA | Confirmed (−0.003 vs −0.010; −0.006 vs −0.018 heavier) |
| SDMA model keeps AUC of at least 0.90 with confounders on later data | Confirmed (0.967) |

- **Single creatinine readings are fragile; the multi-test models are not.** Hyperthyroidism and muscle loss hide high creatinine, and dehydration fakes it. Two visits plus BUN and urine concentration absorb most of that, and SDMA, which muscle loss does not move, absorbs most of the rest.
- **Sensitivity at 95% specificity falls more than AUC.** For M5, it falls from 91% to 88% (heavier confounders). For the latest creatinine alone, it falls from 41% to 18%.
- **The time split shows nothing here because the simulation has no drift.** On real data, changes in lab analyzers, reference ranges or case mix would show up in this test, so it stays in the pipeline.
- **99%-specificity estimates on the time split are noisy.** That test set has 1,877 panels, and M5 sensitivity 12–24 months ahead ranges from 23% to 41% across these scenarios. Treat those figures as indicative.
- **Limits:** confounders here are independent of kidney disease. In real cats they are not: treating hyperthyroidism often reveals hidden kidney disease. Dehydration and muscle-loss effect sizes are assumptions.

## Does the flag pay? Decision-curve analysis (added 2026-10-02)

Spec, written before running: [`feline_ckd_decision_spec.md`](feline_ckd_decision_spec.md). Code: `src/tailsignal/models/feline_ckd_decision.py`. Outputs: `reports/feline_ckd/decision/`.

![Net benefit by threshold](../reports/feline_ckd/decision/net_benefit.png)

The flag is worth using wherever a clinic would accept anything from 1 to 19 unneeded rechecks per early catch (thresholds 5–50%). Over that range the SDMA model gives the most net benefit, and the gap widens as rechecks get more expensive.

| Threshold (unneeded rechecks one catch is worth) | Recheck every cat | Latest creatinine | No SDMA (M3) | With SDMA (M5) | M5, confounded labs |
|---|---|---|---|---|---|
| 10% (9) | 0.156 | 0.164 | 0.184 | **0.219** | 0.217 |
| 20% (4) | 0.050 | 0.121 | 0.160 | **0.211** | 0.209 |
| 30% (2.3) | −0.086 | 0.098 | 0.145 | **0.202** | 0.200 |
| 50% (1) | −0.520 | 0.058 | 0.116 | **0.184** | 0.178 |

Net benefit = early catches per cat screened, after charging each unneeded recheck at the threshold's exchange rate.

| Expectation | Result |
|---|---|
| M5 beats "recheck all" and "recheck none" at every threshold from 5% to 50% | Confirmed |
| M5 at least matches M3 across that range | Confirmed |
| At 10% prevalence, rechecks per early catch at least double | **Failed**: 1.17 → 1.49 (+27%) |

- **Cost per early catch is low and stable.** At the 95%-specificity threshold, a clinic does 1.2 rechecks per cat later diagnosed. In a population with a 10% two-year rate it does 1.5, not double as I expected. At 95% specificity few healthy cats are flagged, so prevalence moves the ratio less than I assumed.
- **For Destination Pet:** the flag pays if one early catch is worth more than about 1.5 recheck panels. That compares one recheck's price with what earlier renal diet and monitoring are worth to the client and the clinic, a figure to confirm with them.
- **Confounders barely change this** (M5 0.209 vs 0.211 at 20%).
- **Limits:** net benefit counts a catch 2 months ahead the same as one 23 months ahead. At 10% prevalence the model's probabilities are no longer calibrated, so read thresholds there as approximate.

## What it would be worth

- **Product:** a risk flag on each senior cat's lab report, embedded in the clinic's lab results or the partner portal. It would prompt a recheck in 3–6 months, or SDMA and urine tests now.
- **Operational value** (owned network such as Destination Pet's vet clinics): earlier renal diets and rechecks, and the follow-up visits they bring.
- **Partner value:** a lab-diagnostics partner gets RenalTech-style screening; a pet food company gets a cohort for renal-diet trials.

## Limits

- The simulated kidney decline was generated from these lab values. Absolute performance is optimistic; read the results as comparisons between models.
- Hyperthyroidism, dehydration, muscle loss and diet all move creatinine and urine concentration in real cats. The stress test adds the first three, independently of disease; diet is not simulated.
- Cats are tracked by clinic record only; a cat seen at two clinics appears as two cats.
- Before any clinical use, this needs validation on real lab histories. The Dog Aging Project does not cover cats, so this means a lab or clinic partner.

## Source

Bradley R. et al. (2019). [Predicting early risk of chronic kidney disease in cats using routine clinical laboratory tests and machine learning](https://escholarship.org/uc/item/7f38t7mc). *Journal of Veterinary Internal Medicine* 33:2644–2656. 106,251 Banfield cats; four features; recurrent neural network.
