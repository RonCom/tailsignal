"""Model A exposure denominators: US reporting rates per 10,000 fluralaner doses, and break-even
doses for the other isoxazolines.

Spec: docs/model_a_exposure_spec.md (pre-registered). Results: docs/model_a_exposure_results.md.

Usage:
    python -m tailsignal.models.pv_exposure
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from tailsignal.models.pharmacovigilance import NEURO, load

OUT = Path("reports/model_a/exposure")

# EMA news item, 17 Aug 2017: ~41.6M doses worldwide Feb 2014 - Dec 2016, ~18M in the EU;
# 2,144 EU dogs with electronically reported suspected side effects to 15 Aug 2017.
FLU_GLOBAL_2016 = 41.6e6
FLU_EU_2016 = 18.0e6
FLU_NON_EU_2016 = FLU_GLOBAL_2016 - FLU_EU_2016
EU_REPORTED_DOGS = 2144
EMA_CONVULSION_BOUND = 1.0  # "fewer than 1 in 10,000 animals treated"
# MSD Animal Health, 10 Jul 2025: more than 350M doses in 100 countries
FLU_GLOBAL_2025 = 350e6
US_SHARE_SCENARIOS = {"lower bound (all non-EU doses in US)": 1.0, "US = 75% of non-EU": 0.75, "US = 50% of non-EU": 0.50}
CONVULSION = r"convul|seiz"
WINDOWS = {  # drug -> (first year, last year) for Q2
    "fluralaner": (2014, 2016),
    "afoxolaner": (2014, 2016),
    "sarolaner": (2014, 2016),
    "lotilaner": (2018, 2020),
}
PER = 1e4


def counts(con: duckdb.DuckDBPyConnection, drug: str, y0: int, y1: int) -> dict:
    """US dog reports naming `drug`, received in [y0, y1]: any, neurologic composite, convulsion."""
    q = f"""
        with rep as (
            select distinct r.report_id from reports r join report_drugs d using (report_id)
            where not d.is_class and d.drug like '%{drug}%' and r.yr between {y0} and {y1}
              and split_part(r.report_id, '-', 1) = 'USA'
        )
        select
            (select count(*) from rep) as any_report,
            (select count(distinct e.report_id) from report_events e semi join rep using (report_id)
              where e.event = '{NEURO}') as neurologic,
            (select count(distinct e.report_id) from report_events e semi join rep using (report_id)
              where not e.is_composite and regexp_matches(lower(e.event), '{CONVULSION}')) as convulsion
    """
    return con.execute(q).df().iloc[0].astype(int).to_dict()


def rates(n: dict, doses: float) -> dict:
    return {k: v / doses * PER for k, v in n.items()}


def analyse(con: duckdb.DuckDBPyConnection) -> dict:
    out: dict = {}
    # Q1
    flu = counts(con, "fluralaner", 2014, 2016)
    q1 = []
    for label, share in US_SHARE_SCENARIOS.items():
        doses = FLU_NON_EU_2016 * share
        q1.append({"scenario": label, "us_doses_m": doses / 1e6, **{f"{k}_per_10k": v for k, v in rates(flu, doses).items()}})
    q1 = pd.DataFrame(q1)
    lb = q1.iloc[0]
    eu_rate = EU_REPORTED_DOGS / FLU_EU_2016 * PER
    out["q1"] = {
        "counts": flu,
        "table": q1.to_dict(orient="records"),
        "eu_electronic_rate_per_10k": eu_rate,
        "P1_convulsion_lb_below_1": bool(lb["convulsion_per_10k"] < EMA_CONVULSION_BOUND),
        "P2_any_lb_at_least_2x_eu": bool(lb["any_report_per_10k"] >= 2 * eu_rate),
        "any_lb_over_eu": float(lb["any_report_per_10k"] / eu_rate),
    }
    # Q2
    ref = lb["neurologic_per_10k"]
    q2 = []
    for drug, (y0, y1) in WINDOWS.items():
        n = counts(con, drug, y0, y1)
        q2.append({"drug": drug, "window": f"{y0}-{y1}", **n,
                   "break_even_us_doses_m": n["neurologic"] / ref * PER / 1e6})
    out["q2"] = {"reference_neuro_per_10k": float(ref), "table": q2}
    # Q3
    flu_all = counts(con, "fluralaner", 2014, 2024)
    out["q3"] = {"counts": flu_all, "per_10k_lower_bound": rates(flu_all, FLU_GLOBAL_2025),
                 "neuro_2014_2016_lb": float(ref)}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = load()
    res = analyse(con)
    (OUT / "exposure.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
