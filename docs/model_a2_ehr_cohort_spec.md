# Model A2 (planned): EHR Active-Comparator Cohort Studies

Adapted from Davies et al. (2025), *Developing electronic health records as a source of real-world data for veterinary pharmacoepidemiology*, Frontiers in Veterinary Science 12:1550468 (SAVSNET, University of Liverpool).

## Why

Model A finds signals in spontaneous reports, which have no denominator (no count of treated animals), heavy under-reporting, and masking by common products. First-opinion EHRs fill that gap: prescriptions give the exposed cohort, and clinical narratives record adverse events whether or not anyone files a report. Davies et al. describe this as **signal validation** that complements spontaneous-report **signal generation**. TailSignal can offer both:

1. **Detect** (Model A): breed-aware disproportionality on FDA reports.
2. **Validate** (Model A2): cohort study in partner EHRs giving absolute incidence and relative risk against a comparator drug with the same indication.

## Design (from the paper, adapted)

| Step | Davies et al. | TailSignal version |
|---|---|---|
| Exposure | Prescription/invoice line mapped to active substance; index = first prescription | Vet line items mapped to ingredients via the drug taxonomy; first dispensing = index |
| Comparator | Same indication, no known risk of the event | Pre-specified per study (e.g., isoxazoline vs. non-isoxazoline flea/tick product) |
| Outcome | Regex dictionaries on free-text narratives: VeDDRA lower-level terms, expanded with word2vec synonyms/misspellings, then expert review | Same three-stage dictionary; plus a fine-tuned text classifier (PetBERT-style) as a comparison |
| Validation of outcome | Precision on 10,000 random narratives; recall where a gold standard exists | Same; synthetic data gives exact recall too |
| Risk window | From median time-to-onset in prior AE reports and drug half-life (e.g., 50 days for convulsions) | Taken from Model A's FDA reports (onset dates) per drug |
| Exclusions | Pre-existing signs before index; no follow-up consults; animals exposed to both products | Same; plus **entity resolution** to recover follow-up at other clinics (the paper cites loss to follow-up across practices as a key limitation, since animals lack a shared identifier) |
| Analysis | Incidence per 10,000; RR with 95% CI; Mantel–Haenszel age adjustment | Same, plus breed stratification (connects to Model A's MDR1 work) and propensity-score adjustment |
| Power | Rule of three: ~30,000 exposed animals to see a 1-in-10,000 event | Report the minimum cohort size per study; feeds partner-recruitment targets |

## What the simulator needs

- Prescriptions in vet line items (flea/tick, heartworm, NSAIDs, antibiotics) with realistic product mixes.
- Adverse events written into clinical narratives with misspellings, abbreviations, and negations ("no seizures", "fit and well"), at known true relative risks.
- A microchip number in some sources (now a legal requirement for dogs in the UK, per the paper), so we can measure how much a shared identifier improves follow-up versus probabilistic linkage.

## Validation plan

- Planted relative risks (e.g., 1.0, 1.5, 3.0) must be recovered within their 95% CIs.
- Dictionary precision/recall reported per stage (VeDDRA only → + embeddings → + expert/rules), mirroring the paper's Table 2.
- Real-text check: precision of the same dictionaries on SAVSNET PetEVAL narratives, if the dataset's terms allow.

## Analysis plan (locked 2026-10-02, before any cohort was built or any outcome counted)

Data: the clinical EHR layer ([spec](simulator_extension_spec.md)). Two networks: the actual simulated network (9,000 households, 9 clinics) and a **scale scenario** with 10× the households (same clinics' parameters drawn afresh), to show what partner recruitment buys. Both are reported; neither is preferred.

### Studies

| | Exposure (new users) | Comparator (new users) | Outcome | Window |
|---|---|---|---|---|
| S1 | First isoxazoline flea/tick dispensing (dogs) | First non-isoxazoline flea/tick dispensing | Seizure | 50 days (Davies et al.); sensitivity: window from real FDA time-to-onset (90th percentile, isoxazoline seizure reports in dogs) |
| S2 | First COX-inhibiting NSAID (carprofen, meloxicam, robenacoxib) for osteoarthritis (dogs) | First grapiprant for osteoarthritis | Vomiting/diarrhea | 14 days |
| S3 (negative control) | First heartworm macrocyclic lactone in an MDR1 breed (Australian Shepherd, Border Collie) | Same drugs, other breeds | Neurologic signs (ataxia, tremor) | 30 days |

Planted truths (from the simulator): S1 RR 1.5, S2 RR 2.0, S3 RR 1.0. The analysis code reads EHR tables only; truth tables are used only to score it.

### Cohort rules

- **Index:** first qualifying dispensing in the record; dogs with both products before or within the window of the index are excluded (Davies et al.).
- **Look-back:** at least 180 days of records before index (primary); sensitivity with no look-back requirement.
- **Pre-existing signs:** exclude if any non-negated mention of the outcome, including history mentions ("hx sz"), occurs before index.
- **Follow-up:** require at least one visit after index (any reason), as in Davies et al.
- **Linkage for follow-up:** four modes compared: clinic record only; microchip; probabilistic match on pet name, species, breed, sex, and birth year within market; and true identity (upper bound).

### Outcome identification (clinical notes)

| Stage | Method |
|---|---|
| 1 | Real VeDDRA term names from the FDA reports (e.g., "Seizure NOS", "Convulsion", "Grand mal seizure"), normalized, word-boundary match |
| 2 | Stage 1 + corpus expansion: note-vocabulary words within edit distance 2 of a stage-1 word, plus abbreviations; each candidate accepted or rejected by documented review (the analog of the paper's word2vec + expert step) |
| 3 | Stage 2 + rules: drop negated mentions ("no", "denies", "nil"), history mentions ("hx", "history", "known epileptic", "previous"), "fit and well", "fitted" |
| Classifier | TF-IDF (word and character n-grams) + logistic regression trained on 2,000 annotated notes (1,000 stage-2 hits + 1,000 random), tested on the rest |

Precision and recall are reported per stage against the note labels. The cohort analysis uses stage 3; a sensitivity analysis uses the true labels to measure the cost of outcome misclassification.

### Estimates

Risk per 10,000 in the window; RR with Wald and exact conditional 95% CIs; Mantel–Haenszel RR stratified by age band (<3, 3–7, 8+); propensity-weighted RR (IPTW on age, size, sex, body condition, prior visit count, clinic; robust SE). Exploratory: S1 by high-epilepsy-risk breeds vs others.

### Pre-stated expectations

- At 1×, S1 and S2 CIs will be too wide to distinguish the planted effect from no effect.
- At 10×, the S1 and S2 estimates should be closer to the planted RRs, with CIs that include them.
- S3 should be compatible with no effect at both sizes.
- Clinic-only follow-up loses outcomes for pets that switch clinics; microchip linkage recovers part, probabilistic linkage more.

### Real-text check

PetEVAL (SAVSNET) is gated on Hugging Face and could not be downloaded from this environment. If downloaded, the stage-1 to stage-3 dictionaries are run on it and a sample of hits is listed for manual precision review.
