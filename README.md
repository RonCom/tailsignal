# TailSignal

[![tests](https://github.com/RonCom/tailsignal/actions/workflows/tests.yml/badge.svg)](https://github.com/RonCom/tailsignal/actions/workflows/tests.yml)

**A multi-channel pet health data platform: collect, organize, analyze, and commercialize data on dogs and cats from veterinary clinics, daycare and boarding, grooming, and wellness plans.**

TailSignal is a working model of a pet health data business. It links each pet's records across the businesses that care for it, standardizes them, protects privacy, and turns the result into four kinds of revenue: data products, research and insights, commercial models, and embedded analytics.

*Portfolio project by Chris Lavelle. Partner records (clinics, daycare, grooming, wellness plans) are simulated; drug-safety, antibiotic-resistance and clinical-text work uses real public data. Every analysis has a written specification and reports its misses.*

## Status

| Phase | Scope | Status |
|---|---|---|
| 1. Collect | Synthetic multi-channel generator; real-data ingest (openFDA, Austin, NYC licenses, Census CBP, PetEVAL) | ✅ Built; openFDA (1.36M reports), FDA NARMS and PetEVAL ingested and used |
| 2. Organize | dbt on DuckDB: staging for 6 source systems, breed/diagnosis/service taxonomies, entity resolution, de-identified products, 28 data tests | ✅ Built |
| 3. Analyze | Model A ✅ · segmentation ✅ · forecasting ✅ · Models C–D ✅ · Model A2 (EHR cohorts) ✅ · clinic benchmarks ✅ · feline CKD ✅ · Model B (awaiting Dog Aging Project access) | In progress |
| 4. Commercialize | Pet Health Index, versioned releases (DuckLake / Parquet), scoring API with entitlements and metering, partner portal, five-year business case | ✅ Built ([results](docs/productization_results.md)) |
| 5. Communicate | Slide deck, executive memo and interactive dashboard (`reports/dashboard/tailsignal_dashboard.html`); technical write-ups in `docs/` | ✅ Built |

## Results so far

**Entity resolution** (26,099 source records → 12,666 resolved pets; ground truth 12,428)

| Method | Precision | Recall | F1 |
|---|---|---|---|
| Deterministic baseline (same phone + same pet name) | 0.992 | 0.830 | 0.904 |
| **Two-stage: Splink household model → within-household pet matching** | 0.990 | **0.975** | **0.983** |

The two-stage design matters: a single Splink model over pet records reached only 0.48 precision, because pets in the same household share every owner field and get merged. Resolving households first and pets second fixes that. Household-level linkage: precision 0.971, recall 0.997.

**Taxonomy.** 114 distinct raw breed strings: 97 exact alias matches, 13 fuzzy (e.g., "Labrador Retreiver", "Daschund"), 4 left unmapped for review ("Sibe", "York. Terrier", "Aus. Shepherd", "Collie"). All diagnosis codes and free-text reasons from the three vet systems map to 12 conditions + wellness.

**Privacy.** De-identified cohort at k = 10 on species, breed group, birth period, geography, and sex, with progressive generalization:

| Release level | Share of pets |
|---|---|
| Birth year + 3-digit ZIP | 19% |
| 5-year birth band + 3-digit ZIP | 67% |
| 5-year birth band + metro | 6% |
| Suppressed | 8% |

The pre-registered target was ≤ 5% suppression; at this panel size (12.7k pets) it is missed. This is a finding: rare breed groups need more partners before they can be released at this granularity.

**Model A: breed-stratified pharmacovigilance** (970,167 real FDA dog adverse-event reports, plus a 144,967-report cat analysis; [full results](docs/model_a_results.md), [one-page brief](docs/briefs/model_a_brief.md))

| | PRR | ROR | MGPS | Hierarchical mixture (ours) |
|---|---|---|---|---|
| False signals per 1,000 cells (permutation null) | 43.2 | 68.6 | 0.0 | 0.0 |
| False *breed-specific* signals per 1,000 cells | 7.3 (unpooled interaction) | | | **0.0** |
| Finds MDR1-breed neurologic risk from ivermectin-class drugs | pooled: no | | pooled: no | **yes** (1.20× all-dog rate) |
| Rank of MDR1 breed signal at equal review effort (2013–2019) | 235–1,545 (unpooled) | | | **16–30** |
| Rank of isoxazoline seizures on the product's own reaction list, mid-2016 | 232 | 104 | 76 | |

The isoxazoline (2018 FDA alert) control was **not** detected before the alert at pre-registered thresholds. Post hoc, PRR flagged isoxazoline seizures 4.5 years early, but at a 43-per-1,000 false-signal rate.

**Model A confirmatory test (2020+ reports, pre-registered):** the breed-specific MDR1 signal and near-zero false-signal rate replicate; the isoxazoline seizure/tremor signal is real (~1.5× expected) but again misses the EB05 ≥ 2 bar. A verified set of label-listed reactions shows the limit of disproportionality for common reactions such as vomiting. Details in [model A results](docs/model_a_results.md), sections 7–8.

**Segmentation and forecasting** ([results](docs/analytics_results.md), [one-page brief](docs/briefs/platform_brief.md))

| | Result |
|---|---|
| Segmentation, pre-registered spec | **Failed** stability (Jaccard 0.36–0.68) |
| Segmentation, revised (behavioral rates only) | 3 top-level / 6 finer segments, all stable (Jaccard 0.76–0.99); daycare regulars = 22% of households, 64% of revenue |
| Forecasting, MSTL + MinT vs. seasonal naive | MASE 0.83 vs. 0.89 (better), but 80% intervals cover only 64% → H8 **fails** on calibration |
| Forecasting, blended model (exploratory) | MASE 0.81, coverage 79%; daycare staffing cost −7% vs. baseline in backtest |
| Forecasting, conformal recalibration (pre-registered) | Same MinT forecasts, recalibrated intervals cover 82% → calibration fixed; staffing to any upper bound still costs more than to the point forecast |

**Models C and D** ([results](docs/models_cd_results.md))

| | Result |
|---|---|
| D: uplift vs. risk targeting for wellness-plan reminders | Uplift ahead (+140 kept per 1,000 contacts) but CI includes zero → H6 **fails**; pilot too small to learn who benefits (~6,000–9,000 members needed). [Proposed trial design](docs/destination_pet_reminder_trial.md) |
| C: cross-channel early warning of sick visits | +0.007 AUC, but an ablation shows it is engagement, not early warning → H5 **fails**; warning value limited to pets active in other channels |

**Antimicrobial resistance** ([results](docs/amr_results.md), real FDA NARMS data, 26,396 dog isolates): MRSP rose from 31% to 43% of skin/other-site isolates (2017–2024); all 16 rising trends are in *S. pseudintermedius*, while *E. coli* is stable or improving. The pre-registered pooled analysis was confounded by site-specific breakpoints and cascade testing; the fix and both versions are documented.

**Clinical EHR layer** ([results](docs/simulator_extension_results.md), [spec](docs/simulator_extension_spec.md)): prescriptions, anesthesia, lab panels, real-NARMS culture results, clinical notes, and microchips on the same simulated world; 26 of 35 validation checks pass, with every miss reported. Key findings: a naive isoxazoline–seizure comparison looks protective (RR 0.33) because epileptic dogs are steered away from the drug, and excluding prior seizures recovers the planted effect; confirming a 1.5× risk needs ~23× this network; clinic death rates cannot be benchmarked at this volume but complication rates can.

**Model A2: EHR drug-safety cohorts** ([results](docs/model_a2_results.md)): new-user, active-comparator studies in clinic records with text-mined outcomes. At this network's size the studies are uninformative (2 vs 0 seizures); at 10× the isoxazoline estimate is RR 1.29 (0.39–4.29) against a planted 1.5. Real FDA onset dates support a 50-day window (89% of seizures begin within it). Rare-event validation needs ~130× this network, and linking records across clinics on pet details alone fails at scale (4% precision at 10×). On real UK clinic notes (SAVSNET PetEVAL), the frozen seizure dictionary's precision falls to 30%, mostly from "fit for vaccination"-type uses of "fit". An independent check against PetEVAL's own diagnosis labels confirms my verdicts and finds every clear seizure among 150 nervous-system records (15 of 15); my two readings agree only moderately (κ 0.48), so a second reader is needed.

**Feline kidney disease prediction** ([results](docs/feline_ckd_results.md)): RenalTech-style early warning from routine lab panels. Two visits beat the latest creatinine (AUC 0.894 vs 0.787 on the 10× network), and adding SDMA reaches 0.965. Flagging cats 12–24 months before diagnosis at 99% specificity remains hard (23%, vs 44% published on real Banfield data). A stress test with hyperthyroidism, dehydration and muscle loss cuts the latest-creatinine AUC to 0.73 but leaves the SDMA model at 0.96; a decision-curve analysis shows the flag beats rechecking every cat at any exchange rate from 1 to 19 rechecks per early catch, at about 1.2–1.5 rechecks per cat later diagnosed.

**Clinic quality benchmarks** ([results](docs/clinic_benchmarks_results.md)): risk-adjusted anesthesia, dental-charting, and antibiotic-stewardship scorecards with funnel plots, shrinkage, and rank ranges. Complication benchmarks work at current clinic volume (rank correlation with planted quality 0.97); death rates need ~5,000 procedures per clinic before they can rank clinics.

**Oral health insights** ([report](docs/oral_health_report.md)): 9.4% of dogs diagnosed per year; toy breeds 2.5× the odds; fewer than half of diagnosed dogs get a cleaning the same year. Compared against published Banfield (US) and VetCompass (UK) studies, which exposed four simulator gaps now queued for the simulator extension. Roadmap: [docs/roadmap.md](docs/roadmap.md).

## Architecture

```
raw sources (6 systems, 4 formats) ─┐
public data (FDA, Census, cities)  ─┤
                                    ▼
dbt staging ── normalize names, phones, dates, units, species codes
     │
dbt intermediate ── breed taxonomy (exact → fuzzy → unmapped)
     │             diagnosis taxonomy (codes + free text → conditions)
     │             one profile per pet record per source
     ▼
Python: entity resolution (Splink) ── household_id, pet_id
     │
dbt marts
  core:    dim_pet · dim_location · fct_service_event · fct_wellness_membership
  product: product_pet_cohort (k-anonymous) · product_condition_prevalence (suppressed)
           product_service_benchmark (partner benchmarks)
  qa:      qa_privacy_release · er_metrics
```

## Monetization models

See [`docs/monetization.md`](docs/monetization.md). Each model maps to a repo component:

| Model | TailSignal offering | Built on |
|---|---|---|
| Data Products | De-identified cohort and aggregate feeds (files, data share, API) | `product_pet_cohort`, `product_condition_prevalence` |
| Research & Insights | Pet Health Index, service benchmarks, market atlas, drug-safety landscape | Prevalence mart, Models A–B, Census data |
| Commercialized Models | Scoring APIs: breed risk, early warning, lapse uplift, demand forecasts | Models A–D, forecasting |
| Embedded Analytics | Partner portal: benchmarks, next-best-service, forecasts | `product_service_benchmark`, models |

## Data and licensing

- **Simulated:** all partner records, generated by `src/tailsignal/synth/` from a fixed seed. Nothing here describes a real clinic, owner or pet.
- **Public, downloaded by the ingest scripts (not stored in this repository):** FDA CVM adverse-event reports via openFDA, FDA NARMS animal pathogen data, U.S. Census County Business Patterns, city pet-license data.
- **Gated:** SAVSNET PetEVAL (Hugging Face) requires accepting its terms; download it yourself with `--source peteval`. It is not redistributed here.
- **Generated outputs:** `data/` is not tracked. In `reports/`, only charts, summaries, scorecards and dashboards are tracked; large intermediate tables are rebuilt by the commands below.

## Run it (Windows, uv)

```powershell
uv sync
uv run python -m tailsignal.pipeline            # ~3 min: generate data, dbt, entity resolution, tests
uv run pytest
uv run python -m tailsignal.ingest.public --source openfda --max-partitions 2   # quick real-data test
uv run python -m tailsignal.ingest.public --source all
```

Outputs: `data/warehouse.duckdb`, `reports/er_metrics.json`, `reports/er_match_weights.html`.

Model A (after the openFDA download; ~1 hour with 20 permutation replicates):

```powershell
uv run python -m tailsignal.models.pharmacovigilance
uv run python -m tailsignal.models.pharmacovigilance --safety-only --leave-drug-out --permutations 5   # exploratory
uv run python -m tailsignal.models.pharmacovigilance --species Cat
uv run python -m tailsignal.models.pv_confirm          # 2020+ confirmatory test
uv run python -m tailsignal.models.segmentation        # ~8 min
uv run python -m tailsignal.models.forecasting         # ~15 min
uv run python -m tailsignal.models.uplift              # Model D, <1 min
uv run python -m tailsignal.models.oral_health         # oral health report, <1 min
uv run python -m tailsignal.ingest.public --source narms   # FDA NARMS dog isolates
uv run python -m tailsignal.models.amr                 # AMR module, <1 min
uv run python -m tailsignal.models.early_warning       # Model C + power study, ~40 min
uv run python -m tailsignal.synth.ehr                  # clinical EHR layer (needs NARMS download), <1 min
uv run python -m tailsignal.synth.ehr_validate         # EHR validation scorecard, ~2 min
uv run python -m tailsignal.models.ehr_cohorts         # Model A2 on the actual network, ~2 min
uv run python -m tailsignal.synth.ehr --households 90000 --out data_scale10                       # 10x scenario, ~8 min
uv run python -m tailsignal.models.ehr_cohorts --root data_scale10 --tag 10x --no-text-eval       # ~10 min
uv run python -m tailsignal.models.peteval_check       # real-text check (after --source peteval)
uv run python -m tailsignal.models.feline_ckd          # feline kidney prediction (add --root data_scale10 --tag 10x)
uv run python -m tailsignal.models.feline_ckd_stress   # confounders + time split (10x; add --heavy for the exploratory run)
uv run python -m tailsignal.models.feline_ckd_decision # decision-curve analysis (10x)
uv run python -m tailsignal.models.peteval_holdout     # independent PetEVAL check
uv run python -m tailsignal.models.forecasting_conformal  # conformal intervals (after forecasting)
uv run python scripts/reminder_trial_power.py          # power for the proposed reminder trial
uv run python -m tailsignal.models.clinic_benchmarks   # clinic scorecards (add --root data_scale10 --tag 10x)
uv run python -m tailsignal.products.release           # versioned data-product release (DuckLake, else Parquet)
uv run uvicorn tailsignal.api.app:app --reload          # API + partner portal; docs at /docs
uv run python scripts/build_business_case.py          # five-year business case workbook
```

Explore with `duckdb data/warehouse.duckdb` or `uv run dbt docs generate --project-dir dbt --profiles-dir dbt`.

## Repo layout

```
docs/          preregistration.md · monetization.md · data_sources.md · model_a_*.md · analytics_results.md · briefs/
src/tailsignal/  synth/ (generator) · ingest/ (public data) · er/ (entity resolution) · models/ · pipeline.py
dbt/           models/{staging,intermediate,marts} · seeds/ (taxonomies) · tests/ (privacy, coverage)
tests/         unit tests
```

## Research standards

Hypotheses, metrics, baselines, and validation rules are in [`docs/preregistration.md`](docs/preregistration.md), committed before model fitting. Novel-method claims (Models A and B) use real data only; simulated data is used where ground truth is the point (linkage, privacy, power analysis).

## License

MIT. See [LICENSE](LICENSE).
