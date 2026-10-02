# Simulator Extension: Clinical EHR Layer (specification)

Written 2026-10-02, before the layer was built or run. Code: `src/tailsignal/synth/ehr.py`. Validation: `src/tailsignal/synth/ehr_validate.py`.

## Purpose

The platform simulator (`generate.py`) produces what partner businesses export: visits, invoices, attendance. Roadmap options 4–6 and the AMR stewardship scorecards need what a clinic's practice-management system holds beneath that: prescriptions, procedures and anesthesia, lab results, culture results, clinical notes, and microchip numbers. This layer adds them.

## Design rules

1. **Same world.** The layer re-creates the platform world from the same seed (households, pets, illnesses, vet visits) and adds clinical detail on top with its own random stream. Every platform table and every earlier result is unchanged.
2. **Every planted effect is written down** in `data/truth/ehr/planted_params.json` and in the tables below, with its source or marked **assumption**.
3. **Real data where it exists.** Culture results are real FDA NARMS dog isolates (Vet-LIRN/NAHLN, 2017–2024) drawn by organism, site, region, and year, so co-resistance patterns are real. Anesthesia mortality is calibrated to CEPSAF. Kidney labs follow IRIS staging.
4. **Effects are realistic in size**, not inflated to make the demonstration easy. Where this panel is too small to detect an effect, the validation says so and states the network size needed.

## Tables (`data/raw/ehr/`)

| Table | Grain | Key fields |
|---|---|---|
| `ehr_patients` | pet × clinic | clinic_patient_id, microchip (nullable, with transcription errors), pet name, species, breed text, date of birth |
| `ehr_visits` | visit | visit type (wellness / sick / recheck / procedure / adverse event), diagnosis, weight, body condition score (BCS 1–9), dental grade if charted |
| `ehr_prescriptions` | dispensing | drug, class, indication, duration, culture before treatment, first-line flag, critically important (HPCIA) flag |
| `ehr_procedures` | anesthetic event | procedure, ASA class, emergency flag, pre-anesthetic bloodwork, complication, death within 48 h |
| `ehr_labs` | result | creatinine, BUN, SDMA, urine specific gravity (USG), urine protein:creatinine (UPC), urine pH, WBC |
| `ehr_cultures` | isolate × drug | organism, site, susceptible/resistant, source NARMS isolate id |
| `ehr_notes` | visit | free-text narrative with abbreviations, misspellings, negations |

Truth (`data/truth/ehr/`): planted parameters, clinic effects, latent dental grades, kidney trajectories, adverse-event causes, note labels, microchip truth.

## Planted parameters

### 1. Dental disease (fixes the four gaps found in the oral health report)

Latent periodontal grade 0–4 per pet, monthly steps from age 1. Onset hazard × size × weight × age; progression one grade per ~2 years; cleaning resets to grade 0.

| Effect | Value | Basis |
|---|---|---|
| Size multiplier (dogs) | toy 2.6, small 2.3, medium 1.4, large 1.0 | **Assumption**, sized so recorded prevalence ratios land near Wallis et al. 2021 (extra-small 1.9× large) and O'Neill et al. 2021 (<10 kg 3.07× risk vs 30–40 kg) |
| Overweight | hazard × 1.8 | **Assumption**, targeting Wallis et al. 2021 OR 1.65–2.23 |
| Age | log-hazard +0.15 per year | **Assumption**, targeting VetCompass 12+ vs 2–4 OR ~3.9 |
| Detection at wellness exam | 0.9 × clinic thoroughness | **Assumption**: disease is found at exams |
| Detection at sick visit / recheck | 0.4 / 0.2 × clinic thoroughness | **Assumption** |
| Clinic charting thoroughness | 0.55–0.95; two clinics planted low (0.45), one high (0.97) | **Assumption**; gives the clinic funnel something to find |
| Overweight prevalence | 30% baseline; Labrador ×1.6, Beagle ×1.4; all pets with a platform obesity diagnosis | **Assumption** |
| Cleaning after exam-detected grade ≥ 2 | 45% within 90 days | **Assumption**, matches the report's treatment gap |

Target: recorded dog prevalence 12–18% per year (VetCompass 12.5%/yr; Banfield 18.2% over 5 years).

### 2. Drug-safety cohorts (feeds Model A2)

| Exposure vs comparator | Outcome, risk window | Planted RR | Basis |
|---|---|---|---|
| Isoxazoline flea/tick (fluralaner, afoxolaner, sarolaner, lotilaner) vs non-isoxazoline (fipronil, imidacloprid/permethrin, selamectin) | Seizure, 50 days after each dispensing | **1.5** | Direction: FDA 2018 class warning; size: Model A confirmatory estimate (~1.5× expected). Window from Davies et al. 2025 |
| COX-inhibiting NSAIDs (carprofen, meloxicam, robenacoxib) vs grapiprant | Vomiting/diarrhea, 14 days after start | **2.0** | **Assumption** (direction from labels) |
| Macrocyclic lactone heartworm preventive in MDR1 breeds vs other breeds | Neurologic signs, 30 days | **1.0** (negative control) | Preventive doses are tolerated by MDR1 dogs; Model A's signal comes from reports, not preventive doses |

Confounding planted on purpose: dogs with idiopathic epilepsy (0.75% of dogs; Border Collie ×3, Australian Shepherd ×2, Beagle ×2, German Shepherd ×1.5, **assumption**) have ~3 seizure episodes a year and, once a seizure is on record, are 70% less likely to be given an isoxazoline (channeling, because the label warns). A naive cohort comparison is biased toward the null or protective; excluding pets with prior seizures (Davies et al.) removes it.

Baseline hazards (**assumptions**): non-epileptic dog seizures 0.4%/yr, cats 0.2%/yr; vomiting/diarrhea events 15%/yr. Share presented to a vet: seizures 0.8, GI 0.5.

### 3. Antibiotic prescribing (feeds AMR stewardship scorecards)

Infections added: urinary tract infection (dogs: female 2.5%/yr, male 1%/yr; cats 1%/yr) and superficial pyoderma (35% of allergic dermatitis episodes, plus 2%/yr). **Assumptions.** Organisms: UTI 75% *E. coli*, 25% *S. pseudintermedius*; pyoderma *S. pseudintermedius*. Cats use dog isolate profiles (NARMS has no cat isolates; **assumption**).

Market → NARMS region: Philadelphia → Northeast, Austin → South, Minneapolis → Midwest. Simulation year 2025 uses 2024 isolates.

Per-clinic stewardship propensities (Beta draws, saved to truth):

| Behavior | Range | Guideline reference |
|---|---|---|
| Culture before or at treatment (UTI / skin) | 0.15–0.75 / 0.05–0.4 | ISCAID urinary (2019) and pyoderma (2014) guidelines recommend culture in many cases |
| First-line choice (amoxicillin or trimethoprim-sulfa for cystitis; cephalexin, clindamycin, amoxicillin-clavulanate, trimethoprim-sulfa for pyoderma) | 0.35–0.85 | ISCAID |
| Critically important antibiotic as first choice (fluoroquinolones, 3rd-gen cephalosporins: enrofloxacin, marbofloxacin, cefovecin, cefpodoxime) | 0.05–0.35 | WHO critically important list |
| Topical-only therapy for pyoderma | 0.1–0.5 | ISCAID pyoderma |
| Metronidazole for acute diarrhea | 0.15–0.6 | Not recommended for uncomplicated acute diarrhea |
| Antibiotic with dental cleaning | 0.1–0.6 | Not routinely needed |

Treatment outcome: the drug is judged against the isolate's real NARMS result (drug proxies documented in code; methicillin-resistant isolates count as resistant to all β-lactams, per CLSI). Failure probability 0.75 if resistant, 0.12 if susceptible, 0.30 for topical-only (**assumptions**). Failure → recheck 10–21 days later, culture (80%), second drug chosen from susceptible options.

### 4. Anesthesia

Procedures: dental cleanings (platform + exam-driven), spay/neuter of juveniles, mass removal (50% of masses), cruciate repair (70%), IVDD surgery (35%, emergency).

| Parameter | Value | Basis |
|---|---|---|
| Death within 48 h, ASA 1–2 | dogs 0.05%, cats 0.11% | CEPSAF (Brodbelt et al. 2008) |
| Death within 48 h, ASA 3–5 | dogs 1.33%, cats 1.40% | CEPSAF |
| ASA class | age ≥ 8, overweight, brachycephalic → ASA 2; chronic heart/kidney disease or emergency → ASA 3–4 | **Assumption** |
| Within-ASA risk factors (OR) | brachycephalic 1.5, dog < 5 kg 2.0, age ≥ 12 1.5, emergency 1.5 | **Assumptions**; directions from CEPSAF and brachycephalic studies |
| Clinic effect on death | log-OR SD 0.3; one clinic planted at OR 2.0 | **Assumption** |
| Non-fatal complication (hypotension, hypothermia, regurgitation, prolonged recovery, airway obstruction) | 8% ASA 1–2, 20% ASA 3–5; brachycephalic OR 2.0; clinic log-OR SD 0.35; one clinic OR 2.0, one OR 0.6 | **Assumptions** |
| Pre-anesthetic bloodwork | 0.5–0.9 by clinic | **Assumption** |

Intercepts are solved numerically so the simulated rates match CEPSAF within each ASA group.

### 5. Kidney labs (feeds feline CKD prediction)

Cats with chronic kidney disease (platform diagnosis day D) lose function from D − L, L ~ Uniform(18, 36 months). Cats without a diagnosis in the window can develop it within 3 years after (same hazard), so late-window labs show early decline in some "healthy" cats, as in practice.

| Analyte | Healthy cat | Trajectory with loss fraction f (0 at onset, 1 at diagnosis) |
|---|---|---|
| Creatinine (mg/dL) | N(1.35, 0.2) + 0.01/yr | rises to ~2.3 (IRIS stage 2: 1.6–2.8) at diagnosis, convex |
| SDMA (µg/dL) | N(11, 2) | rises linearly to ~19 (IRIS stage 2: 18–25), so earlier than creatinine |
| BUN (mg/dL) | 22 + 12 × (creatinine − 1.3) + noise | follows creatinine |
| USG | ~1.045 | falls to ~1.020 |
| UPC | ~0.1 | rises to ~0.35 (borderline 0.2–0.4) |
| Urine pH, WBC | N(6.4, 0.3), N(9, 2.5) | little change |

Staging thresholds from IRIS (2023). RenalTech (Bradley et al. 2019) uses creatinine, BUN, USG, urine protein, urine pH, WBC, and age; all are generated. Panels are run at senior wellness exams (age ≥ 7; 60% × clinic lab intensity), pre-anesthesia, kidney/heart/lethargy sick visits, and kidney rechecks. Dogs get stable values with noise.

### 6. Clinical notes and microchips

Notes are templated SOAP-style text with abbreviations (V/D, BAR, BCS, PD, hx, sz), misspellings (siezure, vomitting, diarrhoea), negations ("no seizures", "no V/D"), history mentions ("hx of seizures"), and the ambiguous "fit and well" (UK usage, not a seizure). Each note carries truth labels: current seizure, current GI event, negated mention, history mention.

Microchips (15-digit ISO, real manufacturer prefixes 900/941/956/981/985): 75% of dogs, 55% of cats chipped (**assumption**); clinics record the number 60–95% of the time with 2% transcription errors. Pets that switch clinics get a new clinic patient id, so linkage by microchip versus probabilistic matching can be compared (Davies et al. limitation).

## Validation (pre-specified)

| Check | Pass rule |
|---|---|
| Dental: recorded prevalence, size gradient, overweight OR, wellness-exam effect, age OR | Dog prevalence 12–18%/yr; small > large; overweight OR 1.5–2.4; pets with a wellness exam have higher recorded prevalence; 12+ vs 2–4 OR 2.5–5 |
| Dental: clinic funnel | Flags the planted low-charting clinics; at most one false flag |
| Anesthesia: deaths by species × ASA | Planted rates within the observed 95% CI |
| Anesthesia: clinic complication funnel | Flags the planted high-complication clinic |
| Kidney: labs before diagnosis | Creatinine and SDMA rise and USG falls over the 24 months before diagnosis; SDMA crosses its stage-2 threshold before creatinine on average |
| Drug safety: planted RRs | Truth-based estimator unbiased and 95% CI coverage ≈ 95% across 200 re-draws of the outcome layer; single-world estimate and the network size needed for 80% power reported |
| Drug safety: confounding | Naive isoxazoline RR biased below 1.5; excluding prior seizures restores it (across re-draws) |
| AMR: culture results | Resistance in simulated cultures within 3 points of the NARMS regional input |
| AMR: stewardship | Observed clinic metrics rank-correlate with planted propensities (Spearman ≥ 0.8); failure rate higher when the isolate is resistant |
| Notes: keyword search for seizures | Report precision and recall of a naive search and a negation-aware search against note labels |

## Limits

- Effect sizes marked **assumption** are not literature estimates; findings about them demonstrate methods, not clinical facts.
- Real NARMS isolates over-represent hard-to-treat infections, so simulated failure rates are pessimistic.
- Infections added here (UTI, pyoderma) and adverse-event visits exist only in the EHR layer; the platform's partner exports are left unchanged so earlier results stay reproducible.

## Sources

- Brodbelt D.C. et al. (2008). [The risk of death: the Confidential Enquiry into Perioperative Small Animal Fatalities](https://www.research.ed.ac.uk/en/publications/the-risk-of-death-the-confidential-enquiry-into-perioperative-sma/). *Veterinary Anaesthesia and Analgesia* 35:365–373.
- International Renal Interest Society (2023). IRIS staging of CKD ([summary of thresholds](https://www.radanalyzer.com/blog/iris-ckd-staging-guide-cats/)).
- Bradley R. et al. (2019). Predicting early risk of chronic kidney disease in cats using routine clinical laboratory tests and machine learning. *JVIM* 33:2644–2656.
- Davies H. et al. (2025). Developing electronic health records as a source of real-world data for veterinary pharmacoepidemiology. *Frontiers in Veterinary Science* 12:1550468.
- Wallis C. et al. (2021); O'Neill D.G. et al. (2021): see the [oral health report](oral_health_report.md).
- FDA NARMS animal pathogen data: see [AMR results](amr_results.md).

## Amendment 2026-10-02: build deviations, calibration, and check revisions

### Built differently from the spec (decided while coding, before any validation run)

| Item | Spec | Built | Why |
|---|---|---|---|
| SDMA trajectory | Linear rise to ~19 | Concave (√f) rise to ~21 | A linear SDMA would cross its threshold *after* creatinine, the opposite of the published pattern |
| Critically important antibiotic propensity | Marginal share 0.05–0.35 | Share of non-first-line choices 0.15–0.70; marginal share saved in truth (0.04–0.31) | Keeps first-line + critically important ≤ 100% for every clinic |

### Calibration (simulator parameters tuned to published targets; three runs)

Calibration means changing the simulated world until it resembles published data. It is not hypothesis testing, but every change is listed.

| Parameter | Run 1 | Run 3 (final) | Target that drove it |
|---|---|---|---|
| Dental onset hazard h0 | 0.055 | 0.017 | Recorded prevalence 23% → 18.1% (VetCompass 12.5%/yr) |
| Age slope (log-hazard/yr) | 0.15 | 0.06 | Age 12+ vs 2–4 OR 5.8 → 4.7 (VetCompass 3.9) |
| Overweight hazard multiplier | 1.8 | 3.5 | Observed OR 1.30 → 1.60 (Wallis et al. 1.65–2.23); the platform's weight-blind dental complaints dilute the effect |
| Small-breed multiplier | 2.3 | 3.0 | Small vs large OR 1.5 → 1.56 |
| Charting at sick visit / recheck | 0.4 / 0.2 | 0.25 / 0.1 | Sick visits focus on the complaint |
| Non-planted clinic charting thoroughness | 0.55–0.95 | 0.70–0.90 | With a wide random spread every clinic differs, so "false flag" had no meaning |

Not calibrated: anesthesia, kidney, drug-safety, infection, and stewardship parameters are as first specified.

### Check revisions (made after seeing results; pre-registered versions still reported)

| Pre-registered check | Problem | Revised check |
|---|---|---|
| Culture resistance within 3 points of NARMS | Compared all cultures, but cultures taken after a failed treatment are enriched for resistant isolates (the same selection that affects real diagnostic submissions); 3 points is also below sampling error at ~100 isolates per cell | First-visit cultures only, same years (2022–2024), binomial test per cell; ≥ 90% of cells consistent at p ≥ 0.05 |
| Funnel "at most one false flag" | Non-planted clinics also have random effects, so flagging them can be correct | Flags agree in direction with the planted effect; rank correlation of observed/expected with planted effect ≥ 0.7 |
| SDMA crosses its stage-2 threshold (18) before creatinine (1.6) | Hall et al. (2014), the source of the "SDMA first" finding, compared SDMA > 14 (upper reference limit) with creatinine above its reference range | SDMA > 14 vs creatinine > 1.6, on the median trajectory and per cat |
| Single-world RR CIs cover the planted RR (NSAID, MDR1 null) | Too few events in this panel to estimate at all (zero cells) | Replicate coverage of a conditional exact CI (Clopper–Pearson on the exposed share of events), suited to sparse counts |
| Wellness exams raise recorded prevalence | Years without a wellness exam are years with sick visits, including dental complaints, so raw prevalence is not higher with exams | Added a truth-based check: among dogs with grade ≥ 2 disease, the share recorded is higher in years with an exam |
