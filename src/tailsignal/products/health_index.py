"""Pet Health Index: condition indexes (network = 100) and a composite illness-cost index.

Spec: docs/productization_spec.md. Built only from the k-suppressed prevalence mart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from tailsignal.synth.generate import DX_PRICE

COST = {c: (lo + hi) / 2 for c, (lo, hi) in DX_PRICE.items()}  # simulator price midpoints (replace with invoices)
KEYS = ["year", "species", "breed_group", "market"]


def condition_index(prev: pd.DataFrame) -> pd.DataFrame:
    d = prev[~prev.suppressed.astype(bool)].copy()
    d["cases"] = d.pets_with_condition.astype(float)
    d["n"] = d.pets_seen.astype(float)
    out = []
    for (sp, cond), g in d.groupby(["species", "condition"]):
        # reference prevalence by year (pet-weighted over released cells)
        ref = g.groupby("year").apply(lambda x: x.cases.sum() / x.n.sum(), include_groups=False)
        g = g.assign(ref=g.year.map(ref))
        g = g[g.ref > 0]  # a condition with no released cases in a species-year has no index
        if g.empty:
            continue
        p = g.cases / g.n
        between = float(np.average((p - g.ref) ** 2, weights=g.n) - np.mean(g.ref * (1 - g.ref) / g.n))
        pr = float(np.average(g.ref, weights=g.n))
        m = pr * (1 - pr) / between - 1 if between > 0 else 1e6
        m = float(np.clip(m, 2, 1e6))
        a, b = g.ref * m + g.cases, (1 - g.ref) * m + (g.n - g.cases)
        g = g.assign(prior_strength=m, shrunk=a / (a + b),
                     lo=stats.beta.ppf(0.05, a, b), hi=stats.beta.ppf(0.95, a, b))
        g["index"] = 100 * g.shrunk / g.ref
        g["index_lo"], g["index_hi"] = 100 * g.lo / g.ref, 100 * g.hi / g.ref
        out.append(g)
    r = pd.concat(out)
    cols = KEYS + ["condition", "pets_seen", "pets_with_condition", "prevalence", "ref", "index", "index_lo", "index_hi",
                   "prior_strength"]
    r = r[cols].rename(columns={"ref": "network_prevalence"})
    for c in ["prevalence", "network_prevalence"]:
        r[c] = r[c].astype(float).round(4)
    for c in ["index", "index_lo", "index_hi"]:
        r[c] = r[c].round(1)
    r["prior_strength"] = r.prior_strength.round(1)
    return r.sort_values(KEYS + ["condition"]).reset_index(drop=True)


def composite(ci: pd.DataFrame) -> pd.DataFrame:
    w = ci.assign(cost=ci.condition.map(COST))
    w["weight"] = w.network_prevalence * w.cost  # expected treatment spend per pet in the network
    g = w.groupby(KEYS)
    tot = w.groupby(["year", "species"]).apply(
        lambda x: x.drop_duplicates("condition").assign(wt=lambda y: y.weight).wt.sum(), include_groups=False)
    res = g.apply(lambda x: pd.Series({
        "illness_cost_index": float(np.average(x["index"], weights=x.weight)),
        "conditions_released": int(len(x)),
        "cost_weight_covered": float(x.drop_duplicates("condition").weight.sum()),
        "pets_seen": int(x.pets_seen.max())}), include_groups=False).reset_index()
    res["cost_weight_covered"] = (res.cost_weight_covered / res.set_index(["year", "species"]).index.map(tot)).round(3)
    res["illness_cost_index"] = res.illness_cost_index.round(1)
    return res.sort_values(KEYS).reset_index(drop=True)


def checks(prev: pd.DataFrame, ci: pd.DataFrame) -> dict:
    released = ci.merge(prev[KEYS + ["condition", "suppressed"]], on=KEYS + ["condition"])
    wmean = ci.groupby(["year", "species", "condition"]).apply(
        lambda x: np.average(x["index"], weights=x.pets_seen), include_groups=False)
    return {"no_suppressed_cell_released": bool((~released.suppressed.astype(bool)).all()),
            "all_cells_ge_10_pets": bool((ci.pets_seen >= 10).all()),
            "pet_weighted_mean_index_within_95_105": bool(wmean.between(95, 105).all()),
            "pet_weighted_mean_index_range": [round(float(wmean.min()), 1), round(float(wmean.max()), 1)]}
