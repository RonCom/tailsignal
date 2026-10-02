# Data Monetization Models

TailSignal evaluates four ways to turn multi-channel pet care data into revenue. Each model is built as a working component of this repo, so the comparison rests on artifacts rather than slideware.

Prices and volumes below are **illustrative assumptions** for the business-case model (`docs/business_case.md`, Phase 4). They are inputs to be validated with buyer interviews, not market facts.

## The four models at a glance

| | 1. Data Products | 2. Research & Insights | 3. Commercialized Models | 4. Embedded Analytics |
|---|---|---|---|---|
| **What is sold** | Access to curated, de-identified data | Packaged analysis and benchmarks | Access to scores and forecasts, not the data | Data-driven features inside a product partners already use |
| **TailSignal offering** | Pet Health Data Feed: cohort-level visit, diagnosis, vaccine, and service-utilization tables | Pet Health Index reports: breed/region health trends, service benchmarks, quarterly market outlook | Scoring APIs: breed-condition risk, wellness-lapse propensity, vet-visit early warning, location demand forecasts | Partner Portal: dashboards, benchmarks, and next-best-service alerts for clinics, daycares, and groomers |
| **Primary buyers** | Animal-health pharma, pet food and nutrition, pet insurers, academic researchers | Pet brands, investors and PE diligence teams, trade associations, retailers | Pet insurers (underwriting), pharma (targeting), multi-site operators (staffing) | The data-contributing partners themselves |
| **Delivery** | Parquet flat files, Snowflake data share, REST API, (later) event stream | PDF/HTML reports, dashboards, analyst briefings | REST scoring API, batch score files | Embedded dashboards and in-workflow alerts |
| **Pricing model** | Annual license by data scope and refresh frequency | Subscription tiers, one-off custom studies | Per-call or per-score fees, or platform license | Per-location SaaS add-on, or free in exchange for data |
| **Repo component** | `marts/product/` exports, `api/` data endpoints | `reports/` notebooks and generated reports | `models/` + `api/score` | `app/partner_portal` (Streamlit) |
| **Powered by** | Entity resolution, taxonomy, de-identification | Segmentation, trends, Bayesian breed-risk, pharmacovigilance | Predictive models A–D, forecasting | All of the above, scoped to one partner |

## 1. Data Products

**Value proposition.** No single vet chain, daycare, or groomer sees the whole pet. A linked, standardized, de-identified view across channels is the scarce asset.

**What makes it sellable**
- Entity resolution links one pet across channels (the cross-channel view no single source has).
- A standard taxonomy for breed, diagnosis, and service codes makes the data usable without cleaning.
- Documented quality metrics ship with each release: match precision/recall, completeness, freshness.
- Privacy controls: k-anonymity thresholds, generalized geography (3-digit ZIP), date shifting, no direct identifiers.

**Product tiers (illustrative)**
| Tier | Content | Refresh |
|---|---|---|
| Aggregate | Counts and rates by breed group × region × month | Quarterly |
| Cohort | De-identified pet-level longitudinal records, k ≥ 10 on quasi-identifiers | Monthly |
| Research | Cohort tier plus linked service and outcome variables, under a data use agreement | Monthly |

**Key risks.** Re-identification, partner objections to resale of their data, and buyers commoditizing raw data. Mitigated by contract terms, the privacy layer, and keeping the highest-value signals in models rather than raw rows.

## 2. Research & Insights

**Value proposition.** Most buyers want answers, not tables. Insights carry higher margins than raw data and expose less of it.

**Offerings**
- **Pet Health Index (quarterly):** condition prevalence and trend by breed group and region, with uncertainty intervals.
- **Service benchmarking:** visit frequency, wellness-plan retention, and cross-channel usage by market, so an operator sees where it sits versus peers.
- **Market opportunity atlas:** pet-care supply vs. estimated demand by county (Census business counts × pet-ownership estimates).
- **Drug-safety landscape:** breed-stratified adverse-event signals from FDA data, aimed at animal-health pharma.

**Key risks.** Insights are easier to copy once published. Mitigated by the subscription cadence and custom cuts.

## 3. Commercialized Models

**Value proposition.** Buyers get the predictive value of the data without receiving the data. This lowers privacy exposure and makes the hardest-to-replicate asset (the models trained on linked cross-channel data) the product.

| Model | Buyer use | Unit sold |
|---|---|---|
| Breed-condition risk (hierarchical Bayesian) | Insurer pricing and underwriting; pharma market sizing | Risk score with interval, per pet profile |
| Vet-visit early warning (cross-channel signals) | Insurer care management; clinic outreach | Weekly risk list |
| Wellness-plan lapse + uplift | Clinic and plan-provider retention | Who to contact, and whether contact will change the outcome |
| Location demand forecast | Multi-site operators staffing and capacity | Forecast with intervals, per site × service |

**Requirements before selling a model:** a model card, a calibration report, drift monitoring, versioned endpoints, and a stated scope of valid use.

**Key risks.** Model liability, drift as partner mix changes, and buyers reverse-engineering scores. Mitigated by monitoring, contractual scope, and returning scores rather than coefficients.

## 4. Embedded Analytics

**Value proposition.** Partners contribute data; in return they get analytics they could not build alone. This is the data flywheel: more partners → better benchmarks and models → more reason to join.

**Partner Portal features**
- Benchmark tiles: "Your wellness-plan retention is in the 34th percentile for your market."
- Next-best-service alerts: daycare clients likely to need grooming, or wellness-plan members at risk of lapsing.
- Demand forecast for the partner's own site, with staffing guidance.
- Early-warning flags: pets showing pre-illness patterns, routed to the partner's vet relationship.

**Key risks.** Building and supporting software is costly; a free portal can be undervalued. Mitigated by tiering (free benchmark, paid predictive features).

## 5. Veterinary EHR–specific offerings

First-opinion EHRs (prescriptions, diagnoses, lab results, and the vet's free-text notes) support products that report-level and transaction data cannot. These extend the four models above.

| Offering | Model type | Buyer | What it delivers | Built on |
|---|---|---|---|---|
| **Signal validation studies** | Research & Insights | Animal-health manufacturers (pharmacovigilance), regulators (FDA CVM; UK VMD and EMA both list big data in their strategies) | Within weeks of a spontaneous-report signal: absolute incidence, relative risk vs. a same-indication comparator, breed and age breakdowns | Model A2 (EHR cohort) + Model A (detection) |
| **Post-approval and label-expansion evidence** | Research & Insights | Manufacturers with post-marketing commitments or new-species/indication filings | Real-world effectiveness and safety in routine practice | EHR cohorts, outcome dictionaries |
| **Trial feasibility and recruitment** | Commercialized models | Veterinary drug developers, CROs | Counts of eligible patients by clinic and region; site selection; flagged candidate patients (with clinic consent) | Entity-resolved patient registry, phenotype queries |
| **External control arms** | Research & Insights | Developers of new therapies, especially for rare or chronic conditions | Matched historical patients as a comparison group | Longitudinal EHRs, propensity matching |
| **Prescribing and adherence analytics** | Research & Insights / Data Products | Manufacturers' commercial teams | Brand share, switching, and **compliance gaps** (e.g., doses dispensed vs. a year of parasite protection) by region and clinic type | Prescription line items, dispensing intervals |
| **Lack-of-efficacy context** | Research & Insights | Manufacturers, clinics | Separates true product failure from missed doses (the masking problem in Model A) | Adherence + outcome data |
| **Syndromic and outbreak surveillance** | Data Products (feed) | Public health / One Health agencies, vaccine makers, insurers | Weekly alerts on GI, respiratory, or tick-borne disease clusters by region | Narrative classifiers, forecasting |
| **Clinical text structuring** | Embedded Analytics / Commercialized models | PIMS vendors, clinic groups | Turns free-text notes into coded diagnoses and adverse events, improving the clinic's own records | Outcome dictionaries and classifiers |
| **AI training data licensing** | Data Products | Developers of veterinary scribes, decision support, and LLMs | De-identified, coded narrative corpora with quality labels | Narrative corpus + de-identification |
| **Insurance claims support** | Commercialized models | Pet insurers | Pre-existing-condition evidence from history, breed-age-condition risk for pricing, anomaly flags | Longitudinal EHRs, Model B |
| **Diagnostics and lab market insight** | Research & Insights | Diagnostics companies | Test utilization and positivity rates by region and season | Lab results in EHRs |

### What EHR monetization requires (and how TailSignal handles it)

- **Clinic and owner terms.** Data-sharing agreements with partner clinics that permit de-identified secondary use and define a revenue share; owner notice at registration. Clinics are data partners, not just sources.
- **Free text needs extra de-identification.** Notes contain owner names, addresses, and phone numbers; narrative products require automated redaction and sampled audits before release.
- **A cross-clinic identifier.** Animals move between practices; without linkage, cohorts lose follow-up. Entity resolution (and microchip numbers where captured) is a selling point in its own right.
- **Exposure completeness.** Products bought online or administered in-clinic may be missing from records; pharmacy partnerships close the gap.
- **Fit-for-purpose evidence.** Regulators and manufacturers expect documented outcome definitions, validation (precision/recall), and pre-specified analyses — the same discipline as `docs/preregistration.md`.

## Comparison framework

Each model is scored 1–5 in `docs/business_case.md` once Phase 4 results exist.

| Criterion | Question |
|---|---|
| Revenue potential | Size of reachable buyer budget |
| Gross margin | Marginal cost of serving one more buyer |
| Time to first revenue | Months from data in hand to a signed buyer |
| Defensibility | How hard it is for a competitor or buyer to replicate |
| Privacy exposure | Re-identification and regulatory risk |
| Partner alignment | Whether data contributors see it as fair or as resale of their data |
| Data requirements | Volume and linkage quality needed before it works |

**Working hypothesis to test (pre-registered):** embedded analytics comes first because it drives partner acquisition; research and insights produce the earliest external revenue; commercialized models carry the most defensible margin once linkage quality and volume are proven; raw data products are sold selectively to research buyers under data use agreements.
