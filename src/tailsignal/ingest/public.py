"""Download real public datasets used by TailSignal.

Sources
-------
openfda      FDA Center for Veterinary Medicine adverse-event reports (bulk JSON via openFDA)
             https://open.fda.gov/apis/animalandveterinary/event
austin       Austin Animal Center intakes/outcomes (Socrata, data.austintexas.gov)
nyc_dogs     NYC Dog Licensing Dataset (Socrata, data.cityofnewyork.us, id nu7n-tubp)
peteval      SAVSNET PetEVAL: annotated UK primary-care veterinary free-text EHRs (Hugging Face;
             check the dataset card for license/access terms; may require `huggingface-cli login`)
vetcompass   VetCompass (RVC) open-access breed-disorder tables: manual download into
             data/raw/public/vetcompass/ (published per paper; see docs/data_sources.md)
census_cbp   Census County Business Patterns: veterinary services (NAICS 541940) and
             pet care except veterinary (NAICS 812910) establishments by county

Usage
-----
    python -m tailsignal.ingest.public --source all
    python -m tailsignal.ingest.public --source openfda --max-partitions 2   # quick test

Raw files land in data/raw/public/<source>/. openFDA reports are also flattened to
Parquet (reports, drugs, reactions) for dbt.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/public")
UA = {"User-Agent": "tailsignal-portfolio/0.1 (research; contact via github.com/RonCom)"}

# Socrata dataset ids. Austin republished its datasets in 2025; the archived ids cover
# 10/2013-05/2025, the current ids continue from there. Override with --austin-ids.
AUSTIN_IDS = {
    "outcomes_current": "gsvs-ypi7",
    "outcomes_archive": "9t4d-g238",
}
NYC_DOGS_ID = "nu7n-tubp"


def _get(url, params=None, retries=4, stream=False):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=120, stream=stream)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))


# ----------------------------------------------------------------------------- Socrata
def socrata_csv(domain: str, dataset_id: str, out: Path, page=50_000) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    frames, offset = [], 0
    while True:
        r = _get(f"https://{domain}/resource/{dataset_id}.csv",
                 {"$limit": page, "$offset": offset, "$order": ":id"})
        df = pd.read_csv(io.StringIO(r.text), dtype=str)
        if df.empty:
            break
        frames.append(df)
        offset += page
        print(f"  {dataset_id}: {offset:,} rows", flush=True)
        if len(df) < page:
            break
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    data.to_csv(out, index=False)
    return len(data)


def ingest_austin(ids=AUSTIN_IDS):
    for name, ds in ids.items():
        try:
            n = socrata_csv("data.austintexas.gov", ds, OUT / "austin" / f"{name}.csv")
            print(f"austin {name} ({ds}): {n:,} rows")
        except Exception as e:  # dataset ids change; keep going
            print(f"austin {name} ({ds}) failed: {e}")


def ingest_nyc_dogs():
    n = socrata_csv("data.cityofnewyork.us", NYC_DOGS_ID, OUT / "nyc_dogs" / "dog_licenses.csv")
    print(f"nyc dog licenses: {n:,} rows")


# ----------------------------------------------------------------------------- Census CBP
CBP_NAICS = {"541940": "veterinary_services", "812910": "pet_care_except_vet"}


def ingest_census_cbp(years=(2019, 2020, 2021, 2022)):
    key = os.environ.get("CENSUS_API_KEY")
    rows = []
    for y in years:
        for code, label in CBP_NAICS.items():
            params = {"get": "NAME,ESTAB,EMP,PAYANN", "for": "county:*", "NAICS2017": code}
            if key:
                params["key"] = key
            r = _get(f"https://api.census.gov/data/{y}/cbp", params)
            data = r.json()
            df = pd.DataFrame(data[1:], columns=data[0])
            df["year"], df["naics_label"] = y, label
            rows.append(df)
            print(f"cbp {y} {code}: {len(df):,} counties")
    out = OUT / "census_cbp" / "cbp_pet_services.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(rows, ignore_index=True).to_csv(out, index=False)


# ----------------------------------------------------------------------------- openFDA
def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def flatten_openfda(results: list[dict]):
    reports, drugs, reactions = [], [], []
    for r in results:
        rid = r.get("unique_aer_id_number")
        a = r.get("animal") or {}
        breed = a.get("breed") or {}
        age = a.get("age") or {}
        wt = a.get("weight") or {}
        reports.append(dict(
            report_id=rid, receive_date=r.get("original_receive_date"), onset_date=r.get("onset_date"),
            primary_reporter=r.get("primary_reporter"), type_of_information=r.get("type_of_information"),
            serious_ae=r.get("serious_ae"), n_affected=r.get("number_of_animals_affected"),
            n_treated=r.get("number_of_animals_treated"), species=a.get("species"), gender=a.get("gender"),
            reproductive_status=a.get("reproductive_status"),
            is_crossbred=breed.get("is_crossbred"), breed_component=json.dumps(_as_list(breed.get("breed_component"))),
            age_min=age.get("min"), age_max=age.get("max"), age_unit=age.get("unit"),
            weight_min=wt.get("min"), weight_unit=wt.get("unit"),
            outcome=json.dumps([o.get("medical_status") for o in _as_list(r.get("outcome"))]),
        ))
        for di, d in enumerate(_as_list(r.get("drug"))):
            ings = _as_list(d.get("active_ingredients")) or [{}]
            for ing in ings:
                drugs.append(dict(report_id=rid, drug_seq=di, brand_name=d.get("brand_name"),
                                  ingredient=(ing or {}).get("name"), route=d.get("route"),
                                  dosage_form=d.get("dosage_form"), atc_vet_code=d.get("atc_vet_code"),
                                  used_according_to_label=d.get("used_according_to_label"),
                                  first_exposure_date=d.get("first_exposure_date")))
        for rx in _as_list(r.get("reaction")):
            reactions.append(dict(report_id=rid, veddra_version=rx.get("veddra_version"),
                                  veddra_term_code=rx.get("veddra_term_code"),
                                  veddra_term_name=rx.get("veddra_term_name"),
                                  n_affected=rx.get("number_of_animals_affected")))
    return pd.DataFrame(reports), pd.DataFrame(drugs), pd.DataFrame(reactions)


def ingest_openfda(max_partitions: int | None = None):
    manifest = _get("https://api.fda.gov/download.json").json()
    parts = manifest["results"]["animalandveterinary"]["event"]["partitions"]
    if max_partitions:
        parts = parts[:max_partitions]
    out = OUT / "openfda"
    (out / "zips").mkdir(parents=True, exist_ok=True)
    rep, drg, rxn = [], [], []
    for i, p in enumerate(parts, 1):
        url = p["file"]
        # every partition file has the same basename (e.g. ...-0001-of-0001.json.zip), so name local
        # copies by their path below /event/ to avoid one file silently standing in for all of them
        zpath = out / "zips" / url.split("/event/")[-1].replace("/", "_")
        if not zpath.exists():
            zpath.write_bytes(_get(url).content)
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                results = json.loads(z.read(name)).get("results", [])
                a, b, c = flatten_openfda(results)
                rep.append(a); drg.append(b); rxn.append(c)
        print(f"openfda partition {i}/{len(parts)} {p.get('display_name', '')}", flush=True)
    for name, frames in [("reports", rep), ("drugs", drg), ("reactions", rxn)]:
        df = pd.concat(frames, ignore_index=True)
        if name == "reports":
            n0 = len(df)
            df = df.drop_duplicates("report_id")
            print(f"openfda reports: dropped {n0 - len(df):,} duplicate report ids")
        else:
            df = df.drop_duplicates()
        df.astype({c: "string" for c in df.columns}).to_parquet(out / f"{name}.parquet", index=False)
        print(f"openfda {name}: {len(df):,} rows")


# ----------------------------------------------------------------------------- NARMS (FDA)
NARMS_FILES = {
    # Vet-LIRN / NAHLN isolates: E. coli and S. pseudintermedius from dogs, Salmonella from cattle and swine
    "animal_pathogen_data.xlsx": "https://www.fda.gov/media/132928/download?attachment",
    "narms_data_dictionary.xlsx": "https://www.fda.gov/media/110404/download?attachment",
}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def ingest_narms():
    out = OUT / "narms"
    out.mkdir(parents=True, exist_ok=True)
    for name, url in NARMS_FILES.items():
        r = requests.get(url, headers=BROWSER_UA, timeout=180)
        r.raise_for_status()
        if r.content[:2] != b"PK":  # .xlsx files are zip archives; anything else is an error page
            raise SystemExit(f"{name}: fda.gov returned {r.headers.get('content-type')} instead of a spreadsheet. "
                             f"Download it in a browser from {url} and save it as data/raw/public/narms/{name}")
        (out / name).write_bytes(r.content)
        print(f"narms {name}: {len(r.content) / 1e6:.1f} MB")


# ----------------------------------------------------------------------------- PetEVAL
def ingest_peteval(repo_id="SAVSNET/PetEVAL"):
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit("pip/uv add huggingface_hub to download PetEVAL")
    path = snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=OUT / "peteval")
    print(f"peteval downloaded to {path}")


def main():
    ap = argparse.ArgumentParser(description="Download TailSignal public datasets")
    ap.add_argument("--source", choices=["all", "openfda", "austin", "nyc_dogs", "census_cbp", "peteval", "narms"], default="all")
    ap.add_argument("--max-partitions", type=int, default=None, help="openFDA: limit partitions for a quick test")
    a = ap.parse_args()
    jobs = {"openfda": lambda: ingest_openfda(a.max_partitions), "austin": ingest_austin,
            "nyc_dogs": ingest_nyc_dogs, "census_cbp": ingest_census_cbp,
            "peteval": ingest_peteval, "narms": ingest_narms}
    for name, fn in jobs.items():
        if a.source in ("all", name):
            print(f"== {name}")
            fn()


if __name__ == "__main__":
    main()
