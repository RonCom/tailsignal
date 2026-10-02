"""Stress test for the feline CKD model: real-world confounders and a time split. Spec: docs/feline_ckd_stress_spec.md.

    uv run python -m tailsignal.models.feline_ckd_stress --root data_scale10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from tailsignal.models.feline_ckd import OUT, START, boot, cohort, cv_predict, features, sens_at_spec

MODELS = ["M0", "M3", "M4", "M5"]
HYPER = dict(share=0.15, onset_age=(10, 16), untreated_days=(180, 540),
             mult={"creatinine_mg_dl": 0.65, "sdma_ug_dl": 0.80, "bun_mg_dl": 0.85}, usg=-0.008)
DEHYD = dict(share=0.10, mult={"creatinine_mg_dl": 1.25, "bun_mg_dl": 1.40, "sdma_ug_dl": 1.15}, usg=0.008)
MUSCLE = dict(from_age=12, per_year=0.02)


def confound(root: Path, seed: int = 11) -> tuple[pd.DataFrame, dict]:
    raw = root / "raw" / "ehr"
    pt = pd.read_parquet(raw / "ehr_patients.parquet")
    cats = pt[pt.species == "cat"].set_index("clinic_patient_id")
    labs = pd.read_parquet(raw / "ehr_labs.parquet")
    labs = labs[labs.clinic_patient_id.isin(cats.index)].copy()
    rng = np.random.default_rng(seed)
    birth = pd.to_datetime(cats.birth_date)
    date = pd.Timestamp(START) + pd.to_timedelta(labs.day, unit="D")
    labs["age"] = ((date - labs.clinic_patient_id.map(birth)).dt.days / 365.25).values

    # hyperthyroidism: cat-level onset and untreated window
    ids = cats.index.to_numpy()
    hyp = rng.random(len(ids)) < HYPER["share"]
    onset = pd.Series(rng.uniform(*HYPER["onset_age"], len(ids)), index=ids)
    dur = pd.Series(rng.uniform(*HYPER["untreated_days"], len(ids)) / 365.25, index=ids)
    hset = set(ids[hyp])
    a0 = labs.clinic_patient_id.map(onset)
    in_h = labs.clinic_patient_id.isin(hset) & (labs.age >= a0) & (labs.age < a0 + labs.clinic_patient_id.map(dur))
    # dehydration: panel-level
    vis = labs.visit_id.unique()
    dset = set(vis[rng.random(len(vis)) < DEHYD["share"]])
    in_d = labs.visit_id.isin(dset)
    # muscle loss
    mus = 1 - MUSCLE["per_year"] * (labs.age - MUSCLE["from_age"]).clip(lower=0)

    v = labs.value.astype(float).to_numpy()
    for a, m in HYPER["mult"].items():
        v = np.where(in_h & (labs.analyte == a), v * m, v)
    for a, m in DEHYD["mult"].items():
        v = np.where(in_d & (labs.analyte == a), v * m, v)
    usg = labs.analyte == "usg"
    v = np.where(in_h & usg, v + HYPER["usg"], v)
    v = np.where(in_d & usg, v + DEHYD["usg"], v)
    v = np.where(labs.analyte == "creatinine_mg_dl", v * mus.clip(lower=0.7), v)
    labs["value"] = v
    info = {"hyperthyroid_cats": int(hyp.sum()), "cats": int(len(ids)),
            "panels_hyperthyroid": int(labs[in_h].visit_id.nunique()), "panels_dehydrated": int(len(dset)),
            "panels": int(len(vis))}
    return labs.drop(columns="age"), info


def time_split_predict(df: pd.DataFrame, name: str, seed=0):
    cut = df.day.median()
    train = df[df.day < cut]
    test = df[(df.day >= cut) & ~df.clinic_patient_id.isin(train.clinic_patient_id)]
    if name == "M0":
        return test, test.creatinine_mg_dl.to_numpy()
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                       l2_regularization=1.0, random_state=seed)
    m.fit(train[features(name)], train.y)
    return test, m.predict_proba(test[features(name)])[:, 1]


def score(df, s) -> dict:
    y = df.y.to_numpy()
    early = ((df.lead_days > 365) | (df.y == 0)).to_numpy()
    return {"n_panels": int(len(df)), "positives": int(y.sum()), "auc": round(roc_auc_score(y, s), 3),
            "auc_ci": [round(x, 3) for x in boot(df.reset_index(drop=True), s, roc_auc_score, B=200)],
            "sens_95spec": round(sens_at_spec(y, s, 0.95)[0], 3),
            "sens_99spec_12_24m": round(sens_at_spec(y[early], s[early], 0.99)[0], 3)}


HEAVY = dict(hyper_share=0.40, untreated_days=(365, 1095), dehyd_share=0.25)  # exploratory, chosen after seeing results


def run(root: Path, heavy: bool = False):
    out = OUT / ("stress_heavy" if heavy else "stress")
    out.mkdir(parents=True, exist_ok=True)
    if heavy:
        HYPER.update(share=HEAVY["hyper_share"], untreated_days=HEAVY["untreated_days"])
        DEHYD.update(share=HEAVY["dehyd_share"])
    clabs, info = confound(root)
    data = {"original": cohort(root), "confounded": cohort(root, clabs)}
    rows = []
    for lab, df in data.items():
        for name in MODELS:
            rows.append({"labs": lab, "split": "cv", "model": name, **score(df, cv_predict(df, name))})
            test, s = time_split_predict(df, name)
            rows.append({"labs": lab, "split": "time", "model": name, **score(test, s)})
    res = pd.DataFrame(rows)
    res.to_csv(out / "estimates.csv", index=False)
    a = res.set_index(["labs", "split", "model"]).auc
    drop = {m: round(a["original", "cv", m] - a["confounded", "cv", m], 3) for m in MODELS}
    exp = {
        "time_split_changes_auc_lt_0.02": bool(all(abs(a["original", "time", m] - a["original", "cv", m]) < 0.02 for m in MODELS)),
        "confounders_lower_M0_by_0.05": bool(drop["M0"] >= 0.05),
        "M5_loses_less_than_M3": bool(drop["M5"] < drop["M3"]),
        "M5_at_least_0.90_confounded_time": bool(a["confounded", "time", "M5"] >= 0.90),
    }
    summary = {"confounders": info, "auc_drop_from_confounders_cv": drop, "expectations": exp}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return res, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data_scale10"))
    ap.add_argument("--heavy", action="store_true", help="exploratory: more hyperthyroidism and dehydration")
    a = ap.parse_args()
    res, s = run(a.root, a.heavy)
    pd.set_option("display.width", 200)
    print(res.drop(columns="auc_ci").to_string())
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
