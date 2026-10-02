"""Decision-curve analysis for the feline CKD flag. Spec: docs/feline_ckd_decision_spec.md.

    uv run python -m tailsignal.models.feline_ckd_decision --root data_scale10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from tailsignal.models.feline_ckd import OUT, cohort, cv_predict, sens_at_spec
from tailsignal.models.feline_ckd_stress import confound

THRESH = np.round(np.arange(0.02, 0.605, 0.01), 2)


def calibrated_m0(df: pd.DataFrame) -> np.ndarray:
    """Latest creatinine turned into a probability by isotonic regression fit within each training fold."""
    p = np.zeros(len(df))
    x, y = df.creatinine_mg_dl.to_numpy(), df.y.to_numpy()
    for tr, te in GroupKFold(5).split(x, y, df.clinic_patient_id):
        iso = IsotonicRegression(out_of_bounds="clip").fit(x[tr], y[tr])
        p[te] = iso.predict(x[te])
    return p


def net_benefit(y, p, t, w=None) -> float:
    """Vickers net benefit; w reweights negatives to change prevalence."""
    w = np.ones_like(y, dtype=float) if w is None else w
    n = w.sum()
    flag = p >= t
    tp = (w * (flag & (y == 1))).sum()
    fp = (w * (flag & (y == 0))).sum()
    return float(tp / n - fp / n * t / (1 - t))


def reweight(y, prev) -> np.ndarray:
    """Weights on negatives so the weighted prevalence equals prev."""
    pos, neg = (y == 1).sum(), (y == 0).sum()
    return np.where(y == 1, 1.0, pos * (1 - prev) / (prev * neg))


def run(root: Path):
    out = OUT / "decision"
    out.mkdir(parents=True, exist_ok=True)
    df = cohort(root)
    y = df.y.to_numpy()
    preds = {"M5": cv_predict(df, "M5"), "M3": cv_predict(df, "M3"), "M0": calibrated_m0(df)}
    cdf = cohort(root, confound(root)[0])
    preds_conf = {"M5": cv_predict(cdf, "M5")}
    prev0 = float(y.mean())
    rows = []
    for t in THRESH:
        r = {"threshold": t, "recheck_all": net_benefit(y, np.ones_like(y, float), t), "recheck_none": 0.0}
        r.update({m: net_benefit(y, p, t) for m, p in preds.items()})
        r["M5_confounded"] = net_benefit(cdf.y.to_numpy(), preds_conf["M5"], t)
        w = reweight(y, 0.10)
        r["recheck_all_prev10"] = net_benefit(y, np.ones_like(y, float), t, w)
        r["M5_prev10"] = net_benefit(y, preds["M5"], t, w)
        rows.append(r)
    nb = pd.DataFrame(rows)
    nb.to_csv(out / "net_benefit.csv", index=False)

    # rechecks per early catch at M5's 95%-specificity threshold
    _, thr = sens_at_spec(y, preds["M5"], 0.95)
    flag = preds["M5"] > thr

    def per_catch(w):
        tp = (w * (flag & (y == 1))).sum()
        return float((w * flag).sum() / tp)

    rpc = {"prev_cohort": round(per_catch(np.ones(len(y))), 2), "prev_10pct": round(per_catch(reweight(y, 0.10)), 2)}
    band = nb[(nb.threshold >= 0.05) & (nb.threshold <= 0.50)]
    exp = {
        "M5_beats_all_and_none_5_to_50": bool(((band.M5 > band.recheck_all) & (band.M5 > 0)).all()),
        "M5_at_least_M3_5_to_50": bool((band.M5 >= band.M3 - 1e-9).all()),
        "rechecks_per_catch_double_at_10pct": bool(rpc["prev_10pct"] >= 2 * rpc["prev_cohort"]),
    }
    pick = nb.set_index("threshold").loc[[0.05, 0.1, 0.2, 0.3, 0.5]].round(4)
    summary = {"cohort_prevalence": round(prev0, 3), "m5_95spec_threshold": round(float(thr), 3),
               "rechecks_per_early_catch_at_95spec": rpc,
               "net_benefit_selected": pick.reset_index().to_dict("records"), "expectations": exp}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    chart(nb, out / "net_benefit.png")
    return summary


def chart(nb: pd.DataFrame, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = nb.threshold * 100
    series = [("M5", "With SDMA (M5)", "#1f5f99", "-", 2.2), ("M3", "Two visits, no SDMA (M3)", "#7fa7c6", "-", 2.0),
              ("M0", "Latest creatinine (M0)", "#b4440e", "-", 2.0),
              ("recheck_all", "Recheck every cat", "#6b7280", "--", 1.6)]
    for col, label, color, ls, lw in series:
        ax.plot(x, nb[col], color=color, ls=ls, lw=lw, label=label)
    ax.axhline(0, color="#2d3748", lw=0.8)
    ax.text(59, 0.004, "Recheck none", ha="right", va="bottom", fontsize=8, color="#2d3748")
    ax.set_ylim(-0.05, 0.25)
    ax.set_xlim(2, 60)
    ax.set_xlabel("Threshold risk for a recheck (%)  ·  20% = one early catch is worth 4 unneeded rechecks")
    ax.set_ylabel("Net benefit (early catches per cat, net)")
    ax.grid(axis="y", color="#e5e7eb", lw=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_title("Kidney flag: net benefit of rechecking flagged cats (10× network, 24% two-year rate)", fontsize=10,
                 loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data_scale10"))
    print(json.dumps(run(ap.parse_args().root), indent=2))


if __name__ == "__main__":
    main()
