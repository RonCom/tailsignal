# Model A: Exposure Denominators for Isoxazoline Reports

Pre-registered 2026-10-02, before any neurologic or convulsion count was computed for this analysis. Code: `src/tailsignal/models/pv_exposure.py`. Results: `docs/model_a_exposure_results.md`.

## Why

Model A ranks drug–event pairs by disproportionality: how much more often a reaction appears in a drug's reports than in reports for other drugs. That ranking can't say how often a reaction happens per dog treated, because FDA reports have no count of dogs treated. A rate needs a denominator.

## What public denominators exist

A search on 2026-10-02 found dose counts for one isoxazoline only.

| Product | Figure | Source |
|---|---|---|
| Fluralaner (Bravecto) | About 41.6 million doses distributed worldwide, February 2014 to December 2016, about 18 million of them in the EU | [EMA, 17 August 2017](https://www.ema.europa.eu/en/news/tick-flea-control-agent-bravecto-continues-be-acceptably-safe-use) |
| Fluralaner (Bravecto) | More than 350 million doses in 100 countries, stated 10 July 2025 | [MSD Animal Health press release](https://www.msd-animal-health.com/2025/07/10/fda-approves-bravecto-quantum-fluralaner-for-extended-release-injectable-suspension-from-msd-animal-health/) |
| Afoxolaner, sarolaner, lotilaner | None published | Palmieri et al. (2020) also note that sales volumes aren't public |

The EMA notice also states that convulsions occur in fewer than 1 in 10,000 dogs treated, and that 2,144 EU dogs had suspected side effects reported electronically (February 2014 to 15 August 2017).

Already known before this spec: FDA holds about 12,000 US dog reports naming fluralaner received 2014–2016 (counted while checking the report-ID country prefix). No reaction-level counts were run.

## Data

- openFDA dog reports, product-defect reports dropped, built with `pharmacovigilance.load()`.
- US reports only: report ID prefix `USA`.
- A report counts for a drug if any listed ingredient matches it.
- Event sets: any report; the neurologic composite from `model_a_spec.md`; convulsions (VeDDRA terms matching `convul|seiz`).

## Denominators

US doses aren't published. Fluralaner's US doses for 2014–2016 are at most the non-EU total, 41.6M − 18M = 23.6M. Dividing by 23.6M gives a **lower bound** on the US reporting rate. Two scenarios give point estimates: the US took 75% or 50% of non-EU doses.

Secondary: US reports 2014–2024 divided by 350M (global doses by July 2025, so at least the doses distributed through 2024) is also a lower bound on the US rate.

Rates are per 10,000 doses. A Bravecto chew lasts 12 weeks, so one dog treated for a year gets about 4 doses. A per-dose rate times about 4 approximates a per-dog-year rate.

## Questions and predictions

**Q1. Fluralaner US reporting rates, 2014–2016.** Report the lower bound and the two scenarios for any report, neurologic and convulsion.

- P1: the convulsion lower bound is below 1 per 10,000 doses, consistent with the EMA label frequency.
- P2: the any-report lower bound is at least twice the EU electronic reporting rate (2,144 dogs / 18M doses = 1.19 per 10,000).

**Q2. Break-even doses for the other isoxazolines.** For afoxolaner and sarolaner, count US neurologic reports from launch through 2016 and compute the US doses each would need for its neurologic reporting rate to equal fluralaner's lower-bound rate. Lotilaner launched in 2018 and gets the same calculation for 2018–2020, flagged as a different window. No prediction: the actual doses aren't public, so this table states what a buyer would have to supply.

**Q3. Reporting after the FDA alert.** Compare fluralaner's secondary 2014–2024 lower bound for neurologic reports with the 2014–2016 lower bound. No prediction; the 2018 alert is expected to raise later reporting, and the global denominator makes the comparison loose.

## What this can't show

- A reporting rate isn't an incidence rate: most adverse events go unreported, and report counts rose after publicity.
- Doses aren't dogs. The per-dog conversion assumes on-label 12-week dosing.
- Reports name every product a dog received; a report naming fluralaner isn't evidence that fluralaner caused the event.
