# Model A: Exposure Denominators — Results

Spec: [`model_a_exposure_spec.md`](model_a_exposure_spec.md) (pre-registered). Code: `src/tailsignal/models/pv_exposure.py`. Output: `reports/model_a/exposure/exposure.json`.

Model A ranks drug–reaction pairs by how over-represented a reaction is in a drug's reports. Turning that into a rate per dog treated needs dose counts, and only one isoxazoline has published any: fluralaner, about 41.6 million doses worldwide from February 2014 to December 2016, 18 million of them in the EU (EMA, 2017). The US got at most the other 23.6 million, so dividing US reports by 23.6 million gives a lower bound on the US reporting rate.

## Q1. Fluralaner US reporting rates, 2014–2016

US dog reports naming fluralaner: 11,939 in total, 713 with a neurologic sign, 376 with a convulsion.

| US doses assumed | Any report per 10,000 doses | Neurologic | Convulsion |
|---|---|---|---|
| 23.6M (all non-EU doses; lower bound on rates) | 5.06 | 0.30 | 0.16 |
| 17.7M (75% of non-EU) | 6.75 | 0.40 | 0.21 |
| 11.8M (50% of non-EU) | 10.12 | 0.60 | 0.32 |

| Prediction | Result | Verdict |
|---|---|---|
| P1: convulsion lower bound below 1 per 10,000 doses (EMA label: fewer than 1 in 10,000 dogs treated) | 0.16 | Pass |
| P2: any-report lower bound at least twice the EU electronic rate (1.19 per 10,000) | 5.06, 4.2× the EU rate | Pass |

P1 passes per dose. A dog treated all year gets about four 12-week doses, so the per-dog-year convulsion reporting rate is about 0.64 per 10,000 at the lower bound and 1.27 per 10,000 if the US took half the non-EU doses. The second figure is above the EMA's "fewer than 1 in 10,000" label frequency, so whether US reports agree with the EU label depends on a US sales figure that isn't public.

US owners and vets report to FDA at four or more times the rate EU dogs were reported to the EMA's electronic system. Comparing raw report counts between FDA and EMA without that adjustment would make fluralaner look four times as risky in the US.

## Q2. Break-even doses for the other isoxazolines

US doses each drug would need for its neurologic reporting rate to equal fluralaner's 2014–2016 lower bound (0.30 per 10,000 doses):

| Drug | Window | US reports | Neurologic | Convulsion | Break-even US doses |
|---|---|---|---|---|---|
| Fluralaner | 2014–2016 | 11,939 | 713 | 376 | 23.6M (reference) |
| Afoxolaner | 2014–2016 | 11,555 | 1,351 | 867 | 44.7M |
| Sarolaner | 2014–2016 (launched 2016) | 439 | 138 | 53 | 4.6M |
| Lotilaner | 2018–2020 (launched 2018; not comparable) | 3,335 | 455 | 258 | 15.1M |

Afoxolaner (NexGard) is a monthly chew. If it sold fewer than 44.7 million US doses in 2014–2016, its neurologic reporting rate per dose was higher than fluralaner's; if it sold more, lower. Neurologic signs appear in 11.7% of afoxolaner reports against 6.0% for fluralaner, which is what a proportional method sees. A manufacturer's monthly US sales would settle the comparison.

## Q3. Reporting after the FDA alert

Through 2024, US reports naming fluralaner reach 57,447 (5,215 neurologic). Divided by the 350 million global doses MSD reported by July 2025, the neurologic lower bound is 0.15 per 10,000 doses, half the 2014–2016 bound. The later denominator is global and includes growth outside the US, so this comparison can't show whether reporting per US dose rose after the 2018 alert.

## What it means for the product

- Proportional signals answer "is this reaction over-represented for this drug?" They can't rank isoxazolines on risk per dog.
- A rate needs doses. Public dose data covers one product, worldwide, for two dates. A manufacturer's US sales, or prescriptions from partner clinics (Model A2), supply the denominator; that makes an exposure-adjusted safety report a data-partnership product, sold with the sales data the buyer already holds.
- Model A's roadmap item "exposure denominators" is done for the one product with public data and stays open for the rest.

## Limits

- A reporting rate isn't incidence; most events go unreported.
- Doses aren't dogs; the per-dog conversion assumes on-label 12-week dosing.
- A report names every product a dog received, so a report naming fluralaner isn't evidence it caused the event. Only 24 US reports from 2014–2016 name two isoxazolines, so the drug counts barely overlap.

## Sources

- European Medicines Agency (17 August 2017). [Tick and flea control agent Bravecto continues to be acceptably safe to use](https://www.ema.europa.eu/en/news/tick-flea-control-agent-bravecto-continues-be-acceptably-safe-use).
- MSD Animal Health (10 July 2025). [FDA approves Bravecto Quantum](https://www.msd-animal-health.com/2025/07/10/fda-approves-bravecto-quantum-fluralaner-for-extended-release-injectable-suspension-from-msd-animal-health/) ("more than 350 million doses distributed in 100 countries").
- Palmieri V. et al. (2020). [Survey of canine use and safety of isoxazoline parasiticides](https://pmc.ncbi.nlm.nih.gov/articles/PMC7738705). *Veterinary Medicine and Science* 6:933–945.
