"""Feline CKD early prediction from routine lab panels (RenalTech-style). Spec: docs/feline_ckd_spec.md.

    uv run python -m tailsignal.models.feline_ckd                       # actual network
    uv run python -m tailsignal.models.feline_ckd --root data_scale10 --tag 10x
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

OUT = Path("reports/feline_ckd")
START = np.datetime64("2022-01-01")
ANALYTES = ["creatinine_mg_dl", "bun_mg_dl", "usg", "upc", "urine_ph", "wbc_k_ul", "sdma_ug_dl"]
BRADLEY = ["creatinine_mg_dl", "bun_mg_dl", "usg"]
HORIZON, BLIND, LOOKBACK = (30, 730), 30, (90, 900)


def cohort(root: Path, labs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Index panels with outcome and features. `labs` overrides the lab file (used by the stress test)."""
    raw = root / "raw" / "ehr"
    pt = pd.read_parquet(raw / "ehr_patients.parquet")
    cats = pt[pt.species == "cat"].set_index("clinic_patient_id")
    labs = pd.read_parquet(raw / "ehr_labs.parquet") if labs is None else labs
    labs = labs[labs.clinic_patient_id.isin(cats.index)]
    pan = labs.pivot_table(index=["visit_id", "clinic_patient_id", "day"], columns="analyte", values="value").reset_index()
    pan = pan.sort_values(["clinic_patient_id", "day"])
    v = pd.read_parquet(raw / "ehr_visits.parquet")
    dx = v[(v.dx == "chronic_kidney_disease") & v.clinic_patient_id.isin(cats.index)].groupby("clinic_patient_id").day.min()
    end = int(v.day.max())
    birth = pd.to_datetime(cats.birth_date)
    rows = []
    for cid, g in pan.groupby("clinic_patient_id"):
        g = g.reset_index(drop=True)
        d = dx.get(cid, np.inf)
        for i in range(1, len(g)):
            idx = g.iloc[i]
            if idx.day >= d:
                break
            gaps = idx.day - g.day.iloc[:i]
            ok = gaps[(gaps >= LOOKBACK[0]) & (gaps <= LOOKBACK[1])]
            if ok.empty:
                continue
            prev = g.iloc[ok.index[-1]]  # most recent eligible earlier panel
            lead = d - idx.day
            if lead < BLIND:
                continue  # diagnosable now; excluded per spec
            y = HORIZON[0] <= lead <= HORIZON[1]
            if not y and idx.day + HORIZON[1] > end:
                continue  # not enough follow-up to call it negative
            r = {"clinic_patient_id": cid, "visit_id": idx.visit_id, "day": int(idx.day), "y": int(y),
                 "lead_days": float(lead) if np.isfinite(lead) else np.nan,
                 "gap_years": (idx.day - prev.day) / 365.25}
            age = ((START + np.timedelta64(int(idx.day), "D")).astype("datetime64[ns]") - birth[cid].to_datetime64()) \
                / np.timedelta64(1, "D") / 365.25
            r["age"] = float(age)
            for a in ANALYTES:
                cur, pre = idx.get(a, np.nan), prev.get(a, np.nan)
                r[a] = cur
                r[a + "_prev"] = pre
                r[a + "_slope"] = (cur - pre) / r["gap_years"] if pd.notna(cur) and pd.notna(pre) else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def features(name: str) -> list[str]:
    two = lambda cols: cols + [c + "_prev" for c in cols] + [c + "_slope" for c in cols]
    return {"M2": ["age"] + BRADLEY,
            "M3": ["age"] + two(BRADLEY),
            "M4": ["age"] + two(BRADLEY + ["upc", "urine_ph", "wbc_k_ul"]),
            "M5": ["age"] + two(BRADLEY + ["upc", "urine_ph", "wbc_k_ul", "sdma_ug_dl"])}[name]


def cv_predict(df: pd.DataFrame, name: str, seed=0) -> np.ndarray:
    pred = np.zeros(len(df))
    if name == "M0":
        return df.creatinine_mg_dl.values
    if name == "M1":
        return ((df.creatinine_mg_dl >= 1.6) | (df.sdma_ug_dl >= 18)).astype(float).values
    X = df[features(name)]
    for tr, te in GroupKFold(5).split(X, df.y, df.clinic_patient_id):
        if name == "M2":
            m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
            Xtr, Xte = X.iloc[tr].fillna(X.iloc[tr].median()), X.iloc[te].fillna(X.iloc[tr].median())
        else:
            m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                               l2_regularization=1.0, random_state=seed)
            Xtr, Xte = X.iloc[tr], X.iloc[te]
        m.fit(Xtr, df.y.iloc[tr])
        pred[te] = m.predict_proba(Xte)[:, 1]
    return pred


def sens_at_spec(y, s, spec):
    neg = s[y == 0]
    thr = np.quantile(neg, spec)
    return float((s[y == 1] > thr).mean()), float(thr)


def boot(df, s, fn, B=300, seed=1):
    rng = np.random.default_rng(seed)
    cats = df.clinic_patient_id.unique()
    idx = {c: np.flatnonzero(df.clinic_patient_id.values == c) for c in cats}
    out = []
    for _ in range(B):
        take = np.concatenate([idx[c] for c in rng.choice(cats, len(cats))])
        yy = df.y.values[take]
        if yy.min() == yy.max():
            continue
        out.append(fn(yy, s[take]))
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def evaluate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    y = df.y.values
    rows, preds = [], {}
    early = (df.lead_days > 365) | (df.y == 0)
    late = (df.lead_days <= 365) | (df.y == 0)
    for name in ["M0", "M1", "M2", "M3", "M4", "M5"]:
        s = cv_predict(df, name)
        preds[name] = s
        r = {"model": name, "auc": roc_auc_score(y, s), "auc_ci": boot(df, s, roc_auc_score),
             "avg_precision": average_precision_score(y, s)}
        if name == "M1":
            r["rule_sensitivity"] = float(s[y == 1].mean())
            r["rule_specificity"] = float(1 - s[y == 0].mean())
        else:
            for sp in (0.95, 0.99):
                r[f"sens_at_{int(sp * 100)}spec"] = sens_at_spec(y, s, sp)[0]
                r[f"sens_at_{int(sp * 100)}spec_lead_1_12m"] = sens_at_spec(y[late.values], s[late.values], sp)[0]
                r[f"sens_at_{int(sp * 100)}spec_lead_12_24m"] = sens_at_spec(y[early.values], s[early.values], sp)[0]
        rows.append(r)
    res = pd.DataFrame(rows)
    s5 = preds["M5"]
    cal = pd.DataFrame({"p": s5, "y": y}).assign(decile=lambda d: pd.qcut(d.p.rank(method="first"), 10, labels=False))
    calib = cal.groupby("decile").agg(mean_predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size")).round(4)
    extra = {"brier_M5": float(brier_score_loss(y, s5)), "brier_M3": float(brier_score_loss(y, preds["M3"])),
             "calibration_M5": calib.reset_index().to_dict("records")}
    return res, extra, preds


def chart(res_by_tag: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = {"M0": "Latest creatinine", "M2": "4 features, 1 visit", "M3": "4 features, 2 visits",
              "M4": "+ urine panel, WBC", "M5": "+ SDMA"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, (key, title) in zip(axes, [("sens_at_99spec_lead_1_12m", "Diagnosis 1–12 months ahead"),
                                       ("sens_at_99spec_lead_12_24m", "Diagnosis 12–24 months ahead")]):
        for k, (tag, res) in enumerate(res_by_tag.items()):
            r = res.set_index("model").loc[list(labels)]
            x = np.arange(len(labels)) + (k - 0.5 * (len(res_by_tag) - 1)) * 0.36
            ax.bar(x, r[key] * 100, width=0.34, label=f"{tag} network", color=["#9db7c9", "#1f5f99"][k % 2])
            for xi, v in zip(x, r[key] * 100):
                ax.text(xi, v + 1, f"{v:.0f}", ha="center", fontsize=8)
        ax.set_xticks(range(len(labels)), labels.values(), rotation=20, ha="right", fontsize=9)
        ax.set_ylim(0, 105)
        ax.set_ylabel("Sensitivity at 99% specificity (%)")
        ax.set_title(title, fontsize=10)
        ax.axhline({"sens_at_99spec_lead_1_12m": 63.0, "sens_at_99spec_lead_12_24m": 44.2}[key], color="#b4440e",
                   ls="--", lw=1)
        ax.text(-0.45, {"sens_at_99spec_lead_1_12m": 63.0, "sens_at_99spec_lead_12_24m": 44.2}[key] + 2,
                "Bradley et al. 2019 (real Banfield data)", color="#b4440e", fontsize=8, ha="left")
        ax.spines[["top", "right"]].set_visible(False)
    axes[1].legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def run(root: Path, tag: str):
    out = OUT / tag
    out.mkdir(parents=True, exist_ok=True)
    df = cohort(root)
    res, extra, preds = evaluate(df)
    res.to_csv(out / "estimates.csv", index=False)
    summary = {"index_panels": int(len(df)), "cats": int(df.clinic_patient_id.nunique()), "positives": int(df.y.sum()),
               "positive_rate": float(df.y.mean()), "models": json.loads(res.to_json(orient="records")), **extra}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return res, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data"))
    ap.add_argument("--tag", default="1x")
    a = ap.parse_args()
    res, s = run(a.root, a.tag)
    pd.set_option("display.width", 220)
    print({k: s[k] for k in ("index_panels", "cats", "positives", "positive_rate", "brier_M5", "brier_M3")})
    print(res.round(3).to_string())
    tags = {t: pd.read_csv(OUT / t / "estimates.csv") for t in ("1x", "10x") if (OUT / t / "estimates.csv").exists()}
    chart(tags, OUT / "sensitivity_by_lead.png")


if __name__ == "__main__":
    main()
