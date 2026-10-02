"""Sequential split-conformal intervals for the demand forecast. Spec: docs/forecast_conformal_spec.md.

Uses reports/forecasting/backtest.csv (run tailsignal.models.forecasting first).

    uv run python -m tailsignal.models.forecasting_conformal
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from tailsignal.models.forecasting import DOGS_PER_HANDLER, HANDLER_DAY_COST, OUT, TURNED_AWAY_COST, staffing_eval

POINT = "MSTL/MinTrace_method-mint_shrink"
LEVEL, MIN_N, POOL = 0.80, 30, 2
BANDS = {"1-4": (1, 4), "5-8": (5, 8), "9-13": (9, 13)}


def conformal(bt: pd.DataFrame) -> pd.DataFrame:
    b = bt[bt.unique_id.str.count("/") == 2].copy()
    b["ds"], b["origin"] = pd.to_datetime(b.ds), pd.to_datetime(b.origin)
    b["h"] = ((b.ds - b.origin).dt.days // 7 + 1).astype(int)
    b["err"] = (b.y - b[POINT]).abs() / b.scale
    q = np.full(len(b), np.nan)
    for origin in sorted(b.origin.unique()):
        past = b[b.ds < origin]  # errors already observed at this origin
        idx = np.flatnonzero((b.origin == origin).to_numpy())
        for h in range(1, 14):
            e = past[past.h == h].err.dropna()
            if len(e) < MIN_N:
                e = past[(past.h - h).abs() <= POOL].err.dropna()
            if len(e) >= MIN_N:
                sel = idx[b.h.to_numpy()[idx] == h]
                n = len(e)
                q[sel] = np.quantile(e, min(1.0, np.ceil((n + 1) * LEVEL) / n))
    b["q"] = q
    # exploratory newsvendor: one-sided quantile of signed scaled errors at the cost ratio
    tau = TURNED_AWAY_COST / (TURNED_AWAY_COST + HANDLER_DAY_COST / DOGS_PER_HANDLER)
    b["signed"] = (b.y - b[POINT]) / b.scale
    qs = np.full(len(b), np.nan)
    for origin in sorted(b.origin.unique()):
        past = b[b.ds < origin]
        idx = np.flatnonzero((b.origin == origin).to_numpy())
        for h in range(1, 14):
            e = past[past.h == h].signed.dropna()
            if len(e) < MIN_N:
                e = past[(past.h - h).abs() <= POOL].signed.dropna()
            if len(e) >= MIN_N:
                sel = idx[b.h.to_numpy()[idx] == h]
                qs[sel] = np.quantile(e, tau)
    b["nv_hi"] = b[POINT] + qs * b.scale
    b.attrs["tau"] = tau
    b["cf_lo"] = b[POINT] - b.q * b.scale
    b["cf_hi"] = b[POINT] + b.q * b.scale
    return b


def main():
    bt = pd.read_csv(OUT / "backtest.csv")
    b = conformal(bt)
    s = b[b.q.notna()].copy()
    lo, hi = f"{POINT}-lo-80", f"{POINT}-hi-80"
    s["cov_cf"] = (s.y >= s.cf_lo) & (s.y <= s.cf_hi)
    s["cov_mint"] = (s.y >= s[lo]) & (s.y <= s[hi])
    s["w_cf"], s["w_mint"] = s.cf_hi - s.cf_lo, s[hi] - s[lo]
    band = {}
    for k, (a, z) in BANDS.items():
        g = s[s.h.between(a, z)]
        band[k] = {"n": int(len(g)), "coverage_conformal": round(float(g.cov_cf.mean()), 3),
                   "coverage_mint": round(float(g.cov_mint.mean()), 3),
                   "median_width_conformal": round(float(g.w_cf.median()), 1),
                   "median_width_mint": round(float(g.w_mint.median()), 1)}
    s_full = s.rename(columns={"cf_hi": "conformal_hi"})
    staff = {"MinT upper 80%": staffing_eval(s_full, hi, POINT),
             "Conformal upper 80%": staffing_eval(s_full, "conformal_hi", POINT),
             "MinT point": staffing_eval(s_full, POINT, POINT),
             "Newsvendor, conformal (exploratory)": staffing_eval(s_full[s_full.nv_hi.notna()], "nv_hi", POINT)}
    cov = float(s.cov_cf.mean())
    exp = {
        "coverage_75_to_85": bool(0.75 <= cov <= 0.85),
        "each_band_70_to_90": bool(all(0.70 <= v["coverage_conformal"] <= 0.90 for v in band.values())),
        "wider_than_mint_every_band": bool(all(v["median_width_conformal"] > v["median_width_mint"] for v in band.values())),
        "staffing_cost_not_higher": bool(staff["Conformal upper 80%"]["total_cost"] <= staff["MinT upper 80%"]["total_cost"]),
    }
    res = {"scored_forecasts": int(len(s)), "scored_origins": int(s.origin.nunique()),
           "origins_total": int(b.origin.nunique()),
           "coverage_conformal": round(cov, 3), "coverage_mint_same_forecasts": round(float(s.cov_mint.mean()), 3),
           "by_horizon": band, "newsvendor_quantile": round(b.attrs["tau"], 3), "staffing_same_weeks": staff, "expectations": exp}
    (OUT / "conformal").mkdir(parents=True, exist_ok=True)
    (OUT / "conformal" / "summary.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
