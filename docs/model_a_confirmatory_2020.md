# Model A Confirmatory Analysis: Reports Received 2020 Onward

Pre-registered 2026-10-02, before any analysis of the 2020+ period on its own. The 2013–2019 results ([`model_a_results.md`](model_a_results.md)) were used to choose the event definition below; this analysis checks whether those findings hold in data that played no part in choosing it.

## Data

openFDA dog and cat reports with receive date on or after 2020-01-01, same exclusions as the primary analysis (product-defect reports dropped; lack-of-effectiveness reports kept). All priors are refit on this period alone.

## Event definition (fixed now)

**Seizure/tremor composite:** reaction terms matching seizure, convulsion, tremor, or twitching (case-insensitive). Excludes trembling, ataxia, and the other terms in the original neurologic composite, which were not elevated for isoxazolines in 2013–2019.

## Predictions

| # | Prediction | Pass criterion |
|---|---|---|
| P1 | Dogs: isoxazolines (class) × seizure/tremor | EB05 ≥ 2 |
| P2 | Dogs: each isoxazoline with ≥ 100 reports in the period | Seizure/tremor ranks in the top 10 of that product's reaction list by EB05 (ranked against single terms with n ≥ 3) |
| P3 | Cats: isoxazolines (class) × seizure/tremor | EB05 ≥ 2 |
| P4 | Dogs: macrocyclic lactones × original neurologic composite, MDR1-high breeds | Hierarchical ratio 5th percentile > 1 (breed-specific excess) |
| P5 | Dogs: MGPS false-signal rate (5 permutation replicates) | ≤ 1 per 1,000 cells |

Each prediction is reported as pass or fail. No thresholds or definitions will change after the run.
