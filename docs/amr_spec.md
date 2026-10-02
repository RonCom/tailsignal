# AMR Module Specification (pre-registered)

Written 2026-10-02, before the NARMS animal pathogen file was downloaded or opened.

## Data

FDA NARMS Animal Pathogen Data: isolates collected by Vet-LIRN and NAHLN laboratories, 2017 onward. Primary analysis: dog *E. coli* and dog *Staphylococcus pseudintermedius*. Cattle and swine *Salmonella* are reported descriptively only. Interpretation (susceptible / intermediate / resistant) uses the categories supplied in the file; if only MICs are supplied, CLSI veterinary breakpoints will be documented per drug before analysis.

## Questions and pre-specified tests

| # | Question | Method | Reported as |
|---|---|---|---|
| H9a | How common is resistance to each antimicrobial, by organism and year? | Share resistant with Wilson 95% CIs; antibiogram table (organism × drug × year) | Table and heat map |
| H9b | Is resistance changing over time? | Logistic regression of resistant (0/1) on year, per organism–drug pair with ≥ 100 isolates; Benjamini–Hochberg false discovery rate 5% across pairs | Pairs with a significant trend, direction, odds ratio per year |
| H9c | How common is multidrug resistance? | Share of isolates resistant to ≥ 3 antimicrobial classes (class map documented before analysis) | By organism and year |
| H9d | Does resistance differ by region or specimen source (if the file has these fields)? | Same as H9b with region/source terms | Exploratory if the field is sparse |

Pre-registered expectation (to be confirmed or refuted, not assumed): methicillin resistance in *S. pseudintermedius* (oxacillin as the marker) is present at a clinically meaningful level and is not declining.

## Products this feeds

- **Regional dog antibiograms** for clinics (embedded analytics): "which first-line antibiotic is still likely to work for a dog UTI in your region."
- **Stewardship scorecards** once simulated prescribing exists (roadmap option 3): a clinic's antibiotic choices compared with the local antibiogram.
- **Trend feed** for agencies, antibiotic makers, and diagnostics companies.

## Limits stated up front

Vet-LIRN isolates come from diagnostic submissions, which over-represent hard-to-treat infections; percentages describe submitted isolates, not all infections in dogs.

## Amendment 2026-10-02: drug classes and panel rule (set after seeing the file's drug list and panel sizes, before any resistance result was computed)

The file has 533,831 rows (one per isolate × drug), all from dogs: 12,958 *E. coli* and 13,438 *S. pseudintermedius* isolates, plus small numbers of *Klebsiella* and *Salmonella*; 30 states; 2017–2024; collection source "UTI" or "other tissues/body sites"; interpretation (Susceptible / Resistant / Non-Interpretable) supplied by FDA. Non-interpretable results are excluded.

**Class map** for multidrug resistance (MDR):

| Class | Drugs |
|---|---|
| Aminoglycosides | amikacin, gentamicin, neomycin, spectinomycin, streptomycin, tobramycin |
| Penicillins | amoxicillin, ampicillin, penicillin, benzylpenicillin, piperacillin, ticarcillin |
| Anti-staphylococcal penicillins (methicillin marker) | oxacillin, oxacillin + 2% NaCl |
| β-lactam + inhibitor | amoxicillin/clavulanic acid (both entries), ampicillin/sulbactam, piperacillin/tazobactam, ticarcillin/clavulanic acid (both entries) |
| Cephalosporins | cefazolin, cephalexin, cephalothin, cefuroxime, cefoxitin, cefotetan, ceforanide, cefpodoxime, ceftazidime, ceftiofur, ceftriaxone, cefovecin, cefepime |
| Carbapenems | imipenem, meropenem |
| Monobactams | aztreonam |
| Fluoroquinolones | ciprofloxacin, danofloxacin, enrofloxacin, gatifloxacin, levofloxacin, marbofloxacin, moxifloxacin, ofloxacin, orbifloxacin, pradofloxacin |
| Tetracyclines | chlortetracycline, doxycycline, minocycline, oxytetracycline, tetracycline |
| Macrolides | azithromycin, clarithromycin, erythromycin, gamithromycin, tildipirosin, tilmicosin, tulathromycin, tylosin |
| Lincosamides | clindamycin, pirlimycin |
| Phenicols | chloramphenicol, florfenicol |
| Folate pathway inhibitors | trimethoprim/sulfamethoxazole, sulphadimethoxine, sulphathiazole |
| Others (one class each) | nitrofurantoin, vancomycin, rifampin, polymyxin-B, fusidic acid, novobiocin (incl. penicillin/novobiocin), tiamulin, bacitracin |

**Core panel rule.** Testing panels can change across years, which would make MDR trends reflect panel size rather than resistance. MDR is therefore counted only over classes tested on at least 90% of that organism's isolates in every year.

**MRSP.** *S. pseudintermedius* resistant to oxacillin (either oxacillin entry).

**Antibiogram reporting threshold.** Cells with fewer than 30 isolates are not reported, following CLSI M39 guidance for cumulative antibiograms.

**Intrinsic resistance excluded from MDR counts.** *E. coli*: macrolides, lincosamides, vancomycin, fusidic acid, tiamulin, bacitracin, novobiocin. *S. pseudintermedius*: polymyxin-B, aztreonam. These organisms are resistant to these drugs by nature, so counting them would inflate MDR (following the Magiorakos et al. 2012 MDR convention of excluding intrinsic resistance).

## Amendment 2026-10-02 (after first results): three biases found in the raw percentages

The first run (pre-registered H9b, pooled across sources) produced implausible patterns: *E. coli* amoxicillin-clavulanate ~100% "resistant" from tissue sites but ~1% from urine; doxycycline ~100% "resistant" in *E. coli*; marbofloxacin and chloramphenicol 95–98% "resistant" in *S. pseudintermedius*. Inspection showed three causes, none of them biology:

1. **Site-specific breakpoints.** FDA's interpretations use different susceptibility cut-offs for urine and for other sites (e.g., amoxicillin-clavulanate in *E. coli*: susceptible up to an MIC of 8–16 in urine, up to 0.25–0.5 elsewhere). Pooling sources mixes cut-offs, so a shift in the UTI share looks like a resistance trend.
2. **Breakpoints below the wild-type population.** Where nearly every isolate is "resistant" at a site, the label means "drug not suitable at this site at standard doses," not acquired resistance.
3. **Selective (cascade) testing.** Some second-line drugs are tested only on a minority of isolates, typically ones already resistant to first-line drugs, so their percentages describe a pre-selected group.

Breakpoints were checked and are stable across years within each organism × drug × site, so year-on-year comparisons within a site are valid.

**Revised rules (applied in addition to reporting the pre-registered pooled result):**
- Trends, antibiograms, and MDR are computed **within site** (UTI vs. other sites).
- An organism × drug × site combination is **eligible** only if the drug was tested on ≥ 90% of that organism's isolates from that site in every year, and fewer than 95% of isolates are classed resistant overall.
- Region adds a "Canada" group for isolates from Canadian laboratories (previously unmapped).
- "Oxacillin" and "Oxacillin + 2% NaCl" are the same drug tested by two methods; they are merged into one oxacillin result per isolate (resistant if either is resistant), consistent with the MRSP definition above.
