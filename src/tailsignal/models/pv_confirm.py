"""Model A confirmatory analysis on reports received 2020-01-01 onward.

Pre-registered in docs/model_a_confirmatory_2020.md. Evaluates predictions P1-P5 and writes
reports/model_a/confirmatory_2020/summary.json.

    python -m tailsignal.models.pv_confirm
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tailsignal.models import pharmacovigilance as pv

OUT = Path("reports/model_a/confirmatory_2020")
SINCE = "2020-01-01"


def product_rank(allc: pd.DataFrame, drug: str, event: str, col: str = "eb05") -> tuple[int | None, int]:
    base = allc[(allc.drug == drug) & ~allc.event.isin(pv.COMPOSITES) & (allc.n >= 3)]
    t = allc[(allc.drug == drug) & (allc.event == event)]
    if t.empty:
        return None, len(base)
    return int((base[col] > t[col].iloc[0]).sum() + 1), len(base)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, default=pv.SRC)
    ap.add_argument("--permutations", type=int, default=5)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    targets = pd.DataFrame({"drug": ["class:isoxazolines", *pv.ISOXAZOLINES, "class:macrocyclic_lactones"],
                            "event": [pv.SEIZTREM] * 5 + [pv.NEURO]})
    res = {"since": SINCE, "predictions": {}}

    # ---------------- dogs
    con = pv.load(a.src, "Dog", since=SINCE)
    res["dog_reports"] = int(con.execute("select count(*) from reports").fetchone()[0])
    r = pv.score(con, targets=targets)
    allc = r["all"]
    cls = allc[(allc.drug == "class:isoxazolines") & (allc.event == pv.SEIZTREM)].iloc[0]
    res["predictions"]["P1_dog_class_seizure_tremor"] = {
        "n": int(cls.n), "E": round(float(cls.E), 1), "ebgm": round(float(cls.ebgm), 3), "eb05": round(float(cls.eb05), 3),
        "prr": round(float(cls.prr), 3), "pass": bool(cls.eb05 >= 2)}
    p2 = {}
    for d in pv.ISOXAZOLINES:
        reports = int(allc.loc[allc.drug == d, "a_b"].max()) if (allc.drug == d).any() else 0
        if reports < 100:
            p2[d] = {"reports": reports, "eligible": False}
            continue
        ranks = {c: product_rank(allc, d, pv.SEIZTREM, c)[0] for c in ["prr", "ror_lo", "eb05"]}
        row = allc[(allc.drug == d) & (allc.event == pv.SEIZTREM)].iloc[0]
        p2[d] = {"reports": reports, "eligible": True, "product_terms": product_rank(allc, d, pv.SEIZTREM)[1],
                 "n": int(row.n), "eb05": round(float(row.eb05), 3), "rank_by": ranks, "pass": ranks["eb05"] <= 10}
    elig = [v for v in p2.values() if v["eligible"]]
    res["predictions"]["P2_dog_products_top10"] = {"products": p2,
                                                   "pass": bool(elig) and all(v["pass"] for v in elig)}
    st = r["strata"]
    m = st[(st.drug == "class:macrocyclic_lactones") & (st.event == pv.NEURO)].set_index("stratum")
    res["predictions"]["P4_dog_mdr1_excess"] = {
        s: {"n": int(m.loc[s, "n"]), "h_ratio_mean": round(float(m.loc[s, "h_ratio_mean"]), 3),
            "h_ratio05": round(float(m.loc[s, "h_ratio05"]), 3), "int_ror_lo": round(float(m.loc[s, "int_ror_lo"]), 3)}
        for s in pv.STRATA if s in m.index}
    res["predictions"]["P4_dog_mdr1_excess"]["pass"] = bool(m.loc["mdr1_high", "h_ratio05"] > 1)
    if a.permutations:
        nr = pv.null_rates(con, a.permutations)
        ev = nr[nr.null == "events_shuffled"].mean(numeric_only=True)
        sh = nr[nr.null == "strata_shuffled"].mean(numeric_only=True)
        res["predictions"]["P5_dog_mgps_false_signals_per_1000"] = {
            "mgps": round(float(ev.mgps), 3), "prr": round(float(ev.prr), 3), "ror": round(float(ev.ror), 3),
            "breed_excess_hier": round(float(sh.excess_hier), 3),
            "breed_excess_unpooled": round(float(sh.excess_unpooled), 3), "pass": bool(ev.mgps <= 1)}
    con.close()

    # ---------------- cats
    con = pv.load(a.src, "Cat", since=SINCE)
    res["cat_reports"] = int(con.execute("select count(*) from reports").fetchone()[0])
    r = pv.score(con, targets=targets)
    c = r["all"]
    cc = c[(c.drug == "class:isoxazolines") & (c.event == pv.SEIZTREM)].iloc[0]
    res["predictions"]["P3_cat_class_seizure_tremor"] = {
        "n": int(cc.n), "E": round(float(cc.E), 1), "ebgm": round(float(cc.ebgm), 3), "eb05": round(float(cc.eb05), 3),
        "prr": round(float(cc.prr), 3), "pass": bool(cc.eb05 >= 2)}
    con.close()

    (OUT / "summary.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
