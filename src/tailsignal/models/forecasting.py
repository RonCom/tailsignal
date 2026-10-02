"""Hierarchical demand forecasting with a rolling-origin backtest (pre-registered H8).

Weekly demand per location for four services (daycare visits, boarding stays, grooming
appointments, vet visits), arranged as service -> market -> location. Base models:
seasonal naive (52 weeks), MSTL with an ETS trend. Reconciliation: bottom-up and MinT
(shrinkage). Backtest: 12 origins, 4 weeks apart, from 2024-07-01; 13-week horizon.

Decision layer: daycare staffing from the forecast's upper 80% bound, compared with
staffing from seasonal naive, under illustrative cost assumptions.

    python -m tailsignal.models.forecasting
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from hierarchicalforecast.core import HierarchicalReconciliation
from hierarchicalforecast.methods import BottomUp, MinTrace
from hierarchicalforecast.utils import aggregate
from statsforecast import StatsForecast
from statsforecast.models import MSTL, AutoETS, SeasonalNaive

DB = Path("data/warehouse.duckdb")
OUT = Path("reports/forecasting")
H = 13
FIRST_ORIGIN = pd.Timestamp("2024-07-01")
N_ORIGINS = 12
STEP_WEEKS = 4
LEVEL = 80
SPEC = [["service"], ["service", "market"], ["service", "market", "location"]]

# illustrative staffing assumptions (not market data)
DOGS_PER_HANDLER = 15
HANDLER_DAY_COST = 160.0       # 8 h x $20
TURNED_AWAY_COST = 40.0        # lost daycare revenue per dog-day over capacity


def weekly_demand(con) -> pd.DataFrame:
    df = con.execute("""
        select l.market, e.location_id as location,
               case e.channel when 'daycare' then 'daycare' when 'boarding' then 'boarding'
                              when 'grooming' then 'grooming' else 'vet' end as service,
               date_trunc('week', e.event_date) as ds, count(*) as y
        from core.fct_service_event e join core.dim_location l using (location_id)
        group by all
    """).df()
    df["ds"] = pd.to_datetime(df.ds)
    # complete grid (weeks with zero demand, sites before opening)
    weeks = pd.date_range(df.ds.min(), df.ds.max(), freq="W-MON")
    keys = df[["service", "market", "location"]].drop_duplicates()
    grid = keys.merge(pd.DataFrame({"ds": weeks}), how="cross")
    df = grid.merge(df, on=["service", "market", "location", "ds"], how="left").fillna({"y": 0})
    # drop the first and last partial weeks
    return df[(df.ds > weeks.min()) & (df.ds < weeks.max())].reset_index(drop=True)


def models():
    return [SeasonalNaive(season_length=52, alias="SNaive"),
            MSTL(season_length=52, trend_forecaster=AutoETS(model="ZZN"), alias="MSTL")]


def add_combo(df: pd.DataFrame) -> pd.DataFrame:
    """Exploratory (added after the one-origin smoke test): equal-weight average of the two base
    models, a standard robust choice when neither model wins everywhere."""
    df = df.copy()
    df["Combo"] = (df["SNaive"] + df["MSTL"]) / 2
    for side in ("lo", "hi"):
        a, b = f"SNaive-{side}-{LEVEL}", f"MSTL-{side}-{LEVEL}"
        if a in df and b in df:
            df[f"Combo-{side}-{LEVEL}"] = (df[a] + df[b]) / 2
    return df


def mase(y, yhat, scale):
    return np.mean(np.abs(y - yhat)) / scale if scale > 0 else np.nan


def run_origin(Y_df, S_df, tags, origin) -> pd.DataFrame:
    train = Y_df[Y_df.ds < origin]
    test = Y_df[(Y_df.ds >= origin) & (Y_df.ds < origin + pd.Timedelta(weeks=H))]
    sf = StatsForecast(models=models(), freq="W-MON", n_jobs=1)
    fc = add_combo(sf.forecast(df=train, h=H, level=[LEVEL], fitted=True))
    fitted = add_combo(sf.forecast_fitted_values())
    rec = HierarchicalReconciliation(reconcilers=[BottomUp(), MinTrace(method="mint_shrink")])
    r = rec.reconcile(Y_hat_df=fc, Y_df=fitted, S_df=S_df, tags=tags, level=[LEVEL])
    r = r.merge(test[["unique_id", "ds", "y"]], on=["unique_id", "ds"], how="inner")
    r["origin"] = origin
    # in-sample seasonal-naive MAE per series for MASE scaling
    scale = (train.sort_values("ds").groupby("unique_id").y
             .apply(lambda s: np.mean(np.abs(s.values[52:] - s.values[:-52])) if len(s) > 52 else np.nan))
    r["scale"] = r.unique_id.map(scale)
    return r


def staffing_eval(bt: pd.DataFrame, col_hi: str, col_point: str) -> dict:
    """Daily daycare staffing from weekly forecasts (5 open days): handlers = ceil(hi/5/15)."""
    d = bt[bt.unique_id.str.startswith("daycare/") & (bt.unique_id.str.count("/") == 2)].copy()
    d["handlers"] = np.ceil(d[col_hi].clip(lower=0) / 5 / DOGS_PER_HANDLER)
    d["need"] = np.ceil(d.y / 5 / DOGS_PER_HANDLER)
    over = (d.handlers - d.need).clip(lower=0) * 5 * HANDLER_DAY_COST
    under_dogs = (d.y / 5 - d.handlers * DOGS_PER_HANDLER).clip(lower=0) * 5
    return {"handler_days": float(d.handlers.sum() * 5), "overstaff_cost": round(float(over.sum()), 0),
            "turned_away_dog_days": round(float(under_dogs.sum()), 0),
            "turned_away_cost": round(float(under_dogs.sum() * TURNED_AWAY_COST), 0),
            "total_cost": round(float(over.sum() + under_dogs.sum() * TURNED_AWAY_COST), 0)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--origins", type=int, default=N_ORIGINS)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(a.db), read_only=True)
    raw = weekly_demand(con)
    Y_df, S_df, tags = aggregate(raw, SPEC)
    Y_df = Y_df.reset_index() if "unique_id" not in Y_df.columns else Y_df

    parts = []
    for i in range(a.origins):
        origin = FIRST_ORIGIN + pd.Timedelta(weeks=STEP_WEEKS * i)
        parts.append(run_origin(Y_df, S_df, tags, origin))
        print(f"  origin {origin.date()}", flush=True)
    bt = pd.concat(parts, ignore_index=True)
    bt.to_csv(OUT / "backtest.csv", index=False)

    bottom = bt[bt.unique_id.str.count("/") == 2]
    methods = {"SNaive": "SNaive", "MSTL (base)": "MSTL", "MSTL + bottom-up": "MSTL/BottomUp",
               "MSTL + MinT shrink": "MSTL/MinTrace_method-mint_shrink",
               "Combo + MinT shrink (exploratory)": "Combo/MinTrace_method-mint_shrink"}
    acc = {}
    for name, col in methods.items():
        per = bottom.groupby("unique_id").apply(lambda g: mase(g.y.values, g[col].values, g.scale.iloc[0]))
        cov = None
        lo, hi = f"{col}-lo-{LEVEL}", f"{col}-hi-{LEVEL}"
        if lo in bottom and hi in bottom:
            cov = float(((bottom.y >= bottom[lo]) & (bottom.y <= bottom[hi])).mean())
        acc[name] = {"mean_mase_bottom": round(float(per.mean()), 3), "median_mase_bottom": round(float(per.median()), 3),
                     "coverage_80": None if cov is None else round(cov, 3)}
    by_service = {}
    for svc in ["daycare", "boarding", "grooming", "vet"]:
        b = bottom[bottom.unique_id.str.startswith(svc + "/")]
        by_service[svc] = {name: round(float(b.groupby("unique_id").apply(
            lambda g: mase(g.y.values, g[col].values, g.scale.iloc[0])).mean()), 3) for name, col in methods.items()}

    best = "MSTL/MinTrace_method-mint_shrink"
    staffing = {f"{name} | {basis}": staffing_eval(bt, col if basis == "point" else f"{col}-hi-{LEVEL}", col)
                for name, col in [("SNaive", "SNaive"), ("MSTL + MinT", best),
                                  ("Combo + MinT", "Combo/MinTrace_method-mint_shrink")]
                for basis in ("point", "upper80") if basis == "point" or f"{col}-hi-{LEVEL}" in bt}
    staffing.update({
                "assumptions": {"dogs_per_handler": DOGS_PER_HANDLER, "handler_day_cost": HANDLER_DAY_COST,
                                "turned_away_cost_per_dog_day": TURNED_AWAY_COST, "note": "illustrative"}})
    h8_pass = (acc["MSTL + MinT shrink"]["mean_mase_bottom"] < acc["SNaive"]["mean_mase_bottom"]
               and acc["MSTL + MinT shrink"]["coverage_80"] is not None
               and 0.75 <= acc["MSTL + MinT shrink"]["coverage_80"] <= 0.85)

    # forward forecast for the 13 weeks after the data ends (for the partner portal / staffing plan)
    sf = StatsForecast(models=models(), freq="W-MON", n_jobs=1)
    fc = add_combo(sf.forecast(df=Y_df, h=H, level=[LEVEL], fitted=True))
    rec = HierarchicalReconciliation(reconcilers=[MinTrace(method="mint_shrink")]).reconcile(
        Y_hat_df=fc, Y_df=add_combo(sf.forecast_fitted_values()), S_df=S_df, tags=tags, level=[LEVEL])
    rec.to_csv(OUT / "forecast_next_13_weeks.csv", index=False)
    # staffing rule = lowest total cost in the backtest
    rule = min((k for k in staffing if "|" in k), key=lambda k: staffing[k]["total_cost"])
    name, basis = [x.strip() for x in rule.split("|")]
    col = {"SNaive": "SNaive", "MSTL + MinT": best, "Combo + MinT": "Combo/MinTrace_method-mint_shrink"}[name]
    col = col if basis == "point" else f"{col}-hi-{LEVEL}"
    if col not in rec:  # forward run only reconciles with MinT; fall back to the MinT version of SNaive
        col = col.replace("SNaive", "SNaive/MinTrace_method-mint_shrink") if "SNaive" in col else col
    dc = rec[rec.unique_id.str.startswith("daycare/") & (rec.unique_id.str.count("/") == 2)].copy()
    dc["handlers_per_day"] = np.ceil(dc[col].clip(lower=0) / 5 / DOGS_PER_HANDLER).astype(int)
    plan = dc.pivot_table(index="ds", columns="unique_id", values="handlers_per_day").astype(int)
    plan.to_csv(OUT / "daycare_staffing_plan.csv")

    summary = {"series": int(Y_df.unique_id.nunique()), "bottom_series": int(bottom.unique_id.nunique()),
               "origins": a.origins, "horizon_weeks": H, "accuracy": acc, "mase_by_service": by_service,
               "H8_pass": bool(h8_pass), "staffing_backtest": staffing, "staffing_rule_used_for_plan": rule,
               "staffing_plan_weeks": [str(d.date()) for d in plan.index]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
