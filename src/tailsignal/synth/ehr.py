"""Clinical EHR layer on top of the platform simulator.

Re-creates the platform world from the same seed, then adds prescriptions, procedures and anesthesia,
lab panels, culture results (real FDA NARMS isolates), clinical notes, and microchip numbers.
Spec and every planted parameter: docs/simulator_extension_spec.md.

    uv run python -m tailsignal.synth.ehr
"""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit

from tailsignal.synth import generate as G
from tailsignal.synth import reference as R

SEED_OFFSET = 7919
REGION = {"PHL": "Northeast", "AUS": "South", "MSP": "Midwest"}

# ----------------------------------------------------------------------------- planted parameters
P = {
    "dental": {
        "h0": 0.017, "size_mult": {"toy": 2.6, "small": 3.0, "medium": 1.4, "large": 1.0, "cat": 1.3},
        "overweight_mult": 3.5, "age_log_slope": 0.06, "progress_per_year": 0.5,
        "detect_by_visit": {"wellness": 0.9, "sick": 0.25, "recheck": 0.1, "procedure": 0.1},
        "low_charting_clinics": {"AUS-VET2": 0.45, "MSP-VET3": 0.45}, "high_charting_clinics": {"PHL-VET1": 0.97},
        "cleaning_after_detection": 0.45,
    },
    "overweight": {"base": 0.30, "breed_mult": {"Labrador Retriever": 1.6, "Beagle": 1.4}},
    "seizure": {"epilepsy_prev": 0.0075, "epilepsy_breed_mult": {"Border Collie": 3, "Australian Shepherd": 2,
                                                                  "Beagle": 2, "German Shepherd": 1.5},
                "epileptic_rate": 3.0, "dog_rate": 0.004, "cat_rate": 0.002, "presented": 0.8,
                "isox_rr": 1.5, "isox_window": 50, "channeling_mult": 0.3},
    "gi": {"rate": 0.15, "presented": 0.5, "cox_rr": 2.0, "window": 14},
    "neuro": {"rate": 0.005, "presented": 0.6, "ml_mdr1_rr": 1.0, "window": 30,
              "mdr1_breeds": ["Australian Shepherd", "Border Collie"]},
    "infection": {"uti_dog_f": 0.025, "uti_dog_m": 0.01, "uti_cat": 0.01, "uti_presented": 0.85,
                  "pyoderma_after_atopy": 0.35, "pyoderma_rate": 0.02, "uti_ecoli_share": 0.75,
                  "fail_if_R": 0.75, "fail_if_S": 0.12, "fail_topical": 0.30, "recheck_culture": 0.8},
    "anesthesia": {"death": {"dog": {"low": 0.0005, "high": 0.0133}, "cat": {"low": 0.0011, "high": 0.0140}},
                   "complication": {"low": 0.08, "high": 0.20},
                   "or_death": {"brachy": 1.5, "dog_lt5kg": 2.0, "age12": 1.5, "emergency": 1.5},
                   "or_comp_brachy": 2.0, "clinic_death_sd": 0.3, "clinic_comp_sd": 0.35,
                   "death_outlier": {"PHL-VET3": 2.0}, "comp_outliers": {"AUS-VET1": 2.0, "MSP-VET1": 0.6}},
    "ckd": {"lead_months": [18, 36], "creat_at_dx": 2.3, "post_dx_f_per_year": 0.5, "future_years": 3},
    "microchip": {"dog": 0.75, "cat": 0.55, "error": 0.02},
}
BRACHY = {"French Bulldog", "Bulldog", "Shih Tzu", "Persian", "Cavalier King Charles Spaniel"}

# ----------------------------------------------------------------------------- formulary
# proxy: NARMS drug used to judge susceptibility, by organism; bl: beta-lactam (MRSP => resistant)
DRUGS = {
    "amoxicillin": dict(cls="Penicillins", hpcia=False, bl=True,
                        proxy={"E. coli": "Ampicillin", "S. pseudintermedius": "Ampicillin"}),
    "amoxicillin-clavulanate": dict(cls="Beta-lactam + inhibitor", hpcia=False, bl=True,
                                    proxy={"E. coli": "Amoxicillin/Clavulanic Acid",
                                           "S. pseudintermedius": "Amoxicillin/Clavulanic Acid"}),
    "cephalexin": dict(cls="Cephalosporins (1st gen)", hpcia=False, bl=True,
                       proxy={"E. coli": "Cephalexin", "S. pseudintermedius": "Cephalothin"}),
    "cefpodoxime": dict(cls="Cephalosporins (3rd gen)", hpcia=True, bl=True,
                        proxy={"E. coli": "Cefpodoxime", "S. pseudintermedius": "Cefpodoxime"}),
    "cefovecin": dict(cls="Cephalosporins (3rd gen)", hpcia=True, bl=True,
                      proxy={"E. coli": "Cefovecin", "S. pseudintermedius": "Cefovecin"}),
    "trimethoprim-sulfamethoxazole": dict(cls="Folate pathway inhibitors", hpcia=False, bl=False,
                                          proxy={"E. coli": "Trimethoprim/Sulfamethoxazole",
                                                 "S. pseudintermedius": "Trimethoprim/Sulfamethoxazole"}),
    "enrofloxacin": dict(cls="Fluoroquinolones", hpcia=True, bl=False,
                         proxy={"E. coli": "Enrofloxacin", "S. pseudintermedius": "Enrofloxacin"}),
    "marbofloxacin": dict(cls="Fluoroquinolones", hpcia=True, bl=False,
                          proxy={"E. coli": "Marbofloxacin", "S. pseudintermedius": "Enrofloxacin"}),
    "clindamycin": dict(cls="Lincosamides", hpcia=False, bl=False, proxy={"S. pseudintermedius": "Clindamycin"},
                        intrinsic_ecoli=True),
    "doxycycline": dict(cls="Tetracyclines", hpcia=False, bl=False,
                        proxy={"E. coli": "Doxycycline", "S. pseudintermedius": "Doxycycline"}),
    "minocycline": dict(cls="Tetracyclines", hpcia=False, bl=False, proxy={"S. pseudintermedius": "Minocycline"}),
    "rifampin": dict(cls="Ansamycins", hpcia=False, bl=False, proxy={"S. pseudintermedius": "Rifampin"},
                     intrinsic_ecoli=True),
    "amikacin": dict(cls="Aminoglycosides", hpcia=False, bl=False,
                     proxy={"E. coli": "Amikacin", "S. pseudintermedius": "Gentamicin"}),
    "oxacillin": dict(cls="Anti-staphylococcal penicillins", hpcia=False, bl=True,
                      proxy={"S. pseudintermedius": "Oxacillin"}),
    "metronidazole": dict(cls="Nitroimidazoles", hpcia=False, bl=False, proxy={}),
}
ABX = {
    "uti": {"first": ["amoxicillin", "trimethoprim-sulfamethoxazole"], "other": ["amoxicillin-clavulanate", "cephalexin"],
            "hpcia": ["cefovecin", "enrofloxacin", "marbofloxacin", "cefpodoxime"],
            "guided": ["amoxicillin", "trimethoprim-sulfamethoxazole", "cephalexin", "amoxicillin-clavulanate",
                       "enrofloxacin", "marbofloxacin", "amikacin"],
            "panel": ["amoxicillin", "amoxicillin-clavulanate", "cephalexin", "cefovecin", "cefpodoxime",
                      "trimethoprim-sulfamethoxazole", "enrofloxacin", "marbofloxacin", "amikacin"], "days": 7},
    "pyoderma": {"first": ["cephalexin", "clindamycin", "amoxicillin-clavulanate", "trimethoprim-sulfamethoxazole"],
                 "other": ["doxycycline"], "hpcia": ["cefovecin", "cefpodoxime", "enrofloxacin", "marbofloxacin"],
                 "guided": ["cephalexin", "clindamycin", "trimethoprim-sulfamethoxazole", "amoxicillin-clavulanate",
                            "doxycycline", "minocycline", "rifampin", "amikacin"],
                 "panel": ["oxacillin", "cephalexin", "amoxicillin-clavulanate", "clindamycin",
                           "trimethoprim-sulfamethoxazole", "doxycycline", "minocycline", "cefovecin", "cefpodoxime",
                           "enrofloxacin", "rifampin", "amikacin"], "days": 21},
}
FLEA_ISOX = {"dog": ["fluralaner", "afoxolaner", "sarolaner", "lotilaner"], "cat": ["fluralaner (topical)",
                                                                                       "sarolaner/selamectin"]}
FLEA_OTHER = {"dog": ["fipronil/s-methoprene", "imidacloprid/permethrin", "selamectin"],
              "cat": ["selamectin", "imidacloprid/moxidectin"]}
HEARTWORM = (["ivermectin/pyrantel", "milbemycin oxime", "moxidectin (injectable)"], [0.4, 0.35, 0.25])
NSAID_DOG = (["carprofen", "meloxicam", "grapiprant", "robenacoxib"], [0.45, 0.30, 0.15, 0.10])
NSAID_CAT = (["meloxicam", "robenacoxib"], [0.5, 0.5])
COX = {"carprofen", "meloxicam", "robenacoxib"}
CHIP_PREFIX = ["900", "941", "956", "981", "985"]


# ----------------------------------------------------------------------------- NARMS isolate sampler
class Narms:
    """Draws real NARMS dog isolates by organism, site, region, year; judges drug susceptibility."""

    def __init__(self, rng):
        from tailsignal.models.amr import load
        df = load()
        df = df[df.organism.isin(["E. coli", "S. pseudintermedius"])]
        self.wide = (df.pivot_table(index=["isolate", "organism", "source", "region", "year"], columns="drug",
                                    values="R", aggfunc="max").reset_index())
        self.groups = {k: g.index.to_numpy() for k, g in self.wide.groupby(["organism", "source", "region", "year"])}
        self.marg = df.groupby(["organism", "source", "drug"]).R.mean().to_dict()
        self.rng = rng

    def draw(self, organism, source, region, year) -> dict:
        y = int(min(max(year, 2017), 2024))
        idx = self.groups.get((organism, source, region, y))
        if idx is None or len(idx) < 20:
            idx = np.concatenate([v for k, v in self.groups.items() if k[:3] == (organism, source, region)])
        return self.wide.loc[int(self.rng.choice(idx))].to_dict()

    def resistant(self, iso: dict, drug: str) -> bool | None:
        d, org = DRUGS[drug], iso["organism"]
        if org == "E. coli" and d.get("intrinsic_ecoli"):
            return True
        if org == "S. pseudintermedius" and d["bl"] and iso.get("Oxacillin") == 1:
            return True  # CLSI: methicillin resistance => resistant to all beta-lactams
        proxy = d["proxy"].get(org)
        if proxy is None:
            return None
        v = iso.get(proxy)
        if v is None or pd.isna(v):
            key = (org, iso["source"], proxy)
            v = self.rng.random() < self.marg.get(key, 0.2)
        return bool(v)


# ----------------------------------------------------------------------------- world
def base_world(cfg: G.Config):
    rng = np.random.default_rng(cfg.seed)
    locs = G.build_locations()
    hh = G.build_households(cfg, rng)
    pets = G.assign_channels(G.build_pets(cfg, hh, rng), locs, rng)
    ill = G.simulate_illness(cfg, pets, rng)
    vet = G.simulate_vet(cfg, pets, ill, rng)
    return locs, pets, ill, vet


def clinic_params(locs, rng) -> dict:
    out = {}
    dp, an = P["dental"], P["anesthesia"]
    for c in sorted(locs[locs.channel == "vet"].location_id):
        u = lambda lo, hi: float(rng.uniform(lo, hi))
        out[c] = dict(
            clinic=c, market=c[:3],
            dental_thoroughness=dp["low_charting_clinics"].get(c, dp["high_charting_clinics"].get(c, u(0.7, 0.9))),
            lab_intensity=u(0.6, 1.0), preanes_bloodwork=u(0.5, 0.9), chip_capture=u(0.6, 0.95),
            death_log_or=float(np.log(an["death_outlier"][c])) if c in an["death_outlier"]
            else float(rng.normal(0, an["clinic_death_sd"])),
            comp_log_or=float(np.log(an["comp_outliers"][c])) if c in an["comp_outliers"]
            else float(rng.normal(0, an["clinic_comp_sd"])),
            p_culture_uti=u(0.15, 0.75), p_culture_skin=u(0.05, 0.4), p_first_line=u(0.35, 0.85),
            p_hpcia_if_not_first=u(0.15, 0.7), p_topical=u(0.1, 0.5), p_metro=u(0.15, 0.6),
            p_dental_abx=u(0.1, 0.6))
        out[c]["p_hpcia_marginal"] = (1 - out[c]["p_first_line"]) * out[c]["p_hpcia_if_not_first"]
    return out


class EHR:
    def __init__(self, cfg, locs, pets, ill, vet, seed):
        self.cfg, self.locs, self.ill, self.vet = cfg, locs, ill, vet
        self.rng = np.random.default_rng(seed)
        self.pets = pets.set_index("pet_uid", drop=False)
        self.clinics = clinic_params(locs, self.rng)
        self.narms = Narms(self.rng)
        self.visits, self.rx, self.procs, self.labs, self.cultures, self.notes = [], [], [], [], [], []
        self.ae, self.infections = [], []
        self.nv = self.nrx = self.ncult = 0
        self.n = cfg.n_days

    # ------------------------------------------------------------------ helpers
    def year(self, day):
        return int(str(G.day_to_date(day))[:4])

    def age(self, pet, day):
        return (day - pet.birth_day) / 365.25

    def clinic_on(self, pet, day):
        if pd.notna(pet.second_vet) and pd.notna(pet.vet_switch_day) and day >= pet.vet_switch_day:
            return pet.second_vet
        return pet.home_vet

    def alive(self, pet, day):
        return pet.join_day <= day < min(pet.exit_day, self.n)

    def add_visit(self, pet, day, vtype, dx, **kw):
        self.nv += 1
        v = dict(visit_id=f"EV{self.nv:07d}", pet_uid=pet.pet_uid, clinic=self.clinic_on(pet, day), day=int(day),
                 visit_type=vtype, dx=dx, **kw)
        self.visits.append(v)
        return v

    def add_rx(self, pet, day, drug, cls, indication, days, visit=None, **kw):
        self.nrx += 1
        r = dict(rx_id=f"RX{self.nrx:07d}", pet_uid=pet.pet_uid, visit_id=visit["visit_id"] if visit else None,
                 clinic=visit["clinic"] if visit else self.clinic_on(pet, day), day=int(day), drug=drug,
                 drug_class=cls, indication=indication, duration_days=int(days), **kw)
        self.rx.append(r)
        return r

    # ------------------------------------------------------------------ 0. latent pet traits
    def latent(self):
        rng, p = self.rng, self.pets
        ow = P["overweight"]
        obese = set(self.ill[self.ill.condition == "obesity"].pet_uid)
        prob = ow["base"] * p.breed.map(ow["breed_mult"]).fillna(1.0)
        p["overweight"] = (rng.random(len(p)) < prob) | p.pet_uid.isin(obese)
        sz = P["seizure"]
        ep = sz["epilepsy_prev"] * p.breed.map(sz["epilepsy_breed_mult"]).fillna(1.0)
        p["epileptic"] = (p.species == "dog") & (rng.random(len(p)) < ep)
        onset_age = rng.uniform(1, 5, len(p))
        p["epilepsy_onset_day"] = np.where(p.epileptic, p.birth_day + onset_age * 365.25, np.nan)
        mc = P["microchip"]
        chipped = rng.random(len(p)) < p.species.map({"dog": mc["dog"], "cat": mc["cat"]})
        p["microchip"] = [rng.choice(CHIP_PREFIX) + "".join(map(str, rng.integers(0, 10, 12))) if c else None
                          for c in chipped]
        p["brachy"] = p.breed.isin(BRACHY)
        # kidney trajectories (cats)
        ck = P["ckd"]
        ckd = self.ill[self.ill.condition == "chronic_kidney_disease"].groupby("pet_uid").event_day.min()
        p["ckd_dx_day"] = p.pet_uid.map(ckd)
        p["ckd_future"] = False
        end_age = (self.n - p.birth_day) / 365.25
        h = 0.008 * np.exp(0.28 * (end_age - 5)) * p.breed.map(lambda b: R.BREED_RR.get(b, {}).get(
            "chronic_kidney_disease", 1.0))
        fut = (p.species == "cat") & p.ckd_dx_day.isna() & (p.exit_day >= self.n) & \
              (rng.random(len(p)) < 1 - np.exp(-ck["future_years"] * h))
        p.loc[fut, "ckd_dx_day"] = self.n + rng.integers(30, 365 * ck["future_years"], fut.sum())
        p.loc[fut, "ckd_future"] = True
        p["ckd_lead_days"] = np.where(p.ckd_dx_day.notna(),
                                      rng.uniform(ck["lead_months"][0], ck["lead_months"][1], len(p)) * 30.44, np.nan)
        p["creat0"] = np.where(p.species == "cat", rng.normal(1.35, 0.2, len(p)), rng.normal(1.0, 0.2, len(p)))
        p["sdma0"] = rng.normal(11, 1.5, len(p)).clip(6, 14)
        p["usg0"] = np.where(p.species == "cat", rng.normal(1.045, 0.006, len(p)), rng.normal(1.030, 0.008, len(p)))
        p["upc0"] = rng.lognormal(np.log(0.1), 0.35, len(p))
        self._pt = {r.pet_uid: r for r in p.itertuples()}

    def pet(self, uid):
        return self._pt[uid]

    # ------------------------------------------------------------------ 1. base visits
    def base_visits(self):
        kinds = {"Wellness exam": "wellness", "Sick visit exam": "sick", "Recheck exam": "recheck",
                 "Dental cleaning under anesthesia": "procedure"}
        for i, r in enumerate(self.vet.itertuples()):
            pet = self.pet(r.pet_uid)
            vt = kinds[r.items[0][0]]
            self.nv += 1
            self.visits.append(dict(visit_id=f"EV{self.nv:07d}", pet_uid=r.pet_uid, clinic=r.clinic, day=int(r.day),
                                    visit_type=vt, dx=r.dx, base_visit_index=i,
                                    procedure="dental_cleaning" if vt == "procedure" else None))

    # ------------------------------------------------------------------ 2. infections and antibiotics
    def choose_empirical(self, kind, c):
        rng, a = self.rng, ABX[kind]
        u = rng.random()
        if u < c["p_first_line"]:
            return rng.choice(a["first"]), "first_line"
        if rng.random() < c["p_hpcia_if_not_first"]:
            return rng.choice(a["hpcia"]), "hpcia"
        return rng.choice(a["other"]), "other"

    def culture(self, pet, visit, kind, iso):
        self.ncult += 1
        cid = f"CU{self.ncult:06d}"
        for d in ABX[kind]["panel"]:
            r = self.narms.resistant(iso, d)
            if r is None:
                continue
            self.cultures.append(dict(culture_id=cid, pet_uid=pet.pet_uid, visit_id=visit["visit_id"],
                                      clinic=visit["clinic"], day=visit["day"], site="urine" if kind == "uti" else "skin",
                                      organism=iso["organism"], drug=d, result="R" if r else "S",
                                      narms_isolate=iso["isolate"]))
        return cid

    def infection_episode(self, pet, day, kind, visit=None):
        rng, inf = self.rng, P["infection"]
        if visit is None:
            visit = self.add_visit(pet, day, "sick", "urinary_tract_infection" if kind == "uti" else "pyoderma")
        else:
            visit["secondary_dx"] = "pyoderma"
        c = self.clinics[visit["clinic"]]
        if kind == "uti":
            org = "E. coli" if rng.random() < inf["uti_ecoli_share"] else "S. pseudintermedius"
            iso = self.narms.draw(org, "UTI", REGION[pet.market], self.year(day))
            p_cult = c["p_culture_uti"]
        else:
            iso = self.narms.draw("S. pseudintermedius", "Other sites", REGION[pet.market], self.year(day))
            p_cult = c["p_culture_skin"]
        ep = dict(pet_uid=pet.pet_uid, kind=kind, day=int(day), visit_id=visit["visit_id"], clinic=visit["clinic"],
                  organism=iso["organism"], mrsp=bool(iso.get("Oxacillin") == 1), narms_isolate=iso["isolate"])
        cultured = rng.random() < p_cult
        if kind == "pyoderma" and rng.random() < c["p_topical"]:
            self.add_rx(pet, day, "chlorhexidine (topical)", "Topical antiseptic", kind, 21, visit,
                        culture_before=cultured, choice_tier="topical", is_hpcia=False)
            if cultured:
                self.culture(pet, visit, kind, iso)
            failed = rng.random() < inf["fail_topical"]
            ep.update(empirical="topical", cultured=cultured, empirical_resistant=None, failed=failed)
        else:
            drug, tier = self.choose_empirical(kind, c)
            self.add_rx(pet, day, drug, DRUGS[drug]["cls"], kind, ABX[kind]["days"], visit,
                        culture_before=cultured, choice_tier=tier, is_hpcia=DRUGS[drug]["hpcia"])
            res = self.narms.resistant(iso, drug)
            if cultured:
                self.culture(pet, visit, kind, iso)
                if res:  # culture comes back in ~3 days; switch to a susceptible drug
                    new = self.guided(kind, iso)
                    self.add_rx(pet, day + 3, new, DRUGS[new]["cls"], kind, ABX[kind]["days"], None,
                                culture_before=True, choice_tier="culture_guided", is_hpcia=DRUGS[new]["hpcia"])
                    res_final = self.narms.resistant(iso, new)
                else:
                    res_final = res
            else:
                res_final = res
            failed = rng.random() < (inf["fail_if_R"] if res_final else inf["fail_if_S"])
            ep.update(empirical=drug, cultured=cultured, empirical_resistant=bool(res), failed=failed)
        if failed:
            rd = int(day + rng.integers(10, 22))
            if self.alive(pet, rd):
                rv = self.add_visit(pet, rd, "recheck", visit["dx"] if kind == "uti" else "pyoderma")
                if not cultured and rng.random() < inf["recheck_culture"]:
                    self.culture(pet, rv, kind, iso)
                    new = self.guided(kind, iso)
                    tier = "culture_guided"
                else:
                    new = self.guided(kind, iso) if cultured else self.choose_empirical(kind, self.clinics[rv["clinic"]])[0]
                    tier = "culture_guided" if cultured else "empirical_second"
                self.add_rx(pet, rd, new, DRUGS[new]["cls"], kind, ABX[kind]["days"], rv, culture_before=tier ==
                            "culture_guided", choice_tier=tier, is_hpcia=DRUGS[new]["hpcia"])
                ep["recheck_visit_id"] = rv["visit_id"]
        self.infections.append(ep)

    def guided(self, kind, iso):
        for d in ABX[kind]["guided"]:
            if self.narms.resistant(iso, d) is False:
                return d
        return ABX[kind]["guided"][-1]

    def infections_and_abx(self):
        rng, inf = self.rng, P["infection"]
        # secondary pyoderma at presented allergic-dermatitis visits; metronidazole at GI visits
        for v in list(self.visits):
            if v["visit_type"] not in ("sick",):
                continue
            pet = self.pet(v["pet_uid"])
            c = self.clinics[v["clinic"]]
            if v["dx"] == "allergic_dermatitis" and pet.species == "dog" and rng.random() < inf["pyoderma_after_atopy"]:
                self.infection_episode(pet, v["day"], "pyoderma", visit=v)
            if v["dx"] == "gastroenteritis" and rng.random() < c["p_metro"]:
                self.add_rx(pet, v["day"], "metronidazole", DRUGS["metronidazole"]["cls"], "acute_diarrhea", 7, v,
                            culture_before=False, choice_tier="not_indicated", is_hpcia=False)
        # new UTI and primary pyoderma events
        for pet in self.pets.itertuples():
            if pd.isna(pet.home_vet):
                continue
            start, end = max(pet.join_day, 0), min(pet.exit_day, self.n)
            years = (end - start) / 365.25
            if pet.species == "dog":
                rates = {"uti": inf["uti_dog_f"] if pet.sex == "F" else inf["uti_dog_m"], "pyoderma": inf["pyoderma_rate"]}
            else:
                rates = {"uti": inf["uti_cat"]}
            pres = inf["uti_presented"] * (0.7 if pet.segment == "low_engagement" else 1.0)
            for kind, rate in rates.items():
                for d in rng.uniform(start, end, rng.poisson(rate * years)).astype(int):
                    if rng.random() < pres:
                        self.infection_episode(pet, d, kind)

    # ------------------------------------------------------------------ 3. procedures
    def procedures(self):
        rng = self.rng
        for pet in self.pets.itertuples():
            if pd.isna(pet.home_vet):
                continue
            age_join = (pet.join_day - pet.birth_day) / 365.25
            if pet.neutered and age_join < 0.6:
                d = int(pet.birth_day + rng.uniform(180, 240))
                d = max(d, pet.join_day + 7)
                if self.alive(pet, d):
                    self.add_visit(pet, d, "procedure", "elective", procedure="spay" if pet.sex == "F" else "neuter")
        rules = {"mass_neoplasia": ("mass_removal", 0.5, (7, 30), False),
                 "cruciate_injury": ("cruciate_repair", 0.7, (5, 30), False),
                 "ivdd": ("ivdd_surgery", 0.35, (0, 2), True)}
        for v in list(self.visits):
            if v["visit_type"] != "sick" or v["dx"] not in rules:
                continue
            name, p, (lo, hi), emerg = rules[v["dx"]]
            pet = self.pet(v["pet_uid"])
            if rng.random() < p:
                d = int(v["day"] + rng.integers(lo, hi + 1))
                if self.alive(pet, d):
                    self.add_visit(pet, d, "procedure", v["dx"], procedure=name, emergency=emerg)

    # ------------------------------------------------------------------ 4. parasiticides + seizures
    def parasiticides_and_seizures(self):
        rng, sz = self.rng, P["seizure"]
        by_pet = {}
        for v in self.visits:
            if v["visit_type"] == "wellness":
                by_pet.setdefault(v["pet_uid"], []).append(v)
        for pet in self.pets.itertuples():
            if pd.isna(pet.home_vet):
                continue
            sp = pet.species
            wv = sorted(by_pet.get(pet.pet_uid, []), key=lambda v: v["day"])
            # dispensing schedule: at wellness visits, plus a pharmacy refill ~6 months later
            disp = []
            for v in wv:
                if rng.random() < (0.7 if sp == "dog" else 0.45):
                    disp.append((v["day"], v))
                    if rng.random() < 0.4:
                        disp.append((v["day"] + int(rng.integers(150, 210)), None))
                if sp == "dog" and rng.random() < 0.65:
                    hw = rng.choice(HEARTWORM[0], p=HEARTWORM[1])
                    self.add_rx(pet, v["day"], hw, "Macrocyclic lactone", "heartworm_prevention", 180, v)
            disp = sorted([d for d in disp if self.alive(pet, d[0])], key=lambda x: x[0])
            # seizure process, piecewise in time so product choice can depend on seizures already on record
            start, end = max(pet.join_day, 0), min(pet.exit_day, self.n)
            if end <= start:
                continue
            exposed = np.zeros(self.n + 400, bool)
            known = bool(pet.epileptic and pet.epilepsy_onset_day < start)  # diagnosed before the window
            days = np.arange(start, end)
            base = np.where(pet.epileptic & (days >= (pet.epilepsy_onset_day if pet.epileptic else 1e9)),
                            sz["epileptic_rate"], sz["dog_rate"] if sp == "dog" else sz["cat_rate"]) / 365.25
            u = rng.random(end - start)
            cuts = [start] + [d for d, _ in disp] + [end]
            for k in range(len(cuts) - 1):
                if k > 0:  # dispensing at cuts[k]; choice depends on seizures already on record
                    d, v = disp[k - 1]
                    w = sz["channeling_mult"] if known else 1.0
                    isox = rng.random() < (0.6 if sp == "dog" else 0.4) * w
                    drug = rng.choice(FLEA_ISOX[sp] if isox else FLEA_OTHER[sp])
                    self.add_rx(pet, d, drug, "Isoxazoline" if isox else "Other ectoparasiticide",
                                "flea_tick", int(rng.choice([90, 180, 365])), v, is_isoxazoline=bool(isox),
                                channeled=known)
                    if isox:
                        exposed[d:d + sz["isox_window"]] = True
                lo, hi = cuts[k] - start, cuts[k + 1] - start
                if hi <= lo:
                    continue
                seg = np.arange(lo, hi)
                rate = base[seg] * np.where(exposed[seg + start], sz["isox_rr"], 1.0)
                for i in seg[u[seg] < rate]:
                    day = int(start + i)
                    presented = rng.random() < sz["presented"]
                    ev = dict(pet_uid=pet.pet_uid, outcome="seizure", day=day, exposed_isox=bool(exposed[day]),
                              epileptic=bool(pet.epileptic), presented=presented, visit_id=None)
                    if presented:
                        ev["visit_id"] = self.add_visit(pet, day, "sick", "seizure", ae_outcome="seizure")["visit_id"]
                        known = True
                    self.ae.append(ev)

    # ------------------------------------------------------------------ 5. NSAIDs + GI and neuro events
    def nsaids_and_events(self):
        rng, gi, ne = self.rng, P["gi"], P["neuro"]
        for v in list(self.visits):
            pet = self.pet(v["pet_uid"])
            sp = pet.species
            post_op = {"spay": (0.8, 5), "neuter": (0.8, 5), "cruciate_repair": (1.0, 14), "mass_removal": (0.5, 5),
                       "ivdd_surgery": (0.6, 14)}
            if v["visit_type"] == "procedure" and v.get("procedure") in post_op:
                p, days = post_op[v["procedure"]]
                if rng.random() < p:
                    names, w = (["carprofen", "meloxicam", "robenacoxib"], [0.5, 0.35, 0.15]) if sp == "dog" else NSAID_CAT
                    self.add_rx(pet, v["day"], rng.choice(names, p=w), "NSAID", "post_operative", days, v)
            elif v["visit_type"] in ("sick", "recheck") and v["dx"] in ("osteoarthritis", "cruciate_injury", "ivdd"):
                if rng.random() < {"osteoarthritis": 0.7, "cruciate_injury": 0.9, "ivdd": 0.6}[v["dx"]]:
                    names, w = NSAID_DOG if sp == "dog" else NSAID_CAT
                    self.add_rx(pet, v["day"], rng.choice(names, p=w), "NSAID", v["dx"], 30 if v["dx"] == "osteoarthritis"
                                else 14, v)
        rx = pd.DataFrame(self.rx)
        cox = rx[rx.drug.isin(COX)].groupby("pet_uid").day.apply(list).to_dict()
        ml = rx[rx.drug_class == "Macrocyclic lactone"].groupby("pet_uid").day.apply(list).to_dict()
        for pet in self.pets.itertuples():
            if pd.isna(pet.home_vet):
                continue
            start, end = max(pet.join_day, 0), min(pet.exit_day, self.n)
            if end <= start:
                continue
            for outcome, rate, rr, window, starts, presented in [
                ("vomiting_diarrhea", gi["rate"], gi["cox_rr"], gi["window"], cox.get(pet.pet_uid, []), gi["presented"]),
                ("neuro_signs", ne["rate"] if pet.species == "dog" else 0.0,
                 ne["ml_mdr1_rr"] if pet.breed in ne["mdr1_breeds"] else 1.0, ne["window"], ml.get(pet.pet_uid, []),
                 ne["presented"])]:
                if rate == 0:
                    continue
                exp = np.zeros(self.n + 400, bool)
                for d in starts:
                    exp[d:d + window] = True
                h = np.full(end - start, rate / 365.25)
                h[exp[start:end]] *= rr
                for i in np.flatnonzero(rng.random(end - start) < h):
                    day = start + int(i)
                    pres = rng.random() < presented
                    ev = dict(pet_uid=pet.pet_uid, outcome=outcome, day=day, exposed=bool(exp[day]), presented=pres,
                              visit_id=None)
                    if outcome == "vomiting_diarrhea":
                        ev["exposed_cox"] = bool(exp[day])
                    else:
                        ev["exposed_ml"] = bool(exp[day])
                    if pres:
                        ev["visit_id"] = self.add_visit(pet, day, "sick", outcome, ae_outcome=outcome)["visit_id"]
                    self.ae.append(ev)

    # ------------------------------------------------------------------ 6. dental (latent grade + charting + cleanings)
    def dental(self):
        rng, dp = self.rng, P["dental"]
        by_pet = {}
        for v in self.visits:
            by_pet.setdefault(v["pet_uid"], []).append(v)
        base_dental = self.ill[self.ill.condition == "dental_disease"].groupby("pet_uid").event_day.apply(list).to_dict()
        latent_rows = []
        for pet in self.pets.itertuples():
            vs = by_pet.get(pet.pet_uid)
            if not vs:
                continue
            mult = dp["size_mult"][pet.size] * (dp["overweight_mult"] if pet.overweight else 1.0) * \
                R.BREED_RR.get(pet.breed, {}).get("dental_disease", 1.0)
            # history from age 1 to window start
            grade = 0
            d0 = int(pet.birth_day + 365)
            day = d0
            first = max(pet.join_day, 0)
            while day < first:
                a = self.age(pet, day)
                grade = self._step(grade, mult, a, rng)
                day += 30
            if grade >= 2 and rng.random() < 0.3:  # cleaned before the window
                grade = 0
            q = [(v["day"], 0, i, v) for i, v in enumerate(vs)]
            for d in base_dental.get(pet.pet_uid, []):
                q.append((int(d), -1, -1, "base_dental"))
            heapq.heapify(q)
            seq = len(vs)
            day = max(day, first)
            cleaned_until = -1
            while q:
                d, _, _, item = heapq.heappop(q)
                while day + 30 <= d:
                    grade = self._step(grade, mult, self.age(pet, day), rng)
                    day += 30
                if item == "base_dental":
                    grade = max(grade, 2)
                    continue
                v = item
                c = self.clinics[v["clinic"]]
                if v.get("procedure") == "dental_cleaning":
                    v["dental_grade"] = max(grade, 1) if grade else int(rng.choice([1, 2]))
                    latent_rows.append(dict(pet_uid=pet.pet_uid, day=d, latent_grade=grade, event="cleaning"))
                    grade = 0
                    continue
                p_chart = dp["detect_by_visit"].get(v["visit_type"], 0.2) * c["dental_thoroughness"]
                if rng.random() < p_chart:
                    if grade == 0:
                        rec = 1 if rng.random() < 0.05 else (2 if rng.random() < 0.01 else 0)
                    else:
                        rec = grade if rng.random() < min(1.0, 0.6 + 0.1 * grade) else max(0, grade - 1)
                    v["dental_grade"] = int(rec)
                    if v["visit_type"] == "wellness" and rec >= 2 and d > cleaned_until and \
                            rng.random() < dp["cleaning_after_detection"]:
                        cd = int(d + rng.integers(14, 91))
                        if self.alive(pet, cd):
                            nv = self.add_visit(pet, cd, "procedure", "dental_disease", procedure="dental_cleaning",
                                                exam_driven=True)
                            seq += 1
                            heapq.heappush(q, (cd, 1, seq, nv))
                            cleaned_until = cd + 120
                latent_rows.append(dict(pet_uid=pet.pet_uid, day=d, latent_grade=grade, event=v["visit_type"]))
        self.dental_truth = pd.DataFrame(latent_rows)

    @staticmethod
    def _step(grade, mult, age, rng):
        dp = P["dental"]
        if grade == 0:
            h = dp["h0"] * mult * np.exp(dp["age_log_slope"] * (age - 5))
            return 1 if rng.random() < 1 - np.exp(-h / 12) else 0
        if grade < 4 and rng.random() < 1 - np.exp(-dp["progress_per_year"] / 12):
            return grade + 1
        return grade

    # ------------------------------------------------------------------ 7. anesthesia
    def anesthesia(self):
        rng, an = self.rng, P["anesthesia"]
        chronic = self.ill[self.ill.condition.isin(["mitral_valve_disease", "chronic_kidney_disease",
                                                    "hypertrophic_cardiomyopathy"])].groupby("pet_uid").event_day.min()
        rows = []
        for v in self.visits:
            if v["visit_type"] != "procedure":
                continue
            pet = self.pet(v["pet_uid"])
            age = self.age(pet, v["day"])
            emerg = bool(v.get("emergency", False))
            asa = 1
            if (age >= 8 or pet.overweight or pet.brachy) and rng.random() < 0.7:
                asa = 2
            if pet.pet_uid in chronic.index and chronic[pet.pet_uid] <= v["day"] and rng.random() < 0.8:
                asa = 3
            if age >= 12 and rng.random() < 0.3:
                asa = max(asa, 3)
            if emerg:
                asa = max(asa, 3 if rng.random() < 0.6 else 4)
            wkg = pet.weight_lb / 2.2046 * (1.15 if pet.overweight else 1.0)
            rows.append(dict(proc_id=f"PR{len(rows) + 1:06d}", visit_id=v["visit_id"], pet_uid=pet.pet_uid,
                             clinic=v["clinic"], day=v["day"], procedure=v["procedure"], species=pet.species,
                             breed=pet.breed, age_years=round(age, 2), weight_kg=round(wkg, 1), asa=asa,
                             emergency=emerg, brachycephalic=bool(pet.brachy),
                             preanes_bloodwork=bool(rng.random() < self.clinics[v["clinic"]]["preanes_bloodwork"]
                                                    or asa >= 3)))
        d = pd.DataFrame(rows)
        o = an["or_death"]
        lin = (np.log(o["brachy"]) * d.brachycephalic + np.log(o["dog_lt5kg"]) * ((d.species == "dog") & (d.weight_kg < 5))
               + np.log(o["age12"]) * (d.age_years >= 12) + np.log(o["emergency"]) * d.emergency
               + d.clinic.map({k: c["death_log_or"] for k, c in self.clinics.items()}))
        lin_c = np.log(an["or_comp_brachy"]) * d.brachycephalic + d.clinic.map(
            {k: c["comp_log_or"] for k, c in self.clinics.items()})
        d["grp"] = np.where(d.asa >= 3, "high", "low")
        d["p_death"] = 0.0
        d["p_comp"] = 0.0
        self.calib = {}
        for (sp, g), idx in d.groupby(["species", "grp"]).groups.items():
            tgt = an["death"][sp][g]
            a = brentq(lambda a: expit(a + lin[idx]).mean() - tgt, -20, 5)
            d.loc[idx, "p_death"] = expit(a + lin[idx])
            self.calib[f"death_{sp}_{g}"] = a
        for g, idx in d.groupby("grp").groups.items():
            tgt = an["complication"][g]
            a = brentq(lambda a: expit(a + lin_c[idx]).mean() - tgt, -20, 5)
            d.loc[idx, "p_comp"] = expit(a + lin_c[idx])
            self.calib[f"comp_{g}"] = a
        d["death_48h"] = rng.random(len(d)) < d.p_death
        comp = rng.random(len(d)) < d.p_comp
        kinds = np.array(["hypotension", "hypothermia", "regurgitation", "prolonged_recovery", "airway_obstruction"])
        pick = np.where(d.brachycephalic & (rng.random(len(d)) < 0.5), 4, rng.integers(0, 4, len(d)))
        d["complication"] = np.where(comp | d.death_48h, kinds[pick], None)
        self.procedures_df = d.drop(columns=["grp"])
        # perioperative antibiotics at dental cleanings
        for r in d[d.procedure == "dental_cleaning"].itertuples():
            if rng.random() < self.clinics[r.clinic]["p_dental_abx"]:
                drug = rng.choice(["clindamycin", "amoxicillin-clavulanate"], p=[0.6, 0.4])
                vv = {"visit_id": r.visit_id, "clinic": r.clinic}
                self.add_rx(self.pet(r.pet_uid), r.day, drug, DRUGS[drug]["cls"], "dental_prophylaxis", 7, vv,
                            culture_before=False, choice_tier="not_indicated", is_hpcia=False)

    # ------------------------------------------------------------------ 8. labs
    def kidney(self, pet, day):
        """Latent kidney-loss fraction f at day (0 healthy, 1 at diagnosis)."""
        if pd.isna(pet.ckd_dx_day):
            return 0.0
        D, L = pet.ckd_dx_day, pet.ckd_lead_days
        if day < D - L:
            return 0.0
        if day <= D:
            return (day - (D - L)) / L
        return 1 + P["ckd"]["post_dx_f_per_year"] * (day - D) / 365.25

    def panel(self, pet, v, reason):
        rng = self.rng
        f = self.kidney(pet, v["day"]) if pet.species == "cat" else 0.0
        age = self.age(pet, v["day"])
        c0 = pet.creat0 + 0.01 * max(0.0, age - 5)
        creat = c0 + (P["ckd"]["creat_at_dx"] - c0) * f ** 3 if f > 0 else c0
        creat = max(0.3, creat + rng.normal(0, 0.06 + 0.04 * creat))
        sdma = pet.sdma0 + 10 * np.sqrt(f) + rng.normal(0, 1.5)
        bun = (22 if pet.species == "cat" else 16) + 14 * (creat - c0) + rng.normal(0, 3)
        usg = max(1.006, pet.usg0 - 0.025 * min(f, 1.4) + rng.normal(0, 0.004))
        upc = pet.upc0 * (1 + 2.5 * f) * rng.lognormal(0, 0.25)
        ph = rng.normal(6.4, 0.3) + 0.05 * f
        wbc = rng.normal(9, 2.5)
        vals = dict(creatinine_mg_dl=round(creat, 2), bun_mg_dl=round(bun, 1), sdma_ug_dl=round(max(sdma, 4), 1),
                    usg=round(usg, 3), upc=round(upc, 2), urine_ph=round(ph, 1), wbc_k_ul=round(max(wbc, 2), 1))
        has_ua = rng.random() < 0.7
        for k, val in vals.items():
            if k in ("usg", "upc", "urine_ph") and not has_ua:
                continue
            self.labs.append(dict(visit_id=v["visit_id"], pet_uid=pet.pet_uid, clinic=v["clinic"], day=v["day"],
                                  reason=reason, analyte=k, value=val))

    def lab_panels(self):
        rng = self.rng
        pre = set(self.procedures_df[self.procedures_df.preanes_bloodwork].visit_id)
        renal = {"chronic_kidney_disease", "mitral_valve_disease", "hypertrophic_cardiomyopathy"}
        for v in self.visits:
            pet = self.pet(v["pet_uid"])
            c = self.clinics[v["clinic"]]
            age = self.age(pet, v["day"])
            reason = None
            if v["visit_id"] in pre:
                reason = "pre_anesthetic"
            elif v["dx"] in renal and v["visit_type"] in ("sick", "recheck"):
                reason = "diagnostic"
            elif v["visit_type"] == "wellness" and rng.random() < (0.6 if age >= 7 else 0.1) * c["lab_intensity"]:
                reason = "senior_screen" if age >= 7 else "wellness_screen"
            elif v["visit_type"] == "sick" and age >= 7 and rng.random() < 0.3 * c["lab_intensity"]:
                reason = "diagnostic"
            if reason:
                self.panel(pet, v, reason)

    # ------------------------------------------------------------------ 9. notes, weights, patients
    def finish(self):
        from tailsignal.synth import ehr_notes as N
        rng = self.rng
        rx_by_visit = {}
        for r in self.rx:
            if r["visit_id"]:
                rx_by_visit.setdefault(r["visit_id"], []).append(r["drug"])
        proc = self.procedures_df.set_index("visit_id")
        hist_gi = set(e["pet_uid"] for e in self.ae if e["outcome"] == "vomiting_diarrhea" and e["presented"])
        for v in self.visits:
            pet = self.pet(v["pet_uid"])
            wkg = pet.weight_lb / 2.2046 * (1.15 if pet.overweight else 1.0)
            v["weight_kg"] = round(float(wkg * rng.normal(1, 0.03)), 1)
            v["bcs"] = int(rng.choice([6, 7, 8], p=[0.5, 0.35, 0.15]) if pet.overweight else rng.choice([4, 5, 5]))
            known_ep = bool(pet.epileptic and v["day"] > pet.epilepsy_onset_day)
            text, labels = N.note(rng, v, pet, rx_by_visit.get(v["visit_id"], []),
                                  proc.loc[v["visit_id"]].to_dict() if v["visit_id"] in proc.index else None,
                                  known_epileptic=known_ep)
            self.notes.append(dict(visit_id=v["visit_id"], pet_uid=v["pet_uid"], clinic=v["clinic"], day=v["day"],
                                   text=text, **labels))
        # patients: one record per pet x clinic, microchip captured with clinic-specific probability
        pts, seqs = [], {}
        for (pid, clinic) in sorted({(v["pet_uid"], v["clinic"]) for v in self.visits}):
            pet = self.pet(pid)
            c = self.clinics[clinic]
            seqs[clinic] = seqs.get(clinic, 0) + 1
            chip = pet.microchip if (pet.microchip and rng.random() < c["chip_capture"]) else None
            if chip and rng.random() < P["microchip"]["error"]:
                i = int(rng.integers(3, 15))
                chip = chip[:i] + str((int(chip[i]) + int(rng.integers(1, 10))) % 10) + chip[i + 1:]
            bdate = G.day_to_date(int(pet.birth_day))
            if rng.random() < 0.3:
                bdate = np.datetime64(str(bdate)[:4] + "-01-01")
            pts.append(dict(clinic=clinic, clinic_patient_id=f"{clinic}-{seqs[clinic]:05d}", pet_uid=pid,
                            pet_name=pet.pet_name, species=pet.species, breed_text=pet.breed,
                            sex=pet.sex, birth_date=str(bdate), microchip=chip))
        self.patients = pd.DataFrame(pts)

    # ------------------------------------------------------------------ run
    def run(self):
        self.latent()
        self.base_visits()
        self.infections_and_abx()
        self.procedures()
        self.parasiticides_and_seizures()
        self.nsaids_and_events()
        self.dental()
        self.anesthesia()
        self.lab_panels()
        self.finish()
        return self


def truncate_after_death(e: EHR, tables: dict) -> dict:
    deaths = e.procedures_df[e.procedures_df.death_48h].groupby("pet_uid").day.min()
    out = {}
    for k, df in tables.items():
        if "pet_uid" in df and "day" in df and len(deaths):
            dd = df.pet_uid.map(deaths)
            df = df[dd.isna() | (df.day <= dd)]
        out[k] = df.reset_index(drop=True)
    return out


def write(e: EHR, out: Path):
    raw, truth = out / "raw" / "ehr", out / "truth" / "ehr"
    raw.mkdir(parents=True, exist_ok=True)
    truth.mkdir(parents=True, exist_ok=True)
    pt = e.patients.set_index(["pet_uid", "clinic"]).clinic_patient_id

    def with_patient(df):
        df = df.copy()
        df.insert(1, "clinic_patient_id", [pt.get((p, c)) for p, c in zip(df.pet_uid, df.clinic)])
        return df

    visits = pd.DataFrame(e.visits).sort_values(["day", "visit_id"])
    tables = {
        "ehr_visits": visits, "ehr_prescriptions": pd.DataFrame(e.rx), "ehr_procedures": e.procedures_df,
        "ehr_labs": pd.DataFrame(e.labs), "ehr_cultures": pd.DataFrame(e.cultures), "ehr_notes": pd.DataFrame(e.notes),
    }
    tables = truncate_after_death(e, tables)
    label_cols = [c for c in tables["ehr_notes"].columns if c.startswith("label_")]
    tables["note_labels"] = tables["ehr_notes"][["visit_id"] + label_cols]
    tables["ehr_notes"] = tables["ehr_notes"].drop(columns=label_cols)
    for k in ["ehr_visits", "ehr_prescriptions", "ehr_procedures", "ehr_labs", "ehr_cultures", "ehr_notes"]:
        df = tables[k]
        drop = [c for c in ("base_visit_index", "p_death", "p_comp", "exam_driven", "ae_outcome") if c in df]
        if k == "ehr_visits":
            tables["visit_truth"] = df[["visit_id"] + drop]
        if k == "ehr_procedures":
            tables["procedure_truth"] = df[["proc_id"] + [c for c in ("p_death", "p_comp") if c in df]]
        pub = df.drop(columns=drop + (["breed", "species"] if k == "ehr_procedures" else []))
        pub = pub.drop(columns=[c for c in ("is_isoxazoline", "channeled") if c in pub])
        with_patient(pub).drop(columns=["pet_uid"]).to_parquet(raw / f"{k}.parquet", index=False)
    e.patients.drop(columns=["pet_uid"]).to_parquet(raw / "ehr_patients.parquet", index=False)
    # truth
    e.patients[["clinic", "clinic_patient_id", "pet_uid", "microchip"]].to_parquet(truth / "patient_map.parquet",
                                                                                   index=False)
    tables["note_labels"].to_parquet(truth / "note_labels.parquet", index=False)
    tables["visit_truth"].to_parquet(truth / "visit_truth.parquet", index=False)
    tables["procedure_truth"].to_parquet(truth / "procedure_truth.parquet", index=False)
    rx = pd.DataFrame(e.rx)
    rx.to_parquet(truth / "prescriptions_with_pet.parquet", index=False)
    pd.DataFrame(e.ae).to_parquet(truth / "ae_events.parquet", index=False)
    pd.DataFrame(e.infections).to_parquet(truth / "infections.parquet", index=False)
    e.dental_truth.to_parquet(truth / "dental_latent.parquet", index=False)
    e.pets[["pet_uid", "overweight", "epileptic", "epilepsy_onset_day", "microchip", "brachy", "ckd_dx_day",
            "ckd_future", "ckd_lead_days", "creat0", "sdma0"]].reset_index(drop=True).to_parquet(
        truth / "pet_latent.parquet", index=False)
    pd.DataFrame(e.clinics.values()).to_parquet(truth / "clinic_effects.parquet", index=False)
    (truth / "planted_params.json").write_text(json.dumps({"params": P, "calibrated_intercepts": e.calib,
                                                           "seed_offset": SEED_OFFSET}, indent=2, default=str))
    summary = {k: int(len(v)) for k, v in tables.items() if k.startswith("ehr_")}
    summary["ehr_patients"] = int(len(e.patients))
    summary["anesthetic_deaths"] = int(e.procedures_df.death_48h.sum())
    (truth / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def build(cfg: G.Config) -> EHR:
    locs, pets, ill, vet = base_world(cfg)
    return EHR(cfg, locs, pets, ill, vet, cfg.seed + SEED_OFFSET).run()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--households", type=int, default=9000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("data"))
    a = ap.parse_args()
    cfg = G.Config(seed=a.seed, n_households=a.households, out_dir=a.out)
    e = build(cfg)
    print(json.dumps(write(e, a.out), indent=2))


if __name__ == "__main__":
    main()
