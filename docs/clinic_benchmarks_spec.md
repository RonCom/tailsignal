# Clinic Quality Benchmarks: Specification (pre-registered)

Written 2026-10-02, before the benchmark code was run. Data: the clinical EHR layer at the actual network size (1×) and the 10× scenario. Both use the same seed, so the nine clinics carry identical planted effects at both sizes; 10× differs only in volume. Code: `src/tailsignal/models/clinic_benchmarks.py`. Outputs: `reports/clinic_benchmarks/`.

## Measures

| Domain | Measure | Risk adjustment |
|---|---|---|
| Anesthesia | Complication within the anesthetic event (any recorded complication or death) | Logistic model: ASA group, emergency, brachycephalic breed, species, procedure, age band, dog under 5 kg |
| Anesthesia | Death within 48 hours | Same model; network-level rates compared with CEPSAF |
| Dental | Recorded periodontal disease (grade ≥ 2) at wellness exams | Logistic model: species, size, age band, overweight (BCS ≥ 6) |
| Stewardship | Culture before treatment (UTI), first-line choice, critically important antibiotic as first choice, metronidazole for acute diarrhea, antibiotics with dental cleanings | None (process measures with guideline direction) |

## Methods

- Observed/expected (O/E) per clinic with exact Poisson 95% and 99.8% funnel limits.
- Empirical Bayes shrinkage of log O/E toward the network mean (between-clinic variance by method of moments), with 95% intervals.
- Rank uncertainty: 2,000 draws from each clinic's approximate posterior; 90% interval of rank.
- Stewardship composite: mean of each measure's z-score across clinics, signed so higher = better stewardship.
- Power: per-clinic procedure volume needed to detect a doubling of death risk at 80% power.

## Scoring against planted truth (simulator)

| Check | Pass rule |
|---|---|
| Complications: shrunken O/E ranks clinics like the planted effect | Spearman ≥ 0.7 at 1× and ≥ 0.8 at 10× |
| Shrinkage helps | Mean squared error of shrunken log O/E vs planted log-OR lower than raw log O/E, at 1× |
| Mortality is not benchmarkable at 1× | No clinic flagged outside 99.8% limits; power to detect OR 2 < 50% |
| Mortality at 10× | Report whether the planted OR 2 clinic (PHL-VET3) is flagged; pre-stated expectation: still underpowered |
| Dental | Both planted low-charting clinics flagged below 95% limits at 1× |
| Stewardship composite | Spearman with planted composite ≥ 0.8 |

## Use

Scorecards for clinic groups (internal improvement), private-equity due diligence on clinic acquisitions, and insurers. The report states which measures are reliable at which clinic volume.

## Amendment 2026-10-02 (after first results)

- **Shrinkage target.** The pre-registered check compared log O/E with the planted log odds ratio. Those are on different scales: an odds ratio of 2 for a 9% complication means an O/E of about 1.4. So shrinking toward the mean always "moves away" from the planted log OR. The revised check compares against each clinic's true O/E, computed from the simulator's per-procedure probabilities. Both are reported. The shrinkage check applies at 1× only, as specified; at 10×, reliability is ~0.97 and shrinkage changes almost nothing.
- **Funnel limits** use Spiegelhalter's continuous interpolation of exact Poisson limits, so limits are smooth in the expected count.
- **Pre-stated expectation wrong.** At 10× (about 5,600 procedures per clinic over four years), the planted death outlier is detected; the expectation that it would still be underpowered was wrong.
