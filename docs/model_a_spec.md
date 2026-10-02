# Model A: Breed-Stratified Hierarchical Pharmacovigilance

Pre-registered specification, written 2026-10-01 before the full openFDA download. Code: `src/tailsignal/models/pharmacovigilance.py`.

## Question

Can a breed-aware Bayesian method find drug safety signals in FDA veterinary adverse-event reports earlier, and find breed-specific signals that all-dog analysis dilutes, without raising the false-signal rate?

## Data

- openFDA Animal & Veterinary adverse-event reports, all partitions, deduplicated on `unique_aer_id_number`.
- Species analyzed separately: dogs (primary), cats (secondary).
- Drug unit: individual active ingredient (combination products split, e.g. "Ivermectin, Pyrantel" → ivermectin, pyrantel), plus pre-defined drug classes.
- Event unit: VeDDRA reaction term, plus the composite **neurologic** event below.
- Counts are reports, not animals.

## Definitions (fixed before analysis)

**Drug classes**

| Class | Ingredients |
|---|---|
| Isoxazolines | fluralaner, afoxolaner, sarolaner, lotilaner |
| Macrocyclic lactones | ivermectin, milbemycin (incl. milbemycin oxime), moxidectin, selamectin, eprinomectin, doramectin |

**Neurologic composite.** Any reaction term matching (case-insensitive): convulsion, seizure, ataxia, tremor, trembling, twitching, fasciculation, mydriasis, blindness, coma (whole word), stupor, disorientation, nystagmus, paresis, paralysis (excluding laryngeal and facial), hyperaesthesia, circling, "neurological signs". Excluded: lethargy, recumbency, head tilt (ear disorder), glaucoma, eye disorder.

**Breed strata (dogs).** Using the WSU Veterinary Clinical Pharmacology Lab MDR1 frequency list:
- `mdr1_high`: Collie (not Border), Australian Shepherd (incl. miniature), McNab, Silken Windhound, Shetland Sheepdog, English Shepherd, Chinook. Whippets go to `other_purebred` because FDA reports do not distinguish long-haired whippets. A crossbred dog with any `mdr1_high` breed component is assigned `mdr1_high`.
- `mdr1_low`: German Shepherd, Old English Sheepdog, Border Collie
- `other_purebred`: any other identified breed
- `mixed_unknown`: crossbred, mixed, unknown, or missing

## Methods compared

| Method | Description |
|---|---|
| PRR (Evans) | Signal if PRR ≥ 2, χ² ≥ 4, n ≥ 3 |
| ROR | Signal if lower 95% CI of ROR > 1 and n ≥ 3 |
| MGPS | DuMouchel two-gamma mixture prior fit to all drug–event cells; signal if EB05 ≥ 2. Expected counts stratified by report year. |
| Stratified MGPS | Separate MGPS per breed stratum (shrinks toward 1) |
| **Hierarchical (ours)** | Stratum cell λ_ijs ~ Gamma(α, α/μ_ij), where μ_ij is the all-dog MGPS posterior mean for that drug–event pair and α is estimated by marginal likelihood across all stratum cells. Shrinks a breed estimate toward the all-dog estimate, not toward 1. Breed-specific excess = posterior of λ_ijs / μ_ij. Signal if EB05 ≥ 2. |

**Breed-specific excess** (is the risk higher in this breed stratum than in dogs overall?):
- Unpooled: interaction ROR (stratum vs. all other dogs) lower 95% CI > 1 and n ≥ 3.
- Hierarchical: 5th percentile of the posterior of λ_ijs / μ_ij > 1 and n ≥ 3.

## Validation

1. **Time to signal (isoxazolines × neurologic, dogs and cats).** Re-run every method on reports received through the end of each quarter, 2013 Q1 to 2019 Q4. Record the first quarter each method signals and the lead time before the FDA alert (2018-09-20).
2. **Breed-specific signal (macrocyclic lactones × neurologic).** Compare stratum estimates for `mdr1_high` vs. `other_purebred`. Primary metric: posterior probability that the `mdr1_high` rate ratio exceeds the `other_purebred` ratio; secondary: whether each method flags the `mdr1_high` cell and not the `other_purebred` cell.
3. **False-signal rate (permutation null).** Shuffle event sets across reports within report year (breaks drug–event association, keeps marginals), and separately shuffle breed strata across reports within year. Re-run all methods 20 times; false-signal rate = signals per 1,000 cells tested. Methods are compared at their default thresholds and at thresholds matched to the same false-signal rate.
4. **Extended reference set** (`docs/model_a_reference_set.csv`): label-listed reactions for common products, used for recall at matched false-signal rate. Each row must be verified against the product label before it is used; unverified rows are excluded.

## Known limitations

- Spontaneous reports: no denominator of exposed animals, reporting is stimulated by publicity (the 2018 alert itself increased reports), and duplicates across manufacturers are possible.
- Breed is often missing; mixed/unknown is the largest stratum.
- MDR1 status is inferred from breed, not genotype.
