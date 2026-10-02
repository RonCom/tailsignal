"""Validate the EHR layer against its planted parameters and published benchmarks.

Pre-specified checks: docs/simulator_extension_spec.md ("Validation"). Outputs: reports/ehr_validation/.

    uv run python -m tailsignal.synth.ehr_validate
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from tailsignal.synth.ehr import P as PLANTED

RAW, TRUTH, OUT = Path("data/raw/ehr"), Path("data/truth/ehr"), Path("reports/ehr_validation")
START = np.datetime64("2022-01-01")


def load():
    t = {k: pd.read_parquet(RAW / f"{k}.parquet") for k in
         ["ehr_visits", "ehr_prescriptions", "ehr_procedures", "ehr_labs", "ehr_cultures", "ehr_notes", "ehr_patients"]}
    pm = pd.read_parquet(TRUTH / "patient_map.parquet").set_index("clinic_patient_id").pet_uid
    for k, df in t.items():
        if "clinic_patient_id" in df and k != "ehr_patients":
            df["pet_uid"] = df.clinic_patient_id.map(pm)
    t["pets"] = pd.read_parquet("data/truth/pets.parquet").merge(pd.read_parquet(TRUTH / "pet_latent.parquet"),
                                                                 on="pet_uid")
    for k in ["ae_events", "infections", "clinic_effects", "note_labels", "visit_truth", "prescriptions_with_pet",
              "patient_map"]:
        t[k] = pd.read_parquet(TRUTH / f"{k}.parquet")
    return t


def exact_rr_ci(a, n1, b, n0):
    """Conditional exact CI: given a+b events, a ~ Binomial(a+b, n1*RR / (n1*RR + n0)); Clopper-Pearson on p."""
    m = a + b
    if m == 0:
        return np.nan, np.nan
    ci = stats.binomtest(int(a), int(m)).proportion_ci(method="exact")
    conv = lambda q: (q / (1 - q)) * n0 / n1 if q < 1 else np.inf
    return conv(ci.low), conv(ci.high)


def rr_ci(a, n1, b, n0):
    elo, ehi = exact_rr_ci(a, n1, b, n0)
    if min(a, b) == 0:
        return dict(a=a, n1=n1, b=b, n0=n0, rr=np.nan, lo=np.nan, hi=np.nan, exact_lo=elo, exact_hi=ehi)
    rr = (a / n1) / (b / n0)
    se = np.sqrt(1 / a - 1 / n1 + 1 / b - 1 / n0)
    return dict(a=int(a), n1=int(n1), b=int(b), n0=int(n0), rr=rr, lo=rr * np.exp(-1.96 * se), hi=rr * np.exp(1.96 * se),
                se_log=se, exact_lo=elo, exact_hi=ehi)


def funnel(obs: pd.Series, exp: pd.Series, z=1.96) -> pd.DataFrame:
    d = pd.DataFrame({"observed": obs, "expected": exp})
    d["ratio"] = d.observed / d.expected
    d["z"] = (d.observed - d.expected) / np.sqrt(d.expected)
    d["flag"] = np.where(d.z > z, "high", np.where(d.z < -z, "low", ""))
    return d


# ----------------------------------------------------------------------------- dental
def dental(t):
    v, pets = t["ehr_visits"], t["pets"].set_index("pet_uid")
    v = v.assign(year=(START + v.day.astype("timedelta64[D]")).astype("datetime64[ns]").dt.year)
    v["case_visit"] = (v.dx == "dental_disease") | (v.dental_grade >= 2)
    g = v.groupby(["pet_uid", "year"]).agg(case=("case_visit", "max"), wellness=("visit_type", lambda s: (s == "wellness").any()),
                                           bcs=("bcs", "max"), clinic=("clinic", "first"), day=("day", "min")).reset_index()
    g = g.join(pets[["species", "size", "birth_day", "market"]], on="pet_uid")
    g["age"] = (g.day - g.birth_day) / 365.25
    g["age_band"] = pd.cut(g.age, [0, 2, 4, 7, 10, 12, 30], labels=["<2", "2-4", "4-7", "7-10", "10-12", "12+"], right=False)
    g["overweight"] = g.bcs >= 6
    g["case"] = g.case.astype(int)
    dogs = g[(g.species == "dog") & g.age_band.notna()].copy()
    out = {"dog_prevalence": dogs.case.mean(), "cat_prevalence": g[g.species == "cat"].case.mean(),
           "dog_years": int(len(dogs))}
    out["by_size"] = dogs.groupby("size").case.mean().round(4).to_dict()
    out["by_wellness"] = dogs.groupby("wellness").case.mean().round(4).to_dict()
    out["by_age"] = dogs.groupby("age_band", observed=True).case.mean().round(4).to_dict()
    dogs["size"] = pd.Categorical(dogs["size"], ["large", "toy", "small", "medium"])
    dogs["age_band"] = dogs.age_band.cat.reorder_categories(["2-4", "<2", "4-7", "7-10", "10-12", "12+"])
    m = smf.glm("case ~ C(size) + C(age_band) + overweight + wellness + C(market)", dogs,
                family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dogs.pet_uid)[0]})
    orr = np.exp(pd.concat([m.params, m.conf_int()], axis=1))
    orr.columns = ["or", "lo", "hi"]
    out["odds_ratios"] = orr.round(3).to_dict(orient="index")
    # clinic funnel: expected from a model without clinic terms
    dogs["p"] = m.predict(dogs)
    f = funnel(dogs.groupby("clinic").case.sum(), dogs.groupby("clinic").p.sum())
    ce = t["clinic_effects"].set_index("clinic")
    f["planted_thoroughness"] = ce.dental_thoroughness
    out["clinic_funnel"] = f.round(3).reset_index().to_dict(orient="records")
    planted_low = set(PLANTED["dental"]["low_charting_clinics"])
    flagged_low = set(f.index[f.flag == "low"])
    flagged = set(f.index[f.flag != ""])
    planted = planted_low | set(PLANTED["dental"]["high_charting_clinics"])
    # truth: among dog-years with latent grade >= 2 at a visit, share recorded, by wellness exam that year
    lat = pd.read_parquet(TRUTH / "dental_latent.parquet").assign(year=lambda d: d.day // 365)
    lat = lat.groupby(["pet_uid", "year"]).latent_grade.max().reset_index()
    vy = v.assign(yr=v.day // 365).groupby(["pet_uid", "yr"]).agg(
        case=("case_visit", "max"), wellness=("visit_type", lambda s: (s == "wellness").any())).reset_index()
    sens = lat[lat.latent_grade >= 2].merge(vy, left_on=["pet_uid", "year"], right_on=["pet_uid", "yr"])
    out["sensitivity_by_wellness"] = sens.groupby("wellness").case.mean().round(4).to_dict()
    mean_thor = ce.dental_thoroughness.mean()
    direction_ok = all((f.loc[c, "flag"] == "low") == (ce.loc[c, "dental_thoroughness"] < mean_thor)
                       for c in f.index if f.loc[c, "flag"])
    rho = stats.spearmanr(f.ratio, f.planted_thoroughness).statistic
    out["funnel_spearman_vs_planted"] = float(rho)
    o = out["odds_ratios"]
    small_gt_large = out["by_size"]["small"] > out["by_size"]["large"]
    checks = {
        "prevalence_12_18pct": 0.12 <= out["dog_prevalence"] <= 0.18,
        "small_gt_large": bool(small_gt_large),
        "overweight_or_1.5_2.4": 1.5 <= o["overweight[T.True]"]["or"] <= 2.4,
        "wellness_raises_recorded_prevalence": out["by_wellness"][True] > out["by_wellness"][False],
        "age12_or_2.5_5": 2.5 <= o["C(age_band)[T.12+]"]["or"] <= 5,
        "funnel_flags_planted_low_clinics": planted_low <= flagged_low,
        "prereg.funnel_false_flags_le_1": len(flagged - planted) <= 1,
        "amended.funnel_flags_match_planted_direction": bool(direction_ok),
        "amended.funnel_spearman_ge_0.7": bool(rho >= 0.7),
        "amended.exam_sensitivity_higher_with_wellness": out["sensitivity_by_wellness"].get(True, 0)
        > out["sensitivity_by_wellness"].get(False, 1),
    }
    f.to_csv(OUT / "dental_clinic_funnel.csv")
    return out, checks, f


# ----------------------------------------------------------------------------- anesthesia
def anesthesia(t):
    pr = t["ehr_procedures"].merge(t["pets"][["pet_uid", "species"]], on="pet_uid")
    pr["grp"] = np.where(pr.asa >= 3, "ASA 3-5", "ASA 1-2")
    rows, ok = [], True
    for (sp, g), d in pr.groupby(["species", "grp"]):
        k, n = int(d.death_48h.sum()), len(d)
        ci = stats.binomtest(k, n).proportion_ci(method="exact")
        tgt = PLANTED["anesthesia"]["death"][sp]["high" if g == "ASA 3-5" else "low"]
        inside = ci.low <= tgt <= ci.high
        ok &= inside
        rows.append(dict(species=sp, asa=g, procedures=n, deaths=k, rate=k / n, ci_lo=ci.low, ci_hi=ci.high,
                         cepsaf=tgt, within_ci=inside))
    deaths = pd.DataFrame(rows)
    # complication funnel, expected from ASA group + brachycephaly
    pr["comp"] = pr.complication.notna() & ~pr.death_48h
    pr["comp_any"] = pr.complication.notna().astype(int)
    m = smf.glm("comp_any ~ C(grp) + brachycephalic + C(species)", pr, family=sm.families.Binomial()).fit()
    pr["p"] = m.predict(pr)
    f = funnel(pr.groupby("clinic").comp_any.sum(), pr.groupby("clinic").p.sum())
    ce = t["clinic_effects"].set_index("clinic")
    f["planted_or"] = np.exp(ce.comp_log_or)
    hi = set(f.index[f.flag == "high"])
    lo = set(f.index[f.flag == "low"])
    # mortality: can a clinic with OR 2 be detected at this volume?
    per_clinic = pr.groupby("clinic").size().mean()
    rate = pr.death_48h.mean()
    e = per_clinic * rate
    crit = stats.poisson.ppf(0.975, e) + 1
    power = 1 - stats.poisson.cdf(crit - 1, 2 * e)
    need = next(n for n in range(500, 200000, 250)
                if 1 - stats.poisson.cdf(stats.poisson.ppf(0.975, n * rate), 2 * n * rate) >= 0.8)
    out = dict(procedures=int(len(pr)), deaths=int(pr.death_48h.sum()), death_table=deaths.round(5).to_dict("records"),
               complication_rate=float(pr.comp_any.mean()), complication_funnel=f.round(3).reset_index().to_dict("records"),
               mortality_power=dict(procedures_per_clinic=round(per_clinic), expected_deaths_per_clinic=round(e, 2),
                                    power_to_detect_or2=round(power, 3), procedures_needed_for_80pct=need))
    checks = {"deaths_within_cepsaf_ci": bool(ok),
              "complication_funnel_flags_planted_high": "AUS-VET1" in hi,
              "complication_funnel_flags_planted_low": "MSP-VET1" in lo,
              "prereg.complication_false_flags_le_1": len((hi | lo) - {"AUS-VET1", "MSP-VET1"}) <= 1,
              "amended.complication_flags_match_planted_direction": all(
                  (f.loc[c, "flag"] == "high") == (f.loc[c, "planted_or"] > 1) for c in hi | lo),
              "amended.complication_spearman_ge_0.7": bool(stats.spearmanr(f.ratio, f.planted_or).statistic >= 0.7)}
    out["complication_spearman_vs_planted"] = float(stats.spearmanr(f.ratio, f.planted_or).statistic)
    deaths.to_csv(OUT / "anesthesia_deaths.csv", index=False)
    f.to_csv(OUT / "anesthesia_complication_funnel.csv")
    return out, checks, f


# ----------------------------------------------------------------------------- kidney
def kidney(t):
    pets = t["pets"].set_index("pet_uid")
    labs = t["ehr_labs"].pivot_table(index=["visit_id", "pet_uid", "day"], columns="analyte", values="value").reset_index()
    labs = labs.join(pets[["species", "ckd_dx_day", "ckd_future"]], on="pet_uid")
    cats = labs[labs.species == "cat"].copy()
    cats["months_before_dx"] = (cats.ckd_dx_day - cats.day) / 30.44
    ckd = cats[cats.ckd_dx_day.notna() & (cats.months_before_dx >= 0)]
    bins = [0, 6, 12, 18, 24, 36, 120]
    ckd = ckd.assign(window=pd.cut(ckd.months_before_dx, bins, right=False,
                                   labels=["0-6", "6-12", "12-18", "18-24", "24-36", "36+"]))
    traj = ckd.groupby("window", observed=True)[["creatinine_mg_dl", "sdma_ug_dl", "usg", "upc", "bun_mg_dl"]].median()
    traj["panels"] = ckd.groupby("window", observed=True).size()
    healthy = cats[cats.ckd_dx_day.isna()][["creatinine_mg_dl", "sdma_ug_dl", "usg", "upc", "bun_mg_dl"]].median()
    traj.loc["never CKD"] = list(healthy) + [int(cats.ckd_dx_day.isna().sum())]
    # threshold crossings: first panel above IRIS stage-2 cut-offs, per cat
    def first_cross(col, thr):
        x = ckd[ckd[col] > thr] if col != "usg" else ckd[ckd[col] < thr]
        return x.groupby("pet_uid").day.min()
    cs, cc = first_cross("sdma_ug_dl", 18), first_cross("creatinine_mg_dl", 1.6)
    both = pd.concat([cs.rename("sdma"), cc.rename("creat")], axis=1).dropna()
    lead = (both.creat - both.sdma)
    w = traj.loc[["18-24", "12-18", "6-12", "0-6"]] if all(x in traj.index for x in ["18-24", "0-6"]) else traj
    checks = {
        "creatinine_rises_over_24m": bool(w.creatinine_mg_dl.is_monotonic_increasing),
        "sdma_rises_over_24m": bool(w.sdma_ug_dl.is_monotonic_increasing),
        "usg_falls_over_24m": bool(w.usg.is_monotonic_decreasing),
        "prereg.sdma_crosses_before_creatinine_per_cat": bool(lead.mean() > 0) if len(lead) else False,
    }
    order = ["24-36", "18-24", "12-18", "6-12", "0-6"]
    tr = traj.loc[[o for o in order if o in traj.index]]
    first = lambda col, thr: next((i for i, w_ in enumerate(tr.index) if tr.loc[w_, col] > thr), 99)
    checks["amended.sdma14_median_crosses_before_creatinine1.6"] = first("sdma_ug_dl", 14) < first("creatinine_mg_dl", 1.6)
    c14 = first_cross("sdma_ug_dl", 14)
    b14 = pd.concat([c14.rename("sdma"), cc.rename("creat")], axis=1).dropna()
    lead14 = (b14.creat - b14.sdma) / 30.44
    hall = dict(cats=int(len(b14)), mean_lead_months=float(lead14.mean()), median_lead_months=float(lead14.median()),
                share_sdma_first=float((lead14 > 0).mean()))
    checks["amended.sdma14_leads_creatinine_per_cat"] = bool(lead14.mean() > 0)
    healthy_hi = cats[cats.ckd_dx_day.isna()].creatinine_mg_dl.gt(1.6).mean()
    out = dict(cats_with_ckd_labs=int(ckd.pet_uid.nunique()), panels=int(len(ckd)),
               trajectory=traj.round(3).reset_index().to_dict("records"),
               healthy_panels_creatinine_gt_1_6=float(healthy_hi), sdma14_vs_creatinine_hall2014=hall,
               sdma_lead=dict(cats=int(len(lead)), mean_days=float(lead.mean()) if len(lead) else None,
                              share_sdma_first=float((lead > 0).mean()) if len(lead) else None))
    traj.to_csv(OUT / "ckd_lab_trajectory.csv")
    return out, checks, traj


# ----------------------------------------------------------------------------- drug safety
def cohort(rx, events, window, exposed_mask):
    """Dispensing-level cohort: outcome = recorded event within `window` days after dispensing."""
    ev = events.groupby("pet_uid").day.apply(np.sort).to_dict()
    hits, prior = [], []
    for p, d in zip(rx.pet_uid, rx.day):
        e = ev.get(p, np.array([]))
        hits.append(bool(((e >= d) & (e < d + window)).any()))
        prior.append(bool((e < d).any()))
    rx = rx.assign(hit=hits, prior=prior)
    a, n1 = rx[exposed_mask(rx)].hit.sum(), exposed_mask(rx).sum()
    b, n0 = rx[~exposed_mask(rx)].hit.sum(), (~exposed_mask(rx)).sum()
    return rr_ci(a, n1, b, n0)


def drug_safety(t, reps=200, seed=11):
    rx, ae, pets = t["prescriptions_with_pet"], t["ae_events"], t["pets"]
    sz, gi, ne = PLANTED["seizure"], PLANTED["gi"], PLANTED["neuro"]
    rec = ae[ae.presented]
    flea = rx[(rx.indication == "flea_tick")].merge(pets[["pet_uid", "species"]], on="pet_uid")
    flea = flea[flea.species == "dog"]
    isox = lambda d: d.drug_class == "Isoxazoline"
    seiz = rec[rec.outcome == "seizure"]
    # history noted in clinic text also counts as a pre-existing sign
    nl = t["note_labels"].merge(t["ehr_notes"][["visit_id", "pet_uid", "day"]], on="visit_id")
    hx = nl[nl.label_seizure_history].groupby("pet_uid").day.min()
    naive = cohort(flea, seiz, sz["isox_window"], isox)
    # restricted: drop dispensings in dogs with a recorded seizure or a seizure-history note before the dispensing
    ev = seiz.groupby("pet_uid").day.apply(np.sort).to_dict()
    hxd = hx.to_dict()
    keep = [not ((ev.get(p, np.array([])) < d).any() or hxd.get(p, 1e9) < d) for p, d in zip(flea.pet_uid, flea.day)]
    fr = flea[keep]
    restricted = cohort(fr, seiz, sz["isox_window"], isox)
    nsaid = rx[rx.drug.isin(["carprofen", "meloxicam", "robenacoxib", "grapiprant"]) & (rx.indication ==
                                                                                       "osteoarthritis")]
    nsaid = nsaid.merge(pets[["pet_uid", "species"]], on="pet_uid")
    nsaid = nsaid[nsaid.species == "dog"]
    cox = lambda d: d.drug != "grapiprant"
    gi_ev = rec[rec.outcome == "vomiting_diarrhea"]
    gi_res = cohort(nsaid, gi_ev, gi["window"], cox)
    hw = rx[rx.drug_class == "Macrocyclic lactone"].merge(pets[["pet_uid", "breed"]], on="pet_uid")
    mdr1 = lambda d: d.breed.isin(ne["mdr1_breeds"])
    ml_res = cohort(hw, rec[rec.outcome == "neuro_signs"], ne["window"], mdr1)

    # ---- replicate re-draws of the outcome layer, exposures fixed as realized
    rng = np.random.default_rng(seed)
    pt = pets.set_index("pet_uid")

    def seizure_rate(r):
        v = np.full(T, sz["dog_rate"] / 365.25, np.float32)
        if r.epileptic:
            v[max(0, int(r.epilepsy_onset_day)):] = sz["epileptic_rate"] / 365.25
        return v

    known_hx = lambda p: pt.loc[p].epilepsy_onset_day if pt.loc[p].epileptic else np.inf
    cox_all = rx[rx.drug.isin(["carprofen", "meloxicam", "robenacoxib"])]
    reps_out = {
        "isoxazoline_seizure": replicate(flea, isox, pt, seizure_rate, flea[isox(flea)], sz["isox_window"],
                                         sz["isox_rr"], sz["presented"], reps, rng, restrict_hx=known_hx),
        "nsaid_gi_oa": replicate(nsaid, cox, pt, lambda r: np.full(T, gi["rate"] / 365.25, np.float32), cox_all,
                                 gi["window"], gi["cox_rr"], gi["presented"], reps, rng),
        "ml_mdr1_neuro_null": replicate(hw, mdr1, pt, lambda r: np.full(T, ne["rate"] / 365.25, np.float32), hw[mdr1(hw)],
                                        ne["window"], ne["ml_mdr1_rr"], ne["presented"], reps, rng),
    }
    out = dict(isoxazoline_seizure_naive=naive, isoxazoline_seizure_restricted=restricted,
               nsaid_gi_oa=gi_res, ml_mdr1_neuro_null=ml_res, replicates=reps_out)
    ri, rg, rm = reps_out["isoxazoline_seizure"], reps_out["nsaid_gi_oa"], reps_out["ml_mdr1_neuro_null"]
    checks = {
        "isox_estimator_coverage_90_99": 0.90 <= ri["coverage"] <= 0.99,
        "isox_restricted_unbiased_within_10pct": abs(ri["mean_rr"] / sz["isox_rr"] - 1) < 0.10,
        "naive_biased_below_planted": ri["naive_mean_rr"] < sz["isox_rr"] * 0.9,
        "nsaid_estimator_coverage_90_99": 0.90 <= rg["coverage"] <= 0.99,
        "prereg.ml_null_estimator_coverage_90_99": 0.90 <= rm["coverage"] <= 0.99,
        "amended.exact_ci_coverage_ge_0.93_all_three": min(ri["exact_coverage"], rg["exact_coverage"],
                                                            rm["exact_coverage"]) >= 0.93,
        # pre-registered single-world wording, kept for the record
        "prereg.nsaid_ci_covers_2": bool(gi_res["lo"] <= gi["cox_rr"] <= gi_res["hi"]),
        "prereg.ml_null_ci_covers_1": bool(ml_res["lo"] <= 1 <= ml_res["hi"]),
    }
    return out, checks


T = 1461


def replicate(coh, exposed_mask, pt, rate_fn, expo_rx, window, rr, presented, reps, rng, restrict_hx=None):
    """Re-draw outcomes `reps` times with exposures fixed; report bias, CI coverage, power, network size needed."""
    ids = coh.pet_uid.unique()
    idx = {p: i for i, p in enumerate(ids)}
    base = np.zeros((len(ids), T), np.float32)
    for p, i in idx.items():
        r = pt.loc[p]
        s, e = max(int(r.join_day), 0), min(int(r.exit_day), T)
        base[i, s:e] = rate_fn(r)[s:e]
    expo = np.zeros(base.shape, bool)
    for p, d in zip(expo_rx.pet_uid, expo_rx.day):
        if p in idx:
            expo[idx[p], int(d):int(d) + window] = True
    hz = base * np.where(expo, rr, 1.0).astype(np.float32) * presented
    hx = {p: restrict_hx(p) for p in ids} if restrict_hx else {}
    res = []
    for _ in range(reps):
        pi, di = np.nonzero(rng.random(hz.shape, dtype=np.float32) < hz)
        e = pd.DataFrame({"pet_uid": ids[pi], "day": di})
        nv = cohort(coh, e, window, exposed_mask)
        if restrict_hx:
            evd = e.groupby("pet_uid").day.apply(np.sort).to_dict()
            k = [not ((evd.get(p, np.array([])) < d).any() or hx[p] < d) for p, d in zip(coh.pet_uid, coh.day)]
            rs = cohort(coh[k], e, window, exposed_mask)
        else:
            rs = nv
        res.append(dict(naive=nv["rr"], rr=rs["rr"], lo=rs["lo"], hi=rs["hi"], events=rs["a"] + rs["b"],
                        elo=rs["exact_lo"], ehi=rs["exact_hi"]))
    rep = pd.DataFrame(res)
    ex = rep.dropna(subset=["elo"])
    ok = rep.dropna()
    se1 = np.log(ok.hi / ok.lo).mean() / (2 * 1.96) if len(ok) else np.nan
    k_needed = ((1.96 + 0.84) * se1 / np.log(rr)) ** 2 if rr != 1 else np.nan
    return dict(planted_rr=rr, reps=int(reps), estimable_share=float(len(ok) / reps),
                mean_events=float(rep.events.mean()), mean_rr=float(np.exp(np.log(ok.rr).mean())) if len(ok) else None,
                naive_mean_rr=float(np.exp(np.log(ok.naive.dropna()).mean())) if len(ok) else None,
                coverage=float(((ok.lo <= rr) & (ok.hi >= rr)).mean()) if len(ok) else 0.0,
                exact_estimable_share=float(len(ex) / reps),
                exact_coverage=float(((ex.elo <= rr) & (ex.ehi >= rr)).mean()) if len(ex) else 0.0,
                power=float((ok.lo > 1).mean()) if len(ok) and rr > 1 else None,
                exposed_n=int(exposed_mask(coh).sum()), comparator_n=int((~exposed_mask(coh)).sum()),
                network_multiple_for_80pct_power=float(k_needed) if k_needed == k_needed else None)


# ----------------------------------------------------------------------------- AMR / stewardship
def stewardship(t):
    from tailsignal.models.amr import load
    cu = t["ehr_cultures"].copy()
    idx_visits = set(t["infections"].visit_id)
    cu["index_visit"] = cu.visit_id.isin(idx_visits)
    cu["region"] = cu.clinic.str[:3].map({"PHL": "Northeast", "AUS": "South", "MSP": "Midwest"})
    cu["R"] = (cu.result == "R").astype(int)
    cu["source"] = np.where(cu.site == "urine", "UTI", "Other sites")
    sim = cu[cu.index_visit].groupby(["organism", "source", "region", "drug"]).R.agg(["mean", "size"]).reset_index()
    marker = cu[((cu.organism == "E. coli") & (cu.drug == "enrofloxacin"))
                | ((cu.organism == "S. pseudintermedius") & (cu.drug == "oxacillin"))]
    enrich = marker.groupby(["organism", "index_visit"]).R.mean().to_dict()
    from tailsignal.synth.ehr import DRUGS
    narms = load()
    narms = narms[narms.year >= 2022]
    rows = []
    for r in sim[sim["size"] >= 50].itertuples():
        d = DRUGS[r.drug]
        proxy = d["proxy"].get(r.organism)
        if proxy is None or (r.organism == "S. pseudintermedius" and d["bl"] and r.drug != "oxacillin"):
            continue  # MRSP rule changes the comparison; checked separately via oxacillin
        x = narms[(narms.organism == r.organism) & (narms.source == r.source) & (narms.region == r.region)
                  & (narms.drug == proxy)].R
        pval = stats.binomtest(int(round(r.mean * r.size)), int(r.size), min(max(x.mean(), 1e-4), 1 - 1e-4)).pvalue
        rows.append(dict(organism=r.organism, source=r.source, region=r.region, drug=r.drug, sim_pct_R=r.mean,
                         narms_pct_R=x.mean(), n_sim=r.size, diff=r.mean - x.mean(), p_value=pval))
    cmp_ = pd.DataFrame(rows)
    # clinic scorecard
    rx, inf, ce = t["prescriptions_with_pet"], t["infections"], t["clinic_effects"].set_index("clinic")
    vis = t["ehr_visits"]
    emp = rx[rx.choice_tier.isin(["first_line", "hpcia", "other"]) & rx.indication.isin(["uti", "pyoderma"])]
    sc = pd.DataFrame({
        "uti_episodes": inf[inf.kind == "uti"].groupby("clinic").size(),
        "uti_culture_rate": inf[inf.kind == "uti"].groupby("clinic").cultured.mean(),
        "pyoderma_culture_rate": inf[inf.kind == "pyoderma"].groupby("clinic").cultured.mean(),
        "first_line_share": emp.groupby("clinic").choice_tier.apply(lambda s: (s == "first_line").mean()),
        "hpcia_share": emp.groupby("clinic").choice_tier.apply(lambda s: (s == "hpcia").mean()),
        "topical_only_pyoderma": inf[inf.kind == "pyoderma"].groupby("clinic").empirical.apply(
            lambda s: (s == "topical").mean()),
        "metronidazole_acute_diarrhea": rx[rx.indication == "acute_diarrhea"].groupby("clinic").size()
        / vis[(vis.dx == "gastroenteritis") & (vis.visit_type == "sick")].groupby("clinic").size(),
        "dental_abx_share": rx[rx.indication == "dental_prophylaxis"].groupby("clinic").size()
        / vis[vis.procedure == "dental_cleaning"].groupby("clinic").size(),
        "treatment_failure": inf.groupby("clinic").failed.mean(),
    })
    planted = {"uti_culture_rate": "p_culture_uti", "pyoderma_culture_rate": "p_culture_skin",
               "first_line_share": "p_first_line", "hpcia_share": "p_hpcia_marginal", "topical_only_pyoderma": "p_topical",
               "metronidazole_acute_diarrhea": "p_metro", "dental_abx_share": "p_dental_abx"}
    rho = {k: float(stats.spearmanr(sc[k], ce.loc[sc.index, v]).statistic) for k, v in planted.items()}
    fail = inf[inf.empirical != "topical"].groupby("empirical_resistant").failed.mean().to_dict()
    checks = {
        "prereg.cultures_within_3pts_of_narms": bool((cmp_["diff"].abs() <= 0.03).mean() >= 0.9),
        "amended.index_cultures_consistent_with_narms": bool((cmp_.p_value >= 0.05).mean() >= 0.9),
        "stewardship_spearman_ge_0.8": bool(np.median(list(rho.values())) >= 0.8),
        "failure_higher_when_resistant": fail.get(True, 0) > fail.get(False, 1),
    }
    out = dict(culture_vs_narms=dict(cells=int(len(cmp_)), share_within_3pts=float((cmp_["diff"].abs() <= 0.03).mean()),
                                     share_p_ge_0_05=float((cmp_.p_value >= 0.05).mean()),
                                     max_abs_diff=float(cmp_["diff"].abs().max())),
               resistance_index_vs_recheck_cultures={f"{k[0]}|{'index' if k[1] else 'recheck'}": float(v)
                                                     for k, v in enrich.items()},
               spearman_by_metric=rho, failure_by_empirical_resistance=fail)
    cmp_.to_csv(OUT / "culture_vs_narms.csv", index=False)
    sc.round(3).to_csv(OUT / "stewardship_scorecard.csv")
    return out, checks, sc


# ----------------------------------------------------------------------------- notes
NAIVE = re.compile(r"seiz|siez|\bsz\b|\bfit|convuls|tonic-clonic|grand mal|tremor", re.I)
NEG = re.compile(r"\b(no|denies|nil|without)\b[^.]*$", re.I)
HIST = re.compile(r"\b(hx|history|known epileptic|previous)\b", re.I)
EXCL = re.compile(r"fit (and|&) well|fitted|tremor", re.I)


def smart_match(text):
    for sent in re.split(r"(?<=\.)\s+", text):
        for m in NAIVE.finditer(sent):
            pre = sent[:m.start()]
            if EXCL.search(sent[max(0, m.start() - 2):m.end() + 12]) or NEG.search(pre) or HIST.search(sent):
                continue
            return True
    return False


def notes(t):
    n = t["ehr_notes"].merge(t["note_labels"], on="visit_id")
    y = n.label_seizure
    out = {}
    for name, pred in [("naive_keywords", n.text.str.contains(NAIVE)), ("negation_history_aware", n.text.map(smart_match))]:
        tp = (pred & y).sum()
        out[name] = dict(precision=float(tp / max(pred.sum(), 1)), recall=float(tp / y.sum()), flagged=int(pred.sum()))
    out["true_seizure_notes"] = int(y.sum())
    out["notes_with_negated_mention"] = int(n.label_seizure_negated.sum())
    out["notes_with_history_mention"] = int(n.label_seizure_history.sum())
    out["notes_with_fit_and_well"] = int(n.label_fit_and_well.sum())
    return out


def microchips(t):
    pm = t["patient_map"]
    multi = pm.groupby("pet_uid").filter(lambda g: len(g) > 1)
    g = multi.groupby("pet_uid").microchip.agg(lambda s: s.notna().all() and s.nunique() == 1)
    return dict(pets_at_2plus_clinics=int(multi.pet_uid.nunique()), linkable_by_microchip=float(g.mean()),
                chip_recorded_share=float(pm.microchip.notna().mean()))


def consistency(t):
    vt = t["visit_truth"]
    base = int(vt.base_visit_index.notna().sum())
    plat = json.loads(Path("data/truth/summary.json").read_text())["vet_visits"]
    return dict(base_visits_in_ehr=base, platform_vet_visits=plat), {"base_visits_match_platform": base >= plat - 50}


def chart(dent_f, comp_f, traj, sc, ce, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    for a, f, title in [(ax[0, 0], dent_f, "Dental charting: clinics vs expected"),
                        (ax[0, 1], comp_f, "Anesthetic complications: clinics vs expected")]:
        e = np.linspace(max(1, f.expected.min() * 0.8), f.expected.max() * 1.2, 100)
        a.plot(e, (e + 1.96 * np.sqrt(e)) / e, "k--", lw=0.8)
        a.plot(e, (e - 1.96 * np.sqrt(e)) / e, "k--", lw=0.8)
        a.axhline(1, color="grey", lw=0.6)
        col = f.flag.map({"high": "#c0392b", "low": "#2471a3", "": "#7f8c8d"})
        a.scatter(f.expected, f.ratio, c=col, s=40)
        for c, r in f.iterrows():
            a.annotate(c, (r.expected, r.ratio), fontsize=7, xytext=(3, 3), textcoords="offset points")
        a.set_xlabel("Expected cases")
        a.set_ylabel("Observed / expected")
        a.set_title(title, fontsize=10)
    w = traj.drop(index="never CKD", errors="ignore")
    a = ax[1, 0]
    a.plot(range(len(w)), w.creatinine_mg_dl, "o-", label="Creatinine (mg/dL)")
    a.plot(range(len(w)), w.sdma_ug_dl / 10, "s-", label="SDMA / 10 (µg/dL)")
    a.axhline(1.6, color="#1f77b4", lw=0.8, ls=":", label="Creatinine 1.6 (IRIS stage 2)")
    a.axhline(1.4, color="#ff7f0e", lw=0.8, ls=":", label="SDMA 14 (upper reference)")
    a.set_xticks(range(len(w)), w.index)
    a.invert_xaxis()
    a.set_xlabel("Months before CKD diagnosis")
    a.set_title("Cat kidney labs before diagnosis (medians)", fontsize=10)
    a.legend(fontsize=8)
    a = ax[1, 1]
    a.scatter(ce.loc[sc.index, "p_hpcia_marginal"], sc.hpcia_share, s=40, color="#8e44ad")
    for c in sc.index:
        a.annotate(c, (ce.loc[c, "p_hpcia_marginal"], sc.loc[c, "hpcia_share"]), fontsize=7, xytext=(3, 3),
                   textcoords="offset points")
    a.set_xlabel("Planted propensity")
    a.set_ylabel("Observed share of empirical choices")
    a.set_title("Critically important antibiotics as first choice, by clinic", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = load()
    results, checks = {}, {}
    results["consistency"], c = consistency(t)
    checks.update(c)
    results["dental"], c, dent_f = dental(t)
    checks.update({f"dental.{k}": v for k, v in c.items()})
    results["anesthesia"], c, comp_f = anesthesia(t)
    checks.update({f"anesthesia.{k}": v for k, v in c.items()})
    results["kidney"], c, traj = kidney(t)
    checks.update({f"kidney.{k}": v for k, v in c.items()})
    results["drug_safety"], c = drug_safety(t)
    checks.update({f"drug_safety.{k}": v for k, v in c.items()})
    results["stewardship"], c, sc = stewardship(t)
    checks.update({f"amr.{k}": v for k, v in c.items()})
    results["notes"] = notes(t)
    results["microchips"] = microchips(t)
    results["checks"] = {k: bool(v) for k, v in checks.items()}
    chart(dent_f, comp_f, traj, sc, t["clinic_effects"].set_index("clinic"), OUT / "ehr_validation.png")
    (OUT / "summary.json").write_text(json.dumps(results, indent=2, default=float))
    for k, v in results["checks"].items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"{sum(results['checks'].values())}/{len(results['checks'])} checks pass")


if __name__ == "__main__":
    main()
