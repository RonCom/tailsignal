# TailSignal Roadmap

Updated 2026-10-02. Sources reviewed for this version: Banfield's 150-million-visit insights (anesthesia safety, oral health, feline CKD), Antech RenalTech, FDA NARMS, VetDataHub, and Davies et al. (2025) on EHR pharmacoepidemiology.

## Done

| Phase | Component | Result in one line |
|---|---|---|
| Collect | Synthetic 6-system generator; FDA, Census, city, PetEVAL ingest | Runs end to end; openFDA verified on 1.36M real reports |
| Organize | dbt models, taxonomies, entity resolution, de-identified products | Pet-level F1 0.983 vs. 0.904 baseline; k-anonymity enforced by tests |
| Analyze | Model A: breed-aware drug-safety signals | Breed signal and near-zero false signals replicate on 2020+ data; isoxazoline threshold missed |
| Analyze | Segmentation | Pre-registered design failed; revised design stable (3 + 6 segments) |
| Analyze | Forecasting | Beats baseline on accuracy, fails interval calibration; blended model promising |
| Analyze | Model C: cross-channel early warning | Lift is engagement, not early warning |
| Analyze | Model D: reminder uplift | Average effect positive; pilot too small for targeting |
| Insights | Option 2: AMR module (real FDA NARMS data) | MRSP 31% → 43% (2017–2024); S. pseudintermedius worsening, E. coli stable/improving; breakpoint and cascade-testing artifacts found and fixed |
| Commercialize | Option 7: productization | Pet Health Index, versioned releases, API with entitlements and metering, partner portal, business case (base case not yet profitable: partner incentives and license volume are the levers) |
| Communicate | Option 8: communication package | 13-slide deck, executive memo, interactive dashboard (clinic scorecards with 10× switch, NARMS trends, regional antibiogram) |
| Analyze | Option 5: clinic quality benchmarks | Complication scorecards reliable at current volume (rank corr. 0.97); per-clinic death benchmarks need ~5,000 procedures; under-charting and stewardship gaps detected |
| Analyze | Option 4: Model A2 EHR drug-safety cohorts | At 10× network, isoxazoline seizure RR 1.29 (0.39–4.29) vs planted 1.5; rare-event validation needs ~130× this network; pet-only record matching fails at scale; no-look-back design recreates channeling bias |
| Organize | Option 3: clinical EHR layer | Prescriptions, anesthesia, labs, real-NARMS cultures, notes, microchips; 26/35 checks pass; channeling bias, network-size, and benchmark-power findings |
| Insights | Option 1: oral health report | 9.4%/yr in dogs, toy breeds 2.5× odds, 46% cleaned; four simulator gaps found vs. published studies |

## Next, in order

| # | Option | Data | Monetization model | Status |
|---|---|---|---|---|
| 1 | **Oral health insights report**: periodontal disease by size, breed, age; detection bias; treatment gap; clinic benchmarks; compared with Banfield (US) and VetCompass (UK) published figures | Platform data + breed size taxonomy (Kaggle breed-traits data optional) | Research & Insights for pet food and dental product makers; clinic benchmarks | **Done** ([report](oral_health_report.md)) |
| 2 | **Antimicrobial resistance (AMR) module**: dog E. coli and S. pseudintermedius antibiograms and trends; clinic prescribing benchmarks | FDA NARMS animal pathogen data (Vet-LIRN, 2017–2024) + simulated prescribing | Agency feeds; stewardship scorecards; insight for antibiotic and diagnostics makers | **Done** ([results](amr_results.md)); stewardship scorecards wait for option 3 |
| 3 | **Simulator extension**: prescriptions, procedures and anesthesia, longitudinal lab panels, clinical narratives with misspellings and negation, microchip IDs; plus calibration fixes from option 1 (small-breed dental risk, obesity link, detection at wellness exams, clinic-level diagnostic differences); antibiotic prescribing matched to the real NARMS antibiograms for stewardship scorecards | — | Enables 4–6 and AMR scorecards | **Done** ([results](simulator_extension_results.md)); stewardship scorecard sample built |
| 4 | **Model A2: EHR drug-safety cohorts** (signal validation; absolute incidence and relative risk vs. comparator) | Synthetic EHRs; PetEVAL text check | Signal validation studies for manufacturers and regulators | **Done** ([results](model_a2_results.md)); PetEVAL check: seizure dictionary precision 30% on real notes |
| 5 | **Clinic quality benchmarks**: risk-adjusted anesthesia mortality and complications, funnel plots | Synthetic EHRs | Scorecards for clinic groups, PE due diligence, insurers | **Done** ([results](clinic_benchmarks_results.md)) |
| 6 | **Feline CKD early prediction** (RenalTech-style: six lab values + age, two time points, 24-month horizon) | Synthetic labs; Dog Aging Project labs when access arrives | Embedded in a lab partner's results; renal diet and drug care pathways | Planned |
| 7 | **Productization**: Pet Health Index, scoring API, partner portal, DuckLake versioned releases, business case | All of the above | All four monetization models | **Done** ([results](productization_results.md)); DuckLake path to be run locally |

## Later or parked

| Item | Why parked |
|---|---|
| Model B: breed-condition risk on real data | Waiting for Dog Aging Project access |
| Wearables channel for early warning (activity collars) | Better signal source than daycare attendance; needs a data partner or sensor dataset (VetDataHub lists a collar accelerometer dataset) |
| Pathology image AI (canine mast cell tumor slides) | Different skill set and very large files |
| Conformal intervals for forecasting; confirm blended model on 2025 data | Small follow-up, fold into productization |

## Timing

Option 1: one working session. Options 2–3: one session each. Options 4–6: one to two sessions each. Option 7: two to three sessions. A "session" here is a block of focused build time like the ones so far, not calendar days.
