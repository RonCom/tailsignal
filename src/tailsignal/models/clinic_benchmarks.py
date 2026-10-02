"""Clinic quality benchmarks: risk-adjusted anesthesia, dental charting, and antibiotic stewardship scorecards.

Spec (pre-registered): docs/clinic_benchmarks_spec.md. Reads EHR tables; truth is used only to score.

    uv run python -m tailsignal.models.clinic_benchmarks
    uv run python -m tailsignal.models.clinic_benchmarks --root data_scale10 --tag 10x
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from scipy import stats

from tailsignal.synth import reference as R

OUT = Path("reports/clinic_benchmarks")
SIZE = {b[0]: b[3] for b in R.BREEDS}


def load(root: Path) -> dict:
    raw = root / "raw" / "ehr"
    t = {k: pd.read_parquet(raw / f"{k}.parquet") for k in
         ["ehr_patients", "ehr_visits", "ehr_procedures", "ehr_prescriptions"]}
    pt = t["ehr_patients"].set_index("clinic_patient_id")
    for k in ["ehr_visits", "ehr_procedures", "ehr_prescriptions"]:
        df = t[k]
        df["species"] = df.clinic_patient_id.map(pt.species)
        df["breed"] = df.clinic_patient_id.map(pt.breed_text)
        df["birth"] = pd.to_datetime(df.clinic_patient_id.map(pt.birth_date))
    return t


def _smooth_ppf(q, e):
    """Continuous Poisson quantile (Spiegelhalter 2005 interpolation), so funnel limits are smooth in e."""
    r = stats.poisson.ppf(q, e)
    c, cm1 = stats.poisson.cdf(r, e), stats.poisson.cdf(r - 1, e)
    a = (c - q) / np.maximum(c - cm1, 1e-12)
    return np.maximum(r - a, 0)


def poisson_limits(e, p):
    e = np.asarray(e, float)
    lo, hi = _smooth_ppf((1 - p) / 2, e), _smooth_ppf(1 - (1 - p) / 2, e)
    return lo / np.maximum(e, 1e-9), hi / np.maximum(e, 1e-9)


def oe_table(df: pd.DataFrame, y: str, p: str, rng, draws=2000) -> pd.DataFrame:
    g = df.groupby("clinic").agg(n=(y, "size"), observed=(y, "sum"), expected=(p, "sum"))
    g["oe"] = g.observed / g.expected
    for lvl, tag in [(0.95, "95"), (0.998, "998")]:
        lo, hi = poisson_limits(g.expected.values, lvl)
        g[f"lim{tag}_lo"], g[f"lim{tag}_hi"] = lo, hi
    g["flag"] = np.where(g.oe > g.lim95_hi, "above", np.where(g.oe < g.lim95_lo, "below", ""))
    g["flag_998"] = np.where(g.oe > g.lim998_hi, "above", np.where(g.oe < g.lim998_lo, "below", ""))
    # empirical Bayes on log O/E (add 0.5 to avoid log 0), sampling variance ~ 1/(O+0.5)
    lr = np.log((g.observed + 0.5) / (g.expected + 0.5))
    v = 1 / (g.observed + 0.5)
    tau2 = max(0.0, float(lr.var(ddof=1) - v.mean()))
    w = tau2 / (tau2 + v)
    mu = float((lr * (1 / (v + tau2))).sum() / (1 / (v + tau2)).sum()) if tau2 > 0 else float(np.average(lr, weights=1 / v))
    post_m = mu + w * (lr - mu)
    post_sd = np.sqrt(w * v)
    g["raw_log_oe"], g["shrunk_log_oe"] = lr, post_m
    g["shrunk_oe"] = np.exp(post_m)
    g["shrunk_lo"], g["shrunk_hi"] = np.exp(post_m - 1.96 * post_sd), np.exp(post_m + 1.96 * post_sd)
    g["reliability"] = w
    sims = rng.normal(post_m.values[:, None], np.maximum(post_sd.values[:, None], 1e-9), (len(g), draws))
    ranks = sims.argsort(0).argsort(0) + 1  # 1 = lowest (best for adverse outcomes)
    g["rank_median"] = np.median(ranks, 1)
    g["rank_lo"], g["rank_hi"] = np.percentile(ranks, 5, 1), np.percentile(ranks, 95, 1)
    g.attrs["tau2"] = tau2
    return g


def anesthesia(t, rng):
    pr = t["ehr_procedures"].copy()
    pr["y_comp"] = (pr.complication.notna() | pr.death_48h).astype(int)
    pr["y_death"] = pr.death_48h.astype(int)
    pr["asa_grp"] = np.where(pr.asa >= 3, "3-5", "1-2")
    pr["age_band"] = pd.cut(pr.age_years, [0, 2, 8, 12, 40], right=False, labels=["<2", "2-7", "8-11", "12+"])
    pr["small_dog"] = (pr.species == "dog") & (pr.weight_kg < 5)
    f = "~ C(asa_grp) + emergency + brachycephalic + C(species) + C(procedure) + C(age_band) + small_dog"
    m = smf.glm("y_comp " + f, pr, family=sm.families.Binomial()).fit()
    pr["p_comp"] = m.predict(pr)
    md = smf.glm("y_death ~ C(asa_grp) + C(species) + emergency", pr, family=sm.families.Binomial()).fit()
    pr["p_death"] = md.predict(pr)
    comp, death = oe_table(pr, "y_comp", "p_comp", rng), oe_table(pr, "y_death", "p_death", rng)
    rate = pr.y_death.mean()
    per = pr.groupby("clinic").size()
    power = {}
    for c, n in per.items():
        e = n * rate
        crit = stats.poisson.ppf(0.975, e) + 1
        power[c] = float(1 - stats.poisson.cdf(crit - 1, 2 * e))
    death["power_or2"] = pd.Series(power)
    need = next(n for n in range(250, 500000, 250)
                if 1 - stats.poisson.cdf(stats.poisson.ppf(0.975, n * rate), 2 * n * rate) >= 0.8)
    net = pr.groupby(["species", "asa_grp"]).y_death.agg(["size", "sum", "mean"]).reset_index()
    return comp, death, dict(procedures=int(len(pr)), death_rate=float(rate), complication_rate=float(pr.y_comp.mean()),
                             procedures_per_clinic_for_80pct=need, network_deaths=net.to_dict("records"))


def dental(t, rng):
    v = t["ehr_visits"]
    w = v[v.visit_type == "wellness"].copy()
    w["y"] = (w.dental_grade >= 2).fillna(False).astype(int)
    day = (np.datetime64("2022-01-01") + w.day.astype("timedelta64[D]")).astype("datetime64[ns]")
    w["age_band"] = pd.cut((day - w.birth).dt.days / 365.25, [0, 2, 4, 7, 10, 40], right=False,
                           labels=["<2", "2-3", "4-6", "7-9", "10+"])
    w["size"] = w.breed.map(SIZE).fillna("medium")
    w["overweight"] = w.bcs >= 6
    w = w[w.age_band.notna()]
    m = smf.glm("y ~ C(species) + C(size) + C(age_band) + overweight", w, family=sm.families.Binomial()).fit()
    w["p"] = m.predict(w)
    g = oe_table(w, "y", "p", rng)
    g["charted_share"] = w.assign(ch=w.dental_grade.notna()).groupby("clinic").ch.mean()
    return g


def stewardship(t):
    rx, v = t["ehr_prescriptions"], t["ehr_visits"]
    uti_idx = v[(v.dx == "urinary_tract_infection") & (v.visit_type == "sick")]
    emp = rx[rx.choice_tier.isin(["first_line", "hpcia", "other"]) & rx.indication.isin(["uti", "pyoderma"])]
    uti_rx = rx[rx.indication == "uti"].merge(uti_idx[["visit_id"]], on="visit_id")
    s = pd.DataFrame({
        "uti_visits": uti_idx.groupby("clinic").size(),
        "culture_before_uti_tx": uti_rx.assign(cb=uti_rx.culture_before.astype(float)).groupby("clinic").cb.mean(),
        "first_line_share": emp.groupby("clinic").choice_tier.apply(lambda x: (x == "first_line").mean()),
        "critically_important_first": emp.groupby("clinic").choice_tier.apply(lambda x: (x == "hpcia").mean()),
        "metronidazole_acute_diarrhea": rx[rx.indication == "acute_diarrhea"].groupby("clinic").size()
        / v[(v.dx == "gastroenteritis") & (v.visit_type == "sick")].groupby("clinic").size(),
        "abx_with_dental_cleaning": rx[rx.indication == "dental_prophylaxis"].groupby("clinic").size()
        / v[v.procedure == "dental_cleaning"].groupby("clinic").size(),
    })
    s = s.astype(float)
    sign = {"culture_before_uti_tx": 1, "first_line_share": 1, "critically_important_first": -1,
            "metronidazole_acute_diarrhea": -1, "abx_with_dental_cleaning": -1}
    z = pd.DataFrame({k: sgn * (s[k] - s[k].mean()) / s[k].std() for k, sgn in sign.items()})
    s["composite"] = z.mean(1)
    s["composite_rank"] = s.composite.rank(ascending=False).astype(int)
    return s


def score(root, comp, death, dent, stew, power_tag):
    ce = pd.read_parquet(root / "truth" / "ehr" / "clinic_effects.parquet").set_index("clinic")
    r = {}
    r["complication_spearman_shrunk"] = float(stats.spearmanr(comp.shrunk_log_oe, ce.comp_log_or).statistic)
    r["complication_spearman_raw"] = float(stats.spearmanr(comp.raw_log_oe, ce.comp_log_or).statistic)
    cen = lambda x: x - x.mean()
    tgt = cen(ce.comp_log_or.loc[comp.index])
    r["complication_mse_raw"] = float(((cen(comp.raw_log_oe) - tgt) ** 2).mean())
    r["complication_mse_shrunk"] = float(((cen(comp.shrunk_log_oe) - tgt) ** 2).mean())
    r["death_flags_998"] = death.index[death.flag_998 != ""].tolist()
    r["death_flags_95"] = death.index[death.flag != ""].tolist()
    r["death_planted_outlier_flagged"] = "PHL-VET3" in r["death_flags_95"]
    r["death_mean_power_or2"] = float(death.power_or2.mean())
    r["dental_flagged_below"] = dent.index[dent.flag == "below"].tolist()
    r["dental_spearman"] = float(stats.spearmanr(dent.oe, ce.dental_thoroughness.loc[dent.index]).statistic)
    sign = {"p_culture_uti": 1, "p_first_line": 1, "p_hpcia_marginal": -1, "p_metro": -1, "p_dental_abx": -1}
    pz = pd.DataFrame({k: s * (ce[k] - ce[k].mean()) / ce[k].std() for k, s in sign.items()}).mean(1)
    r["stewardship_spearman"] = float(stats.spearmanr(stew.composite, pz.loc[stew.index]).statistic)
    # amended target: the clinic's true O/E implied by the simulator's per-procedure probabilities
    pt = pd.read_parquet(root / "truth" / "ehr" / "procedure_truth.parquet")
    pr = pd.read_parquet(root / "raw" / "ehr" / "ehr_procedures.parquet")[["proc_id", "clinic"]].merge(pt, on="proc_id")
    for name, tab, col in [("complication", comp, "p_comp"), ("death", death, "p_death")]:
        tru = cen(np.log(pr.groupby("clinic")[col].sum() / tab.expected))
        r[f"{name}_mse_vs_true_oe_raw"] = float(((cen(tab.raw_log_oe) - tru) ** 2).mean())
        r[f"{name}_mse_vs_true_oe_shrunk"] = float(((cen(tab.shrunk_log_oe) - tru) ** 2).mean())
        r[f"{name}_reliability"] = tab.reliability.round(2).to_dict()
    checks = {
        "amended.shrinkage_lowers_mse_vs_true_oe": (r["complication_mse_vs_true_oe_shrunk"] <= r["complication_mse_vs_true_oe_raw"])
        and (r["death_mse_vs_true_oe_shrunk"] <= r["death_mse_vs_true_oe_raw"]),
        "complication_spearman": r["complication_spearman_shrunk"] >= (0.8 if power_tag == "10x" else 0.7),
        "prereg.shrinkage_lowers_mse_vs_planted_log_or": r["complication_mse_shrunk"] < r["complication_mse_raw"],
        "dental_low_clinics_flagged": {"AUS-VET2", "MSP-VET3"} <= set(r["dental_flagged_below"]),
        "stewardship_spearman_ge_0.8": r["stewardship_spearman"] >= 0.8,
    }
    if power_tag != "1x":  # spec: shrinkage checks apply at 1x (at 10x reliability ~0.97 makes shrinkage a no-op)
        checks.pop("amended.shrinkage_lowers_mse_vs_true_oe")
        checks.pop("prereg.shrinkage_lowers_mse_vs_planted_log_or")
    if power_tag == "1x":
        checks["mortality_not_benchmarkable"] = (len(r["death_flags_998"]) == 0) and r["death_mean_power_or2"] < 0.5
    r["checks"] = {k: bool(v) for k, v in checks.items()}
    r["planted"] = ce[["comp_log_or", "death_log_or", "dental_thoroughness", "p_culture_uti", "p_first_line",
                       "p_hpcia_marginal", "p_metro", "p_dental_abx"]].round(3).to_dict("index")
    return r


def chart(comp, death, dent, stew, path, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(18, 4.8))
    for a, g, title in [(ax[0], comp, "Anesthetic complications"), (ax[1], death, "Anesthetic deaths (48 h)"),
                        (ax[2], dent, "Periodontal disease recorded at wellness exams")]:
        e = np.linspace(max(0.3, g.expected.min() * 0.7), g.expected.max() * 1.3, 200)
        for lvl, ls in [(0.95, "--"), (0.998, ":")]:
            lo, hi = poisson_limits(e, lvl)
            a.plot(e, hi, "k" + ls, lw=0.7)
            a.plot(e, lo, "k" + ls, lw=0.7)
        a.axhline(1, color="grey", lw=0.6)
        col = g.flag.map({"above": "#c0392b", "below": "#2471a3", "": "#7f8c8d"})
        a.scatter(g.expected, g.oe, c=col, s=36, zorder=3)
        for c, r in g.iterrows():
            a.annotate(c, (r.expected, r.oe), fontsize=6.5, xytext=(3, 3), textcoords="offset points")
        a.set_xlabel("Expected (risk-adjusted)")
        a.set_ylabel("Observed / expected")
        a.set_title(f"{title} ({tag})", fontsize=9.5)
    s = stew.sort_values("composite")
    ax[3].barh(s.index, s.composite, color=np.where(s.composite >= 0, "#27ae60", "#c0392b"))
    ax[3].axvline(0, color="grey", lw=0.6)
    ax[3].set_xlabel("Composite (higher = better stewardship)")
    ax[3].set_title(f"Antibiotic stewardship ({tag})", fontsize=9.5)
    ax[3].tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def scorecard(comp, death, dent, stew) -> pd.DataFrame:
    sc = pd.DataFrame({
        "procedures": comp.n, "complication_oe": comp.oe.round(2),
        "complication_oe_shrunk": comp.shrunk_oe.round(2),
        "complication_95ci": comp.apply(lambda r: f"{r.shrunk_lo:.2f}-{r.shrunk_hi:.2f}", axis=1),
        "complication_rank_90pct": comp.apply(lambda r: f"{int(r.rank_lo)}-{int(r.rank_hi)}", axis=1),
        "complication_flag": comp.flag, "deaths": death.observed.astype(int), "deaths_expected": death.expected.round(1),
        "death_flag": death.flag, "power_to_detect_double_death_risk": death.power_or2.round(2),
        "dental_detection_oe": dent.oe.round(2), "dental_flag": dent.flag, "dental_charted_share": dent.charted_share.round(2),
        "stewardship_composite": stew.composite.round(2), "stewardship_rank": stew.composite_rank,
        "culture_before_uti_tx": stew.culture_before_uti_tx.round(2), "first_line_share": stew.first_line_share.round(2),
        "critically_important_first": stew.critically_important_first.round(2),
    })
    return sc


def run(root: Path, tag: str):
    out = OUT / tag
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(5)
    t = load(root)
    comp, death, ana = anesthesia(t, rng)
    dent = dental(t, rng)
    stew = stewardship(t)
    for name, df in [("complications", comp), ("deaths", death), ("dental", dent), ("stewardship", stew)]:
        df.round(4).to_csv(out / f"{name}.csv")
    sc = scorecard(comp, death, dent, stew)
    sc.to_csv(out / "scorecard.csv")
    res = dict(anesthesia=ana, complication_tau2=comp.attrs["tau2"], death_tau2=death.attrs["tau2"],
               scoring=score(root, comp, death, dent, stew, tag))
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=float))
    chart(comp, death, dent, stew, out / "benchmarks.png", tag)
    return sc, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data"))
    ap.add_argument("--tag", default="1x")
    a = ap.parse_args()
    sc, res = run(a.root, a.tag)
    pd.set_option("display.width", 250)
    print(sc.to_string())
    print(json.dumps({k: v for k, v in res["scoring"].items() if k != "planted"}, indent=1, default=float))


if __name__ == "__main__":
    main()
