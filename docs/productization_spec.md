# Productization: Specification

Written 2026-10-02, before the product code was built. Code: `src/tailsignal/products/` and `src/tailsignal/api/`. Business case: a separate spreadsheet.

## Products

| Product | Content | Source | Buyer |
|---|---|---|---|
| **Pet Health Index** | Condition-by-condition index (network average = 100) for each species × breed group × market × year, plus a composite **illness-cost index** weighting conditions by typical treatment cost | `product.product_condition_prevalence` (already k-suppressed) | Insurers (pricing), pet food and health brands (targeting) |
| **Drug-safety signals** | Drug–reaction pairs flagged by the MGPS model (EB05 ≥ 2, n ≥ 3), and breed-stratum excesses flagged by the hierarchical model | Model A outputs (real FDA data) | Manufacturers, regulators |
| **Regional antibiogram** | Percent susceptible by region, organism, site and drug, 2022–2024; cells < 30 isolates withheld | AMR module (real FDA NARMS data) | Clinics, clinic groups |
| **Clinic scorecards** | Risk-adjusted complications, deaths, dental charting, stewardship | Clinic benchmarks | Clinic groups (embedded), PE due diligence |
| **Service benchmarks** | Monthly revenue per active pet by location and market percentile | `product.product_service_benchmark` | Partners (embedded) |

## Pet Health Index method

- For each condition and species-year, the network prevalence is the reference (index 100).
- Cell prevalence is shrunk toward the reference with a beta-binomial prior whose strength is estimated per condition (method of moments), so small cells do not swing.
- Index = 100 × shrunk prevalence ÷ reference; a 90% interval is reported.
- Composite illness-cost index = cost-weighted mean of a cell's condition indexes, weights = each condition's share of expected treatment cost in the network (simulator price midpoints; to be replaced by partner invoice data).
- Cells suppressed upstream (fewer than 10 pets seen, or 1–9 cases) are never released.

## Versioned releases

- Each release writes every product table as one snapshot of a **DuckLake** catalog (`data/lake/`), and records version, timestamp, row counts, and content hashes in a `release_log` table. Any past release can be read back exactly (time travel).
- Where the DuckLake extension cannot be installed, the same release is written as versioned Parquet files plus a manifest (`data/releases/vN/`). Both paths are tested.
- A release diff lists added, removed and changed rows per product versus the previous release.

## Scoring API

FastAPI service reading the latest (or a pinned) release:

| Endpoint | Returns | Access |
|---|---|---|
| `GET /v1/releases` | Release history | Any key |
| `GET /v1/health-index` | Index rows filtered by species, breed group, market, year | Data-product keys |
| `GET /v1/drug-signals` | Signals filtered by drug, event, breed stratum | Pharma keys |
| `GET /v1/antibiogram` | Regional susceptibility | Clinic and data-product keys |
| `GET /v1/clinics/{clinic}/scorecard` | One clinic's scorecard plus network benchmarks | That clinic's own key only |
| `GET /portal/{clinic}` | The same scorecard as a partner-portal page | That clinic's own key only |

Every successful call is metered (key, endpoint, rows returned) for usage-based billing.

## Acceptance checks

1. No released Health Index cell comes from a suppressed upstream cell; every released cell has ≥ 10 pets.
2. Index values average about 100 across cells within each species-year and condition (pet-weighted mean within 100 ± 5).
3. A release can be read back by version and matches its recorded hashes.
4. Releasing twice with unchanged inputs produces identical hashes and an empty diff.
5. API: a clinic key cannot read another clinic's scorecard (HTTP 403); unknown keys get 401; every successful call is metered.
