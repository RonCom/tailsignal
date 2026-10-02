# Clinic Quality Benchmarks — Results

Risk-adjusted scorecards for the nine simulated clinics, built from routine EHR data: anesthesia outcomes, dental charting, and antibiotic stewardship. Spec and amendment: [`clinic_benchmarks_spec.md`](clinic_benchmarks_spec.md). Code: `src/tailsignal/models/clinic_benchmarks.py`. Outputs: `reports/clinic_benchmarks/{1x,10x}/` (scorecard, funnel tables, charts).

![Benchmarks, actual network](../reports/clinic_benchmarks/1x/benchmarks.png)

## Headlines

1. **Complication rates separate clinics reliably, even at the current size.** About 555 anesthetics per clinic over four years is enough. Risk-adjusted observed/expected (O/E) ranks clinics almost exactly as the planted quality differences do (rank correlation 0.97). The two clinics with planted high complication risk are flagged above expected (AUS-VET1, MSP-VET3), and the three with low risk below (MSP-VET1, MSP-VET2, PHL-VET2). There are no flags in the wrong direction.
2. **Death rates cannot be benchmarked per clinic at this size.** Each clinic expects 0.7–1.8 deaths in four years. A clinic with double the death risk would be detected 13% of the time. The planted high-mortality clinic (PHL-VET3: 5 deaths vs 1.6 expected) did cross the 95% line, but that was luck at this power. The statistical model agrees: estimated between-clinic variation is zero, so every clinic's shrunken death estimate collapses to the network average.
3. **With ~10× the volume, deaths become benchmarkable.** About 5,600 procedures per clinic: PHL-VET3 has 30 deaths vs 16.2 expected and is flagged beyond the 99.8% limit; average power is 81%. The threshold is roughly **4,750–5,250 procedures per clinic**, about a large hospital's four-year volume or a group of 8–10 typical clinics.
4. **Under-charting of dental disease is visible.** Both clinics planted to chart less thoroughly record about two thirds of the expected periodontal disease (O/E 0.65 and 0.57) and are flagged. Rank correlation with planted charting thoroughness is 0.96. The measure shows which clinic finds less disease, which affects revenue (dental procedures) and any prevalence statistic sold from the data; it does not show which clinic has sicker pets.
5. **Stewardship scores match planted prescribing behavior** (rank correlation 0.97). The weakest clinic (MSP-VET1) cultures before treating only 18% of urinary infections and uses critically important antibiotics as first choice in 32% of cases. The strongest (AUS-VET1) cultures 72%.

## Actual-network scorecard (selected columns)

| Clinic | Procedures | Complications O/E (95% interval) | Rank range (90%) | Deaths obs / exp | Dental O/E | Stewardship rank |
|---|---|---|---|---|---|---|
| AUS-VET1 | 577 | **1.34** (1.07–1.67) ▲ | 6–9 | 1 / 1.2 | 1.11 ▲ | 1 |
| AUS-VET2 | 566 | 1.04 (0.81–1.33) | 3–8 | 2 / 1.2 | **0.65** ▼ | 5 |
| AUS-VET3 | 634 | 1.02 (0.81–1.29) | 4–7 | 0 / 1.7 | 1.19 ▲ | 6 |
| MSP-VET1 | 386 | **0.56** (0.37–0.84) ▼ | 1–3 | 0 / 1.0 | 1.00 | 9 |
| MSP-VET2 | 380 | **0.63** (0.43–0.92) ▼ | 1–3 | 1 / 1.0 | 0.97 | 8 |
| MSP-VET3 | 364 | **1.34** (1.03–1.76) ▲ | 6–9 | 0 / 0.7 | **0.57** ▼ | 7 |
| PHL-VET1 | 726 | 1.00 (0.80–1.25) | 3–7 | 0 / 1.8 | 1.32 ▲ | 3 |
| PHL-VET2 | 677 | **0.76** (0.59–0.99) ▼ | 1–4 | 3 / 1.8 | 1.02 | 2 |
| PHL-VET3 | 685 | 1.22 (0.98–1.50) | 5–9 | **5 / 1.6** ▲ (95% only) | 0.97 | 4 |

Complication O/E is shrunk toward the network mean; ▲/▼ = outside 95% funnel limits. Lower complication rank = better.

**Read the rank ranges before the ranks.** Six of nine clinics have 90% rank ranges covering four or more positions. A league table that prints a single rank overstates what the data can tell apart.

## Checks against planted truth

| Check | 1× | 10× |
|---|---|---|
| Complication ranking (Spearman ≥ 0.7 / 0.8) | 0.97 ✓ | 0.98 ✓ |
| Shrinkage improves accuracy (revised: vs true O/E) | Complications error 0.0092 → 0.0053; deaths 0.49 → 0.06 ✓ | n/a (reliability ~0.97) |
| Shrinkage vs planted log OR (pre-registered; scale mismatch, see amendment) | ✗ | n/a |
| Mortality not benchmarkable (no 99.8% flags, power < 50%) | ✓ (power 13%) | Detected beyond 99.8%, power 81%; expectation of "still underpowered" was wrong |
| Both under-charting clinics flagged | ✓ | ✓ |
| Stewardship composite (Spearman ≥ 0.8) | 0.97 ✓ | 0.98 ✓ |

## Commercial use

| Buyer | Product | Rule from these results |
|---|---|---|
| Clinic groups | Quarterly scorecard: complications, dental charting, stewardship, with funnel plots and rank ranges | Report complications per clinic; report deaths only pooled, or per clinic once volume passes ~5,000 procedures |
| PE due diligence on clinic acquisitions | Target-vs-network benchmark from 2–4 years of records | Complication and charting gaps are measurable at single-clinic volume; mortality claims need the acquirer's whole network |
| Insurers | Network quality tiers | Use shrunken estimates and rank ranges, not raw league tables |

Dental under-charting is also a revenue finding. If the two low-charting clinics recorded disease at the network rate, they would identify roughly 55–75% more periodontal cases, each a candidate for a cleaning.

## Limits

- All effects are simulated. The planted clinic differences are assumptions chosen to test whether the methods recover them.
- Risk adjustment uses only recorded fields (ASA, emergency, breed, size, age, weight). Real clinics differ in case mix in ways records miss, so real benchmarks need peer review of outliers before any conclusion.
