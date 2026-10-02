"""Antimicrobial resistance in dog clinical isolates (FDA NARMS / Vet-LIRN / NAHLN), pre-registered H9.

Spec: docs/amr_spec.md. Input: data/raw/public/narms/animal_pathogen_data.xlsx (or .parquet cache).
Outputs: reports/amr/ — summary.json, antibiogram.csv, trends.csv, regional_uti_antibiogram.csv,
mdr_by_year.csv, amr_trends.png

    python -m tailsignal.models.amr
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

from tailsignal.models.oral_health import wilson

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SRC = Path("data/raw/public/narms")
OUT = Path("reports/amr")
MIN_N = 30           # CLSI M39 minimum isolates per antibiogram cell
MIN_TREND_N = 100    # pre-registered minimum isolates for a trend test
PRIMARY = ["E. coli", "S. pseudintermedius"]

CLASSES = {
    "Aminoglycosides": ["Amikacin", "Gentamicin", "Neomycin", "Spectinomycin", "Streptomycin", "Tobramycin"],
    "Penicillins": ["Amoxicillin", "Ampicillin", "Penicillin", "Benzylpenicillin", "Piperacillin", "Ticarcillin"],
    "Anti-staphylococcal penicillins": ["Oxacillin", "Oxacillin + 2% NaCl"],
    "Beta-lactam + inhibitor": ["Amoxicillin/Clavulanic Acid", "Amoxicillin/clavulanic acid 2:1", "Ampicillin/Sulbactam",
                                "Piperacillin/Tazobactam", "Ticarcillin/Clavulanic Acid", "Ticarcillin/clavulanic Acid"],
    "Cephalosporins": ["Cefazolin", "Cephalexin", "Cephalothin", "Cefuroxime", "Cefoxitin", "Cefotetan", "Ceforanide",
                       "Cefpodoxime", "Ceftazidime", "Ceftiofur", "Ceftriaxone", "Cefovecin", "Cefepime"],
    "Carbapenems": ["Imipenem", "Meropenem"],
    "Monobactams": ["Aztreonam"],
    "Fluoroquinolones": ["Ciprofloxacin", "Danofloxacin", "Enrofloxacin", "Gatifloxacin", "Levofloxacin", "Marbofloxacin",
                         "Moxifloxacin", "Ofloxacin", "Orbifloxacin", "Pradofloxacin"],
    "Tetracyclines": ["Chlortetracycline", "Doxycycline", "Minocycline", "Oxytetracycline", "Tetracycline"],
    "Macrolides": ["Azithromycin", "Clarithromycin", "Erythromycin", "Gamithromycin", "Tildipirosin", "Tilmicosin",
                   "Tulathromycin", "Tylosin"],
    "Lincosamides": ["Clindamycin", "Pirlimycin"],
    "Phenicols": ["Chloramphenicol", "Florfenicol"],
    "Folate pathway inhibitors": ["Trimethoprim/Sulfamethoxazole", "Sulphadimethoxine", "Sulphathiazole"],
    "Nitrofurans": ["Nitrofurantoin"], "Glycopeptides": ["Vancomycin"], "Rifamycins": ["Rifampin"],
    "Polymyxins": ["Polymyxin-B"], "Fusidanes": ["Fusidic Acid"], "Aminocoumarins": ["Novobiocin", "Penicillin/Novobiocin"],
    "Pleuromutilins": ["Tiamulin"], "Polypeptides": ["Bacitracin"],
}
DRUG_CLASS = {d: c for c, ds in CLASSES.items() for d in ds}
INTRINSIC = {"E. coli": {"Macrolides", "Lincosamides", "Glycopeptides", "Fusidanes", "Pleuromutilins", "Polypeptides",
                         "Aminocoumarins"},
             "S. pseudintermedius": {"Polymyxins", "Monobactams"}}
DRUG_ALIASES = {"Amoxicillin/clavulanic acid 2:1": "Amoxicillin/Clavulanic Acid", "Oxacillin + 2% NaCl": "Oxacillin",
                "Ticarcillin/clavulanic Acid": "Ticarcillin/Clavulanic Acid"}
REGION = {  # US Census regions
    "Northeast": ["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont", "New Jersey",
                  "New York", "Pennsylvania"],
    "Midwest": ["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota", "Missouri",
                "Nebraska", "North Dakota", "South Dakota"],
    "South": ["Delaware", "Florida", "Georgia", "Maryland", "North Carolina", "South Carolina", "Virginia",
              "District of Columbia", "West Virginia", "Alabama", "Kentucky", "Mississippi", "Tennessee", "Arkansas",
              "Louisiana", "Oklahoma", "Texas"],
    "West": ["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah", "Wyoming", "Alaska",
             "California", "Hawaii", "Oregon", "Washington"],
}
STATE_REGION = {s: r for r, ss in REGION.items() for s in ss}
UTI_DRUGS = ["Amoxicillin", "Ampicillin", "Amoxicillin/Clavulanic Acid", "Trimethoprim/Sulfamethoxazole", "Cephalexin",
             "Cefazolin", "Cefpodoxime", "Enrofloxacin", "Marbofloxacin", "Nitrofurantoin", "Doxycycline"]


def load(src: Path = SRC) -> pd.DataFrame:
    pq = src / "animal_pathogen_data.parquet"
    df = pd.read_parquet(pq) if pq.exists() else pd.read_excel(src / "animal_pathogen_data.xlsx")
    df = df.rename(columns={"Sample ID": "isolate", "Host Species": "host", "Collection Source": "source",
                            "Genus": "organism", "Drug Name": "drug", "Interpretation": "interp", "Year": "year",
                            "State": "state", "Agency": "agency"})
    df["drug"] = df.drug.replace(DRUG_ALIASES)
    df = df[df.interp.isin(["Susceptible", "Resistant"])].copy()
    df["R"] = (df.interp == "Resistant").astype(int)
    df["drug_class"] = df.drug.map(DRUG_CLASS).fillna("Unclassified")
    df["region"] = df.state.map(STATE_REGION).fillna(df.state.where(df.state == "Canada", "Unknown"))
    df["source"] = df.source.str.contains("UTI").map({True: "UTI", False: "Other sites"})
    # one result per isolate x drug (keep resistant if any duplicate disagrees)
    return (df.groupby(["isolate", "organism", "source", "state", "region", "year", "agency", "drug", "drug_class"],
                       as_index=False).R.max())


def pct_table(df, by) -> pd.DataFrame:
    g = df.groupby(by).R.agg(n="size", resistant="sum").reset_index()
    g["pct_resistant"] = g.resistant / g.n
    ci = [wilson(k, n) for k, n in zip(g.resistant, g.n)]
    g["ci_lo"], g["ci_hi"] = [c[0] for c in ci], [c[1] for c in ci]
    g["reported"] = g.n >= MIN_N
    return g


def eligibility(df) -> pd.DataFrame:
    """Organism x drug x site combinations fit for comparison (amendment 2026-10-02):
    tested on >= 90% of isolates every year, < 95% resistant overall, breakpoint stable across years."""
    d = df[df.organism.isin(PRIMARY)]
    iso = d.groupby(["organism", "source", "year"]).isolate.nunique().rename("isolates")
    tested = d.groupby(["organism", "source", "drug", "year"]).isolate.nunique().rename("tested")
    t = tested.reset_index().merge(iso.reset_index(), on=["organism", "source", "year"])
    t["share"] = t.tested / t.isolates
    years = d.groupby(["organism", "source"]).year.nunique().rename("n_years")
    e = t.groupby(["organism", "source", "drug"]).agg(min_share=("share", "min"), years=("year", "nunique")).reset_index()
    e = e.merge(years.reset_index(), on=["organism", "source"])
    e.loc[e.years < e.n_years, "min_share"] = 0.0  # not tested at all in some year
    pr = d.groupby(["organism", "source", "drug"]).R.mean().rename("pct_resistant").reset_index()
    e = e.merge(pr, on=["organism", "source", "drug"])
    e["eligible"] = (e.min_share >= 0.90) & (e.pct_resistant < 0.95)
    e["reason"] = np.where(e.min_share < 0.90, "selective testing",
                           np.where(e.pct_resistant >= 0.95, "breakpoint below wild type", "eligible"))
    return e


def trends(df, elig=None, by_source=False) -> pd.DataFrame:
    rows = []
    d = df[df.organism.isin(PRIMARY)]
    keys = ["organism", "source", "drug"] if by_source else ["organism", "drug"]
    if elig is not None:
        d = d.merge(elig[elig.eligible][["organism", "source", "drug"]], on=["organism", "source", "drug"])
    for k, g in d.groupby(keys):
        org, drug = k[0], k[-1]
        if len(g) < MIN_TREND_N or g.year.nunique() < 3 or g.R.nunique() < 2:
            continue
        x = sm.add_constant(g.year - 2017)
        try:
            fit = sm.Logit(g.R, x).fit(disp=0)
        except Exception:
            continue
        b, se = fit.params.iloc[1], fit.bse.iloc[1]
        rows.append(dict(organism=org, source=k[1] if by_source else "pooled", drug=drug,
                         drug_class=DRUG_CLASS.get(drug, "Unclassified"), n=len(g),
                         first_year=int(g.year.min()), last_year=int(g.year.max()),
                         pct_first=g[g.year == g.year.min()].R.mean(), pct_last=g[g.year == g.year.max()].R.mean(),
                         or_per_year=np.exp(b), or_lo=np.exp(b - 1.96 * se), or_hi=np.exp(b + 1.96 * se),
                         p=fit.pvalues.iloc[1]))
    t = pd.DataFrame(rows)
    t["q_bh"] = multipletests(t.p, method="fdr_bh")[1]
    t["trend"] = np.where(t.q_bh < 0.05, np.where(t.or_per_year > 1, "rising", "falling"), "no clear trend")
    return t.sort_values(["organism", "source", "q_bh"])


def mdr(df, elig=None) -> tuple[pd.DataFrame, dict]:
    out, panels = [], {}
    if elig is not None:  # drop drug x site combinations whose breakpoint sits below the wild type
        bad = elig[elig.reason == "breakpoint below wild type"][["organism", "source", "drug"]]
        df = df.merge(bad.assign(_bad=1), on=["organism", "source", "drug"], how="left")
        df = df[df._bad.isna()].drop(columns="_bad")
    for org in PRIMARY:
        d = df[(df.organism == org) & ~df.drug_class.isin(INTRINSIC[org] | {"Unclassified"})]
        iso_year = d.groupby("isolate").year.first()
        tested = d.groupby(["isolate", "drug_class"]).size().unstack(fill_value=0) > 0
        share = tested.groupby(iso_year.reindex(tested.index)).mean()   # share of isolates tested, per year
        core = [c for c in share.columns if (share[c] >= 0.90).all()]
        panels[org] = core
        res = d[d.drug_class.isin(core)].groupby(["isolate", "drug_class"]).R.max().unstack(fill_value=0)
        n_cls = res.sum(axis=1)
        m = pd.DataFrame({"year": iso_year.reindex(res.index), "mdr": (n_cls >= 3).astype(int)})
        g = m.groupby("year").mdr.agg(n="size", mdr_isolates="sum").reset_index()
        g["pct_mdr"] = g.mdr_isolates / g.n
        g["organism"] = org
        out.append(g)
        fit = sm.Logit(m.mdr, sm.add_constant(m.year - 2017)).fit(disp=0)
        panels[f"{org}_trend_or_per_year"] = [round(float(np.exp(fit.params.iloc[1])), 3),
                                               round(float(np.exp(fit.conf_int().iloc[1, 0])), 3),
                                               round(float(np.exp(fit.conf_int().iloc[1, 1])), 3),
                                               float(fit.pvalues.iloc[1])]
        panels[f"{org}_overall_pct_mdr"] = round(float(m.mdr.mean()), 4)
    return pd.concat(out), panels


def mrsp(df) -> dict:
    sp = df[(df.organism == "S. pseudintermedius") & (df.drug_class == "Anti-staphylococcal penicillins")]
    iso = sp.groupby(["isolate", "year", "region", "source"]).R.max().reset_index()
    by_year = pct_table(iso, ["year"])
    fit = smf.logit("R ~ I(year - 2017) + C(region) + C(source)", data=iso[~iso.region.isin(["Unknown"])]).fit(disp=0)
    ci = fit.conf_int().loc["I(year - 2017)"]
    return {"isolates": int(len(iso)), "overall_pct": round(float(iso.R.mean()), 4),
            "by_year": by_year.round(4).to_dict("records"),
            "by_year_and_site": pct_table(iso, ["source", "year"]).round(4).to_dict("records"),
            "by_region": pct_table(iso, ["region"]).round(4).to_dict("records"),
            "adjusted_or_per_year": [round(float(np.exp(fit.params["I(year - 2017)"])), 3),
                                     round(float(np.exp(ci[0])), 3), round(float(np.exp(ci[1])), 3)],
            "p_trend": float(fit.pvalues["I(year - 2017)"])}


def region_source_models(df, elig=None) -> list[dict]:
    """H9d (exploratory if sparse): adjusted region and source effects for key drug markers."""
    rows = []
    markers = [("E. coli", "Enrofloxacin"), ("E. coli", "Amoxicillin/Clavulanic Acid"),
               ("E. coli", "Trimethoprim/Sulfamethoxazole"), ("E. coli", "Cefpodoxime"),
               ("S. pseudintermedius", "Clindamycin"), ("S. pseudintermedius", "Trimethoprim/Sulfamethoxazole")]
    for org, drug in markers:
        g = df[(df.organism == org) & (df.drug == drug) & ~df.region.isin(["Unknown", "Canada"])]
        if elig is not None:
            ok = elig[(elig.organism == org) & (elig.drug == drug) & elig.eligible].source
            g = g[g.source.isin(ok)]
            if g.source.nunique() < 2:
                g = g.assign(source="single")
        if len(g) < MIN_TREND_N:
            continue
        f = "R ~ I(year - 2017) + C(region, Treatment('Midwest'))" + (" + C(source)" if g.source.nunique() > 1 else "")
        fit = smf.logit(f, data=g).fit(disp=0)
        ors = np.exp(fit.params).round(3).to_dict()
        rows.append({"organism": org, "drug": drug, "n": len(g),
                     "odds_ratios": {k: v for k, v in ors.items() if k != "Intercept"},
                     "p_values": fit.pvalues.round(4).to_dict()})
    return rows


def chart(abg: pd.DataFrame, mrsp_years: list[dict], path: Path, elig: pd.DataFrame | None = None):
    if elig is not None:  # only plot combinations that passed the eligibility rules
        ok = elig[elig.eligible][["organism", "source", "drug"]]
        abg = abg.merge(ok, on=["organism", "source", "drug"])
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # reference categorical slots 1-4
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=150, sharey=True)
    fig.patch.set_facecolor("#fcfcfb")
    panels = [("E. coli (urinary isolates)", "E. coli", "UTI",
               ["Ampicillin", "Trimethoprim/Sulfamethoxazole", "Enrofloxacin", "Cefpodoxime"]),
              ("S. pseudintermedius (skin and other sites)", "S. pseudintermedius", "Other sites",
               ["Oxacillin", "Clindamycin", "Trimethoprim/Sulfamethoxazole", "Cefpodoxime"])]
    for ax, (title, org, src, drugs) in zip(axes, panels):
        ax.set_facecolor("#fcfcfb")
        sub = abg[(abg.organism == org) & (abg.source == src)]
        for c, d in zip(colors, drugs):
            if d == "Oxacillin":  # MRSP has its own pre-registered analysis (all oxacillin results)
                r = pd.DataFrame([x for x in mrsp_years if x["source"] == src]).sort_values("year")
                r["reported"] = r.n >= MIN_N
            else:
                r = sub[(sub.drug == d) & sub.reported].sort_values("year")
            if r.empty:
                continue
            lab = "Oxacillin (MRSP)" if d == "Oxacillin" else d.replace("Trimethoprim/Sulfamethoxazole", "TMP-SMX")
            ax.plot(r.year, r.pct_resistant * 100, color=c, lw=2, marker="o", ms=3.5, label=lab)
        ax.set_title(title, loc="left", fontsize=9.5, color="#0b0b0b")
        ax.grid(axis="y", color="#e6e5e0", lw=0.8)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        for sp in ["left", "bottom"]:
            ax.spines[sp].set_color("#c9c8c2")
        ax.tick_params(colors="#52514e", labelsize=8)
        ax.legend(fontsize=7.5, frameon=False, loc="upper right" if org == "E. coli" else "lower right")
    axes[0].set_ylabel("Isolates resistant (%)", color="#52514e", fontsize=9)
    fig.suptitle("Resistance in dog clinical isolates, FDA NARMS (Vet-LIRN/NAHLN), 2017–2024",
                 x=0.01, ha="left", fontsize=10.5, color="#0b0b0b")
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, default=SRC)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    df = load(a.src)
    prim = df[df.organism.isin(PRIMARY)]
    elig = eligibility(df)
    elig.round(4).to_csv(OUT / "eligibility.csv", index=False)

    # H9a antibiogram: organism x source x drug x year (plus all sources pooled)
    abg = pd.concat([pct_table(prim, ["organism", "source", "drug", "drug_class", "year"]),
                     pct_table(prim, ["organism", "drug", "drug_class", "year"]).assign(source="All")])
    abg.round(4).to_csv(OUT / "antibiogram.csv", index=False)

    # Regional UTI antibiogram for clinics: E. coli urinary isolates, latest 3 years, % susceptible
    recent = prim[(prim.organism == "E. coli") & (prim.source == "UTI") & (prim.year >= prim.year.max() - 2)
                  & prim.drug.isin(UTI_DRUGS) & (prim.region != "Unknown")]
    ok_uti = elig[(elig.organism == "E. coli") & (elig.source == "UTI") & elig.eligible].drug
    reg = pct_table(recent[recent.drug.isin(ok_uti)], ["region", "drug"])
    reg["pct_susceptible"] = 1 - reg.pct_resistant
    reg.loc[~reg.reported, ["pct_susceptible", "pct_resistant", "ci_lo", "ci_hi"]] = np.nan
    reg.round(4).to_csv(OUT / "regional_uti_antibiogram.csv", index=False)

    tr_pooled = trends(df)  # pre-registered H9b as specified (pooled across sites)
    tr_pooled.round(5).to_csv(OUT / "trends_pooled_prereg.csv", index=False)
    tr = trends(df, elig, by_source=True)  # amendment: within site, eligible combinations only
    tr.round(5).to_csv(OUT / "trends.csv", index=False)
    mdr_tab, panels = mdr(df, elig)
    mdr_tab.round(4).to_csv(OUT / "mdr_by_year.csv", index=False)
    mr = mrsp(df)
    rs = region_source_models(df, elig)
    chart(abg, mr["by_year_and_site"], OUT / "amr_trends.png", elig)

    summary = {
        "isolates": {o: int(df[df.organism == o].isolate.nunique()) for o in df.organism.unique()},
        "years": [int(df.year.min()), int(df.year.max())], "states": int(df.state.nunique()),
        "test_results": int(len(df)),
        "eligibility": elig.groupby(["organism", "source", "reason"]).size().rename("combos").reset_index()
                          .to_dict("records"),
        "trends_pooled_prereg": {"tested_pairs": int(len(tr_pooled)),
                                 "rising": int((tr_pooled.trend == "rising").sum()),
                                 "falling": int((tr_pooled.trend == "falling").sum())},
        "trends": {"tested_pairs": int(len(tr)), "rising": int((tr.trend == "rising").sum()),
                   "falling": int((tr.trend == "falling").sum()),
                   "rising_pairs": tr[tr.trend == "rising"][["organism", "source", "drug", "n", "or_per_year",
                                                              "pct_first", "pct_last"]].round(3).to_dict("records"),
                   "falling_pairs": tr[tr.trend == "falling"][["organism", "source", "drug", "n", "or_per_year",
                                                                "pct_first", "pct_last"]].round(3).to_dict("records")},
        "mdr": {k: v for k, v in panels.items()}, "mdr_by_year": mdr_tab.round(4).to_dict("records"),
        "mrsp": mr, "region_source_models": rs,
        "regional_uti_antibiogram": reg.round(3).to_dict("records"),
        "prereg_expectation_mrsp_present_and_not_declining": bool(
            mr["overall_pct"] >= 0.10 and not (mr["adjusted_or_per_year"][2] < 1)),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ["isolates", "trends", "mdr", "prereg_expectation_mrsp_present_and_not_declining"]},
                     indent=2, default=str)[:6000])
    print(json.dumps({"overall_pct": mr["overall_pct"], "or": mr["adjusted_or_per_year"], "by_year": mr["by_year"],
                      "by_region": mr["by_region"]}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
