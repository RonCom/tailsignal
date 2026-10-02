# Productization — Results

Spec: [`productization_spec.md`](productization_spec.md). Code: `src/tailsignal/products/` (Health Index, releases), `src/tailsignal/api/app.py` (API and partner portal), `scripts/build_business_case.py`. Business case: `docs/business_case/TailSignal_Business_Case.xlsx`.

## What ships in a release

| Product | Rows (release v1) | Built from |
|---|---|---|
| Pet Health Index, by condition | 695 cells | k-suppressed prevalence mart |
| Pet Health Index, illness-cost composite | 139 cells | Condition index, cost-weighted |
| Drug-safety signals (all dogs) | 53,656 pairs | Model A, real FDA reports |
| Drug-safety signals by breed group | 331 excesses | Model A hierarchical model |
| Regional antibiogram | 194 cells | FDA NARMS, 2022–2024, ≥ 30 isolates, eligible drugs only |
| Clinic scorecards | 9 clinics | Clinic benchmarks |
| Service benchmarks | 1,262 location-months | Partner service data |

All five acceptance checks pass:

| Check | Result |
|---|---|
| No suppressed or under-10-pet cell is released | ✓ |
| Index averages ~100 within each species-year-condition | ✓ (pet-weighted means 99.2–100.2) |
| A release reads back by version and matches its recorded hashes | ✓ |
| An unchanged rebuild produces no new release | ✓ |
| A clinic key cannot read another clinic's scorecard; unknown keys rejected; successful calls metered | ✓ (unit tests) |

## Pet Health Index: how to read it

100 = network average for that species, condition and year. Toy-breed dogs score **113** on dental disease across markets and years, the highest of any dog breed group. Herding breeds score 95.

The index is deliberately conservative. Small cells are pulled strongly toward 100, so a cell whose raw prevalence is nearly double the network rate (15% vs 8%) reads 117 (90% interval 99–136). This is the right default for pricing (insurers should not reprice on noise), but it understates real differences in small cells. Buyers who want raw rates get them in the same rows.

Only 695 of 1,764 cells (39%) can be released at today's size. Privacy suppression limits this product most, so the business case gates data licenses at 100 clinics.

## Versioned releases

`tailsignal.products.release` builds every product, hashes each table, and publishes a release only if something changed. The release log records version, time, row counts, content hashes and a row-level diff against the previous release. Any past release can be read back exactly.

- **DuckLake** is the primary store: one catalog snapshot per release, with time travel by version. Verified on Windows: release v1 written as DuckLake snapshot 2 and read back with matching hashes. (Drug-safety products were skipped on that machine because the Model A outputs had not been generated there.)
- **Versioned Parquet** (`data/releases/vN/` plus a manifest) is the automatic fallback. Release v1 was published and verified this way.

## API and partner portal

FastAPI service over the latest or a pinned release (`?release=N`). Each key has a role, and each role has entitlements:

| Role | Can read |
|---|---|
| Insurer | Health Index |
| Pharma | Drug-safety signals, Health Index |
| Public health | Antibiogram, drug-safety signals |
| Clinic | Its own scorecard and portal page, antibiogram |
| Admin | Everything |

Every successful call is logged (key, endpoint, rows, release) for usage-based billing. A customer portal at `/app` (`src/tailsignal/api/static/portal.html`) is the front end on the same API: a customer signs in with a key, sees only the products in its plan, and can chart, filter and download each one, with the request, response and billed usage shown for every view. `GET /v1/me` returns a key's role and entitlements; `GET /v1/service-benchmarks` serves the benchmarks product. The same page runs as a static demo over a release sample (`scripts/export_portal_sample.py`) on [the project website](https://roncom.github.io/projects/tailsignal/portal/). The partner portal (`/portal/{clinic}`) is the same scorecard rendered as a page: the clinic's values beside the network median. Demo keys are in `config/api_keys.json`; real keys belong in a secrets store.

## Business case (illustrative assumptions)

Five-year model with three scenarios. Every number is a formula; prices, adoption, headcount and partner ramp are **illustrative assumptions** to be replaced with market quotes. Market context is cited: about 34,000 US veterinary practices, about 30% corporate-owned (AVMA via dvm360), 95 million pet-owning households and $158 billion industry spend in 2025 (APPA).

| | Low | Base | High |
|---|---|---|---|
| Partner clinics, Year 5 | 900 | 1,500 | 1,950 |
| Revenue, Year 5 | $2.65M | $4.25M | $5.26M |
| EBITDA, Year 5 | −$1.59M | −$0.89M | −$0.42M |
| Cumulative EBITDA, Years 1–5 | −$6.87M | −$5.14M | −$3.96M |
| Extra data licenses to break even in Year 5 | 17 | 8 | 4 |

What the model says, under these assumptions:

1. **The business does not break even within five years** in any scenario. The first-pass assumptions are not a viable plan.
2. **Partner incentives are the biggest variable cost.** Each partner clinic brings in about $2,800 a year in revenue at Year 5 but costs $1,000 in incentives. The incentive has to buy data access cheaply, through free scorecards rather than cash, or the network grows at a loss.
3. **Data licenses are the swing line.** Eight more licenses at $120,000 would break even in Year 5 (Base). Licenses unlock only once privacy suppression falls, which needs about 100 clinics.
4. **Validation studies arrive late.** Common side-effect studies unlock in Year 4 and rare ones in Year 5 (Base), set by the scale requirements found in Model A2. In the Base case they are 29% of Year-5 revenue ($1.25M of $4.25M).

## Owned-network version: Destination Pet

`docs/business_case/DestinationPet_Data_Business_Case.xlsx` (built by `scripts/build_destination_pet_case.py`) reworks the case for an operator that owns every location, so there are no partner data incentives. Value comes mainly from running the business better, and it shows up as EBITDA:

| | Low | Base | High |
|---|---|---|---|
| Net EBITDA impact, Year 5 | $0.29M | $2.80M | $4.79M |
| Payback | Not within 5 years | Year 3 | Year 2 |
| Enterprise value at 12x | $3.5M | $33.6M | $57.5M |

Staffing savings from demand forecasting are 70% of Base-case value, so a staffing pilot comes before rollout. Drug-safety studies stay out of reach of one network's veterinary volume within five years. Company inputs (vet locations, pets per location, labor cost) are placeholders flagged for confirmation. The memo version is a separate shared document.

## Run it

```powershell
uv sync
uv run python -m tailsignal.products.release            # tries DuckLake first; falls back to Parquet
uv run python -m tailsignal.products.release --list
uv run uvicorn tailsignal.api.app:app --reload           # then open http://127.0.0.1:8000/docs
# partner portal: http://127.0.0.1:8000/portal/PHL-VET1 with header X-API-Key: clinic-PHL-VET1
uv run python scripts/build_business_case.py           # rebuilds the workbook
```

The interactive API docs at `/docs` let you set the `X-API-Key` header and try each endpoint. A browser cannot send that header to the portal page directly, so use the `/docs` page or `curl -H "X-API-Key: clinic-PHL-VET1" http://127.0.0.1:8000/portal/PHL-VET1`.

## Sources

- AVMA 2025 Economic State of the Veterinary Profession, summarized by [dvm360](https://www.dvm360.com/view/2025-economic-state-of-the-veterinary-profession-trends-and-opportunities-for-your-practice).
- [APPA: U.S. pet industry reaches $158 billion in 2025](https://americanpetproducts.org/news/u.s.-pet-industry-reaches-158-billion-in-2025-poised-for-continued-growth-in-2026).
