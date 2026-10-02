# Model A2: EHR Drug-Safety Cohorts — Results

Active-comparator, new-user cohort studies in clinic records, following Davies et al. (2025). Analysis plan locked before running: [`model_a2_ehr_cohort_spec.md`](model_a2_ehr_cohort_spec.md). Code: `src/tailsignal/models/ehr_cohorts.py`, `ehr_text.py`. Outputs: `reports/model_a2/{1x,10x}/`. Data: the clinical EHR layer at the actual network size (1×, 9 clinics) and a 10× scale scenario.

![Forest plot](../reports/model_a2/forest.png)

## Headlines

1. **At this network's size, the studies cannot answer their question.** After new-user, look-back, and pre-existing-sign rules, the isoxazoline study has 986 exposed and 616 comparator dogs with 2 and 0 seizures. The NSAID and MDR1 studies have 3 and 0 events. This was the pre-stated expectation.
2. **At 10×, estimates land near the planted effects but stay inconclusive.** Isoxazoline seizures: RR 1.29 (95% CI 0.39–4.29) with propensity weighting, 1.44 (0.50–4.14) with perfect linkage; planted 1.5. Confirming a 1.5× seizure risk needs about **81,000 dogs per arm, roughly 130× this network's 616 comparator dogs**. Rare adverse events need pooled multi-network data, which is the commercial case for a data consortium.
3. **Skipping the look-back recreates the channeling bias.** Without 180 days of history, dogs with prior seizures can't be identified and excluded. At 10× the estimate drops to RR 0.80 (0.50–1.27), the same "protective" artifact seen in the simulator validation.
4. **Matching records on pet details alone breaks down as the network grows.** Name, breed, sex, and birth year link 99% of true cross-clinic pairs. At 1× only 49% of proposed links are correct; at 10× only 4%, because common names collide. The resulting false merges shrank the 10× isoxazoline cohort from 9,879 to 6,170 dogs. Microchips are always right but find only 31% of pairs. **Owner identifiers are needed**, which the platform's household-level Splink model has (pet-level F1 0.983). The pre-stated expectation that probabilistic linkage would recover the most follow-up is not supported.
5. **A vague outcome definition dilutes a real effect.** The planted NSAID effect (RR 2.0) applies to drug-related vomiting/diarrhea. About half of all GI visits are unrelated, so "any GI note" can show at most ~1.5. The 10× estimate is 0.87 (0.38–1.96): it includes 1.5 but just excludes 2.0. Detecting 1.5 needs ~4,500 grapiprant users, about 11× the 10× comparator.
6. **The negative control behaves.** MDR1-breed dogs on heartworm preventives: 0 neurologic events in 753 vs 4 in 10,989 (exact upper bound RR 22). This is compatible with no effect, as planted.

## Real-data input: how soon after an isoxazoline do seizures start?

From 13,407 FDA dog reports linking an isoxazoline to a seizure term, with both exposure and onset dates: median 2 days, 75th percentile 14 days, 90th percentile 61 days. 89% start within 50 days, which supports the 50-day window Davies et al. used. A 61-day sensitivity window gives RR 1.08 (0.39–2.97) at 10×.

## Finding outcomes in clinical notes (1× corpus, 61,527 notes)

| Outcome | Stage | Precision | Recall |
|---|---|---|---|
| Seizure | 1: real VeDDRA terms | 2% | 47% |
| | 2: + spelling variants, abbreviations ("sz"), co-occurrence words | 3% | 83% |
| | 3: + negation, history, "fit and well" rules | 75% | 71% |
| | Classifier (2,000 annotated notes) | 96% | 100% |
| Vomiting/diarrhea | 3 | 99% | 98% |
| Neurologic signs | 3 | 100% | 84% |
| | Classifier | 100% | 7% |

- **Stages 1–2 are unusable alone** because most seizure words in notes are negations ("no seizures") or history ("hx sz").
- **Stage 3 still misses phrasings no expansion found**, such as "tonic-clonic episode" and "fitting, paddling". Recall stops at 71%.
- **The classifier's near-perfect score reflects templated synthetic text.** It is an upper bound, not a forecast.
- **The neurologic classifier failed (7% recall)** because its training notes were sampled from dictionary hits. It never saw the phrasings the dictionary missed. Annotation samples must include non-hits.
- **Outcome errors matter in small cohorts.** With perfect labels instead of stage 3, the 10× isoxazoline estimate moves from 1.29 to 0.54. Four false-positive notes are enough to swing it.
- **The stage-2 review is optimistic.** I accepted or rejected each candidate word, but I also wrote the note templates. The PetEVAL check below tests the dictionaries on genuine clinic language.

## Real-text check: SAVSNET PetEVAL (added 2026-10-02)

The seizure dictionary, frozen from the synthetic notes, was run on the 4,999 public PetEVAL test records (real UK first-opinion clinic notes). I read and judged all 60 stage-3 hits (`docs/peteval_seizure_review.csv`).

| | Flagged | True seizure mention | Uncertain (differential) | False | Precision |
|---|---|---|---|---|---|
| Stage 3, frozen | 60 | 18 | 3 | 39 | **30%** (35% counting uncertain) |
| Stage 3 + post-hoc "fit" rules | 28 | 18 | 3 | 7 | 64% (75%); optimistic, written after reading these hits |

- **Real notes are much harder than synthetic ones.** Precision fell from 75% on synthetic notes to 30%. 37 of the 39 false hits come from the VeDDRA term "Fit" in its everyday UK sense: "fit for vaccination", "fit to travel", "muzzle fits well", "coughing fit".
- **The negation and history rules held up.** All 36 hits removed by stage 3 (e.g., "no seizures since last visit", "no fits since restarting Epiphen") were correctly dropped.
- **The post-hoc rules lost no true mentions** here and don't change results on the synthetic notes. The independent check below tests them further.
- **Recall can't be fully measured** without annotating every record. A wider search ("petit mal", "epileptoid", "twitching") found 1–3 seizure-like episodes the dictionary missed, plus several records about epilepsy medication with no current event.
- **Only the test split (4,999 records) is distributed publicly.** The 11,000 training records needed to fine-tune a PetBERT-style classifier are not, so the classifier comparison stays on synthetic text.

This confirms the paper's point that dictionaries need expert review on real clinic text. It is also why the synthetic results above are best read as an upper bound.

### Independent check (added 2026-10-02)

Spec, written before running: [`peteval_holdout_spec.md`](peteval_holdout_spec.md). Code: `src/tailsignal/models/peteval_holdout.py`. A fresh sample of hits was not possible: every hit in the public set had already been read. Instead, my verdicts were compared with PetEVAL's own diagnosis labels, and recall was measured on the 150 records PetEVAL files under "Diseases of the nervous system", which I read with the dictionary output hidden (`docs/peteval_nervous_system_labels.csv`).

| Check | Expected | Result |
|---|---|---|
| My true hits that PetEVAL files under nervous-system disease | at least 80% | **100%** (18 of 18) |
| My false hits that PetEVAL files there | at most 15% | **8%** (3 of 39) |
| Recall of the frozen dictionary on clear current or recent seizures | at least 70% | **100%** (15 of 15) |
| Recall counting "possible" episodes too | not stated | 74% (23 of 31) |
| True seizures lost by the post-hoc "fit" rules | at most 1 | **0** |
| Dictionary flags on nervous-system records with no seizure | not stated | 1 of 119 |

- **My first labels hold up against PetEVAL's annotators.** Every hit I called true carries their nervous-system label; the three "false" hits that do are dogs with epilepsy but no current seizure ("no fits since restarting phenobarbital").
- **The dictionary misses vague episodes, not clear seizures.** Of the 8 misses, 6 are episodes the vet could not name ("? petit mals", "collapse, possible syncope", "? canine cramping epileptoid syndrome"). The other 2 are epileptic dogs with no fit since treatment started, which the negation rule drops on purpose.
- **The post-hoc rules cost no true seizures here either**, so they can be adopted. The 64% precision estimate is still optimistic, because those rules were written from the same notes.
- **My two readings agree only moderately.** On the 24 notes read both times, the labels match on 18 (75%; Cohen's kappa 0.48, or 0.52 for seizure vs not). Four notes I first called true seizures I later marked "possible" (vague episodes, or a fit with no date). Two I had called false moved up: one to "possible" and one to "seizure", a recheck that reads "no further seizures" and arguably fails the criterion. Recall is unaffected: every note either reading calls a seizure is flagged. Precision is: under the stricter second reading, frozen precision would be 15 of 60 (25%) rather than 18 of 60 (30%). A second reader is needed. The blind read was also not truly blind for these 24 notes, since I had read them before.
- **Limits:** recall is measured only within the nervous-system label, so seizure notes filed elsewhere are not counted; 15 clear cases give a wide interval (exact 95% CI for 15 of 15: 78–100%).

## Pre-stated expectations, scored

| Expectation | Result |
|---|---|
| 1× CIs too wide to separate planted effect from none | Confirmed |
| 10× estimates closer to planted RRs, CIs include them | S1 confirmed; S2 crude exact CI includes 2.0, propensity-weighted CI just excludes it (0.38–1.96); both include the diluted 1.5 |
| S3 compatible with no effect | Confirmed |
| Probabilistic linkage recovers the most follow-up | **Not supported**: pet-only matching merges different dogs; microchip or clinic-only follow-up gave results closer to perfect linkage |

## What this means commercially

| Offering | Feasible now? |
|---|---|
| Signal validation for **rare** events (seizures, 1 in 1,000 per window) | Only with pooled data at ~130× this network: a consortium or a large clinic-group partner |
| Validation for **common** events (GI upset after NSAIDs) | Needs ~4,500 comparator dogs, ~80× this network; within reach of a large clinic group |
| Time-to-onset and risk-window evidence from FDA reports (Model A) | Now; supports study design for manufacturers |
| Outcome dictionaries and annotation services | Now; precision/recall per stage is the deliverable |
| Linkage across clinics | Requires owner identifiers or the platform's household model; microchips alone link a third |

## Limits

- Synthetic notes are templated, so text-mining performance is optimistic.
- The 10× scenario is a separately simulated world, not 10 copies of this one.
- New-user cohorts with a 180-day look-back drop about three quarters of first dispensings, because most dogs get their first flea/tick product at their first visit.

## Sources

- Davies H. et al. (2025). Developing electronic health records as a source of real-world data for veterinary pharmacoepidemiology. *Frontiers in Veterinary Science* 12:1550468.
- FDA CVM adverse event reports via [openFDA](https://open.fda.gov/apis/animalandveterinary/event/) (onset and first-exposure dates; VeDDRA terms).
- Farrell S. et al. (2025). [PetEVAL: A veterinary free text electronic health records benchmark](https://aclanthology.org/2025.bionlp-1.29/). BioNLP 2025. [Dataset card](https://huggingface.co/datasets/SAVSNET/PetEVAL).
