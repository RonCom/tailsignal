"""Synthetic multi-channel pet care data generator.

Simulates households and pets moving through veterinary clinics (three different
practice-management systems), daycare/boarding, grooming, and a wellness-plan provider.
Each source writes data the way that kind of system would: different schemas, ID
schemes, date formats, units, code systems, and data-entry noise. Ground truth
(true pet identity, latent segment, illness events, randomized-experiment effects)
is written separately to data/truth/ for evaluation only.

Usage:
    python -m tailsignal.synth.generate --households 9000 --seed 42
"""
from __future__ import annotations

import argparse
import json
import string
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import reference as R

START = np.datetime64("2022-01-01")
END = np.datetime64("2025-12-31")


@dataclass
class Config:
    seed: int = 42
    n_households: int = 9000
    prodrome_prob: float = 0.5  # P(an illness shows a pre-visit signal in non-vet channels)
    out_dir: Path = Path("data")
    start: np.datetime64 = START
    end: np.datetime64 = END
    n_days: int = field(init=False)

    def __post_init__(self):
        self.n_days = int((self.end - self.start).astype(int)) + 1


# ----------------------------------------------------------------------------- helpers
def day_to_date(d):
    return START + np.asarray(d, dtype="int64").astype("timedelta64[D]")


def typo(s: str, rng) -> str:
    if len(s) < 3:
        return s
    i = int(rng.integers(1, len(s) - 1))
    op = rng.integers(0, 3)
    if op == 0:  # swap
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if op == 1:  # drop
        return s[:i] + s[i + 1:]
    return s[:i] + rng.choice(list(string.ascii_lowercase)) + s[i + 1:]


def fmt_phone(p: str, style: str) -> str:
    if not isinstance(p, str) or not p:
        return ""
    if style == "paren":
        return f"({p[:3]}) {p[3:6]}-{p[6:]}"
    if style == "dash":
        return f"{p[:3]}-{p[3:6]}-{p[6:]}"
    if style == "dot":
        return f"{p[:3]}.{p[3:6]}.{p[6:]}"
    if style == "plus1":
        return f"+1{p}"
    return p


AREA_CODES = {"PHL": ["215", "267", "610", "484"], "AUS": ["512", "737"], "MSP": ["612", "651", "952", "763"]}
STREETS = ["Maple", "Oak", "Cedar", "Pine", "Elm", "Walnut", "Chestnut", "Lancaster", "Main", "Park", "Lake",
           "Hillside", "Ridge", "Spring", "Willow", "Highland", "Sunset", "River", "Church", "Mill"]
STREET_TYPES = [("Street", "St"), ("Avenue", "Ave"), ("Road", "Rd"), ("Lane", "Ln"), ("Drive", "Dr")]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "aol.com", "comcast.net"]


# ----------------------------------------------------------------------------- locations
def build_locations() -> pd.DataFrame:
    rows = []
    pims = {"PHL": ["vet_alpha", "vet_alpha", "vet_beta"], "AUS": ["vet_beta", "vet_gamma", "vet_gamma"],
            "MSP": ["vet_alpha", "vet_beta", "vet_gamma"]}
    for m, systems in pims.items():
        for i, s in enumerate(systems, 1):
            rows.append((f"{m}-VET{i}", "vet", s, m, 0))
        for i in (1, 2):
            open_day = int((np.datetime64("2023-06-01") - START).astype(int)) if (m == "AUS" and i == 2) else 0
            rows.append((f"{m}-DC{i}", "daycare_boarding", "pawstay", m, open_day))
            rows.append((f"{m}-GR{i}", "grooming", "groomly", m, 0))
    return pd.DataFrame(rows, columns=["location_id", "channel", "source_system", "market", "open_day"])


# ----------------------------------------------------------------------------- households
def build_households(cfg: Config, rng) -> pd.DataFrame:
    n = cfg.n_households
    markets = list(R.MARKETS)
    mw = np.array([R.MARKETS[m]["weight"] for m in markets])
    market = rng.choice(markets, size=n, p=mw / mw.sum())
    segs = list(R.SEGMENTS)
    sw = np.array([R.SEGMENTS[s][0] for s in segs])
    segment = rng.choice(segs, size=n, p=sw / sw.sum())

    zip_suffix = [f"{i:02d}" for i in rng.choice(100, size=15, replace=False)]

    def zip_for(m):
        return rng.choice(R.MARKETS[m]["zip3"]) + rng.choice(zip_suffix)

    def phone_for(m):
        return rng.choice(AREA_CODES[m]) + f"{rng.integers(200, 999)}{rng.integers(0, 10000):04d}"

    first = rng.choice(R.FIRST_NAMES, size=n)
    last = rng.choice(R.LAST_NAMES, size=n)
    recs = []
    for i in range(n):
        m = market[i]
        f, l = first[i], last[i]
        style = rng.integers(0, 4)
        dom = rng.choice(EMAIL_DOMAINS)
        if style == 0:
            email = f"{f}.{l}@{dom}".lower()
        elif style == 1:
            email = f"{f[0]}{l}{rng.integers(1, 99)}@{dom}".lower()
        elif style == 2:
            email = f"{l}{f[0]}@{dom}".lower()
        else:
            email = f"{f}{rng.integers(70, 99)}@{dom}".lower()
        st, (st_long, st_short) = rng.choice(STREETS), STREET_TYPES[rng.integers(0, len(STREET_TYPES))]
        num = int(rng.integers(10, 9999))
        moved = rng.random() < 0.08
        move_day = int(rng.integers(90, cfg.n_days - 90)) if moved else -1
        recs.append(dict(
            household_uid=f"H{i:06d}", market=m, segment=segment[i], first_name=f, last_name=l,
            email=email, phone=phone_for(m), zip=zip_for(m), street=f"{num} {st} {st_long}",
            street_short=f"{num} {st} {st_short}", move_day=move_day,
            phone_after_move=phone_for(m) if (moved and rng.random() < 0.5) else None,
            zip_after_move=zip_for(m) if moved else None,
            street_after_move=f"{int(rng.integers(10, 9999))} {rng.choice(STREETS)} Street" if moved else None,
            cat_household=rng.random() < 0.28,
        ))
    return pd.DataFrame(recs)


# ----------------------------------------------------------------------------- pets
def build_pets(cfg: Config, hh: pd.DataFrame, rng) -> pd.DataFrame:
    dog_breeds = [b for b in R.BREEDS if b[1] == "dog"]
    cat_breeds = [b for b in R.BREEDS if b[1] == "cat"]
    dw = np.array([b[4] for b in dog_breeds], float)
    cw = np.array([b[4] for b in cat_breeds], float)
    # grooming-focused households skew toward high-groom-need breeds
    dw_groom = dw * np.array([0.3 + 2.0 * b[5] for b in dog_breeds])

    recs = []
    k = 0
    for h in hh.itertuples():
        n_pets = rng.choice([1, 2, 3], p=[0.6, 0.3, 0.1])
        for _ in range(n_pets):
            is_cat = rng.random() < (0.75 if h.cat_household else 0.12)
            if h.segment == "full_service_urban":
                is_cat = is_cat and rng.random() < 0.4
            if is_cat:
                b = cat_breeds[rng.choice(len(cat_breeds), p=cw / cw.sum())]
            else:
                w = dw_groom if h.segment == "grooming_focused" else dw
                b = dog_breeds[rng.choice(len(dog_breeds), p=w / w.sum())]
            joins_later = rng.random() < 0.30
            join_day = int(rng.integers(1, cfg.n_days - 60)) if joins_later else 0
            if joins_later and rng.random() < 0.5:
                age_at_join = rng.uniform(0.15, 0.5)
            else:
                age_at_join = rng.uniform(0.5, 16 if is_cat else 13)
            birth_day = join_day - int(age_at_join * 365.25)
            # exit (death/rehome/move away) hazard rises with age
            exit_day = cfg.n_days
            for yr in range(5):
                age = age_at_join + yr
                p = 0.03 + 0.012 * max(0, age - 8) ** 1.3
                if rng.random() < p:
                    exit_day = min(cfg.n_days, join_day + int((yr + rng.random()) * 365))
                    break
            if exit_day <= join_day + 30:
                exit_day = min(cfg.n_days, join_day + 31)
            recs.append(dict(
                pet_uid=f"P{k:06d}", household_uid=h.household_uid, market=h.market, segment=h.segment,
                species=b[1], breed=b[0], breed_group=b[2], size=b[3], groom_need=b[5],
                pet_name=rng.choice(R.PET_NAMES), sex=rng.choice(["M", "F"]), neutered=rng.random() < 0.8,
                birth_day=birth_day, join_day=join_day, exit_day=exit_day,
                weight_lb=_weight(b[3], rng),
            ))
            k += 1
    return pd.DataFrame(recs)


def _weight(size, rng):
    mu = {"toy": 7, "small": 18, "medium": 40, "large": 72, "cat": 10.5}[size]
    return round(float(rng.normal(mu, mu * 0.15)), 1)


# ----------------------------------------------------------------------------- channel assignment
def assign_channels(pets: pd.DataFrame, locs: pd.DataFrame, rng) -> pd.DataFrame:
    p = pets.copy()
    vets = locs[locs.channel == "vet"]
    dcs = locs[locs.channel == "daycare_boarding"]
    grs = locs[locs.channel == "grooming"]
    home_vet, second_vet, switch_day, dc_site, dc_days, gr_site, gr_interval, board_rate = ([] for _ in range(8))
    for r in p.itertuples():
        seg = R.SEGMENTS[r.segment]
        mv = vets[vets.market == r.market].location_id.tolist()
        uses_vet = rng.random() < (0.85 if r.segment == "low_engagement" else 0.98)
        hv = rng.choice(mv) if uses_vet else None
        home_vet.append(hv)
        if hv and rng.random() < 0.12:
            second_vet.append(rng.choice([v for v in mv if v != hv]))
            switch_day.append(int(rng.integers(r.join_day + 30, max(r.join_day + 31, r.exit_day))))
        else:
            second_vet.append(None)
            switch_day.append(None)
        # daycare
        md = dcs[dcs.market == r.market]
        days = 0.0
        if r.species == "dog" and seg[1] > 0:
            part = 0.9 if seg[1] >= 2 else 0.25
            if rng.random() < part:
                days = float(np.clip(rng.normal(seg[1] if seg[1] >= 2 else 1.2, 0.8), 0.5, 5))
        dc_days.append(days)
        site = rng.choice(md.location_id.tolist())
        dc_site.append(site)
        # boarding trips per year
        board_rate.append(seg[2] * (0.3 if r.species == "cat" else 1.0) * rng.gamma(2, 0.5))
        # grooming
        pg = min(0.97, 0.05 + seg[3] * (0.2 + 0.9 * r.groom_need))
        if r.species == "cat":
            pg *= 0.3
        if rng.random() < pg:
            gr_site.append(rng.choice(grs[grs.market == r.market].location_id.tolist()))
            gr_interval.append(int(np.clip(rng.normal(4 + 10 * (1 - r.groom_need), 1.5), 3, 16)) * 7)
        else:
            gr_site.append(None)
            gr_interval.append(None)
    p["home_vet"], p["second_vet"], p["vet_switch_day"] = home_vet, second_vet, switch_day
    p["daycare_site"], p["daycare_days_per_week"] = dc_site, dc_days
    p["groom_site"], p["groom_interval_days"] = gr_site, gr_interval
    p["boarding_trips_per_year"] = board_rate
    return p


# ----------------------------------------------------------------------------- illness
def simulate_illness(cfg: Config, pets: pd.DataFrame, rng) -> pd.DataFrame:
    conds = list(R.CONDITIONS)
    n_months = cfg.n_days // 30
    rows = []
    for r in pets.itertuples():
        rr = R.BREED_RR.get(r.breed, {})
        had_chronic = set()
        for m in range(n_months):
            d0 = m * 30
            if d0 < r.join_day or d0 >= r.exit_day:
                continue
            age = (d0 - r.birth_day) / 365.25
            for c in conds:
                sp, base, age_eff, acute, sig = R.CONDITIONS[c]
                if sp != "both" and sp != r.species:
                    continue
                if not acute and c in had_chronic:
                    continue
                h = base * np.exp(age_eff * (age - 5)) * rr.get(c, 1.0)
                if r.size == "large" and c in ("osteoarthritis", "cruciate_injury"):
                    h *= 1.3
                if r.size == "toy" and c == "dental_disease":
                    h *= 1.5
                if r.species == "cat" and c == "gastroenteritis":
                    h *= 0.6
                if rng.random() < 1 - np.exp(-h / 12):
                    day = d0 + int(rng.integers(0, 30))
                    if day >= r.exit_day:
                        continue
                    if not acute:
                        had_chronic.add(c)
                    presented = rng.random() < (0.6 if r.segment == "low_engagement" else 0.92)
                    has_prodrome = sig != "none" and rng.random() < cfg.prodrome_prob
                    lead = int(rng.integers(7, 31)) if (acute or c == "gastroenteritis") else int(rng.integers(14, 46))
                    rows.append(dict(pet_uid=r.pet_uid, condition=c, acute=acute, signal_type=sig,
                                     event_day=day, presented_to_vet=presented, has_prodrome=has_prodrome,
                                     prodrome_start_day=day - lead if has_prodrome else None))
    return pd.DataFrame(rows)


def prodrome_windows(ill: pd.DataFrame) -> dict:
    """pet_uid -> list of (start, end, signal_type)."""
    out: dict = {}
    for r in ill[ill.has_prodrome].itertuples():
        out.setdefault(r.pet_uid, []).append((int(r.prodrome_start_day), int(r.event_day), r.signal_type))
    return out


def in_window(windows, day):
    for s, e, sig in windows:
        if s <= day < e:
            return sig
    return None


DAYCARE_VISIBLE = {"gi": 0.8, "mobility": 0.8, "lethargy": 0.8, "skin": 0.3, "ear": 0.3, "lump": 0.1, "dental": 0.2}
GROOM_VISIBLE = {"skin": 0.8, "ear": 0.8, "lump": 0.8, "dental": 0.4, "mobility": 0.4, "gi": 0.1, "lethargy": 0.3}


def staff_note(rng, sig, visibility, base_noise=0.02):
    if sig and rng.random() < visibility.get(sig, 0) * 0.75:
        return rng.choice(R.SIGNAL_NOTES[sig])
    if rng.random() < base_noise:  # false-positive concerning note
        return rng.choice(R.SIGNAL_NOTES[rng.choice(["gi", "mobility", "lethargy", "skin", "ear"])])
    return rng.choice(R.GENERIC_NOTES)


# ----------------------------------------------------------------------------- vet visits
PRICE = {"PHL": 1.05, "AUS": 1.0, "MSP": 0.95}
DX_PRICE = {"allergic_dermatitis": (140, 320), "otitis_externa": (120, 260), "gastroenteritis": (150, 600),
            "dental_disease": (90, 180), "osteoarthritis": (150, 400), "cruciate_injury": (3200, 5800),
            "ivdd": (900, 6500), "mass_neoplasia": (250, 1400), "mitral_valve_disease": (350, 900),
            "chronic_kidney_disease": (250, 700), "hypertrophic_cardiomyopathy": (450, 1100),
            "obesity": (90, 160)}


def simulate_vet(cfg, pets, ill, rng) -> pd.DataFrame:
    rows = []
    ill_by_pet = {k: g for k, g in ill.groupby("pet_uid")} if len(ill) else {}
    for r in pets.itertuples():
        if pd.isna(r.home_vet):
            continue
        adherence = R.SEGMENTS[r.segment][4]

        def clinic_on(day):
            if pd.notna(r.second_vet) and pd.notna(r.vet_switch_day) and day >= r.vet_switch_day:
                return r.second_vet
            return r.home_vet

        d = r.join_day + int(rng.integers(5, 200))
        while d < r.exit_day:
            if rng.random() < adherence:
                vacc = [v for v in R.VACCINES[r.species] if rng.random() < 0.85]
                items = [("Wellness exam", round(rng.uniform(70, 110) * PRICE[r.market], 2))]
                items += [(f"Vaccine - {v}", round(rng.uniform(25, 48) * PRICE[r.market], 2)) for v in vacc]
                rows.append(dict(pet_uid=r.pet_uid, clinic=clinic_on(d), day=d, dx="wellness", items=items))
            d += int(rng.normal(365, 30)) if rng.random() < adherence else int(rng.normal(540, 90))
        g = ill_by_pet.get(r.pet_uid)
        if g is None:
            continue
        for e in g.itertuples():
            if not e.presented_to_vet:
                continue
            lo, hi = DX_PRICE[e.condition]
            rows.append(dict(pet_uid=r.pet_uid, clinic=clinic_on(e.event_day), day=e.event_day, dx=e.condition,
                             items=[("Sick visit exam", round(rng.uniform(80, 130) * PRICE[r.market], 2)),
                                    ("Diagnostics/treatment", round(rng.uniform(lo, hi) * PRICE[r.market], 2))]))
            if not e.acute:  # rechecks
                for k in range(int(rng.integers(0, 3))):
                    dd = e.event_day + int(rng.integers(60, 200)) * (k + 1)
                    if dd < r.exit_day:
                        rows.append(dict(pet_uid=r.pet_uid, clinic=clinic_on(dd), day=dd, dx=e.condition,
                                         items=[("Recheck exam", round(rng.uniform(60, 95) * PRICE[r.market], 2))]))
            if e.condition == "dental_disease" and rng.random() < 0.6:
                dd = e.event_day + int(rng.integers(14, 75))
                if dd < r.exit_day:
                    rows.append(dict(pet_uid=r.pet_uid, clinic=clinic_on(dd), day=dd, dx="dental_disease",
                                     items=[("Dental cleaning under anesthesia",
                                             round(rng.uniform(450, 1100) * PRICE[r.market], 2))]))
    v = pd.DataFrame(rows)
    v = v[(v.day >= 0) & (v.day < cfg.n_days)].sort_values(["day", "pet_uid"]).reset_index(drop=True)
    return v


# ----------------------------------------------------------------------------- daycare / boarding / grooming
MONTH_DAYCARE = np.array([1.0, 1.0, 0.97, 1.0, 1.0, 0.92, 0.85, 0.85, 1.02, 1.03, 0.98, 0.85])
MONTH_BOARD = np.array([0.6, 0.6, 1.1, 0.9, 1.0, 1.3, 1.5, 1.3, 0.8, 0.9, 1.3, 1.6])


def simulate_daycare(cfg, pets, locs, windows, rng) -> pd.DataFrame:
    days = np.arange(cfg.n_days)
    dates = day_to_date(days)
    dow = ((days + 5) % 7)  # 2022-01-01 is Saturday -> dow 5 (Mon=0)
    weekday = dow < 5
    month = (dates.astype("datetime64[M]").astype(int) % 12)
    md = (dates - dates.astype("datetime64[Y]")).astype(int)
    season = MONTH_DAYCARE[month].copy()
    season[(md >= 355) | (md <= 1)] *= 0.5  # Christmas-New Year
    open_day = dict(zip(locs.location_id, locs.open_day))
    out_pet, out_day, out_half = [], [], []
    for r in pets[pets.daycare_days_per_week > 0].itertuples():
        start = max(r.join_day, open_day[r.daycare_site])
        if r.exit_day <= start:
            continue
        # some pets "graduate" from daycare
        stop = r.exit_day if rng.random() < 0.7 else int(rng.integers(start + 1, r.exit_day + 1))
        d = days[start:stop]
        p = (r.daycare_days_per_week / 5.0) * season[start:stop] * weekday[start:stop]
        for s, e, sig in windows.get(r.pet_uid, []):
            if DAYCARE_VISIBLE.get(sig, 0) >= 0.5:
                lo, hi = max(s, start) - start, min(e, stop) - start
                if hi > lo:
                    p[lo:hi] *= 0.45
        hit = rng.random(len(d)) < np.clip(p, 0, 1)
        sel = d[hit]
        out_pet.extend([r.pet_uid] * len(sel))
        out_day.extend(sel.tolist())
        out_half.extend((rng.random(len(sel)) < 0.2).tolist())
    dc = pd.DataFrame({"pet_uid": out_pet, "day": out_day, "half_day": out_half})
    site = dict(zip(pets.pet_uid, pets.daycare_site))
    market = dict(zip(pets.pet_uid, pets.market))
    dc["site"] = dc.pet_uid.map(site)
    base = dc.pet_uid.map(market).map(PRICE).astype(float) * 40
    dc["price"] = np.where(dc.half_day, base * 0.6, base).round(2)
    notes = []
    for pid, day in zip(dc.pet_uid.values, dc.day.values):
        sig = in_window(windows.get(pid, []), day)
        notes.append(staff_note(rng, sig, DAYCARE_VISIBLE) if (sig or rng.random() < 0.25) else "")
    dc["note"] = notes
    return dc


def simulate_boarding(cfg, pets, locs, windows, rng) -> pd.DataFrame:
    mw = MONTH_BOARD / MONTH_BOARD.sum()
    open_day = dict(zip(locs.location_id, locs.open_day))
    rows = []
    for r in pets.itertuples():
        years = (r.exit_day - r.join_day) / 365.25
        n = rng.poisson(r.boarding_trips_per_year * years)
        for _ in range(n):
            # sample a day respecting month seasonality
            for _try in range(10):
                d = int(rng.integers(r.join_day, r.exit_day))
                m = int(day_to_date(d).astype("datetime64[M]").astype(int) % 12)
                if rng.random() < mw[m] / mw.max():
                    break
            if d < open_day[r.daycare_site]:
                continue
            nights = 1 + int(rng.poisson(3.5))
            sig = in_window(windows.get(r.pet_uid, []), d)
            rows.append(dict(pet_uid=r.pet_uid, site=r.daycare_site, check_in=d, nights=nights,
                             room=rng.choice(["Standard", "Standard", "Suite", "Cat Condo"] if r.species == "cat"
                                             else ["Standard", "Standard", "Suite"]),
                             price=round(nights * rng.uniform(48, 85) * PRICE[r.market], 2),
                             note=staff_note(rng, sig, DAYCARE_VISIBLE)))
    return pd.DataFrame(rows)


def simulate_grooming(cfg, pets, windows, rng) -> pd.DataFrame:
    rows = []
    for r in pets[pets.groom_site.notna()].itertuples():
        d = r.join_day + int(rng.integers(0, int(r.groom_interval_days)))
        while d < r.exit_day:
            if rng.random() > 0.08:  # occasional skipped appointment
                svc = "Full Groom" if r.groom_need >= 0.5 else rng.choice(["Bath & Brush", "Bath & Brush", "Nail Trim"])
                if r.species == "cat":
                    svc = rng.choice(["Lion Cut", "Bath & Brush", "Nail Trim"])
                price = {"Full Groom": 95, "Bath & Brush": 55, "Nail Trim": 20, "Lion Cut": 110}[svc]
                price *= {"toy": 0.8, "small": 0.9, "medium": 1.0, "large": 1.35, "cat": 1.0}[r.size]
                sig = in_window(windows.get(r.pet_uid, []), d)
                rows.append(dict(pet_uid=r.pet_uid, site=r.groom_site, day=d,
                                 minute=int(rng.choice([8, 9, 10, 11, 13, 14, 15])) * 60 + int(rng.choice([0, 30])),
                                 service=svc, price=round(price * PRICE[r.market] * rng.uniform(0.95, 1.1), 2),
                                 note=staff_note(rng, sig, GROOM_VISIBLE, base_noise=0.03)))
            d += int(r.groom_interval_days + rng.integers(-7, 15))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- wellness plans + experiment
def simulate_wellness(cfg, pets, vet, rng):
    first_wellness = vet[vet.dx == "wellness"].groupby("pet_uid").agg(day=("day", "min"), clinic=("clinic", "first"))
    rows, exp_rows = [], []
    k = 0
    for r in pets.itertuples():
        if r.pet_uid not in first_wellness.index:
            continue
        seg = R.SEGMENTS[r.segment]
        if rng.random() > seg[5]:
            continue
        start, clinic = first_wellness.loc[r.pet_uid]
        tier = rng.choice(["Basic", "Plus", "Premium"], p=[0.5, 0.35, 0.15])
        fee = {"Basic": 29, "Plus": 45, "Premium": 69}[tier] + (10 if r.species == "dog" and r.size == "large" else 0)
        base = seg[6] * (1.25 if tier == "Premium" else 1.0)
        age0 = (start - r.birth_day) / 365.25
        # heterogeneous treatment effect: segment effect, stronger for senior pets
        tau = seg[7] * (1.5 if age0 >= 8 else 1.0)
        exp_month = 6
        arm = None
        end = None
        month = 0
        d = int(start)
        while d < min(r.exit_day, cfg.n_days):
            month += 1
            if month == exp_month:
                arm = "reminder" if rng.random() < 0.5 else "control"
                exp_day = d
            p = base
            if arm is not None and month > exp_month and month <= exp_month + 6:
                p = max(0.001, base + (tau if arm == "reminder" else 0.0))
            if rng.random() < p:
                end = d
                break
            d += 30
        lapsed_6m = None
        if arm is not None:
            lapsed_6m = end is not None and end <= exp_day + 180
            exp_rows.append(dict(membership_id=f"WP{k:06d}", pet_uid=r.pet_uid, segment=r.segment, arm=arm,
                                 campaign_day=exp_day, pet_age_years=round(age0 + exp_month / 12, 1),
                                 true_tau_monthly=tau, lapsed_within_6m=lapsed_6m))
        rows.append(dict(membership_id=f"WP{k:06d}", pet_uid=r.pet_uid, clinic=clinic, tier=tier, fee=fee,
                         start_day=int(start), end_day=end,
                         cancel_reason=(rng.choice(["Cost", "Moved", "Not using benefits", "Pet passed", "Other"])
                                        if end is not None else None),
                         arm=arm, campaign_day=exp_day if arm is not None else None))
        k += 1
    return pd.DataFrame(rows), pd.DataFrame(exp_rows)


# ----------------------------------------------------------------------------- source views (messy identities)
class IdentityView:
    """How one source system 'knows' a household and pet: frozen at registration with noise."""

    def __init__(self, rng, hh_row, pet_row, reg_day, p_nick, p_typo, p_email_missing, p_breed_variant,
                 p_petname_variant):
        moved = hh_row.move_day >= 0 and reg_day >= hh_row.move_day
        f = hh_row.first_name
        if f in R.NICKNAMES and rng.random() < p_nick:
            f = rng.choice(R.NICKNAMES[f])
        if rng.random() < p_typo:
            f = typo(f, rng)
        l = hh_row.last_name
        if rng.random() < p_typo:
            l = typo(l, rng)
        self.first, self.last = f, l
        self.phone = hh_row.phone_after_move if (moved and isinstance(hh_row.phone_after_move, str)) else hh_row.phone
        if rng.random() < 0.04:
            self.phone = ""
        self.zip = hh_row.zip_after_move if moved else hh_row.zip
        self.street = hh_row.street_after_move if moved else (hh_row.street if rng.random() < 0.5 else hh_row.street_short)
        self.email = "" if rng.random() < p_email_missing else hh_row.email
        if self.email and rng.random() < 0.03:
            self.email = typo(self.email.split("@")[0], rng) + "@" + self.email.split("@")[1]
        pn = pet_row.pet_name
        if pn in R.PET_NAME_VARIANTS and rng.random() < p_petname_variant:
            pn = rng.choice(R.PET_NAME_VARIANTS[pn])
        if rng.random() < p_typo:
            pn = typo(pn, rng)
        self.pet_name = pn
        variants = next(b[6] for b in R.BREEDS if b[0] == pet_row.breed)
        self.breed = rng.choice(variants) if rng.random() < p_breed_variant else pet_row.breed


def _date_str(day, fmt):
    return pd.Timestamp(day_to_date(day)).strftime(fmt)


def write_sources(cfg, hh, pets, vet, dc, board, groom, wp, rng):
    raw = cfg.out_dir / "raw" / "synthetic"
    raw.mkdir(parents=True, exist_ok=True)
    hh_i = hh.set_index("household_uid")
    pets_i = pets.set_index("pet_uid")
    record_map = []

    # ---------------- vet systems: one patient record per (clinic, pet)
    vet = vet.copy()
    vet["system"] = vet.clinic.str.extract(r"^(\w+)-")[0]  # market prefix; system from locs below
    locs = build_locations()
    sys_of = dict(zip(locs.location_id, locs.source_system))
    vet["system"] = vet.clinic.map(sys_of)

    patients = vet.groupby(["system", "clinic", "pet_uid"]).day.min().reset_index().rename(columns={"day": "reg_day"})
    patients["patient_id"] = [f"{i:07d}" for i in rng.permutation(10**6)[: len(patients)] + 1_000_000]
    # client ids: per clinic per household
    patients["household_uid"] = patients.pet_uid.map(pets_i.household_uid)
    cl = patients[["clinic", "household_uid"]].drop_duplicates().reset_index(drop=True)
    cl["client_id"] = [f"C{i:06d}" for i in rng.permutation(10**6)[: len(cl)]]
    patients = patients.merge(cl, on=["clinic", "household_uid"])
    views = {}
    for p in patients.itertuples():
        v = IdentityView(rng, hh_i.loc[p.household_uid], pets_i.loc[p.pet_uid], p.reg_day,
                         p_nick=0.15, p_typo=0.03, p_email_missing=0.12, p_breed_variant=0.3, p_petname_variant=0.08)
        views[(p.clinic, p.pet_uid)] = v
    pmap = patients.set_index(["clinic", "pet_uid"])
    vet["visit_no"] = np.arange(len(vet)) + 500000

    # alpha: flat CSV
    a = vet[vet.system == "vet_alpha"]
    rows = []
    for e in a.itertuples():
        pt = pmap.loc[(e.clinic, e.pet_uid)]
        v = views[(e.clinic, e.pet_uid)]
        pr = pets_i.loc[e.pet_uid]
        code, desc = R.DX_ALPHA[e.dx]
        rows.append(dict(clinic_id=e.clinic, client_id=pt.client_id, client_first_name=v.first,
                         client_last_name=v.last, client_phone=fmt_phone(v.phone, "paren"), client_email=v.email,
                         client_address=v.street, client_zip=v.zip, patient_id=pt.patient_id, patient_name=v.pet_name,
                         species="Canine" if pr.species == "dog" else "Feline", breed=v.breed,
                         sex=pr.sex + ("N" if pr.neutered and pr.sex == "M" else "S" if pr.neutered else ""),
                         dob=_date_str(pr.birth_day, "%Y-%m-%d"), weight_lb=pr.weight_lb,
                         visit_id=f"V{e.visit_no}", visit_date=_date_str(e.day, "%Y-%m-%d"), dx_code=code,
                         dx_desc=desc, line_items=";".join(f"{n}:{amt:.2f}" for n, amt in e.items),
                         invoice_total=round(sum(x[1] for x in e.items), 2)))
    pd.DataFrame(rows).to_csv(raw / "vet_alpha_visits.csv", index=False)
    for (clinic, pet_uid), pt in pmap.iterrows():
        if pt.system == "vet_alpha":
            record_map.append(("vet_alpha", f"{clinic}|{pt.patient_id}", pet_uid))

    # beta: nested JSONL, age instead of DOB, kg, MM/DD/YYYY
    b = vet[vet.system == "vet_beta"]
    with open(raw / "vet_beta_encounters.jsonl", "w") as fh:
        for e in b.itertuples():
            pt = pmap.loc[(e.clinic, e.pet_uid)]
            v = views[(e.clinic, e.pet_uid)]
            pr = pets_i.loc[e.pet_uid]
            code, text = R.DX_BETA[e.dx]
            rec = {"encounter_id": f"E{e.visit_no}", "site": e.clinic, "date": _date_str(e.day, "%m/%d/%Y"),
                   "client": {"id": pt.client_id, "name": f"{v.last.upper()}, {v.first}",
                              "phones": [p for p in [fmt_phone(v.phone, "dash")] if p], "email": v.email or None,
                              "zip": v.zip},
                   "patient": {"id": pt.patient_id, "name": v.pet_name, "species": "D" if pr.species == "dog" else "C",
                               "breed": v.breed, "sex": pr.sex,
                               "age_years_at_reg": max(0, int((pt.reg_day - pr.birth_day) / 365.25)),
                               "registered": _date_str(pt.reg_day, "%Y-%m-%d"),
                               "weight_kg": round(pr.weight_lb * 0.4536, 1)},
                   "diagnoses": [{"code": code, "text": text}],
                   "charges": [{"item": n, "amount": amt} for n, amt in e.items]}
            fh.write(json.dumps(rec) + "\n")
    for (clinic, pet_uid), pt in pmap.iterrows():
        if pt.system == "vet_beta":
            record_map.append(("vet_beta", f"{clinic}|{pt.patient_id}", pet_uid))

    # gamma: pipe-delimited, no patient id, free-text reason, owner account number only
    g = vet[vet.system == "vet_gamma"]
    lines = ["CLINIC|ACCT|OWNER_NAME|PHONE|EMAIL|ZIP|PET_NAME|SPECIES|BREED|BIRTH|SEX|VISIT_NO|VISIT_DT|REASON|TOTAL"]
    gamma_visit_truth = []
    for e in g.itertuples():
        pt = pmap.loc[(e.clinic, e.pet_uid)]
        v = views[(e.clinic, e.pet_uid)]
        pr = pets_i.loc[e.pet_uid]
        bd = pr.birth_day
        birth = _date_str(bd, "%Y%m%d") if rng.random() < 0.7 else _date_str(bd, "%Y") + "0101"
        reason = rng.choice(R.DX_GAMMA[e.dx])
        lines.append("|".join(map(str, [e.clinic, pt.client_id.replace("C", "A"), f"{v.first} {v.last}",
                                        fmt_phone(v.phone, "dash"), v.email, v.zip, v.pet_name, pr.species,
                                        v.breed, birth, pr.sex, e.visit_no, _date_str(e.day, "%Y%m%d"), reason,
                                        f"{sum(x[1] for x in e.items):.2f}"])))
        gamma_visit_truth.append((e.visit_no, e.pet_uid))
    (raw / "vet_gamma_visits.txt").write_text("\n".join(lines) + "\n")

    # ---------------- pawstay (daycare + boarding)
    dcb_pets = pd.concat([dc[["pet_uid", "site", "day"]],
                          board[["pet_uid", "site"]].assign(day=board.check_in)]) if len(board) else dc
    reg = dcb_pets.groupby(["pet_uid", "site"]).day.min().reset_index().rename(columns={"day": "reg_day"})
    reg["pawstay_pet_id"] = [f"PS{i:06d}" for i in rng.permutation(10**6)[: len(reg)]]
    # 3% duplicate registrations (owner re-registered online); later visits split across the two ids
    dup = reg.sample(frac=0.03, random_state=int(rng.integers(1e9))).copy()
    dup["pawstay_pet_id"] = [f"PS{i:06d}" for i in rng.permutation(np.arange(10**6, 2 * 10**6))[: len(dup)]]
    dup["reg_day"] = dup.reg_day + rng.integers(30, 400, len(dup))
    reg_all = pd.concat([reg.assign(dup=False), dup.assign(dup=True)], ignore_index=True)
    ps_rows = []
    for p in reg_all.itertuples():
        hhr = hh_i.loc[pets_i.loc[p.pet_uid].household_uid]
        v = IdentityView(rng, hhr, pets_i.loc[p.pet_uid], p.reg_day, p_nick=0.3, p_typo=0.04,
                         p_email_missing=0.2, p_breed_variant=0.7, p_petname_variant=0.15)
        pr = pets_i.loc[p.pet_uid]
        age = (p.reg_day - pr.birth_day) / 365.25
        age_text = f"{int(age * 12)} mos" if age < 1 else (f"{int(age)} yrs" if rng.random() < 0.8 else f"{int(age)}")
        owner = f"{v.first} {v.last}" if rng.random() < 0.85 else f"{v.last}, {v.first}"
        ps_rows.append(dict(pawstay_pet_id=p.pawstay_pet_id, site_id=p.site, owner_name=owner,
                            owner_phone=fmt_phone(v.phone, rng.choice(["raw", "dot", "plus1"])),
                            owner_email=v.email, owner_zip=v.zip, pet_name=v.pet_name, breed=v.breed,
                            age_text=age_text, weight_lb=round(pr.weight_lb * rng.uniform(0.95, 1.05)),
                            registered_on=_date_str(min(p.reg_day, cfg.n_days - 1), "%Y-%m-%d")))
        record_map.append(("pawstay", p.pawstay_pet_id, p.pet_uid))
    pd.DataFrame(ps_rows).to_csv(raw / "pawstay_pets.csv", index=False)

    # assign visits to registration ids (duplicate ids take visits after their reg_day, 50%)
    ids = reg_all.sort_values("dup").groupby(["pet_uid", "site"])
    id_lookup = {k: list(zip(g_.pawstay_pet_id, g_.reg_day, g_.dup)) for k, g_ in ids}

    def pick_id(pet_uid, site, day):
        opts = id_lookup[(pet_uid, site)]
        if len(opts) > 1 and day >= opts[1][1] and rng.random() < 0.5:
            return opts[1][0]
        return opts[0][0]

    dcv = dc.copy()
    dcv["pawstay_pet_id"] = [pick_id(a_, b_, c_) for a_, b_, c_ in zip(dcv.pet_uid, dcv.site, dcv.day)]
    out = pd.DataFrame({
        "visit_id": [f"DV{i:08d}" for i in range(len(dcv))], "pawstay_pet_id": dcv.pawstay_pet_id,
        "site_id": dcv.site, "visit_date": pd.to_datetime(day_to_date(dcv.day.values)).strftime("%Y-%m-%d"),
        "service": np.where(dcv.half_day, "Half Day", "Full Day"), "price": dcv.price, "staff_note": dcv.note})
    out.to_csv(raw / "pawstay_daycare_visits.csv", index=False)

    bs = board.copy()
    bs["pawstay_pet_id"] = [pick_id(a_, b_, c_) for a_, b_, c_ in zip(bs.pet_uid, bs.site, bs.check_in)]
    pd.DataFrame({
        "stay_id": [f"BS{i:07d}" for i in range(len(bs))], "pawstay_pet_id": bs.pawstay_pet_id,
        "site_id": bs.site, "check_in": pd.to_datetime(day_to_date(bs.check_in.values)).strftime("%Y-%m-%d"),
        "check_out": pd.to_datetime(day_to_date((bs.check_in + bs.nights).values)).strftime("%Y-%m-%d"),
        "room_type": bs.room, "price": bs.price, "staff_note": bs.note}).to_csv(raw / "pawstay_boarding_stays.csv",
                                                                                index=False)

    # ---------------- groomly: denormalized appointments
    gcust = groom.groupby("pet_uid").agg(reg_day=("day", "min"), site=("site", "first")).reset_index()
    gcust["customer_id"] = [f"G{i:05d}" for i in rng.permutation(10**5)[: len(gcust)]]
    gviews = {}
    for p in gcust.itertuples():
        hhr = hh_i.loc[pets_i.loc[p.pet_uid].household_uid]
        gviews[p.pet_uid] = (p.customer_id, IdentityView(rng, hhr, pets_i.loc[p.pet_uid], p.reg_day, p_nick=0.35,
                                                         p_typo=0.05, p_email_missing=0.4, p_breed_variant=0.8,
                                                         p_petname_variant=0.15))
        record_map.append(("groomly", f"{p.customer_id}|{gviews[p.pet_uid][1].pet_name}", p.pet_uid))
    grows = []
    for i, e in enumerate(groom.itertuples()):
        cid, v = gviews[e.pet_uid]
        ts = pd.Timestamp(day_to_date(e.day)) + pd.Timedelta(minutes=e.minute)
        grows.append(dict(appointment_id=f"GA{i:07d}", location=e.site, customer_id=cid, customer_first=v.first,
                          customer_last=v.last, customer_phone=fmt_phone(v.phone, "dash"), customer_email=v.email,
                          pet_name=v.pet_name, pet_breed=v.breed, appt_datetime=ts.strftime("%m/%d/%Y %I:%M %p"),
                          service=e.service, price=e.price, groomer_notes=e.note))
    pd.DataFrame(grows).to_csv(raw / "groomly_appointments.csv", index=False)

    # ---------------- wellplan memberships + campaign
    wrows = []
    for m in wp.itertuples():
        pr = pets_i.loc[m.pet_uid]
        v = IdentityView(rng, hh_i.loc[pr.household_uid], pr, m.start_day, p_nick=0.1, p_typo=0.02,
                         p_email_missing=0.02, p_breed_variant=0.0, p_petname_variant=0.05)
        wrows.append(dict(membership_id=m.membership_id, clinic_id=m.clinic, member_name=f"{v.first} {v.last}",
                          member_email=v.email, member_phone=fmt_phone(v.phone, "raw"), pet_name=v.pet_name,
                          species=pr.species.capitalize(), plan_tier=m.tier, monthly_fee=m.fee,
                          start_date=_date_str(m.start_day, "%Y-%m-%d"),
                          end_date=_date_str(m.end_day, "%Y-%m-%d") if m.end_day is not None and not pd.isna(m.end_day) else "",
                          cancel_reason=m.cancel_reason or ""))
        record_map.append(("wellplan", m.membership_id, m.pet_uid))
    pd.DataFrame(wrows).to_csv(raw / "wellplan_memberships.csv", index=False)
    camp = wp[wp.arm.notna()][["membership_id", "campaign_day", "arm"]].copy()
    camp["campaign_date"] = pd.to_datetime(day_to_date(camp.campaign_day.astype(int).values)).strftime("%Y-%m-%d")
    camp[["membership_id", "campaign_date", "arm"]].to_csv(raw / "wellplan_campaign.csv", index=False)

    return pd.DataFrame(record_map, columns=["source_system", "source_record_key", "pet_uid"]), \
        pd.DataFrame(gamma_visit_truth, columns=["visit_no", "pet_uid"])


# ----------------------------------------------------------------------------- main
def generate(cfg: Config) -> dict:
    rng = np.random.default_rng(cfg.seed)
    locs = build_locations()
    hh = build_households(cfg, rng)
    pets = assign_channels(build_pets(cfg, hh, rng), locs, rng)
    ill = simulate_illness(cfg, pets, rng)
    win = prodrome_windows(ill)
    vet = simulate_vet(cfg, pets, ill, rng)
    dc = simulate_daycare(cfg, pets, locs, win, rng)
    board = simulate_boarding(cfg, pets, locs, win, rng)
    groom = simulate_grooming(cfg, pets, win, rng)
    wp, exp = simulate_wellness(cfg, pets, vet, rng)
    record_map, gamma_truth = write_sources(cfg, hh, pets, vet, dc, board, groom, wp, rng)

    truth = cfg.out_dir / "truth"
    truth.mkdir(parents=True, exist_ok=True)
    raw = cfg.out_dir / "raw" / "synthetic"
    locs.to_csv(raw / "locations.csv", index=False)
    hh.to_parquet(truth / "households.parquet", index=False)
    pets.to_parquet(truth / "pets.parquet", index=False)
    ill.to_parquet(truth / "illness_events.parquet", index=False)
    exp.to_parquet(truth / "wellness_experiment.parquet", index=False)
    record_map.to_parquet(truth / "record_map.parquet", index=False)
    gamma_truth.to_parquet(truth / "vet_gamma_visit_map.parquet", index=False)
    summary = {"households": len(hh), "pets": len(pets), "illness_events": len(ill), "vet_visits": len(vet),
               "daycare_visits": len(dc), "boarding_stays": len(board), "grooming_appts": len(groom),
               "wellness_memberships": len(wp), "source_pet_records": len(record_map)}
    (truth / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--households", type=int, default=9000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prodrome-prob", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=Path("data"))
    a = ap.parse_args()
    s = generate(Config(seed=a.seed, n_households=a.households, prodrome_prob=a.prodrome_prob, out_dir=a.out))
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
