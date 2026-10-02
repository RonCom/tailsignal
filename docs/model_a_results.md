# Model A Results: Breed-Stratified Pharmacovigilance

Data: openFDA Animal & Veterinary adverse-event reports (1,357,337 reports, 1987–2026), downloaded 2026-10-01. Primary population: 970,167 dog reports with at least one drug and one reaction, excluding product-defect reports. Spec: [`model_a_spec.md`](model_a_spec.md). Outputs: `reports/model_a/dog/` (primary) and `reports/model_a/dog_safety_ldo/` (exploratory).

| Breed stratum | Dog reports |
|---|---|
| MDR1 high-frequency breeds | 31,159 |
| MDR1 low-frequency breeds | 52,952 |
| Other purebred | 613,971 |
| Mixed / unknown | 272,085 |

## 1. False-signal rates (permutation null, 20 replicates)

| Method | False signals per 1,000 drug–event cells |
|---|---|
| PRR (Evans) | 43.2 |
| ROR | 68.6 |
| MGPS (EB05 ≥ 2) | 0.0 |
| Stratified MGPS / hierarchical (EB05 ≥ 2) | 0.0 |

| Breed-specific excess test | False breed signals per 1,000 stratum cells |
|---|---|
| Unpooled interaction ROR | 7.3 |
| **Hierarchical mixture (ours)** | **0.0** |

At their default thresholds, the frequentist screens flag about 1 in 20 cells by chance. The Bayesian methods flag none.

## 2. Breed-specific positive control: macrocyclic lactones × neurologic events — **supported**

| Analysis | Result |
|---|---|
| All dogs pooled (MGPS) | EBGM 0.78: no signal. In pooled data the neurologic risk in MDR1 breeds is invisible. |
| MDR1 high-frequency breeds, hierarchical | Rate 1.20× the all-dog rate (5th percentile 1.15): **breed-specific excess flagged** |
| MDR1 low-frequency, other purebred, mixed | No excess (5th percentiles 0.86–0.99) |
| P(MDR1-high rate > other-purebred rate) | > 0.999 |
| Unpooled interaction ROR | Also flags MDR1-high (1.47, lower CI 1.38), but has a 7.3 per 1,000 false-breed-signal rate |

Both breed-aware methods find the known MDR1 sensitivity. The hierarchical model finds it while producing no false breed signals in 20 null replicates, so its breed flags can be acted on. The unpooled test would raise about 6,600 false breed alerts across the ~900,000 stratum cells.

The analysis window starts in 2013, more than a decade after MDR1 drug sensitivity was described, so this control tests detection and specificity, not lead time.

## 3. Isoxazolines × neurologic events — **not supported at pre-registered thresholds**

| Method | First quarter flagged (composite neurologic) | vs. FDA alert (2018-09-20) |
|---|---|---|
| PRR | never (through 2019) | — |
| ROR | 2014 Q2 (transient; steady from 2018 Q2) | ~4 years before, but at a 69/1,000 false-signal rate |
| MGPS | never (through 2019) | — |

Today, isoxazolines × neurologic composite: 27,351 reports vs. 20,416 expected, EBGM 1.34. The excess is real but well below the EB05 ≥ 2 threshold.

Why it was hard (findings, not excuses):
- **Masking.** Parasiticides dominate this database, and about a quarter of dog reports are lack-of-effectiveness reports. That depresses proportional ratios for every parasiticide.
- **Self-inflation.** Isoxazolines account for about half of all dog "Seizure NOS" reports. When one product dominates an event, it inflates its own expected count.
- **Composite dilution.** The pre-registered composite includes ataxia and trembling, which are not elevated. Seizure and tremor terms carry the signal.

## 4. Exploratory (post hoc, labeled as such)

Run after seeing section 3: lack-of-effectiveness reports and terms removed, and expected counts computed without the drug's own reports. Five null replicates.

| Target | PRR / ROR first flag | MGPS first flag | Current EBGM (EB05) |
|---|---|---|---|
| Isoxazolines × Seizure NOS | 2014 Q1 (4.5 years before alert) | 2019 Q3 (1 year after) | 2.51 (2.48) |
| Isoxazolines × neurologic composite | ROR 2018 Q4 | never through 2019 | 1.72 (1.70) |

False-signal rates were unchanged (PRR 43, ROR 68, MGPS 0, hierarchical excess 0 per 1,000), and the MDR1 result held (rate ratio vs. other purebred 1.11, probability > 0.999).

**Interpretation.** In this database there is a real speed–specificity trade-off. PRR saw the isoxazoline seizure pattern 4.5 years before the alert but would have raised tens of thousands of other alerts alongside it. MGPS raised none, and it also missed this one until after the alert. A screening program would use the frequentist screen to queue cases for review and the Bayesian score to prioritize them.

## 5. Like-for-like comparison: fixed review budget (amendment 2026-10-02)

Default thresholds hand PRR and ROR roughly 40–70 alerts per 1,000 cells and MGPS almost none, so sections 1–3 compare methods at very different alert volumes. Here every method gets the same review effort: each quarter, it ranks reaction terms by its own score and a reviewer looks at the top K. Lower rank = found sooner. A rank counts only when the target has n ≥ 3 and the product has at least 20 reviewable terms.

**Within-product ranks** (where the target sits on that product's own reaction list):

| Dogs, primary analysis | Terms on list | PRR | ROR | MGPS (EB05) |
|---|---|---|---|---|
| Isoxazolines × Seizure, 2016 Q2 | 885 | 232 | 104 | **76** |
| Isoxazolines × Seizure, 2018 Q2 (quarter before FDA alert) | 1,277 | 275 | 91 | **57** |
| Isoxazolines × neurologic composite, 2018 Q2 | 1,277 | 774 | 510 | **118** |
| Afoxolaner × Seizure, 2018 Q2 | 810 | 98 | 37 | **32** |
| Sarolaner × Seizure, 2018 Q2 | 402 | 42 | **14** | **14** |

At equal review effort, MGPS ranks the isoxazoline signals at or above PRR in every product and quarter checked, typically 3–5× higher. Against ROR it is ahead for the class-level targets but mixed for single products (2019 Q4 fluralaner × seizure: ROR 109, MGPS 158; lotilaner: 21 vs. 28). A reviewer working down the isoxazoline list in mid-2016, two years before the alert, would have reached seizures after about 76 terms with MGPS versus 232 with PRR. None of the methods put it in a database-wide top 1,000: the global lists are filled with expected and label-listed associations (2019 Q4 ranks 17,000–62,000 of about 87,000 cells).

**Breed-specific excess ranks** (macrocyclic lactones × neurologic in MDR1-high breeds, among all stratum cells):

| Quarter | Stratum cells | Unpooled interaction ROR | Hierarchical mixture |
|---|---|---|---|
| 2013 Q1 | ~35,000 | 235 | **16** |
| 2016 Q1 | ~67,000 | 833 | **26** |
| 2019 Q1 | ~101,000 | 1,545 | **30** |
| 2019 Q4, safety-only exploratory | ~101,000 | 1,820 | **1** |

With a review budget of 50 breed alerts, the hierarchical model surfaces the MDR1 signal in every quarter from 2013 to 2019; the unpooled test would need a list of 235–1,820. Once lack-of-effectiveness reports are removed, it is the single top breed-specific signal in the database.

## 6. Cats (secondary analysis)

Population: 144,967 cat reports. Breed strata are not used for cats.

| False signals per 1,000 cells (20 null replicates) | PRR 36.9 | ROR 57.6 | MGPS 0.0 |
|---|---|---|---|

| Target | Default thresholds | Within-product rank (PRR / ROR / MGPS) |
|---|---|---|
| Isoxazolines × neurologic composite | No method, through 2019 | 2019 Q4: 351 / 264 / **81** of 491 |
| Isoxazolines × Seizure | PRR 2017 Q1, ROR 2016 Q4 (before alert); MGPS never through 2019 | 2018 Q2: 109 / 77 / **44** of 290 |
| Sarolaner × Seizure | Today EB05 10.6 (102 reports vs. 8 expected) | 2018 Q2: 2 / **1** / 2 of 18 |

Cats repeat the dog pattern. At default thresholds PRR/ROR flag early with a high false-signal rate. At equal review effort MGPS ranks the class signal highest. Sarolaner seizures in cats (Revolution Plus, approved for cats in 2018) are at or near the top of the product's list under every method as soon as there are enough reports to rank.

## 7. Label-listed reactions (verified reference set)

Eight reaction–product pairs checked against the US product labels (sources in [`model_a_reference_set.csv`](model_a_reference_set.csv)). Two unverifiable rows were dropped (selamectin alopecia is labeled for cats only; there is no FDA-approved veterinary phenobarbital label for dogs). Ranks are within each product's own reaction list in today's data.

| Pair | Reports | PRR rank | ROR rank | MGPS rank | Flagged at default threshold |
|---|---|---|---|---|---|
| Carprofen × vomiting (dog) | 12,272 | 1,120 | 718 | 879 | ROR only |
| Meloxicam × vomiting | 2,031 | 800 | 516 | 554 | ROR only |
| Deracoxib × vomiting | 3,355 | 597 | 401 | 453 | ROR only |
| Spinosad × vomiting | 44,779 | 256 | 70 | 53 | ROR only |
| Cyclosporine × vomiting | 4,121 | 382 | 152 | 225 | ROR only |
| Melarsomine × injection site pain | 1,101 | 11 | **5** | 8 | all three |
| Melarsomine × injection site swelling | 1,751 | 8 | **4** | 6 | all three |
| Selamectin × application site alopecia (cat) | 5,221 | 28 | **6** | 16 | all three |

| Found in the top K of the product list | K = 5 | K = 10 | K = 20 |
|---|---|---|---|
| PRR | 0 | 1 | 2 |
| ROR (lower bound) | 2 | 3 | 3 |
| MGPS (EB05) | 0 | 2 | 3 |

**What this shows.** Disproportionality methods cannot find reactions that are common across all drugs. Vomiting is the most-reported dog reaction overall, so even the NSAIDs and cyclosporine, where vomiting is the labeled top reaction, sit only 1.3–1.7× above expectation. ROR's lower bound rewards large report counts and ranks these slightly better; MGPS and ROR tie on the distinctive reactions; PRR trails. The label set does not favor MGPS. Its advantage in sections 1–5 is specificity (no false signals) and breed-level shrinkage, not recall of common reactions.

## 8. Confirmatory test on 2020+ reports (pre-registered)

Spec: [`model_a_confirmatory_2020.md`](model_a_confirmatory_2020.md). New period only: 305,744 dog and 58,902 cat reports received from 2020-01-01; all priors refit. Event: seizure/tremor composite, chosen from 2013–2019 results.

| # | Prediction | Result | Pass? |
|---|---|---|---|
| P1 | Dogs: isoxazolines × seizure/tremor EB05 ≥ 2 | 14,393 reports vs. 9,524 expected; EBGM 1.51, EB05 1.49 | **Fail** |
| P2 | Dogs: each isoxazoline puts seizure/tremor in its top 10 (MGPS) | Sarolaner 9th of 748 (pass); afoxolaner 66th, lotilaner 143rd, fluralaner 201st | **Fail** (1 of 4) |
| P3 | Cats: isoxazolines × seizure/tremor EB05 ≥ 2 | 1,357 vs. 971 expected; EB05 1.34 | **Fail** |
| P4 | Dogs: MDR1-high breed excess for macrocyclic lactones × neurologic | Ratio 1.12 (5th percentile 1.05); no other stratum above 1 | **Pass** |
| P5 | Dogs: MGPS false signals ≤ 1 per 1,000 cells | MGPS 0.0; PRR 19.0; ROR 32.1; breed excess: hierarchical 0.0 vs. unpooled 5.4 | **Pass** |

The two method claims replicate on new data: the breed-specific MDR1 signal and near-zero false signals. The isoxazoline finding does not reach the strict threshold. The seizure excess is real and stable (about 1.5× expected in both periods) but small relative to a database dominated by parasiticide reports. That is a limit of spontaneous-report disproportionality for this kind of signal, which is why linked clinic data with exposure counts is the next step for TailSignal.

## Hypothesis scorecard (H3)

| Part | Result |
|---|---|
| Lower false-signal rate than PRR/ROR | **Supported** (0 vs. 43–69 per 1,000) |
| Breed-specific signal found that pooled analysis misses | **Supported** (MDR1 control; 0 false breed signals vs. 7.3 per 1,000) |
| Earlier detection of isoxazoline neurologic signal | **Not supported** at the pre-registered threshold |
| At equal review effort, Bayesian ranks surface the controls higher (amendment) | **Supported** for isoxazoline seizures (dogs and cats) and for the MDR1 breed signal (rank 16–30 vs. 235–1,545); **not** for label-listed common reactions, where ROR does as well or better (section 7) |
| Replicates on 2020+ data (confirmatory) | Breed signal and false-signal rate **replicate**; isoxazoline threshold **fails again** (section 8) |

## Next steps

1. ~~Compare methods at matched alert volume~~ (done, section 5).
2. ~~Cats~~ (done, section 6).
3. ~~Verify the reference set against labels~~ (done, section 7).
4. ~~Pre-registered seizure/tremor analysis on 2020+ data~~ (done, section 8).
5. Add exposure denominators (doses sold or prescriptions from partner clinics) so rates replace proportional ratios.
