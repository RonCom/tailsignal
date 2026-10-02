"""Oral health insights: periodontal (dental) disease in dogs and cats.

A Research & Insights product built on the resolved platform data, modeled on the published
Banfield/Waltham (US, 3M+ records) and VetCompass (UK, 22,333 dogs) periodontal studies.

Unit: pet-year. A pet is in the denominator for a calendar year if it had any vet visit that
year; it is a case if any visit that year carried a dental-disease diagnosis or procedure.

Outputs (reports/oral_health/): summary.json, breed_prevalence.csv, clinic_benchmark.csv,
product_dental_prevalence.csv (k-suppressed), prevalence_by_size_age.png

    python -m tailsignal.models.oral_health
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DB = Path("data/warehouse.duckdb")
OUT = Path("reports/oral_health")
K = 10
CLEANING_MIN_AMOUNT = 400  # dental visits at or above this are cleanings under anesthesia (verified on line items)
AGE_BANDS = [0, 2, 4, 7, 10, 12, 30]
AGE_LABELS = ["<2", "2-4", "4-7", "7-10", "10-12", "12+"]
SIZE_ORDER = ["toy", "small", "medium", "large"]

# Published benchmarks (see docs/oral_health_report.md for citations)
BANFIELD = {"overall": 0.182, "by_size": {"extra-small (<6.5 kg)": 0.224, "small": 0.257, "medium-small": 0.220,
                                          "medium-large": 0.089, "large": 0.119, "giant": 0.091}}
VETCOMPASS = {"annual_prevalence": 0.125, "rr_under10kg_vs_30to40kg": 3.07, "rr_age12plus_vs_2to4": 3.91}


def pet_years(con) -> pd.DataFrame:
    return con.execute(f"""
        with sizes as (select distinct breed, size_class from reference.breed_aliases where alias = breed),
        vy as (
            select e.pet_id, year(e.event_date) yr,
                   max((e.condition = 'dental_disease')::int) dental,
                   max((e.condition = 'dental_disease' and e.amount >= {CLEANING_MIN_AMOUNT})::int) cleaning,
                   max((e.service_code = 'wellness_exam')::int) had_wellness,
                   mode(e.location_id) clinic, count(*) visits
            from core.fct_service_event e where e.channel = 'vet' group by 1, 2
        ),
        obese as (select distinct pet_id from core.fct_service_event where condition = 'obesity')
        select vy.*, p.species, p.breed, p.breed_group, coalesce(s.size_class, 'unknown') size_class,
               p.market, p.sex, (ob.pet_id is not null)::int ever_obese,
               date_diff('day', p.birth_date, make_date(vy.yr, 7, 1)) / 365.25 age
        from vy join core.dim_pet p using (pet_id)
        left join sizes s on s.breed = p.breed
        left join obese ob using (pet_id)
        where p.birth_date is not null
    """).df()


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def prev_table(df, by):
    g = df.groupby(by).agg(pet_years=("dental", "size"), cases=("dental", "sum")).reset_index()
    g["prevalence"] = g.cases / g.pet_years
    ci = [wilson(k, n) for k, n in zip(g.cases, g.pet_years)]
    g["ci_lo"], g["ci_hi"] = [c[0] for c in ci], [c[1] for c in ci]
    return g


def breed_shrinkage(dogs: pd.DataFrame, min_n=30) -> pd.DataFrame:
    """Beta-binomial empirical Bayes: each breed's prevalence shrunk toward its size class."""
    rows = []
    for size, g in dogs.groupby("size_class"):
        b = g.groupby("breed").agg(n=("dental", "size"), k=("dental", "sum")).reset_index()
        p = b.k.sum() / b.n.sum()
        # method-of-moments prior strength from between-breed variance
        obs = b.k / b.n
        var_between = max(np.average((obs - p) ** 2, weights=b.n) - p * (1 - p) / b.n.mean(), 1e-6)
        m = max(p * (1 - p) / var_between - 1, 1.0)
        a0, b0 = p * m, (1 - p) * m
        for r in b.itertuples():
            post = stats.beta(a0 + r.k, b0 + r.n - r.k)
            rows.append(dict(breed=r.breed, size_class=size, pet_years=int(r.n), cases=int(r.k),
                             raw_prevalence=r.k / r.n, shrunk_prevalence=post.mean(),
                             ci90_lo=post.ppf(0.05), ci90_hi=post.ppf(0.95), prior_strength=m))
    out = pd.DataFrame(rows)
    return out[out.pet_years >= min_n].sort_values("shrunk_prevalence", ascending=False)


def clinic_benchmark(dogs: pd.DataFrame, model) -> pd.DataFrame:
    d = dogs.copy()
    d["expected"] = model.predict(d)
    g = d.groupby("clinic").agg(pet_years=("dental", "size"), observed=("dental", "sum"),
                                expected=("expected", "sum"), cleanings=("cleaning", "sum")).reset_index()
    g["o_e"] = g.observed / g.expected
    # funnel-plot 95% and 99.8% limits for O/E under Poisson
    se = 1 / np.sqrt(g.expected)
    g["lim95_lo"], g["lim95_hi"] = 1 - 1.96 * se, 1 + 1.96 * se
    g["lim998_lo"], g["lim998_hi"] = 1 - 3.09 * se, 1 + 3.09 * se
    g["flag"] = np.where(g.o_e < g.lim95_lo, "below expected",
                         np.where(g.o_e > g.lim95_hi, "above expected", "within range"))
    return g.sort_values("o_e")


def chart(dogs: pd.DataFrame, path: Path):
    # palette: reference categorical slots 1-4 (light), validated for adjacent pairs
    colors = {"toy": "#2a78d6", "small": "#eb6834", "medium": "#1baf7a", "large": "#eda100"}
    t = prev_table(dogs[dogs.size_class.isin(SIZE_ORDER)], ["size_class", "age_band"])
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    x = np.arange(len(AGE_LABELS))
    for s in SIZE_ORDER:
        r = t[t.size_class == s].set_index("age_band").reindex(AGE_LABELS)
        ax.plot(x, r.prevalence * 100, color=colors[s], lw=2, marker="o", ms=4, label=s)
        last = r.prevalence.last_valid_index()
        if last is not None and s == "toy":  # other sizes overlap at the right edge; the legend names them
            ax.annotate(s, (AGE_LABELS.index(last), r.prevalence[last] * 100), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8, color="#52514e")
    ax.set_xticks(x, AGE_LABELS)
    ax.set_xlabel("Age (years)", color="#52514e", fontsize=9)
    ax.set_ylabel("Dogs diagnosed in the year (%)", color="#52514e", fontsize=9)
    ax.set_title("Dental disease rises with age; toy breeds lead at every age",
                 loc="left", fontsize=10, color="#0b0b0b")
    ax.grid(axis="y", color="#e6e5e0", lw=0.8)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color("#c9c8c2")
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.legend(title="Breed size", fontsize=8, title_fontsize=8, frameon=False, loc="upper left")
    ax.set_xlim(-0.3, len(AGE_LABELS) - 0.3)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(a.db), read_only=True)
    py = pet_years(con)
    py["age_band"] = pd.cut(py.age, AGE_BANDS, labels=AGE_LABELS, right=False).astype(str)
    dogs = py[py.species == "dog"].copy()
    cats = py[py.species == "cat"].copy()

    overall = {sp: {"pet_years": int(len(d)), "prevalence": round(float(d.dental.mean()), 4),
                    "ci95": [round(x, 4) for x in wilson(int(d.dental.sum()), len(d))]}
               for sp, d in [("dog", dogs), ("cat", cats)]}
    by_size = prev_table(dogs[dogs.size_class.isin(SIZE_ORDER)], ["size_class"])
    by_age = prev_table(dogs[dogs.age_band.isin(AGE_LABELS)], ["age_band"])
    by_year = prev_table(py, ["species", "yr"])

    # adjusted odds ratios (dogs), clustered by pet
    m = dogs[dogs.size_class.isin(SIZE_ORDER) & dogs.age_band.isin(AGE_LABELS)].copy()
    m["size_class"] = pd.Categorical(m.size_class, SIZE_ORDER[::-1])  # reference = large
    m["age_band"] = pd.Categorical(m.age_band, ["2-4", "<2", "4-7", "7-10", "10-12", "12+"])  # reference 2-4
    fit = smf.glm("dental ~ C(size_class) + C(age_band) + ever_obese + had_wellness + C(market)", data=m,
                  family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(m.pet_id)[0]})
    ors = pd.DataFrame({"odds_ratio": np.exp(fit.params), "ci_lo": np.exp(fit.conf_int()[0]),
                        "ci_hi": np.exp(fit.conf_int()[1]), "p": fit.pvalues}).round(4)

    # detection: diagnosed share with vs. without a wellness exam that year
    detection = prev_table(dogs, ["had_wellness"])

    # treatment gap: diagnosed dog-years with a cleaning in the same year
    diag = dogs[dogs.dental == 1]
    treat = {"diagnosed_dog_years": int(len(diag)), "with_cleaning_same_year": int(diag.cleaning.sum()),
             "cleaning_rate": round(float(diag.cleaning.mean()), 4)}
    treat["by_size"] = (diag[diag.size_class.isin(SIZE_ORDER)].groupby("size_class").cleaning.mean()
                        .round(4).to_dict())
    price = con.execute(f"""select avg(amount) from core.fct_service_event
                            where condition = 'dental_disease' and amount >= {CLEANING_MIN_AMOUNT}""").fetchone()[0]

    breeds = breed_shrinkage(dogs)
    bench = clinic_benchmark(m, fit)
    gap = bench[bench.flag == "below expected"]
    opp = float(((gap.expected - gap.observed) * treat["cleaning_rate"] * price).sum())

    # k-suppressed product table: species x size x age band x market x year
    prod = prev_table(py, ["species", "size_class", "age_band", "market", "yr"])
    small = (prod.pet_years < K) | ((prod.cases > 0) & (prod.cases < K))
    prod.loc[small, ["cases", "prevalence", "ci_lo", "ci_hi"]] = np.nan
    prod["suppressed"] = small
    prod.loc[small, "pet_years"] = np.nan
    prod.round(4).to_csv(OUT / "product_dental_prevalence.csv", index=False)

    breeds.round(4).to_csv(OUT / "breed_prevalence.csv", index=False)
    bench.round(4).to_csv(OUT / "clinic_benchmark.csv", index=False)
    chart(dogs, OUT / "prevalence_by_size_age.png")

    toy, large = by_size.set_index("size_class").prevalence.reindex(["toy", "large"])
    a12 = by_age.set_index("age_band").prevalence
    summary = {
        "overall": overall, "by_size_dogs": by_size.round(4).to_dict("records"),
        "by_age_dogs": by_age.round(4).to_dict("records"), "by_year": by_year.round(4).to_dict("records"),
        "adjusted_odds_ratios_dogs": ors.reset_index().rename(columns={"index": "term"}).to_dict("records"),
        "detection_by_wellness_exam": detection.round(4).to_dict("records"),
        "treatment_gap": treat, "avg_cleaning_price": round(float(price), 2),
        "clinics_below_expected": int(len(gap)), "clinics": int(len(bench)),
        "cleaning_revenue_gap_per_year_total": round(opp / dogs.yr.nunique(), 0),
        "top_breeds": breeds.head(8).round(4).to_dict("records"),
        "comparison": {
            "ours": {"dog_annual_prevalence": overall["dog"]["prevalence"],
                     "toy_to_large_ratio": round(float(toy / large), 2),
                     "age12plus_to_2to4_ratio": round(float(a12.get("12+") / a12.get("2-4")), 2)},
            "banfield_us": {"period_prevalence": BANFIELD["overall"],
                            "extra_small_to_large_ratio": round(0.224 / 0.119, 2)},
            "vetcompass_uk": {"annual_prevalence": VETCOMPASS["annual_prevalence"],
                              "under10kg_vs_30to40kg_risk": VETCOMPASS["rr_under10kg_vs_30to40kg"],
                              "age12plus_vs_2to4_risk": VETCOMPASS["rr_age12plus_vs_2to4"]},
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ["overall", "comparison", "treatment_gap", "clinics_below_expected",
                                              "cleaning_revenue_gap_per_year_total"]}, indent=2, default=str))
    print(by_size.round(3).to_string(), by_age.round(3).to_string(), detection.round(3).to_string(),
          ors.to_string(), breeds.head(10).round(3).to_string(), bench.round(2).to_string(), sep="\n\n")


if __name__ == "__main__":
    main()
