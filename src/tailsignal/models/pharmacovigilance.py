"""Model A: breed-stratified hierarchical pharmacovigilance on FDA veterinary adverse events.

Spec: docs/model_a_spec.md (pre-registered). Methods compared: PRR (Evans), ROR, MGPS
(DuMouchel two-gamma empirical Bayes), stratified MGPS, and a hierarchical model that shrinks
each breed-stratum estimate toward the all-dog estimate instead of toward 1.

Usage:
    python -m tailsignal.models.pharmacovigilance                   # full validation
    python -m tailsignal.models.pharmacovigilance --permutations 3  # quicker
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, special, stats

SRC = Path("data/raw/public/openfda")
OUT = Path("reports/model_a")

ISOXAZOLINES = ["fluralaner", "afoxolaner", "sarolaner", "lotilaner"]
MACROCYCLIC_LACTONES = ["ivermectin", "milbemycin", "moxidectin", "selamectin", "eprinomectin", "doramectin"]
CLASSES = {"class:isoxazolines": ISOXAZOLINES, "class:macrocyclic_lactones": MACROCYCLIC_LACTONES}
NEURO = "NEUROLOGIC"
NEURO_INCLUDE = (r"convul|seiz|ataxi|tremor|trembl|twitch|fascicul|mydria|blind|\bcoma\b|stupor|disorient|nystag"
                 r"|paresis|paraly|hyperaesth|hyperesth|circling|neurological sign")
NEURO_EXCLUDE = r"laryngeal|facial paraly|eye disorder|glaucoma|head tilt"
# confirmatory 2020+ analysis (docs/model_a_confirmatory_2020.md): narrower composite chosen from 2013-2019 results
SEIZTREM = "SEIZURE_TREMOR"
SEIZTREM_INCLUDE = r"seiz|convul|tremor|twitch"
COMPOSITES = [NEURO, SEIZTREM]

# FDA breed vocabulary looks like "Collie - Rough", "Shepherd Dog - Australian", "Sheepdog - Shetland"
MDR1_HIGH = r"^collie|shepherd dog - australian|australian shepherd|sheepdog - shetland|shetland|mcnab|silken windhound|english shepherd|chinook"
MDR1_LOW = r"shepherd dog - german|german shepherd|old english|collie - border|border collie"
MIXED = r"crossbred|mixed|\(unknown\)|^dog$|unknown"
STRATA = ["mdr1_high", "mdr1_low", "other_purebred", "mixed_unknown"]
FDA_ALERT = pd.Timestamp("2018-09-20")


# ----------------------------------------------------------------------------- data
def load(src: Path = SRC, species: str = "Dog", safety_only: bool = False,  # noqa: C901
         since: str | None = None) -> duckdb.DuckDBPyConnection:
    """Build report-level tables in an in-memory DuckDB: reports, report_drugs, report_events.

    safety_only (exploratory sensitivity analysis): drop lack-of-effectiveness-only reports and
    lack-of-efficacy reaction terms. These make up a large share of parasiticide reports and mask
    safety signals in proportional analyses ("competition bias").
    """
    con = duckdb.connect()
    since_clause = ""
    if since:
        since_clause = "and regexp_extract(receive_date, '(\\d{8})', 1) >= '" + since.replace("-", "") + "'"
    con.execute(f"""
        create table reports as
        select report_id,
               -- a few records carry a list of dates ("['20250409', '20250409']"); take the first
               strptime(regexp_extract(receive_date, '(\\d{{8}})', 1), '%Y%m%d')::date as receive_date,
               year(strptime(regexp_extract(receive_date, '(\\d{{8}})', 1), '%Y%m%d')) as yr,
               breed_component
        from read_parquet('{src.as_posix()}/reports.parquet')
        where species = '{species}' and regexp_matches(coalesce(receive_date, ''), '\\d{{8}}')
          {since_clause}
          and coalesce(type_of_information, '') not ilike '%product defect%'
          {"and coalesce(type_of_information, '') not ilike 'lack of expected effectiveness%'" if safety_only else ""}
        qualify row_number() over (partition by report_id order by receive_date) = 1
    """)
    con.execute(f"""
        create table report_drugs as
        with raw as (
            select distinct d.report_id, lower(trim(unnest(string_split(d.ingredient, ',')))) as ing
            from read_parquet('{src.as_posix()}/drugs.parquet') d
            semi join reports r on r.report_id = d.report_id
            where d.ingredient is not null
        ), norm as (
            select report_id,
                   regexp_replace(regexp_replace(ing, '\\s+(oxime|hydrochloride|dihydrochloride|sodium|phosphate|acetate)$', ''), '\\s+', ' ', 'g') as drug
            from raw where ing <> ''
        )
        select distinct report_id, drug, false as is_class from norm
    """)
    for cls, members in CLASSES.items():
        pat = "|".join(members)
        con.execute(f"""insert into report_drugs
            select distinct report_id, '{cls}', true from report_drugs
            where not is_class and regexp_matches(drug, '{pat}')""")
    con.execute(f"""
        create table report_events as
        select distinct x.report_id, x.veddra_term_name as event, false as is_composite
        from read_parquet('{src.as_posix()}/reactions.parquet') x
        semi join reports r on r.report_id = x.report_id
        where x.veddra_term_name is not null
        {"and not regexp_matches(lower(x.veddra_term_name), 'lack of efficacy|ineffective')" if safety_only else ""}
    """)
    con.execute(f"""insert into report_events
        select distinct report_id, '{NEURO}', true from report_events
        where regexp_matches(lower(event), '{NEURO_INCLUDE}') and not regexp_matches(lower(event), '{NEURO_EXCLUDE}')""")
    con.execute(f"""insert into report_events
        select distinct report_id, '{SEIZTREM}', true from report_events
        where not is_composite and regexp_matches(lower(event), '{SEIZTREM_INCLUDE}')""")
    # breed stratum
    con.execute(f"""
        create table report_strata as
        with comps as (
            select report_id, lower(unnest(cast(json(breed_component) as varchar[]))) as b from reports
        ), flags as (
            select report_id,
                   bool_or(regexp_matches(b, '{MDR1_HIGH}') and not regexp_matches(b, 'border')) as hi,
                   bool_or(regexp_matches(b, '{MDR1_LOW}')) as lo,
                   bool_and(regexp_matches(b, '{MIXED if species == "Dog" else MIXED + "|domestic"}')) as mixed_only,
                   count(*) as n_comp
            from comps group by 1
        )
        select r.report_id,
               case when f.hi then 'mdr1_high'
                    when f.lo then 'mdr1_low'
                    when f.report_id is null or f.mixed_only or f.n_comp > 1 then 'mixed_unknown'
                    else 'other_purebred' end as stratum
        from reports r left join flags f using (report_id)
    """)
    # keep only reports that have at least one drug and one event
    con.execute("""create or replace table reports as select r.*, s.stratum from reports r join report_strata s using (report_id)
                   where r.report_id in (select report_id from report_drugs) and r.report_id in (select report_id from report_events)""")
    return con


# ----------------------------------------------------------------------------- counts
def cell_counts(con, cutoff: pd.Timestamp | None = None, by_stratum: bool = False,
                drug_events: pd.DataFrame | None = None, leave_drug_out: bool = False) -> pd.DataFrame:
    """Observed n and year-stratified expected E for drug x event (x stratum) cells.

    With drug_events given, returns exactly those cells (including n = 0); otherwise every cell with n >= 1.
    """
    where = f"where r.receive_date <= DATE '{cutoff.date()}'" if cutoff is not None else ""
    s = ", r.stratum" if by_stratum else ""
    sk = ", stratum" if by_stratum else ""
    con.execute(f"create or replace temp table R as select r.report_id, r.yr {s} from reports r {where}")
    con.execute(f"""create or replace temp table DY as select d.drug, d.is_class, R.yr {s.replace('r.', 'R.')}, count(*) nd
                    from report_drugs d join R using (report_id) group by all""")
    con.execute(f"""create or replace temp table EY as select e.event, e.is_composite, R.yr {s.replace('r.', 'R.')}, count(*) ne
                    from report_events e join R using (report_id) group by all""")
    con.execute(f"create or replace temp table TY as select yr {sk}, count(*) nt from R group by all")
    if drug_events is None:
        con.execute(f"""create or replace temp table C as
            select d.drug, e.event, d.is_class, e.is_composite {s.replace('r.', 'R.')}, count(*) n
            from report_drugs d join report_events e using (report_id) join R using (report_id) group by all""")
    else:
        con.register("targets", drug_events[["drug", "event"]].drop_duplicates())
        strata = f"cross join (select unnest({STRATA}) as stratum)" if by_stratum else ""
        con.execute(f"""create or replace temp table C as
            with grid as (select t.drug, t.event {sk} from targets t {strata}),
            obs as (select d.drug, e.event {s.replace('r.', 'R.')}, count(*) n
                    from report_drugs d join report_events e using (report_id) join R using (report_id)
                    where (d.drug, e.event) in (select (drug, event) from targets) group by all)
            select g.*, coalesce(o.n, 0) n from grid g left join obs o using (drug, event {sk})""")
    join_s = "and DY.stratum = C.stratum and EY.stratum = C.stratum and TY.stratum = C.stratum" if by_stratum else ""
    if leave_drug_out and not by_stratum:
        # E_ij = sum_y n_i.y * (n_.jy - n_ijy) / (n_..y - n_i.y): the event rate among reports WITHOUT
        # the drug. Standard MGPS includes the drug's own reports in the event margin, so a drug that
        # dominates an event (isoxazolines account for ~half of dog seizure reports) inflates its own
        # expected count and caps its ratio.
        con.execute("""create or replace temp table CY as
            select d.drug, e.event, R.yr, count(*) n from report_drugs d join report_events e using (report_id)
            join R using (report_id) where (d.drug, e.event) in (select (drug, event) from C) group by all""")
        df = con.execute("""
            select C.drug, C.event, any_value(C.n) n,
                   sum(DY.nd * (EY.ne - coalesce(CY.n, 0)) / nullif(TY.nt - DY.nd, 0)) E
            from C join DY on DY.drug = C.drug
            join EY on EY.event = C.event and EY.yr = DY.yr
            join TY on TY.yr = DY.yr
            left join CY on CY.drug = C.drug and CY.event = C.event and CY.yr = DY.yr
            group by all""").df()
        df["E"] = df.E.clip(lower=1e-6)
    else:
        df = con.execute(f"""
            select C.drug, C.event {', C.stratum' if by_stratum else ''}, any_value(C.n) n,
                   sum(DY.nd * EY.ne / TY.nt) E
            from C
            join DY on DY.drug = C.drug
            join EY on EY.event = C.event and EY.yr = DY.yr
            join TY on TY.yr = DY.yr
            where true {join_s}
            group by all
            """).df()
    # 2x2 margins for PRR/ROR: reports with drug, with event, total (no year stratification)
    m_d = con.execute(f"select d.drug {s.replace('r.', 'R.')}, count(*) a_b from report_drugs d join R using (report_id) group by all").df()
    m_e = con.execute(f"select e.event {s.replace('r.', 'R.')}, count(*) a_c from report_events e join R using (report_id) group by all").df()
    tot = con.execute(f"select {'stratum, ' if by_stratum else ''}count(*) N from R {'group by stratum' if by_stratum else ''}").df()
    keys_d = ["drug"] + (["stratum"] if by_stratum else [])
    keys_e = ["event"] + (["stratum"] if by_stratum else [])
    df = df.merge(m_d, on=keys_d, how="left").merge(m_e, on=keys_e, how="left")
    df = df.merge(tot, on="stratum", how="left") if by_stratum else df.assign(N=int(tot.N.iat[0]))
    return df


# ----------------------------------------------------------------------------- frequentist
def prr_ror(df: pd.DataFrame) -> pd.DataFrame:
    a = df.n.astype(float)
    b = (df.a_b - df.n).clip(lower=0).astype(float)
    c = (df.a_c - df.n).clip(lower=0).astype(float)
    d = (df.N - df.a_b - df.a_c + df.n).clip(lower=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        prr = (a / (a + b)) / (c / (c + d))
        exp_a = (a + b) * (a + c) / (a + b + c + d)
        # Yates-corrected chi-square
        chi2 = (a + b + c + d) * (np.abs(a * d - b * c) - (a + b + c + d) / 2).clip(lower=0) ** 2 / (
            (a + b) * (c + d) * (a + c) * (b + d))
        ror = (a * d) / (b * c)
        se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        ror_lo = np.exp(np.log(ror) - 1.96 * se)
    out = df.copy()
    out["prr"], out["chi2"], out["ror"], out["ror_lo"] = prr, chi2, ror, ror_lo
    out["sig_prr"] = (prr >= 2) & (chi2 >= 4) & (a >= 3)
    out["sig_ror"] = (ror_lo > 1) & (a >= 3)
    return out


# ----------------------------------------------------------------------------- MGPS
@dataclass
class MGPSPrior:
    a1: float
    b1: float
    a2: float
    b2: float
    p: float

    def as_dict(self):
        return self.__dict__.copy()


def _log_nb(n, a, b, E):
    return (special.gammaln(a + n) - special.gammaln(a) - special.gammaln(n + 1)
            + a * np.log(b / (b + E)) + n * np.log(E / (b + E)))


def fit_mgps(n: np.ndarray, E: np.ndarray, max_cells: int = 150_000, seed: int = 0) -> MGPSPrior:
    """Maximum likelihood fit of DuMouchel's two-gamma mixture prior (zero-truncated, cells with n >= 1).

    Five parameters are well identified from a random subsample of cells; fitting on 150k cells
    instead of ~600k changes the prior negligibly and cuts run time ~4x (matters for the
    quarterly re-fits and permutation nulls).
    """
    n, E = np.asarray(n, float), np.asarray(E, float)
    if len(n) > max_cells:
        idx = np.random.default_rng(seed).choice(len(n), max_cells, replace=False)
        n, E = n[idx], E[idx]

    def nll(t):
        a1, b1, a2, b2 = np.exp(t[:4])
        p = special.expit(t[4])
        l1 = np.log(p) + _log_nb(n, a1, b1, E)
        l2 = np.log1p(-p) + _log_nb(n, a2, b2, E)
        ll = np.logaddexp(l1, l2)
        p0 = p * (b1 / (b1 + E)) ** a1 + (1 - p) * (b2 / (b2 + E)) ** a2
        return -(ll - np.log1p(-np.clip(p0, 0, 1 - 1e-12))).sum()

    t0 = np.array([np.log(0.2), np.log(0.1), np.log(2.0), np.log(4.0), special.logit(1 / 3)])
    res = optimize.minimize(nll, t0, method="L-BFGS-B", bounds=[(-8, 6)] * 4 + [(-8, 8)])
    a1, b1, a2, b2 = np.exp(res.x[:4])
    return MGPSPrior(a1, b1, a2, b2, float(special.expit(res.x[4])))


def _mix_quantile(q, w, a1, r1, a2, r2, lo=1e-6, hi=1e5, iters=36):
    """Vectorized bisection for quantile of w*Gamma(a1, rate r1) + (1-w)*Gamma(a2, rate r2)."""
    lo = np.full_like(w, np.log(lo))
    hi = np.full_like(w, np.log(hi))
    for _ in range(iters):
        mid = (lo + hi) / 2
        x = np.exp(mid)
        cdf = w * special.gammainc(a1, r1 * x) + (1 - w) * special.gammainc(a2, r2 * x)
        hi = np.where(cdf > q, mid, hi)
        lo = np.where(cdf > q, lo, mid)
    return np.exp((lo + hi) / 2)


def mgps_posterior(n, E, pr: MGPSPrior) -> pd.DataFrame:
    n, E = np.asarray(n, float), np.asarray(E, float)
    l1 = np.log(pr.p) + _log_nb(n, pr.a1, pr.b1, E)
    l2 = np.log1p(-pr.p) + _log_nb(n, pr.a2, pr.b2, E)
    w = np.exp(l1 - np.logaddexp(l1, l2))
    A1, R1, A2, R2 = pr.a1 + n, pr.b1 + E, pr.a2 + n, pr.b2 + E
    elog = w * (special.digamma(A1) - np.log(R1)) + (1 - w) * (special.digamma(A2) - np.log(R2))
    mean = w * A1 / R1 + (1 - w) * A2 / R2
    return pd.DataFrame({"ebgm": np.exp(elog), "post_mean": mean,
                         "eb05": _mix_quantile(0.05, w, A1, R1, A2, R2)})


# ----------------------------------------------------------------------------- hierarchical stratum model
@dataclass
class HierPrior:
    """lambda_s ~ pi * Gamma(a_c, a_c/mu) + (1 - pi) * Gamma(a_d, a_d/mu).

    Both components are centered on the all-dog rate mu. The concentrated component (a_c large)
    says "this breed stratum behaves like dogs overall"; the diffuse component (a_d small) lets a
    stratum depart from mu when its own data are strong enough. A single-gamma version collapses to
    a_c -> infinity because most drug-event pairs really are homogeneous across breeds, which would
    shrink every genuine breed-specific signal away.
    """
    a_c: float
    a_d: float
    pi: float

    def as_dict(self):
        return self.__dict__.copy()


def fit_hier(n, E, mu) -> HierPrior:
    n, E, mu = (np.asarray(x, float) for x in (n, E, mu))

    def nll(t):
        a_d = np.exp(t[0])
        a_c = a_d + np.exp(t[1])
        pi = special.expit(t[2])
        l1 = np.log(pi) + _log_nb(n, a_c, a_c / mu, E)
        l2 = np.log1p(-pi) + _log_nb(n, a_d, a_d / mu, E)
        return -np.logaddexp(l1, l2).sum()

    res = optimize.minimize(nll, np.array([0.0, np.log(100.0), 2.0]), method="L-BFGS-B",
                            bounds=[(-5, 5), (-5, 10), (-6, 9)])
    a_d = float(np.exp(res.x[0]))
    return HierPrior(a_c=a_d + float(np.exp(res.x[1])), a_d=a_d, pi=float(special.expit(res.x[2])))


def hierarchical_posterior(n, E, mu, hp: HierPrior) -> pd.DataFrame:
    n, E, mu = (np.asarray(x, float) for x in (n, E, mu))
    l1 = np.log(hp.pi) + _log_nb(n, hp.a_c, hp.a_c / mu, E)
    l2 = np.log1p(-hp.pi) + _log_nb(n, hp.a_d, hp.a_d / mu, E)
    w = np.exp(l1 - np.logaddexp(l1, l2))  # P(stratum follows the all-dog rate)
    A1, R1 = hp.a_c + n, hp.a_c / mu + E
    A2, R2 = hp.a_d + n, hp.a_d / mu + E
    elog = w * (special.digamma(A1) - np.log(R1)) + (1 - w) * (special.digamma(A2) - np.log(R2))
    return pd.DataFrame({
        "h_ebgm": np.exp(elog),
        "h_eb05": _mix_quantile(0.05, w, A1, R1, A2, R2),
        "h_ratio05": _mix_quantile(0.05, w, A1, R1 * mu, A2, R2 * mu),
        "h_ratio_mean": w * A1 / (R1 * mu) + (1 - w) * A2 / (R2 * mu),
        "h_p_departs": 1 - w,
        "h_w": w, "h_a1": A1, "h_r1": R1, "h_a2": A2, "h_r2": R2,
    })


def sample_hier(row, draws, rng):
    comp = rng.random(draws) < row.h_w
    return np.where(comp, rng.gamma(row.h_a1, 1 / row.h_r1, draws), rng.gamma(row.h_a2, 1 / row.h_r2, draws))


# ----------------------------------------------------------------------------- full scoring
def score(con, cutoff=None, targets: pd.DataFrame | None = None, leave_drug_out: bool = False) -> dict:
    """Score all-dog and stratum cells. Priors are fit on non-composite, non-class cells with n >= 1."""
    allc = cell_counts(con, cutoff, leave_drug_out=leave_drug_out)
    allc = prr_ror(allc)
    base = ~allc.drug.str.startswith("class:") & (~allc.event.isin(COMPOSITES))
    prior = fit_mgps(allc.loc[base, "n"], allc.loc[base, "E"])
    allc = pd.concat([allc.reset_index(drop=True), mgps_posterior(allc.n, allc.E, prior)], axis=1)
    allc["sig_mgps"] = allc.eb05 >= 2

    strat = cell_counts(con, cutoff, by_stratum=True)
    # complete the stratum grid for every pair observed overall (stratum cells with n = 0 carry information)
    if targets is not None:
        tgt_strat = cell_counts(con, cutoff, by_stratum=True, drug_events=targets)
        strat = pd.concat([strat, tgt_strat]).drop_duplicates(["drug", "event", "stratum"], keep="last")
    strat = prr_ror(strat)
    # the stratum model is centered on an all-dog rate on the same (standard) expected-count scale
    parent = allc
    if leave_drug_out:
        parent = cell_counts(con, cutoff)
        parent = pd.concat([parent.reset_index(drop=True), mgps_posterior(parent.n, parent.E, fit_mgps(
            parent.loc[~parent.drug.str.startswith("class:") & (~parent.event.isin(COMPOSITES)), "n"],
            parent.loc[~parent.drug.str.startswith("class:") & (~parent.event.isin(COMPOSITES)), "E"]))], axis=1)
    strat = strat.merge(parent[["drug", "event", "post_mean", "n", "a_b", "a_c", "N"]].rename(
        columns={"post_mean": "mu", "n": "n_all", "a_b": "a_b_all", "a_c": "a_c_all", "N": "N_all"}),
        on=["drug", "event"], how="left")
    # interaction ROR: stratum vs all other dogs
    o = pd.DataFrame({"n": strat.n_all - strat.n, "a_b": strat.a_b_all - strat.a_b,
                      "a_c": strat.a_c_all - strat.a_c, "N": strat.N_all - strat.N})
    o = prr_ror(o)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(strat.ror) - np.log(o.ror)
        a = strat.n.astype(float); b = (strat.a_b - strat.n).astype(float)
        c = (strat.a_c - strat.n).astype(float); d = (strat.N - strat.a_b - strat.a_c + strat.n).astype(float)
        a2, b2, c2, d2 = o.n.astype(float), (o.a_b - o.n).astype(float), (o.a_c - o.n).astype(float), \
            (o.N - o.a_b - o.a_c + o.n).astype(float)
        se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d + 1 / a2 + 1 / b2 + 1 / c2 + 1 / d2)
        strat["int_ror"] = np.exp(lr)
        strat["int_ror_lo"] = np.exp(lr - 1.96 * se)
    strat["sig_excess_unpooled"] = (strat.int_ror_lo > 1) & (strat.n >= 3)

    priors_s, alphas = {}, {}
    parts = []
    for s, g in strat.groupby("stratum"):
        g = g.reset_index(drop=True)
        gb = ~g.drug.str.startswith("class:") & (~g.event.isin(COMPOSITES)) & (g.n >= 1)
        priors_s[s] = fit_mgps(g.loc[gb, "n"], g.loc[gb, "E"]).as_dict() if gb.sum() > 50 else None
        sp = mgps_posterior(g.n, g.E, MGPSPrior(**priors_s[s])) if priors_s[s] else pd.DataFrame(index=g.index)
        sp = sp.rename(columns={"ebgm": "s_ebgm", "eb05": "s_eb05", "post_mean": "s_post_mean"})
        ok = g.mu.notna() & (g.E > 0)
        ga = ~g.drug.str.startswith("class:") & (~g.event.isin(COMPOSITES)) & ok
        hprior = fit_hier(g.loc[ga, "n"], g.loc[ga, "E"], g.loc[ga, "mu"]) if ga.sum() > 50 else HierPrior(1e4, 1.0, 0.99)
        alphas[s] = hprior.as_dict()
        hp = hierarchical_posterior(g.n, g.E.clip(lower=1e-9), g.mu.fillna(1.0), hprior)
        parts.append(pd.concat([g, sp, hp], axis=1))
    strat = pd.concat(parts, ignore_index=True)
    strat["sig_mgps_strat"] = strat.get("s_eb05", pd.Series(np.nan, index=strat.index)) >= 2
    strat["sig_hier"] = strat.h_eb05 >= 2
    strat["sig_excess_hier"] = (strat.h_ratio05 > 1) & (strat.n >= 3)
    return {"all": allc, "strata": strat, "prior": prior.as_dict(), "strata_priors": priors_s, "alphas": alphas}


# ----------------------------------------------------------------------------- validation
BUDGETS = [10, 50, 100, 500, 1000]
PRODUCT_BUDGETS = [1, 3, 5, 10, 20]


def _product_ranks(allc: pd.DataFrame, rows: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rank of each target among the reaction terms reported for the same drug (or drug class).

    This is the list a product's own safety reviewer works from: "what are the top reactions
    for my product this quarter?" Composite targets are ranked against the drug's single terms.
    """
    out = rows.copy()
    out["product_cells"] = [int(((allc.drug == d) & (~allc.event.isin(COMPOSITES)) & (allc.n >= 3)).sum()) for d in rows.drug]
    for c in cols:
        ranks = []
        for r in rows.itertuples():
            base = allc[(allc.drug == r.drug) & (~allc.event.isin(COMPOSITES)) & (allc.n >= 3)]
            v = base[c].replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
            x = getattr(r, c)
            ranks.append(np.nan if pd.isna(x) else int((v > x).sum() + 1))
        out[f"prank_{c}"] = ranks
    return out


def _ranks(base: pd.DataFrame, rows: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rank of each target row among base cells for each score column (1 = top). Ties count against the target."""
    out = rows.copy()
    for c in cols:
        v = np.sort(base[c].replace([np.inf, -np.inf], np.nan).dropna().to_numpy())
        x = rows[c].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)
        out[f"rank_{c}"] = np.where(np.isnan(x), np.nan, len(v) - np.searchsorted(v, x, side="left") + 1)
    return out


def _review_base(df: pd.DataFrame) -> pd.DataFrame:
    """Cells a safety team would actually review: single ingredients, single reaction terms, n >= 3."""
    return df[~df.drug.str.startswith("class:") & (~df.event.isin(COMPOSITES)) & (df.n >= 3)]


def timeline(con, start="2013-03-31", end="2019-12-31", targets=None, leave_drug_out=False,
             with_strata=True) -> pd.DataFrame:
    rows = []
    for q in pd.date_range(start, end, freq="QE"):
        res = score(con, q, targets, leave_drug_out)
        allc = res["all"]
        a = _ranks(_review_base(allc), allc.merge(targets, on=["drug", "event"]), ["prr", "ror_lo", "eb05"])
        a = _product_ranks(allc, a, ["prr", "ror_lo", "eb05"])
        n_base = len(_review_base(allc))
        for r in a.itertuples():
            rows.append(dict(quarter_end=q.date(), drug=r.drug, event=r.event, stratum="all", n=r.n, E=r.E,
                             prr=r.prr, ror_lo=r.ror_lo, sig_prr=r.sig_prr, sig_ror=r.sig_ror, ebgm=r.ebgm,
                             eb05=r.eb05, sig_mgps=r.sig_mgps, rank_prr=r.rank_prr, rank_ror_lo=r.rank_ror_lo,
                             rank_eb05=r.rank_eb05, cells_ranked=n_base, prank_prr=r.prank_prr,
                             prank_ror_lo=r.prank_ror_lo, prank_eb05=r.prank_eb05,
                             product_cells=r.product_cells))
        if with_strata:
            st = res["strata"]
            sb = _review_base(st)
            s = _ranks(sb, st.merge(targets, on=["drug", "event"]), ["int_ror_lo", "h_ratio05"])
            for r in s.itertuples():
                rows.append(dict(quarter_end=q.date(), drug=r.drug, event=r.event, stratum=r.stratum, n=r.n, E=r.E,
                                 prr=r.prr, sig_prr=r.sig_prr, sig_ror=r.sig_ror, ebgm=getattr(r, "s_ebgm", np.nan),
                                 eb05=getattr(r, "s_eb05", np.nan), sig_mgps=r.sig_mgps_strat, h_eb05=r.h_eb05,
                                 sig_hier=r.sig_hier, h_ratio05=r.h_ratio05, sig_excess_hier=r.sig_excess_hier,
                                 int_ror_lo=r.int_ror_lo, sig_excess_unpooled=r.sig_excess_unpooled,
                                 rank_int_ror_lo=r.rank_int_ror_lo, rank_h_ratio05=r.rank_h_ratio05,
                                 cells_ranked=len(sb)))
        print(f"  timeline {q.date()}", flush=True)
    return pd.DataFrame(rows)


def budget_detection(tl: pd.DataFrame, drug, event, stratum, rank_cols, budgets=BUDGETS) -> dict:
    """First quarter each method ranks the target within each review budget K."""
    t = tl[(tl.drug == drug) & (tl.event == event) & (tl.stratum == stratum)].sort_values("quarter_end")
    # a rank only counts when the target has n >= 3 and, for within-product lists, the product has at
    # least 20 reviewable terms (otherwise "top 5" is most of the list)
    ok = t.n >= 3
    if "product_cells" in t and any(c.startswith("prank_") for c in rank_cols):
        ok &= t.product_cells >= 20
    t = t[ok]
    out = {}
    for c in rank_cols:
        if c not in t:
            continue
        out[c] = {f"top_{k}": (str(t.loc[t[c] <= k, "quarter_end"].min()) if (t[c] <= k).any() else None)
                  for k in budgets}
        out[c]["rank_at_last_quarter"] = None if t.empty or pd.isna(t[c].iloc[-1]) else int(t[c].iloc[-1])
    return out


def first_signal(tl: pd.DataFrame, drug, event, stratum, col):
    t = tl[(tl.drug == drug) & (tl.event == event) & (tl.stratum == stratum) & tl[col].fillna(False).astype(bool)]
    return None if t.empty else str(t.quarter_end.min())


def mdr1_comparison(res, drug="class:macrocyclic_lactones", event=NEURO, draws=20000, seed=0) -> dict:
    s = res["strata"]
    g = s[(s.drug == drug) & (s.event == event)].set_index("stratum")
    if not {"mdr1_high", "other_purebred"} <= set(g.index):
        return {}
    rng = np.random.default_rng(seed)
    hi = sample_hier(g.loc["mdr1_high"], draws, rng)
    ot = sample_hier(g.loc["other_purebred"], draws, rng)
    cols = ["n", "E", "prr", "sig_prr", "ror", "ror_lo", "sig_ror", "int_ror", "int_ror_lo", "sig_excess_unpooled",
            "s_ebgm", "s_eb05", "sig_mgps_strat", "h_ebgm", "h_eb05", "h_ratio05", "h_ratio_mean", "h_p_departs", "sig_hier",
            "sig_excess_hier"]
    tbl = g[[c for c in cols if c in g.columns]].reset_index()
    a = res["all"]
    pooled = a[(a.drug == drug) & (a.event == event)][["n", "E", "prr", "sig_prr", "ebgm", "eb05", "sig_mgps"]]
    return {"strata": json.loads(tbl.to_json(orient="records")),
            "pooled_all_dogs": json.loads(pooled.to_json(orient="records")),
            "p_rate_mdr1_high_gt_other_purebred": float((hi > ot).mean()),
            "rate_ratio_mdr1_high_vs_other_median": float(np.median(hi / ot))}


def permute_events(con, seed):
    """Null 1: reassign each report's event set to another report in the same year."""
    con.execute(f"""create or replace table _perm as
        with r as (select report_id, yr, row_number() over (partition by yr order by report_id) i,
                          row_number() over (partition by yr order by hash(report_id || '{seed}')) j from reports)
        select a.report_id as new_id, b.report_id as old_id from r a join r b on a.yr = b.yr and a.i = b.j""")
    con.execute("create or replace table _events_orig as select * from report_events")
    con.execute("create or replace table report_events as select p.new_id report_id, e.event, e.is_composite "
                "from _events_orig e join _perm p on p.old_id = e.report_id")


def permute_strata(con, seed):
    """Null 2: shuffle breed strata across reports within year."""
    con.execute("create or replace table _reports_orig as select * from reports")
    con.execute(f"""create or replace table reports as
        with r as (select *, row_number() over (partition by yr order by report_id) i,
                          row_number() over (partition by yr order by hash(report_id || '{seed}')) j from _reports_orig)
        select a.report_id, a.receive_date, a.yr, a.breed_component, b.stratum
        from r a join r b on a.yr = b.yr and a.i = b.j""")


def restore(con):
    if con.execute("select count(*) from information_schema.tables where table_name = '_events_orig'").fetchone()[0]:
        con.execute("create or replace table report_events as select * from _events_orig")
        con.execute("drop table _events_orig")
    if con.execute("select count(*) from information_schema.tables where table_name = '_reports_orig'").fetchone()[0]:
        con.execute("create or replace table reports as select * from _reports_orig")
        con.execute("drop table _reports_orig")


def null_rates(con, k=20, leave_drug_out=False) -> pd.DataFrame:
    rows = []
    for i in range(k):
        permute_events(con, i)
        r = score(con, leave_drug_out=leave_drug_out)
        a = r["all"][(r["all"].drug.str.startswith("class:") == False) & (~r["all"].event.isin(COMPOSITES))]
        s = r["strata"][(r["strata"].drug.str.startswith("class:") == False) & (~r["strata"].event.isin(COMPOSITES))]
        rows.append(dict(null="events_shuffled", rep=i, cells=len(a),
                         prr=a.sig_prr.mean() * 1000, ror=a.sig_ror.mean() * 1000, mgps=a.sig_mgps.mean() * 1000,
                         strat_cells=len(s), mgps_strat=s.sig_mgps_strat.mean() * 1000,
                         hier=s.sig_hier.mean() * 1000))
        restore(con)
        permute_strata(con, i)
        r = score(con, leave_drug_out=leave_drug_out)
        s = r["strata"][(r["strata"].drug.str.startswith("class:") == False) & (~r["strata"].event.isin(COMPOSITES))]
        rows.append(dict(null="strata_shuffled", rep=i, strat_cells=len(s),
                         excess_unpooled=s.sig_excess_unpooled.mean() * 1000,
                         excess_hier=s.sig_excess_hier.mean() * 1000))
        restore(con)
        print(f"  null replicate {i + 1}/{k}", flush=True)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--species", default="Dog")
    ap.add_argument("--permutations", type=int, default=20)
    ap.add_argument("--skip-timeline", action="store_true")
    ap.add_argument("--rerun-timeline", action="store_true", help="recompute even if timeline.csv exists")
    ap.add_argument("--rerun-nulls", action="store_true", help="recompute even if null_rates.csv exists")
    ap.add_argument("--safety-only", action="store_true", help="exploratory: drop lack-of-effectiveness reports/terms")
    ap.add_argument("--leave-drug-out", action="store_true", help="exploratory: expected counts exclude the drug's own reports")
    a = ap.parse_args()
    tag = a.species.lower() + ("_safety" if a.safety_only else "") + ("_ldo" if a.leave_drug_out else "")
    out = OUT / tag
    out.mkdir(parents=True, exist_ok=True)

    con = load(a.src, a.species, a.safety_only)
    info = con.execute("""select (select count(*) from reports) reports, (select min(receive_date) from reports) first_date,
                          (select max(receive_date) from reports) last_date,
                          (select count(distinct drug) from report_drugs) drugs,
                          (select count(distinct event) from report_events) events""").df().to_dict("records")[0]
    strata = con.execute("select stratum, count(*) n from reports group by 1 order by 2 desc").df()
    print(info, strata, sep="\n")
    targets = pd.DataFrame({"drug": ["class:isoxazolines", "class:macrocyclic_lactones"] + ISOXAZOLINES + MACROCYCLIC_LACTONES,
                            "event": NEURO})
    # secondary target in every run (amendment 2026-10-02): the most-reported neurologic term
    targets = pd.concat([targets, targets.assign(event="Seizure NOS")], ignore_index=True)
    is_dog = a.species == "Dog"

    res = score(con, targets=targets, leave_drug_out=a.leave_drug_out)
    res["all"].sort_values("eb05", ascending=False).to_csv(out / "signals_all.csv", index=False)
    res["strata"].to_csv(out / "signals_strata.csv", index=False)
    summary = {"data": {k: str(v) for k, v in info.items()}, "strata": strata.to_dict("records"),
               "prior": res["prior"], "strata_priors": res["strata_priors"], "hier_priors": res["alphas"],
               "targets_current": json.loads(res["all"].merge(targets).to_json(orient="records")),
               "mdr1": mdr1_comparison(res) if a.species == "Dog" else None}
    if not a.skip_timeline:
        if (out / "timeline.csv").exists() and not a.rerun_timeline:
            tl = pd.read_csv(out / "timeline.csv")  # reuse; the quarterly re-fits are the slow part
        else:
            tl = timeline(con, targets=targets, leave_drug_out=a.leave_drug_out, with_strata=is_dog)
            tl.to_csv(out / "timeline.csv", index=False)
        summary["time_to_signal"] = {
            f"isox_{ev}_{col}": {"first_quarter": first_signal(tl, "class:isoxazolines", ev, "all", col),
                                 "fda_alert": str(FDA_ALERT.date())}
            for ev in sorted(set(targets.event)) for col in ["sig_prr", "sig_ror", "sig_mgps"]}
        if is_dog:
            for col in ["sig_prr", "sig_mgps", "sig_hier", "sig_excess_unpooled", "sig_excess_hier"]:
                summary["time_to_signal"][f"ml_mdr1_high_{col}"] = first_signal(
                    tl, "class:macrocyclic_lactones", NEURO, "mdr1_high", col)
        if "rank_eb05" in tl:
            rb = {f"isox_{ev}": budget_detection(tl, "class:isoxazolines", ev, "all",
                                                 ["rank_prr", "rank_ror_lo", "rank_eb05"])
                  for ev in sorted(set(targets.event))}
            for d in ["class:isoxazolines"] + ISOXAZOLINES:
                for ev in sorted(set(targets.event)):
                    rb[f"product_{d}_{ev}"] = budget_detection(tl, d, ev, "all",
                                                              ["prank_prr", "prank_ror_lo", "prank_eb05"],
                                                              PRODUCT_BUDGETS)
            if is_dog:
                rb["ml_mdr1_high_excess"] = budget_detection(tl, "class:macrocyclic_lactones", NEURO, "mdr1_high",
                                                             ["rank_int_ror_lo", "rank_h_ratio05"])
            summary["review_budget"] = rb
    if a.permutations:
        if (out / "null_rates.csv").exists() and not a.rerun_nulls:
            nr = pd.read_csv(out / "null_rates.csv")
        else:
            nr = null_rates(con, a.permutations, a.leave_drug_out)
            nr.to_csv(out / "null_rates.csv", index=False)
        summary["null_signals_per_1000_cells"] = json.loads(
            nr.groupby("null").mean(numeric_only=True).drop(columns="rep").round(3).to_json(orient="index"))
    summary["config"] = {"species": a.species, "safety_only": a.safety_only, "leave_drug_out": a.leave_drug_out,
                         "analysis": "pre-registered primary" if not (a.safety_only or a.leave_drug_out) else "exploratory"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in summary if k not in ("strata_priors", "mdr1")}, indent=2, default=str)[:6000])


if __name__ == "__main__":
    main()
