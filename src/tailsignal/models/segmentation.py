"""Household segmentation from cross-channel service behavior (pre-registered H7).

Features come from the resolved platform data (core.fct_service_event, core.dim_pet,
core.fct_wellness_membership), measured over the training window only. Model: Gaussian
mixture on standardized log rates; k chosen by BIC subject to "no segment < 5%";
stability by bootstrap Jaccard. Synthetic ground-truth segments are used only as a
recovery check, never for fitting or choosing k.

    python -m tailsignal.models.segmentation
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

DB = Path("data/warehouse.duckdb")
OUT = Path("reports/segmentation")
TRAIN_END = "2024-06-30"

FEATURES = ["vet_visits_py", "wellness_share", "daycare_days_py", "boarding_nights_py", "grooming_appts_py",
            "spend_py", "channels_used", "pets", "dog_share", "on_wellness_plan", "groom_need_breed_share"]
# Exploratory revision (logged in docs/preregistration.md): the pre-registered feature set mixes
# binary and near-constant columns (dog_share, on_wellness_plan, ...) with rates; the mixture then
# spends components on exact-0/1 spikes and the solution is unstable. Behavioral rates only are
# clustered; household attributes become descriptors.
BEHAVIOR = ["vet_visits_py", "wellness_share", "daycare_days_py", "boarding_nights_py", "grooming_appts_py"]
LOG_COLS = ["vet_visits_py", "daycare_days_py", "boarding_nights_py", "grooming_appts_py", "spend_py", "pets"]


def household_features(con, train_end=TRAIN_END) -> pd.DataFrame:
    return con.execute(f"""
        with pets as (
            select pet_id, household_id, species, breed, first_seen from core.dim_pet
        ), ev as (
            select p.household_id, e.*
            from core.fct_service_event e join pets p using (pet_id)
            where e.event_date <= DATE '{train_end}'
        ), hh as (
            select household_id,
                   count(*) as pets,
                   avg(case when species = 'dog' then 1.0 else 0.0 end) as dog_share,
                   avg(case when breed in ('Poodle', 'Goldendoodle', 'Labradoodle', 'Shih Tzu', 'Yorkshire Terrier',
                                           'Persian') then 1.0 else 0.0 end) as groom_need_breed_share,
                   min(first_seen) as first_seen
            from pets group by 1
        ), act as (
            select household_id,
                   -- years observed: from first record to the end of the training window (min 0.25)
                   greatest(date_diff('day', min(event_date), DATE '{train_end}') / 365.25, 0.25) as years,
                   count(*) filter (where channel = 'vet') as vet,
                   count(*) filter (where channel = 'vet' and service_code = 'wellness_exam') as wellness,
                   count(*) filter (where channel = 'daycare') as daycare,
                   coalesce(sum(nights) filter (where channel = 'boarding'), 0) as nights,
                   count(*) filter (where channel = 'grooming') as grooming,
                   sum(amount) as spend,
                   count(distinct channel) as channels_used
            from ev group by 1
        ), wp as (
            select distinct p.household_id from core.fct_wellness_membership m join pets p using (pet_id)
            where m.start_date <= DATE '{train_end}'
        )
        select h.household_id, h.pets, h.dog_share, h.groom_need_breed_share,
               a.vet / a.years / h.pets as vet_visits_py,
               case when a.vet > 0 then a.wellness * 1.0 / a.vet else 0 end as wellness_share,
               a.daycare / a.years as daycare_days_py,
               a.nights / a.years as boarding_nights_py,
               a.grooming / a.years as grooming_appts_py,
               a.spend / a.years as spend_py,
               a.channels_used,
               (wp.household_id is not null)::int as on_wellness_plan
        from hh h join act a using (household_id) left join wp using (household_id)
    """).df()


def design(df: pd.DataFrame, cols=FEATURES) -> np.ndarray:
    X = df[cols].astype(float).copy()
    for c in cols:
        if c in LOG_COLS:
            X[c] = np.log1p(X[c])
    return StandardScaler().fit_transform(X)


def gmm(k, cov="full", reg=1e-6, n_init=4, seed=0):
    return GaussianMixture(k, covariance_type=cov, reg_covar=reg, n_init=n_init, random_state=seed)


def choose_k(X, ks=range(2, 11), min_share=0.05, seed=0, cov="full", reg=1e-6) -> tuple[int, pd.DataFrame]:
    rows = []
    for k in ks:
        gm = gmm(k, cov, reg, 4, seed).fit(X)
        share = np.bincount(gm.predict(X), minlength=k) / len(X)
        rows.append(dict(k=k, bic=gm.bic(X), min_share=share.min(), usable=share.min() >= min_share))
    sel = pd.DataFrame(rows)
    usable = sel[sel.usable]
    k = int(usable.loc[usable.bic.idxmin(), "k"]) if not usable.empty else int(sel.loc[sel.bic.idxmin(), "k"])
    return k, sel


def bootstrap_jaccard(X, labels, k, reps=50, seed=0, cov="full", reg=1e-6) -> np.ndarray:
    """Mean best-match Jaccard per original segment across bootstrap refits (Hennig 2007)."""
    rng = np.random.default_rng(seed)
    n = len(X)
    scores = np.zeros((reps, k))
    for b in range(reps):
        idx = rng.choice(n, n, replace=True)
        u = np.unique(idx)
        gm = gmm(k, cov, reg, 2, b).fit(X[idx])
        lb = gm.predict(X[u])
        lo = labels[u]
        J = np.zeros((k, k))
        for i in range(k):
            a = lo == i
            for j in range(k):
                bb = lb == j
                inter = (a & bb).sum()
                union = (a | bb).sum()
                J[i, j] = inter / union if union else 0
        scores[b] = J.max(axis=1)
    return scores.mean(axis=0)


def name_segment(p: pd.Series, overall: pd.Series | None = None) -> str:
    """Plain-language segment names from the behavioral profile (annual rates per household)."""
    if p.vet_visits_py < 0.3:
        return "No partner-vet visits"
    if p.daycare_days_py >= 50:
        return "Daycare + grooming regulars" if p.grooming_appts_py >= 2 else "Daycare regulars, no grooming"
    if p.grooming_appts_py >= 3:
        return "Grooming-led"
    if p.boarding_nights_py >= 5:
        return "Vet + boarding"
    if p.daycare_days_py < 1 and p.boarding_nights_py < 1 and p.grooming_appts_py < 1:
        return "Vet only"
    return "Vet-centric light users"


def name_top(p: pd.Series) -> str:
    if p.daycare_days_py >= 50:
        return "Daycare regulars"
    if p.grooming_appts_py >= 3:
        return "Grooming-led"
    return "Vet-centric"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--reps", type=int, default=50)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(a.db), read_only=True)
    df = household_features(con)

    # 1) pre-registered specification (reported as is)
    Xp = design(df, FEATURES)
    kp, selp = choose_k(Xp)
    lp = gmm(kp, n_init=8).fit(Xp).predict(Xp)
    stab_p = bootstrap_jaccard(Xp, lp, kp, reps=a.reps)
    prereg = {"k": kp, "k_selection": selp.round(4).to_dict("records"),
              "jaccard_by_segment": np.round(stab_p, 3).tolist(), "H7_pass": bool(stab_p.min() >= 0.75)}

    # 2) exploratory revision: behavioral rates only; diagonal covariance (top level) and full
    #    covariance (finer level), both with reg_covar = 0.1
    X = design(df, BEHAVIOR)
    k, sel = choose_k(X, cov="diag", reg=0.1)
    gm = gmm(k, "diag", 0.1, 8).fit(X)
    df["segment"] = gm.predict(X)
    stab = bootstrap_jaccard(X, df.segment.to_numpy(), k, reps=a.reps, cov="diag", reg=0.1)
    kf, self_ = choose_k(X, cov="full", reg=0.1)
    df["subsegment"] = gmm(kf, "full", 0.1, 8).fit(X).predict(X)
    stab_f = bootstrap_jaccard(X, df.subsegment.to_numpy(), kf, reps=a.reps, cov="full", reg=0.1)
    finer = {"k": kf, "jaccard_by_subsegment": np.round(stab_f, 3).tolist(),
             "nesting": pd.crosstab(df.segment, df.subsegment).to_dict()}

    overall = df[FEATURES].mean()
    prof = df.groupby("segment")[FEATURES].mean()
    prof["households"] = df.groupby("segment").size()
    prof["pets_total"] = df.groupby("segment").pets.sum()
    prof["share_households"] = prof.households / len(df)
    prof["share_pets"] = prof.pets_total / df.pets.sum()
    prof["revenue_share"] = df.groupby("segment").spend_py.sum() / df.spend_py.sum()
    prof["bootstrap_jaccard"] = stab
    names = {s: name_top(prof.loc[s]) for s in prof.index}
    # disambiguate duplicate names by spend
    seen = {}
    for s in prof.sort_values("spend_py", ascending=False).index:
        nm = names[s]
        seen[nm] = seen.get(nm, 0) + 1
        if seen[nm] > 1:
            names[s] = f"{nm} ({'lower' if seen[nm] == 2 else seen[nm]} spend)"
    prof["name"] = pd.Series(names)
    df["segment_name"] = df.segment.map(names)

    sub = df.groupby("subsegment")[FEATURES].mean()
    sub["households"] = df.groupby("subsegment").size()
    sub["share_households"] = sub.households / len(df)
    sub["revenue_share"] = df.groupby("subsegment").spend_py.sum() / df.spend_py.sum()
    sub["bootstrap_jaccard"] = stab_f
    sub["parent_segment"] = df.groupby("subsegment").segment_name.agg(lambda x: x.mode().iat[0])
    sub["name"] = [name_segment(sub.loc[i], overall) for i in sub.index]
    finer["subsegments"] = json.loads(sub.round(3).reset_index().to_json(orient="records"))

    # cross-sell sizing: daycare/boarding households not using grooming, valued at the
    # grooming-led segment's average grooming spend (illustrative, labeled as such)
    groom_users = df[df.grooming_appts_py > 0]
    avg_groom_appts = groom_users.grooming_appts_py.median() if len(groom_users) else 0
    xs = df[(df.daycare_days_py > 0) & (df.grooming_appts_py == 0)]

    # recovery check against synthetic truth (households -> majority true segment of their pets)
    recovery = None
    truth_p = Path("data/truth/pets.parquet")
    if truth_p.exists():
        rm = pd.read_parquet("data/truth/record_map.parquet")
        rm["unique_id"] = rm.source_system + ":" + rm.source_record_key
        cl = con.execute("select unique_id, household_id from intermediate.int_pet_clusters").df()
        t = pd.read_parquet(truth_p)[["pet_uid", "segment"]]
        m = cl.merge(rm[["unique_id", "pet_uid"]], on="unique_id").merge(t, on="pet_uid")
        hh_truth = m.groupby("household_id").segment.agg(lambda s: s.mode().iat[0]).rename("true_segment")
        j = df.set_index("household_id").join(hh_truth, how="inner")
        recovery = {"ari": round(float(adjusted_rand_score(j.true_segment, j.segment)), 3),
                    "crosstab": pd.crosstab(j.segment_name, j.true_segment).to_dict()}

    summary = {
        "households": len(df), "train_end": TRAIN_END,
        "preregistered_spec": prereg,
        "exploratory_top_level": {"features": BEHAVIOR, "covariance": "diag", "reg_covar": 0.1,
                                  "k_selection": sel.round(4).to_dict("records"), "k": k},
        "exploratory_finer_level": finer, "k": k,
        "segments": json.loads(prof.round(3).reset_index().to_json(orient="records")),
        "top_level_min_jaccard": round(float(stab.min()), 3),
        "top_level_passes_H7_criteria": bool(stab.min() >= 0.75 and prof.share_pets.min() >= 0.05),
        "cross_sell_daycare_no_grooming": {"households": len(xs),
                                           "median_grooming_appts_py_among_groomers": round(float(avg_groom_appts), 2)},
        "recovery_check_vs_synthetic_truth": recovery,
    }
    df.to_csv(OUT / "household_segments.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k_: v for k_, v in summary.items() if k_ not in ("k_selection",)}, indent=2, default=str)[:7000])


if __name__ == "__main__":
    main()
