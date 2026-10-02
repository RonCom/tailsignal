# Data Sources

## Real public data

| Source | Use in TailSignal | Access | Ingest |
|---|---|---|---|
| [openFDA Animal & Veterinary Adverse Events](https://open.fda.gov/apis/animalandveterinary/event) | Model A: breed-stratified pharmacovigilance | Public bulk download | `--source openfda` |
| [Dog Aging Project](https://data.dogagingproject.org/) | Model B: hierarchical breed-condition risk | Access request (submitted) | Manual, after approval → `data/raw/public/dap/` |
| [SAVSNET PetEVAL](https://huggingface.co/datasets/SAVSNET/PetEVAL) | Real veterinary free text for diagnosis normalization; PetBERT baseline; syndromic surveillance product | Hugging Face; check dataset card for license/terms | `--source peteval` |
| [VetCompass open access](https://www.rvc.ac.uk/vetcompass/papers-and-data/open-access-data) | External benchmark for breed-disorder prevalence; grounds the simulator's breed risks | Per-paper downloads | Manual → `data/raw/public/vetcompass/` |
| [Austin Animal Center outcomes](https://data.austintexas.gov/Health-and-Community-Services/Austin-Animal-Center-Outcomes/gsvs-ypi7) | Real-data forecasting demonstration | Public (Socrata) | `--source austin` |
| [NYC Dog Licensing](https://data.cityofnewyork.us/Health/NYC-Dog-Licensing-Dataset/nu7n-tubp) | Breed mix and trends by ZIP | Public (Socrata) | `--source nyc_dogs` |
| Census County Business Patterns (NAICS 541940, 812910) | Market opportunity atlas: pet-care supply by county | Public API (key optional: `CENSUS_API_KEY`) | `--source census_cbp` |

Notes
- PetEVAL and VetCompass describe UK populations. They are used for methods (text normalization) and as an external benchmark, not as US prevalence estimates.
- Austin republished its animal-center datasets in 2025; the archived id (`9t4d-g238`) covers 10/2013–05/2025. Check ids if a download returns 404.
- The cloud environment used to scaffold this repo could not reach these APIs, so the ingest scripts were unit-tested on sample records but not yet run against live endpoints. Run them locally first.

## Synthetic multi-channel data

No public dataset links the same pets across vets, daycares, groomers, and wellness plans, so `tailsignal.synth.generate` simulates it. Each source writes data the way that kind of system would:

| Source system | Channel | Format quirks |
|---|---|---|
| `vet_alpha` | Vet clinics | Flat CSV; alphanumeric diagnosis codes; line items packed in one string |
| `vet_beta` | Vet clinics | Nested JSON lines; "LAST, First" names; age at registration instead of DOB; kg |
| `vet_gamma` | Vet clinics | Pipe-delimited; no patient id; free-text visit reason; some birth dates year-only |
| `pawstay` | Daycare + boarding | Registrations with free-text age ("10 mos"); 3% duplicate registrations |
| `groomly` | Grooming | Denormalized appointments; 12-hour timestamps; frequent missing email |
| `wellplan` | Wellness plans | Memberships plus a randomized reminder campaign |

Identity noise: nicknames (Bob/Robert), typos, stale phone and ZIP after a move, missing emails, pet-name variants (Max/Maxwell), and breed spellings (Frenchie, Labrador Retreiver).

Ground truth (in `data/truth/`, never read by models): true pet and household ids, latent segment, illness events with pre-visit "prodrome" signals in non-vet channels, and the true heterogeneous effect of the reminder campaign.

All rates, relative risks, and behaviors in `synth/reference.py` are synthetic assumptions. Novel-method claims are made only on real data (see `docs/preregistration.md`).
