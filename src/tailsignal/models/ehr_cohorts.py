"""Model A2: active-comparator new-user cohort studies in clinic EHRs (signal validation).

Analysis plan (locked before running): docs/model_a2_ehr_cohort_spec.md. Reads EHR tables only; truth tables are
used afterwards to score linkage, text mining, and estimates.

    uv run python -m tailsignal.models.ehr_cohorts                      # actual network (data/)
    uv run python -m tailsignal.models.ehr_cohorts --root data_scale10 --tag 10x
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from tailsignal.models.ehr_text import OUTCOMES, Dictionary, evaluate, veddra_terms
from tailsignal.synth import reference as R

FDA = Path("data/raw/public/openfda")
OUT = Path("reports/model_a2")
ISOX = r"fluralaner|afoxolaner|sarolaner|lotilaner"
COX = {"carprofen", "meloxicam", "robenacoxib"}
MDR1 = {"Australian Shepherd", "Border Collie"}
HIGH_EPILEPSY = {"Border Collie", "Australian Shepherd", "Beagle", "German Shepherd"}
SIZE = {b[0]: b[3] for b in R.BREEDS}
START = np.datetime64("2022-01-01")

STUDIES = {
    "S1_isoxazoline_seizure": dict(outcome="seizure", window=50, planted=1.5),
    "S2_nsaid_gi": dict(outcome="gi", window=14, planted=2.0),
    "S3_ml_mdr1_neuro_null": dict(outcome="neuro", window=30, planted=1.0),
}


# ----------------------------------------------------------------------------- real-data input: FDA time to onset
def fda_onset_window() -> dict:
    rep = pd.read_parquet(FDA / "reports.parquet", columns=["report_id", "onset_date", "species"])
    drg = pd.read_parquet(FDA / "drugs.parquet", columns=["report_id", "ingredient", "first_exposure_date"])
    rxn = pd.read_parquet(FDA / "reactions.parquet", columns=["report_id", "veddra_term_name"])
    ids = set(rxn[rxn.veddra_term_name.isin(set(veddra_terms("seizure")))].report_id)
    d = drg[drg.ingredient.str.lower().str.contains(ISOX, na=False) & drg.report_id.isin(ids)]
    d = d.merge(rep[rep.species.astype(str).str.lower() == "dog"], on="report_id")
    on = pd.to_datetime(d.onset_date.astype(str).str[:8], format="%Y%m%d", errors="coerce")
    fe = pd.to_datetime(d.first_exposure_date.astype(str).str[:8], format="%Y%m%d", errors="coerce")
    days = (on - fe).dt.days.groupby(d.report_id).min().dropna()
    days = days[(days >= 0) & (days <= 365)]
    q = days.quantile([0.5, 0.75, 0.9])
    return dict(reports=int(len(days)), median_days=float(q[0.5]), p75_days=float(q[0.75]), p90_days=float(q[0.9]),
                share_within_50_days=float((days < 50).mean()), window=int(round(q[0.9])))


# ----------------------------------------------------------------------------- linkage
class UnionFind:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def link(patients: pd.DataFrame) -> dict[str, pd.Series]:
    """Entity id per clinic_patient_id under each linkage mode (truth excluded)."""
    pt = patients.copy()
    pt["market"] = pt.clinic.str[:3]
    pt["byear"] = pt.birth_date.str[:4].astype(int)
    pt["name"] = pt.pet_name.str.upper().str.strip()
    ids = pd.Series(pt.clinic_patient_id.values, index=pt.clinic_patient_id.values)
    modes = {"clinic": ids}
    uf = UnionFind(pt.clinic_patient_id)
    for _, g in pt[pt.microchip.notna()].groupby("microchip"):
        grp = g.clinic_patient_id.tolist()
        for x in grp[1:]:
            uf.union(grp[0], x)
    modes["microchip"] = ids.map(uf.find)
    for _, g in pt.groupby(["market", "species", "sex", "name"]):
        if g.clinic.nunique() < 2:
            continue
        r = g.to_dict("records")
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                a, b = r[i], r[j]
                if a["clinic"] == b["clinic"] or a["breed_text"] != b["breed_text"] or abs(a["byear"] - b["byear"]) > 1:
                    continue
                if isinstance(a["microchip"], str) and isinstance(b["microchip"], str) and a["microchip"] != b["microchip"]:
                    continue
                uf.union(a["clinic_patient_id"], b["clinic_patient_id"])
    modes["probabilistic"] = ids.map(uf.find)
    # exploratory (added after seeing linkage precision): also require the exact birth date when both records
    # carry a full date (records with a year-only date fall back to the year rule)
    uf2 = UnionFind(pt.clinic_patient_id)
    for cid, root in modes["microchip"].items():
        uf2.union(cid, root)
    full = ~pt.birth_date.str.endswith("-01-01")
    pt["full"] = full
    for _, g in pt.groupby(["market", "species", "sex", "name"]):
        if g.clinic.nunique() < 2:
            continue
        r = g.to_dict("records")
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                a, b = r[i], r[j]
                if a["clinic"] == b["clinic"] or a["breed_text"] != b["breed_text"] or abs(a["byear"] - b["byear"]) > 1:
                    continue
                if a["full"] and b["full"] and a["birth_date"] != b["birth_date"]:
                    continue
                if isinstance(a["microchip"], str) and isinstance(b["microchip"], str) and a["microchip"] != b["microchip"]:
                    continue
                uf2.union(a["clinic_patient_id"], b["clinic_patient_id"])
    modes["probabilistic_strict"] = ids.map(uf2.find)
    return modes


def pairwise_scores(entity: pd.Series, truth: pd.Series) -> dict:
    df = pd.DataFrame({"e": entity, "t": truth.reindex(entity.index)})
    pairs = lambda s: int((s.value_counts() * (s.value_counts() - 1) // 2).sum())
    tp = int(sum(pairs(g.t) for _, g in df.groupby("e")))
    pred, true = pairs(df.e), pairs(df.t)
    return dict(true_pairs=true, predicted_pairs=pred, precision=round(tp / max(pred, 1), 4),
                recall=round(tp / max(true, 1), 4))


# ----------------------------------------------------------------------------- estimates
def exact_rr(a, n1, b, n0):
    m = a + b
    if m == 0:
        return np.nan, np.nan
    ci = stats.binomtest(int(a), int(m)).proportion_ci(method="exact")
    f = lambda q: (q / (1 - q)) * n0 / n1 if q < 1 else np.inf
    return f(ci.low), f(ci.high)


def crude(d):
    e, c = d[d.exposed], d[~d.exposed]
    a, n1, b, n0 = int(e.y.sum()), len(e), int(c.y.sum()), len(c)
    out = dict(n_exposed=n1, n_comparator=n0, events_exposed=a, events_comparator=b,
               risk10k_exposed=1e4 * a / max(n1, 1), risk10k_comparator=1e4 * b / max(n0, 1))
    if a and b:
        rr = (a / n1) / (b / n0)
        se = np.sqrt(1 / a - 1 / n1 + 1 / b - 1 / n0)
        out.update(rr=rr, lo=rr * np.exp(-1.96 * se), hi=rr * np.exp(1.96 * se))
    else:
        out.update(rr=np.nan, lo=np.nan, hi=np.nan)
    out["exact_lo"], out["exact_hi"] = exact_rr(a, n1, b, n0)
    return out


def mantel_haenszel(d, strata="age_band"):
    """MH risk ratio with Greenland–Robins variance."""
    num = den = P = 0.0
    for _, g in d.groupby(strata, observed=True):
        a, n1 = g[g.exposed].y.sum(), g.exposed.sum()
        b, n0 = g[~g.exposed].y.sum(), (~g.exposed).sum()
        N = n1 + n0
        if N == 0 or n1 == 0 or n0 == 0:
            continue
        num += a * n0 / N
        den += b * n1 / N
        P += (n1 * n0 * (a + b) - a * b * N) / N ** 2
    if num == 0 or den == 0:
        return dict(mh_rr=np.nan, mh_lo=np.nan, mh_hi=np.nan)
    rr = num / den
    se = np.sqrt(P / (num * den))
    return dict(mh_rr=rr, mh_lo=rr * np.exp(-1.96 * se), mh_hi=rr * np.exp(1.96 * se))


def iptw(d):
    X = pd.get_dummies(d[["age", "size", "sex", "bcs", "prior_visits", "clinic"]],
                       columns=["size", "sex", "clinic"], drop_first=True, dtype=float)
    X["age2"] = X.age ** 2
    X = sm.add_constant(X)
    try:
        ps = sm.Logit(d.exposed.astype(float), X).fit(disp=0, method="lbfgs", maxiter=500).predict(X)
    except Exception:
        return dict(iptw_rr=np.nan, iptw_lo=np.nan, iptw_hi=np.nan)
    p = d.exposed.mean()
    w = np.where(d.exposed, p / ps, (1 - p) / (1 - ps))
    lo, hi = np.percentile(w, [1, 99])
    w = np.clip(w, lo, hi)
    if d[d.exposed].y.sum() == 0 or d[~d.exposed].y.sum() == 0:
        return dict(iptw_rr=np.nan, iptw_lo=np.nan, iptw_hi=np.nan, ps_auc=auc(d.exposed, ps))
    m = sm.GLM(d.y.astype(float), sm.add_constant(d.exposed.astype(float)), family=sm.families.Poisson(),
               var_weights=w).fit(cov_type="HC0")
    b, se = m.params.iloc[1], m.bse.iloc[1]
    return dict(iptw_rr=float(np.exp(b)), iptw_lo=float(np.exp(b - 1.96 * se)), iptw_hi=float(np.exp(b + 1.96 * se)),
                ps_auc=auc(d.exposed, ps))


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y.astype(int), s))


def n_per_arm(p0, rr, alpha=0.05, power=0.8):
    p1 = min(p0 * rr, 0.999)
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    pb = (p0 + p1) / 2
    return float(((za * np.sqrt(2 * pb * (1 - pb)) + zb * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) / (p1 - p0)) ** 2)


# ----------------------------------------------------------------------------- data
class EHRData:
    def __init__(self, root: Path):
        raw = root / "raw" / "ehr"
        self.root = root
        self.patients = pd.read_parquet(raw / "ehr_patients.parquet")
        self.visits = pd.read_parquet(raw / "ehr_visits.parquet")
        self.rx = pd.read_parquet(raw / "ehr_prescriptions.parquet")
        self.notes = pd.read_parquet(raw / "ehr_notes.parquet")
        self.flags = {}

    def text_flags(self):
        for oc in OUTCOMES:
            d = Dictionary(oc, self.notes.text)
            self.flags[oc] = pd.DataFrame({"visit_id": self.notes.visit_id, "clinic_patient_id": self.notes.clinic_patient_id,
                                           "day": self.notes.day, "current": d.stage3(self.notes.text).values,
                                           "any_mention": d.stage3(self.notes.text, allow_history=True).values})
        return self


def build_cohort(D: EHRData, study: str, entity: pd.Series, outcome_flag="current", window=None, lookback=180,
                 label_outcomes: pd.DataFrame | None = None) -> pd.DataFrame:
    spec = STUDIES[study]
    window = window or spec["window"]
    pt = D.patients.set_index("clinic_patient_id")
    rx = D.rx.assign(entity=D.rx.clinic_patient_id.map(entity), species=D.rx.clinic_patient_id.map(pt.species),
                     breed=D.rx.clinic_patient_id.map(pt.breed_text))
    rx = rx[rx.species == "dog"]
    if study.startswith("S1"):
        q = rx[rx.indication == "flea_tick"].copy()
        q["exposed"] = q.drug_class == "Isoxazoline"
    elif study.startswith("S2"):
        q = rx[(rx.indication == "osteoarthritis") & rx.drug.isin(COX | {"grapiprant"})].copy()
        q["exposed"] = q.drug.isin(COX)
    else:
        q = rx[rx.drug_class == "Macrocyclic lactone"].copy()
        q["exposed"] = q.breed.isin(MDR1)
    q = q.sort_values(["entity", "day"])
    idx = q.drop_duplicates("entity").reset_index(drop=True)
    # exclude dogs given both products before or within the window after index (not applicable to S3)
    if not study.startswith("S3"):
        other = q.merge(idx[["entity", "day", "exposed"]], on="entity", suffixes=("", "_idx"))
        both = other[(other.exposed != other.exposed_idx) & (other.day < other.day_idx + window)].entity.unique()
        idx = idx[~idx.entity.isin(both)]
    v = D.visits.assign(entity=D.visits.clinic_patient_id.map(entity))
    first_visit = v.groupby("entity").day.min()
    idx = idx[idx.day - idx.entity.map(first_visit) >= lookback] if lookback else idx
    fl = D.flags[spec["outcome"]].assign(entity=lambda f: f.clinic_patient_id.map(entity))
    if label_outcomes is not None:  # sensitivity: perfect text mining
        fl = fl.drop(columns=["current"]).merge(label_outcomes, on="visit_id")
    m = fl.merge(idx[["entity", "day", "visit_id"]], on="entity", suffixes=("", "_idx"))
    base = m[(m.day < m.day_idx) | ((m.day == m.day_idx) & (m.visit_id == m.visit_id_idx))]
    pre = set(base[base.any_mention].entity)
    idx = idx[~idx.entity.isin(pre)]
    after = v.merge(idx[["entity", "day"]], on="entity", suffixes=("", "_idx"))
    fu = set(after[after.day > after.day_idx].entity)
    win = m[(m.day >= m.day_idx) & (m.day < m.day_idx + window) & (m.visit_id != m.visit_id_idx) & m[outcome_flag]]
    hit = set(win.entity)
    idx = idx[idx.entity.isin(fu | hit)].copy()
    idx["y"] = idx.entity.isin(hit)
    # covariates at index
    birth = pd.to_datetime(idx.clinic_patient_id.map(pt.birth_date))
    idx["age"] = ((START + idx.day.astype("timedelta64[D]")).astype("datetime64[ns]") - birth).dt.days / 365.25
    idx["age_band"] = pd.cut(idx.age, [0, 3, 8, 40], right=False, labels=["<3", "3-7", "8+"])
    idx["size"] = idx.breed.map(SIZE).fillna("medium")
    idx["sex"] = idx.clinic_patient_id.map(pt.sex)
    vb = v.merge(idx[["entity", "day"]], on="entity", suffixes=("", "_idx"))
    prior = vb[(vb.day <= vb.day_idx) & (vb.day > vb.day_idx - 365)]
    idx["prior_visits"] = idx.entity.map(prior.groupby("entity").size()).fillna(0)
    last = vb[vb.day <= vb.day_idx].sort_values("day").groupby("entity").bcs.last()
    idx["bcs"] = idx.entity.map(last).fillna(5)
    idx["high_epilepsy_breed"] = idx.breed.isin(HIGH_EPILEPSY)
    return idx


def analyze(d: pd.DataFrame) -> dict:
    out = crude(d)
    out.update(mantel_haenszel(d))
    out.update(iptw(d))
    return out


def run(root: Path, tag: str, with_text_eval: bool):
    out = OUT / tag
    out.mkdir(parents=True, exist_ok=True)
    D = EHRData(root).text_flags()
    truth_map = pd.read_parquet(root / "truth" / "ehr" / "patient_map.parquet").set_index("clinic_patient_id").pet_uid
    modes = link(D.patients)
    modes["truth"] = truth_map.reindex(D.patients.clinic_patient_id)
    results = {"linkage": {k: pairwise_scores(v, truth_map) for k, v in modes.items() if k != "truth"}}
    labels = pd.read_parquet(root / "truth" / "ehr" / "note_labels.parquet")
    rows = []
    onset = fda_onset_window()
    results["fda_time_to_onset"] = onset
    for study, spec in STUDIES.items():
        lab = labels[["visit_id", OUTCOMES[spec["outcome"]]["label"]]].rename(
            columns={OUTCOMES[spec["outcome"]]["label"]: "current"})
        scen = {"primary": dict(entity=modes["probabilistic"])}
        for mname in ["clinic", "microchip", "probabilistic_strict", "truth"]:
            scen[f"linkage_{mname}"] = dict(entity=modes[mname])
        scen["no_lookback"] = dict(entity=modes["probabilistic"], lookback=0)
        scen["outcome_from_true_labels"] = dict(entity=modes["probabilistic"], label_outcomes=lab)
        if study.startswith("S1"):
            scen["fda_window"] = dict(entity=modes["probabilistic"], window=onset["window"])
        for sname, kw in scen.items():
            c = build_cohort(D, study, **kw)
            r = dict(network=tag, study=study, scenario=sname, planted_rr=spec["planted"], **analyze(c))
            rows.append(r)
            if sname == "primary":
                c.to_parquet(out / f"cohort_{study}.parquet", index=False)
                p0 = r["events_comparator"] / max(r["n_comparator"], 1)
                if p0 > 0 and spec["planted"] != 1:
                    r_need = n_per_arm(p0, spec["planted"])
                    results.setdefault("power", {})[study] = dict(
                        comparator_risk=p0, n_per_arm_for_80pct=round(r_need),
                        multiple_of_current_comparator=round(r_need / max(r["n_comparator"], 1), 1),
                        rule_of_three_min_exposed_for_1_in_10k=30000)
                if study.startswith("S1"):
                    for hb, g in c.groupby("high_epilepsy_breed"):
                        rows.append(dict(network=tag, study=study, scenario=f"exploratory_high_epilepsy_breed={hb}",
                                         planted_rr=spec["planted"], **crude(g)))
    res = pd.DataFrame(rows)
    res.to_csv(out / "estimates.csv", index=False)
    results["estimates"] = res.round(4).replace({np.nan: None}).to_dict("records")
    if with_text_eval:
        ev, _ = evaluate(D.notes, labels, out)
        results["text_mining"] = ev
    (out / "summary.json").write_text(json.dumps(results, indent=2, default=float))
    return results


def forest(paths: dict[str, Path], dest: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    frames = [pd.read_csv(p).assign(network=k) for k, p in paths.items()]
    d = pd.concat(frames)
    d = d[d.scenario.isin(["primary", "no_lookback", "linkage_clinic", "outcome_from_true_labels"])]
    titles = {"S1_isoxazoline_seizure": "S1 Isoxazoline vs other flea/tick: seizure",
              "S2_nsaid_gi": "S2 COX NSAID vs grapiprant: vomiting/diarrhea",
              "S3_ml_mdr1_neuro_null": "S3 Heartworm drug, MDR1 vs other breeds (null)"}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharey=False)
    for ax, (study, g) in zip(axes, d.groupby("study", sort=True)):
        g = g.reset_index(drop=True)
        ylab = [f"{r.network} · {r.scenario.replace('_', ' ')}" for r in g.itertuples()]
        for i, r in enumerate(g.itertuples()):
            est = r.iptw_rr if pd.notna(r.iptw_rr) else r.rr
            lo = r.iptw_lo if pd.notna(r.iptw_rr) else r.exact_lo
            hi = r.iptw_hi if pd.notna(r.iptw_rr) else r.exact_hi
            if pd.isna(lo):
                ax.text(0.06, i, "no events", fontsize=7, va="center", color="grey")
                continue
            hi = min(hi, 50) if pd.notna(hi) else 50
            ax.plot([max(lo, 0.02), hi], [i, i], color="#34495e")
            if pd.notna(est):
                ax.plot(est, i, "o", color="#c0392b" if r.network == "10x" else "#2471a3")
        ax.axvline(1, color="grey", lw=0.6)
        ax.axvline(g.planted_rr.iat[0], color="#27ae60", ls="--", lw=1, label="planted RR")
        if study.startswith("S2"):
            ax.axvline(1.5, color="#e67e22", ls=":", lw=1, label="expected for 'any GI note' outcome")
            ax.legend(fontsize=7, loc="lower right")
        ax.set_xscale("log")
        ax.set_xlim(0.05, 50)
        ax.set_yticks(range(len(g)), ylab, fontsize=7)
        ax.set_title(titles[study], fontsize=10)
        ax.set_xlabel("Risk ratio, 95% CI (log scale)")
    axes[0].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(dest, dpi=150)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data"))
    ap.add_argument("--tag", default="1x")
    ap.add_argument("--no-text-eval", action="store_true")
    a = ap.parse_args()
    r = run(a.root, a.tag, not a.no_text_eval)
    cols = ["study", "scenario", "n_exposed", "n_comparator", "events_exposed", "events_comparator", "rr", "lo", "hi",
            "iptw_rr", "iptw_lo", "iptw_hi"]
    print(pd.DataFrame(r["estimates"])[cols].to_string())
    print(json.dumps({k: r[k] for k in ("linkage", "fda_time_to_onset")}, indent=1))
    paths = {t: OUT / t / "estimates.csv" for t in ("1x", "10x") if (OUT / t / "estimates.csv").exists()}
    forest(paths, OUT / "forest.png")


if __name__ == "__main__":
    main()
