"""Model D: who should get a wellness-plan renewal reminder? (pre-registered H6)

The wellness-plan provider randomized a reminder at month 6 of each membership. Outcome:
membership lapses within 180 days of the campaign. Compares three ways to choose whom to
contact: modeled uplift (T-learner and X-learner, gradient boosting), lapse risk alone
(the usual churn-model approach), and random.

Evaluation (pre-registered): train on campaigns through 2024-06-30, test on campaigns
2024-07-01 to 2025-06-30 (later campaigns lack 180 days of follow-up). Secondary: 5-fold
cross-fitting over all eligible campaigns for more test data. Simulator ground truth (the true
per-member effect) is used only as a recovery check.

    python -m tailsignal.models.uplift
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

DB = Path("data/warehouse.duckdb")
OUT = Path("reports/uplift")
TRAIN_END, TEST_END = "2024-06-30", "2025-06-30"
TOP = 0.30  # contact budget: top 30% by score
FEATURES = ["dog", "age_years", "tier_rank", "monthly_fee", "months_on_plan", "hh_pets",
            "vet_365", "wellness_365", "clinical_365", "daycare_365", "boarding_365", "grooming_365",
            "days_since_vet"]


def load(con) -> pd.DataFrame:
    return con.execute(f"""
        with m as (
            select w.membership_id, w.pet_id, w.plan_tier, w.monthly_fee, w.start_date, w.end_date,
                   w.campaign_arm, w.campaign_date, p.household_id, p.species, p.birth_date
            from core.fct_wellness_membership w join core.dim_pet p using (pet_id)
            where w.campaign_arm is not null and w.campaign_date <= DATE '{TEST_END}'
        ), hh_events as (
            select m.membership_id, e.channel, e.service_code, e.event_date
            from m join core.dim_pet p2 on p2.household_id = m.household_id
            join core.fct_service_event e on e.pet_id = p2.pet_id
            where e.event_date < m.campaign_date and e.event_date >= m.campaign_date - 365
        ), agg as (
            select membership_id,
                   count(*) filter (where channel = 'vet') vet_365,
                   count(*) filter (where service_code = 'wellness_exam') wellness_365,
                   count(*) filter (where service_code = 'clinical_visit') clinical_365,
                   count(*) filter (where channel = 'daycare') daycare_365,
                   count(*) filter (where channel = 'boarding') boarding_365,
                   count(*) filter (where channel = 'grooming') grooming_365
            from hh_events group by 1
        ), lastvet as (
            select m.membership_id, max(e.event_date) last_vet
            from m join core.fct_service_event e on e.pet_id = m.pet_id
            where e.channel = 'vet' and e.event_date < m.campaign_date group by 1
        ), hh as (select household_id, count(*) hh_pets from core.dim_pet group by 1)
        select m.membership_id, m.household_id, m.campaign_date,
               (m.campaign_arm = 'reminder')::int as treated,
               (m.end_date is not null and m.end_date <= m.campaign_date + 180)::int as lapsed,
               (m.species = 'dog')::int as dog,
               date_diff('day', m.birth_date, m.campaign_date) / 365.25 as age_years,
               case m.plan_tier when 'Basic' then 0 when 'Plus' then 1 else 2 end as tier_rank,
               m.monthly_fee, date_diff('day', m.start_date, m.campaign_date) / 30.4 as months_on_plan,
               hh.hh_pets, coalesce(a.vet_365, 0) vet_365, coalesce(a.wellness_365, 0) wellness_365,
               coalesce(a.clinical_365, 0) clinical_365, coalesce(a.daycare_365, 0) daycare_365,
               coalesce(a.boarding_365, 0) boarding_365, coalesce(a.grooming_365, 0) grooming_365,
               coalesce(date_diff('day', l.last_vet, m.campaign_date), 999) days_since_vet
        from m left join agg a using (membership_id) left join lastvet l using (membership_id)
        join hh using (household_id)
    """).df()


def gb():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=40,
                                          l2_regularization=1.0, random_state=0)


def fit_scores(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Return test scores: uplift_T, uplift_X (expected reduction in lapse prob.), risk (lapse prob. if not contacted)."""
    X, Xt = train[FEATURES], test[FEATURES]
    t, y = train.treated.values, train.lapsed.values
    m0 = gb().fit(X[t == 0], y[t == 0])
    m1 = gb().fit(X[t == 1], y[t == 1])
    p0, p1 = m0.predict_proba(Xt)[:, 1], m1.predict_proba(Xt)[:, 1]
    # X-learner: imputed effects, regressed with classifiers on [0,1]-scaled targets via regression trees
    from sklearn.ensemble import HistGradientBoostingRegressor
    d1 = m0.predict_proba(X[t == 1])[:, 1] - y[t == 1]   # benefit for treated = P(lapse | no reminder) - observed
    d0 = y[t == 0] - m1.predict_proba(X[t == 0])[:, 1]   # benefit for controls
    reg = dict(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=40, random_state=0)
    g1 = HistGradientBoostingRegressor(**reg).fit(X[t == 1], d1)
    g0 = HistGradientBoostingRegressor(**reg).fit(X[t == 0], d0)
    e = t.mean()
    out = test[["membership_id", "household_id", "treated", "lapsed"]].copy()
    out["uplift_T"] = p0 - p1
    out["uplift_X"] = e * g0.predict(Xt) + (1 - e) * g1.predict(Xt)
    out["risk"] = p0
    return out


def retained_per_1000(df: pd.DataFrame, score: str | None, top=TOP) -> float:
    """Members kept per 1,000 contacts if the top `top` share by score is contacted (randomized estimate)."""
    d = df if score is None else df.nlargest(max(1, int(len(df) * top)), score)
    c, t = d[d.treated == 0], d[d.treated == 1]
    if len(c) == 0 or len(t) == 0:
        return np.nan
    return 1000 * (c.lapsed.mean() - t.lapsed.mean())


def qini_area(df: pd.DataFrame, score: str, grid=20) -> float:
    """Area between the uplift (Qini-style) curve and the random-targeting line, per member."""
    d = df.sort_values(score, ascending=False).reset_index(drop=True)
    n = len(d)
    overall = d[d.treated == 0].lapsed.mean() - d[d.treated == 1].lapsed.mean()
    xs, gain = np.linspace(0, 1, grid + 1)[1:], []
    for f in xs:
        top = d.iloc[: max(2, int(n * f))]
        c, t = top[top.treated == 0], top[top.treated == 1]
        u = (c.lapsed.mean() - t.lapsed.mean()) if len(c) and len(t) else 0.0
        gain.append(u * f)
    gain = np.array(gain)
    return float(np.trapezoid(gain - overall * xs, xs))


def evaluate(df: pd.DataFrame, reps=1000, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    methods = {"uplift_X": "uplift_X", "uplift_T": "uplift_T", "risk": "risk", "random": None}
    point = {m: retained_per_1000(df, s) for m, s in methods.items()}
    qini = {m: qini_area(df, s) for m, s in methods.items() if s}
    boots = {m: [] for m in methods}
    diff = []
    for _ in range(reps):
        b = df.iloc[rng.integers(0, len(df), len(df))]
        vals = {m: retained_per_1000(b, s) for m, s in methods.items()}
        for m in methods:
            boots[m].append(vals[m])
        diff.append(vals["uplift_X"] - vals["risk"])
    ci = {m: [round(float(np.nanpercentile(v, 2.5)), 1), round(float(np.nanpercentile(v, 97.5)), 1)]
          for m, v in boots.items()}
    return {"n": len(df), "retained_per_1000_contacts_top30": {m: round(float(v), 1) for m, v in point.items()},
            "ci95": ci, "qini_area": {m: round(v, 4) for m, v in qini.items()},
            "uplift_X_minus_risk": {"point": round(float(point["uplift_X"] - point["risk"]), 1),
                                    "ci95": [round(float(np.nanpercentile(diff, 2.5)), 1),
                                             round(float(np.nanpercentile(diff, 97.5)), 1)],
                                    "p_greater": round(float(np.mean(np.array(diff) > 0)), 3)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(a.db), read_only=True)
    df = load(con)
    df["campaign_date"] = pd.to_datetime(df.campaign_date)

    train = df[df.campaign_date <= TRAIN_END]
    test = df[df.campaign_date > TRAIN_END]
    s_test = fit_scores(train, test)
    primary = evaluate(s_test)

    # secondary: 5-fold cross-fitting (grouped by household) over all eligible campaigns
    parts = []
    for tr, te in GroupKFold(5).split(df, groups=df.household_id):
        parts.append(fit_scores(df.iloc[tr], df.iloc[te]))
    s_cf = pd.concat(parts)
    secondary = evaluate(s_cf)

    # recovery check vs simulator truth (true monthly effect on lapse probability; negative = reminder helps)
    rec = None
    tp = Path("data/truth/wellness_experiment.parquet")
    if tp.exists():
        tr_ = pd.read_parquet(tp)[["membership_id", "true_tau_monthly", "segment"]]
        j = s_cf.merge(tr_, on="membership_id")
        rho_x = spearmanr(j.uplift_X, -j.true_tau_monthly).statistic
        rho_r = spearmanr(j.risk, -j.true_tau_monthly).statistic
        j["oracle"] = -j.true_tau_monthly
        rec = {"spearman_uplift_X_vs_true_benefit": round(float(rho_x), 3),
               "spearman_risk_vs_true_benefit": round(float(rho_r), 3),
               "oracle_retained_per_1000_top30": round(float(retained_per_1000(j, "oracle")), 1),
               "true_benefit_by_segment": j.groupby("segment").oracle.mean().round(4).to_dict()}

    summary = {"memberships": len(df), "train": len(train), "test": len(test),
               "overall_effect_lapse_rate": {"control": round(float(df[df.treated == 0].lapsed.mean()), 4),
                                             "reminder": round(float(df[df.treated == 1].lapsed.mean()), 4)},
               "primary_time_holdout": primary, "secondary_crossfit": secondary,
               "H6_pass": bool(primary["uplift_X_minus_risk"]["ci95"][0] > 0),
               "recovery_check": rec}
    s_cf.to_csv(OUT / "crossfit_scores.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
