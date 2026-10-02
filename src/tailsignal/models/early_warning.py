"""Model C: do non-veterinary channels give early warning of a sick visit? (pre-registered H5)

Unit: pet-month snapshot (first of each month). Outcome: a clinical (non-wellness) vet visit in
the next 60 days. Two gradient-boosting models: vet-history features only, and vet history plus
daycare attendance change and concerning staff notes from daycare, boarding, and grooming.

Two parts:
1. Observed lift on the resolved platform data (entity-resolved, as a real partner network would be).
2. Power study: how many linked pets are needed to detect the lift, across signal strengths.
   Uses fresh simulations in memory with true pet identity, varying how often an illness
   shows a pre-visit signal in other channels (prodrome probability 0, 0.25, 0.5, 1.0).

The staff-note lexicon below matches the simulator's vocabulary; a deployment would use a
text classifier trained on real notes (e.g. PetBERT-style models on SAVSNET data).

    python -m tailsignal.models.early_warning                # both parts
    python -m tailsignal.models.early_warning --skip-power   # part 1 only
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

DB = Path("data/warehouse.duckdb")
OUT = Path("reports/early_warning")
START, LAST = "2022-07-01", "2025-10-01"
TRAIN_LAST, TEST_FIRST = "2024-04-01", "2024-07-01"
CONCERN = (r"letharg|low energy|napping more|breathing heavy|not eating|skipped meal|vomit|soft stool|limp|stairs|"
           r"reluctant to jump|stiff|scratch|licking paws|hot spot|red skin|shaking head|ear odor|ear looks red|"
           r"lump|bump|bad breath|dropping food|chewing on one side")
CHRONIC = ("osteoarthritis", "chronic_kidney_disease", "mitral_valve_disease", "hypertrophic_cardiomyopathy",
           "dental_disease", "allergic_dermatitis", "obesity", "mass_neoplasia")
VET_FEATURES = ["age", "dog", "vet_365", "clinical_365", "clinical_90", "days_since_vet", "chronic_hist"]
CROSS_FEATURES = ["uses_daycare", "dc_28", "dc_base_rate", "dc_drop", "concern_30", "concern_groom_60",
                  "concern_any_90", "boarding_60", "nonvet_90"]


def snapshot_features(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Expects tables pets(pet_id, species, birth_date) and events(pet_id, channel, event_date, clinical, condition, note)."""
    return con.execute(f"""
        with snaps as (
            select unnest(generate_series(DATE '{START}', DATE '{LAST}', INTERVAL 1 MONTH))::date as s
        ), vetpets as (select distinct pet_id from events where channel = 'vet'),
        grid as (
            select p.pet_id, s.s, p.species, p.birth_date
            from pets p join vetpets using (pet_id) cross join snaps s
            where p.pet_id in (select pet_id from events where event_date < s.s)
        ),
        f as (
            select g.pet_id, g.s,
                count(*) filter (where e.channel = 'vet' and e.event_date >= g.s - 365) vet_365,
                count(*) filter (where e.clinical and e.event_date >= g.s - 365) clinical_365,
                count(*) filter (where e.clinical and e.event_date >= g.s - 90) clinical_90,
                coalesce(date_diff('day', max(e.event_date) filter (where e.channel = 'vet'), g.s), 999) days_since_vet,
                (count(*) filter (where e.condition in {CHRONIC}) > 0)::int chronic_hist,
                (count(*) filter (where e.channel = 'daycare' and e.event_date >= g.s - 365) > 0)::int uses_daycare,
                count(*) filter (where e.channel = 'daycare' and e.event_date >= g.s - 28) dc_28,
                count(*) filter (where e.channel = 'daycare' and e.event_date < g.s - 28 and e.event_date >= g.s - 112) / 3.0 dc_base_rate,
                count(*) filter (where e.channel in ('daycare', 'boarding') and e.event_date >= g.s - 30
                                 and regexp_matches(lower(coalesce(e.note, '')), '{CONCERN}')) concern_30,
                count(*) filter (where e.channel = 'grooming' and e.event_date >= g.s - 60
                                 and regexp_matches(lower(coalesce(e.note, '')), '{CONCERN}')) concern_groom_60,
                count(*) filter (where e.channel <> 'vet' and e.event_date >= g.s - 90
                                 and regexp_matches(lower(coalesce(e.note, '')), '{CONCERN}')) concern_any_90,
                count(*) filter (where e.channel = 'boarding' and e.event_date >= g.s - 60) boarding_60,
                count(*) filter (where e.channel <> 'vet' and e.event_date >= g.s - 90) nonvet_90
            from grid g join events e on e.pet_id = g.pet_id and e.event_date < g.s
            group by g.pet_id, g.s
        ),
        y as (
            select g.pet_id, g.s, (count(e.pet_id) > 0)::int as y
            from grid g left join events e on e.pet_id = g.pet_id and e.clinical
                 and e.event_date >= g.s and e.event_date < g.s + 60
            group by g.pet_id, g.s
        )
        select f.*, y.y, date_diff('day', g.birth_date, g.s) / 365.25 as age, (g.species = 'dog')::int as dog,
               f.dc_base_rate - f.dc_28 as dc_drop
        from f join y using (pet_id, s) join grid g using (pet_id, s)
    """).df()


def platform_tables(db: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"attach '{db.as_posix()}' as wh (read_only)")
    con.execute("create table pets as select pet_id, species, birth_date from wh.core.dim_pet")
    con.execute("""create table events as select pet_id, channel, event_date,
                   (service_code = 'clinical_visit') as clinical, condition, staff_note as note
                   from wh.core.fct_service_event""")
    return con


def sim_tables(prodrome: float, seed: int = 7, households: int = 9000) -> duckdb.DuckDBPyConnection:
    """Fresh in-memory simulation with true identities (no source files, no entity resolution)."""
    from tailsignal.synth import generate as G
    cfg = G.Config(seed=seed, n_households=households, prodrome_prob=prodrome)
    rng = np.random.default_rng(seed)
    locs = G.build_locations()
    hh = G.build_households(cfg, rng)
    pets = G.assign_channels(G.build_pets(cfg, hh, rng), locs, rng)
    ill = G.simulate_illness(cfg, pets, rng)
    win = G.prodrome_windows(ill)
    vet = G.simulate_vet(cfg, pets, ill, rng)
    dc = G.simulate_daycare(cfg, pets, locs, win, rng)
    bd = G.simulate_boarding(cfg, pets, locs, win, rng)
    gr = G.simulate_grooming(cfg, pets, win, rng)
    d = lambda x: pd.to_datetime(G.day_to_date(np.asarray(x, dtype="int64")))
    ev = pd.concat([
        pd.DataFrame({"pet_id": vet.pet_uid, "channel": "vet", "event_date": d(vet.day),
                      "clinical": vet.dx != "wellness", "condition": vet.dx, "note": None}),
        pd.DataFrame({"pet_id": dc.pet_uid, "channel": "daycare", "event_date": d(dc.day), "clinical": False,
                      "condition": None, "note": dc.note}),
        pd.DataFrame({"pet_id": bd.pet_uid, "channel": "boarding", "event_date": d(bd.check_in), "clinical": False,
                      "condition": None, "note": bd.note}),
        pd.DataFrame({"pet_id": gr.pet_uid, "channel": "grooming", "event_date": d(gr.day), "clinical": False,
                      "condition": None, "note": gr.note}),
    ], ignore_index=True)
    ev["event_date"] = ev.event_date.dt.date
    p = pd.DataFrame({"pet_id": pets.pet_uid, "species": pets.species, "birth_date": d(pets.birth_day).date})
    con = duckdb.connect()
    con.register("p_df", p)
    con.register("e_df", ev)
    con.execute("create table pets as select * from p_df")
    con.execute("create table events as select * from e_df")
    return con


def model():
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=150, min_samples_leaf=50,
                                          random_state=0)


def fit_compare(df: pd.DataFrame, boot: int = 200, seed: int = 0) -> dict:
    df = df.copy()
    df["s"] = pd.to_datetime(df.s)
    tr, te = df[df.s <= TRAIN_LAST], df[df.s >= TEST_FIRST]
    if te.y.nunique() < 2 or tr.y.nunique() < 2:
        return {}
    pv = model().fit(tr[VET_FEATURES], tr.y).predict_proba(te[VET_FEATURES])[:, 1]
    px = model().fit(tr[VET_FEATURES + CROSS_FEATURES], tr.y).predict_proba(te[VET_FEATURES + CROSS_FEATURES])[:, 1]
    y = te.y.values
    auc_v, auc_x = roc_auc_score(y, pv), roc_auc_score(y, px)
    # cluster bootstrap over pets
    rng = np.random.default_rng(seed)
    pid = te.pet_id.values
    upets = np.unique(pid)
    idx_by_pet = pd.Series(np.arange(len(te))).groupby(pid).apply(np.array).to_dict()
    diffs = []
    for _ in range(boot):
        sel = np.concatenate([idx_by_pet[p] for p in rng.choice(upets, len(upets), replace=True)])
        if y[sel].min() == y[sel].max():
            continue
        diffs.append(roc_auc_score(y[sel], px[sel]) - roc_auc_score(y[sel], pv[sel]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    # alert value: among the top 5% risk scores, how many sick visits are caught
    k = max(1, int(0.05 * len(te)))
    cap_v = y[np.argsort(-pv)[:k]].sum() / max(1, y.sum())
    cap_x = y[np.argsort(-px)[:k]].sum() / max(1, y.sum())
    # secondary (not pre-registered): pets seen in a non-vet channel in the prior 90 days, the only
    # pets for whom cross-channel data can carry any signal
    m = te.nonvet_90.values > 0
    sub = {}
    if m.sum() > 100 and y[m].min() != y[m].max():
        sub = {"rows": int(m.sum()), "auc_vet_only": round(float(roc_auc_score(y[m], pv[m])), 4),
               "auc_with_cross_channel": round(float(roc_auc_score(y[m], px[m])), 4)}
        sub["lift"] = round(sub["auc_with_cross_channel"] - sub["auc_vet_only"], 4)
    return {"active_in_other_channels": sub, "test_rows": int(len(te)), "test_pets": int(len(upets)), "event_rate": round(float(y.mean()), 4),
            "auc_vet_only": round(float(auc_v), 4), "auc_with_cross_channel": round(float(auc_x), 4),
            "lift": round(float(auc_x - auc_v), 4), "lift_ci95": [round(float(lo), 4), round(float(hi), 4)],
            "share_of_sick_visits_in_top5pct": {"vet_only": round(float(cap_v), 3),
                                                "with_cross_channel": round(float(cap_x), 3)}}


USAGE = ["uses_daycare", "nonvet_90", "boarding_60", "dc_base_rate"]
SIGNAL = ["dc_28", "dc_drop", "concern_30", "concern_groom_60", "concern_any_90"]


def ablation(df: pd.DataFrame, boot: int = 200, seed: int = 0) -> dict:
    """Exploratory (added after the power study showed lift with no planted signal): separate
    'this pet uses other channels' (engagement) from 'something changed before the visit'
    (attendance drop, concerning notes). Compares vet + usage vs. vet + usage + signal."""
    df = df.copy()
    df["s"] = pd.to_datetime(df.s)
    tr, te = df[df.s <= TRAIN_LAST], df[df.s >= TEST_FIRST]
    base, full = VET_FEATURES + USAGE, VET_FEATURES + USAGE + SIGNAL
    pb = model().fit(tr[base], tr.y).predict_proba(te[base])[:, 1]
    pf = model().fit(tr[full], tr.y).predict_proba(te[full])[:, 1]
    pv = model().fit(tr[VET_FEATURES], tr.y).predict_proba(te[VET_FEATURES])[:, 1]
    y = te.y.values
    rng = np.random.default_rng(seed)
    pid = te.pet_id.values
    upets = np.unique(pid)
    idx = pd.Series(np.arange(len(te))).groupby(pid).apply(np.array).to_dict()
    d = []
    for _ in range(boot):
        sel = np.concatenate([idx[p] for p in rng.choice(upets, len(upets), replace=True)])
        d.append(roc_auc_score(y[sel], pf[sel]) - roc_auc_score(y[sel], pb[sel]))
    m = te.nonvet_90.values > 0
    return {"auc_vet_only": round(float(roc_auc_score(y, pv)), 4),
            "auc_vet_plus_usage": round(float(roc_auc_score(y, pb)), 4),
            "auc_plus_warning_signals": round(float(roc_auc_score(y, pf)), 4),
            "engagement_lift": round(float(roc_auc_score(y, pb) - roc_auc_score(y, pv)), 4),
            "warning_signal_lift": round(float(roc_auc_score(y, pf) - roc_auc_score(y, pb)), 4),
            "warning_signal_lift_ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)],
            "warning_signal_lift_active_pets": round(float(roc_auc_score(y[m], pf[m]) - roc_auc_score(y[m], pb[m])), 4)}


def power_study(levels=(0.0, 0.25, 0.5, 1.0), sizes=(500, 1000, 2000, 4000, 8000), reps=15, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for lv in levels:
        con = sim_tables(lv)
        df = snapshot_features(con)
        full = fit_compare(df, boot=100)
        pets = df.pet_id.unique()
        print(f"  prodrome {lv}: full-sample lift {full['lift']} ({len(pets)} pets)", flush=True)
        for n in sizes:
            if n > len(pets):
                continue
            sig = []
            lifts = []
            for r in range(reps):
                sub = rng.choice(pets, n, replace=False)
                res = fit_compare(df[df.pet_id.isin(sub)], boot=100, seed=r)
                if not res:
                    continue
                lifts.append(res["lift"])
                sig.append(res["lift_ci95"][0] > 0)
            rows.append(dict(prodrome=lv, full_sample_lift=full["lift"], pets=n, reps=len(sig),
                             mean_lift=float(np.mean(lifts)), power=float(np.mean(sig))))
            print(f"    n={n}: power {np.mean(sig):.2f}", flush=True)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--skip-power", action="store_true")
    ap.add_argument("--reps", type=int, default=15)
    ap.add_argument("--ablation-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    df = snapshot_features(platform_tables(a.db))
    if a.ablation_only:
        res = {"platform": ablation(df)}
        for lv in (0.0, 0.25, 0.5, 1.0):
            res[f"sim_prodrome_{lv}"] = ablation(snapshot_features(sim_tables(lv)))
            print(lv, res[f"sim_prodrome_{lv}"], flush=True)
        (OUT / "ablation.json").write_text(json.dumps(res, indent=2))
        print(json.dumps(res, indent=2))
        return
    observed = fit_compare(df, boot=300)
    summary = {"snapshots": len(df), "observed_platform": observed}
    print(json.dumps(summary, indent=2), flush=True)
    if not a.skip_power:
        pw = power_study(reps=a.reps)
        pw.to_csv(OUT / "power.csv", index=False)
        need = {}
        for lv, g in pw.groupby("prodrome"):
            ok = g[g.power >= 0.8]
            need[str(lv)] = {"full_sample_lift": float(g.full_sample_lift.iloc[0]),
                             "min_pets_for_80pct_power": int(ok.pets.min()) if not ok.empty else None}
        summary["power"] = need
        summary["H5_note"] = "minimum linked pets for 80% power to detect the lift each signal strength produces"
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
