"""Cross-channel entity resolution: which source records are the same pet?

Input:  intermediate.int_source_pet_profiles (one row per pet record per source system)
Output: intermediate.int_pet_clusters (unique_id -> pet_id)
        qa.er_metrics (precision / recall / F1 vs. ground truth, when truth exists)

Method: Splink (Fellegi-Sunter) link-and-dedupe across all sources, trained without labels
(random-sampling u, EM for m). A deterministic rule (same phone + same pet name) is
evaluated alongside as the baseline a skeptical reviewer would propose first.
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import duckdb
import pandas as pd

import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink import Linker, SettingsCreator, block_on
from splink.internals.duckdb.database_api import DuckDBAPI

DB = Path("data/warehouse.duckdb")
TRUTH = Path("data/truth")


def load_profiles(con) -> pd.DataFrame:
    df = con.sql("select * from intermediate.int_source_pet_profiles").df()
    df["breed"] = df["breed"].where(df["breed"] != "Unmapped")
    df["owner_zip3"] = df["owner_zip"].str[:3]
    # first initial helps with nicknames (Bob/Robert won't match; Chris/Christopher will)
    df["owner_first_initial"] = df["owner_first"].str[:1]
    for c in ["owner_first", "owner_last", "owner_phone", "owner_email", "owner_zip", "pet_name", "species",
              "breed", "breed_group", "market", "owner_zip3", "owner_first_initial"]:
        df[c] = df[c].astype("object").where(df[c].notna(), None)
    df["birth_year"] = df["birth_year"].astype("Int64")
    return df


def owner_settings() -> SettingsCreator:
    """Stage 1: probabilistic household linkage on owner attributes."""
    return SettingsCreator(
        link_type="dedupe_only",  # one combined table; source_system is a column
        unique_id_column_name="unique_id",
        comparisons=[
            cl.ExactMatch("owner_phone"),
            cl.EmailComparison("owner_email"),
            cl.JaroWinklerAtThresholds("owner_last", [0.95, 0.88]),
            cl.CustomComparison(
                output_column_name="owner_first",
                comparison_levels=[
                    cll.NullLevel("owner_first"),
                    cll.ExactMatchLevel("owner_first"),
                    cll.JaroWinklerLevel("owner_first", 0.88),
                    cll.ExactMatchLevel("owner_first_initial"),
                    cll.ElseLevel(),
                ],
            ),
            cl.ExactMatch("owner_zip"),
            cl.ExactMatch("market"),
        ],
        blocking_rules_to_generate_predictions=[
            block_on("owner_phone"),
            block_on("owner_email"),
            block_on("owner_last", "market"),
        ],
        retain_intermediate_calculation_columns=False,
    )


def run_household_linkage(df: pd.DataFrame, threshold: float):
    db_api = DuckDBAPI()
    sdf = db_api.register(df, dataset_display_name="profiles")
    linker = Linker(sdf, owner_settings(), log_level=30)
    linker.training.estimate_probability_two_random_records_match(
        [block_on("owner_phone", "owner_last"), block_on("owner_email")], recall=0.8)
    linker.training.estimate_u_using_random_sampling(max_pairs=2e6, seed=7)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("owner_phone"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("owner_last", "market"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("owner_email"))
    preds = linker.inference.predict(threshold_match_probability=0.05)
    return linker, preds


def household_clusters(linker, preds, threshold):
    c = linker.clustering.cluster_pairwise_predictions_at_threshold(preds, threshold_match_probability=threshold)
    return c.as_pandas_dataframe()[["unique_id", "cluster_id"]].rename(columns={"cluster_id": "household_id"})


def _jw(a: str, b: str) -> float:
    return duckdb.sql(f"select jaro_winkler_similarity('{a}', '{b}')").fetchone()[0]


def _v(x):
    """Missing-value normalizer: pandas may hold None, NaN, or pd.NA depending on dtype."""
    return None if x is None or (not isinstance(x, (list, tuple)) and pd.isna(x)) else x


def pet_match(a, b) -> bool:
    """Stage 2: within a household, do two pet records describe the same pet?

    Names must agree (exact, prefix such as MAX/MAXWELL, or Jaro-Winkler >= 0.88); species,
    breed group, and birth year must not contradict each other when both sides are present.
    """
    na, nb = _v(a.pet_name), _v(b.pet_name)
    if na is None or nb is None:
        return False
    if not (na == nb or na.startswith(nb) or nb.startswith(na) or _jw_cached(na, nb) >= 0.88):
        return False
    sa, sb = _v(a.species), _v(b.species)
    if sa and sb and sa != sb:
        return False
    ga, gb = _v(a.breed_group), _v(b.breed_group)
    if ga and gb and ga != gb and "Mixed" not in (ga, gb):
        return False
    ya, yb = _v(a.birth_year), _v(b.birth_year)
    if ya is not None and yb is not None and abs(int(ya) - int(yb)) > 2:
        return False
    return True


_JW: dict = {}


def _jw_cached(a, b):
    k = (a, b) if a < b else (b, a)
    if k not in _JW:
        _JW[k] = _jw(a.replace("'", ""), b.replace("'", ""))
    return _JW[k]


def pet_clusters(df: pd.DataFrame, hh: pd.DataFrame) -> pd.DataFrame:
    d = df.merge(hh, on="unique_id")
    out = []
    for hid, g in d.groupby("household_id"):
        rows = list(g.itertuples())
        parent = list(range(len(rows)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, j in combinations(range(len(rows)), 2):
            if pet_match(rows[i], rows[j]):
                parent[find(j)] = find(i)
        for i, r in enumerate(rows):
            out.append((r.unique_id, hid, f"{hid}-{find(i)}"))
    return pd.DataFrame(out, columns=["unique_id", "household_id", "cluster_id"])


def deterministic_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """Union-find on (phone, pet_name) exact matches."""
    parent = {u: u for u in df.unique_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    keyed = df.dropna(subset=["owner_phone", "pet_name"])
    for _, g in keyed.groupby(["owner_phone", "pet_name"]):
        ids = g.unique_id.tolist()
        for a in ids[1:]:
            ra, rb = find(ids[0]), find(a)
            if ra != rb:
                parent[rb] = ra
    return pd.DataFrame({"unique_id": list(parent), "cluster_id": [find(u) for u in parent]})


# ----------------------------------------------------------------------------- evaluation
def truth_map(con) -> pd.DataFrame | None:
    if not (TRUTH / "record_map.parquet").exists():
        return None
    rm = pd.read_parquet(TRUTH / "record_map.parquet")
    rm["unique_id"] = rm.source_system + ":" + rm.source_record_key
    # vet_gamma has no patient id; derive truth for derived keys from visit-level truth
    gv = pd.read_parquet(TRUTH / "vet_gamma_visit_map.parquet")
    gkeys = con.sql("select source_event_id, source_pet_key from staging.stg_vet_gamma__visits").df()
    gkeys["visit_no"] = gkeys.source_event_id.astype(int)
    g = gkeys.merge(gv, on="visit_no")
    g = g.groupby("source_pet_key").pet_uid.agg(lambda s: s.mode().iat[0]).reset_index()
    g["unique_id"] = "vet_gamma:" + g.source_pet_key
    return pd.concat([rm[["unique_id", "pet_uid"]], g[["unique_id", "pet_uid"]]], ignore_index=True)


def pair_set(df, key):
    pairs = set()
    for _, ids in df.groupby(key).unique_id:
        ids = sorted(ids)
        if len(ids) > 1:
            pairs.update(combinations(ids, 2))
    return pairs


def evaluate(clusters: pd.DataFrame, truth: pd.DataFrame) -> dict:
    t = truth[truth.unique_id.isin(clusters.unique_id)]
    c = clusters[clusters.unique_id.isin(t.unique_id)]
    tp_pairs, pred_pairs = pair_set(t, "pet_uid"), pair_set(c, "cluster_id")
    tp = len(tp_pairs & pred_pairs)
    prec = tp / len(pred_pairs) if pred_pairs else 0.0
    rec = tp / len(tp_pairs) if tp_pairs else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"records": len(c), "true_clusters": int(t.pet_uid.nunique()), "predicted_clusters": int(c.cluster_id.nunique()),
            "true_pairs": len(tp_pairs), "predicted_pairs": len(pred_pairs), "precision": round(prec, 4),
            "recall": round(rec, 4), "f1": round(f1, 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--threshold", type=float, default=0.9)
    a = ap.parse_args()

    con = duckdb.connect(str(a.db))
    df = load_profiles(con)
    print(f"profiles: {len(df):,}")
    linker, preds = run_household_linkage(df, a.threshold)
    hh = household_clusters(linker, preds, a.threshold)
    clusters = pet_clusters(df, hh)
    clusters["pet_id"] = "PET-" + clusters.groupby("cluster_id").ngroup().astype(str).str.zfill(6)
    clusters["household_id"] = "HH-" + clusters.groupby("household_id").ngroup().astype(str).str.zfill(6)
    con.execute("create schema if not exists qa")
    con.register("clusters_df", clusters[["unique_id", "household_id", "pet_id"]])
    con.execute("create or replace table intermediate.int_pet_clusters as select * from clusters_df")
    print(f"households: {clusters.household_id.nunique():,}  pets: {clusters.pet_id.nunique():,}")

    Path("reports").mkdir(exist_ok=True)
    linker.visualisations.match_weights_chart().save("reports/er_match_weights.html")

    truth = truth_map(con)
    if truth is not None:
        hh_truth = truth.merge(pd.read_parquet(TRUTH / "pets.parquet")[["pet_uid", "household_uid"]], on="pet_uid")
        res = {
            "pet_level": {
                "two_stage_splink": evaluate(clusters[["unique_id", "pet_id"]].rename(columns={"pet_id": "cluster_id"}), truth),
                "deterministic_phone_petname": evaluate(deterministic_baseline(df), truth),
            },
            "household_level": {
                "splink_owner_model": evaluate(hh.rename(columns={"household_id": "cluster_id"}),
                                               hh_truth.drop(columns="pet_uid").rename(columns={"household_uid": "pet_uid"})),
            },
        }
        sweep = []
        for th in [0.5, 0.8, 0.9, 0.95, 0.99]:
            h = household_clusters(linker, preds, th)
            c = pet_clusters(df, h)
            sweep.append({"threshold": th, **evaluate(c[["unique_id", "cluster_id"]], truth)})
        res["pet_level_threshold_sweep"] = sweep
        Path("reports/er_metrics.json").write_text(json.dumps(res, indent=2))
        rows = [{"level": lvl, "method": k, **v} for lvl in ("pet_level", "household_level") for k, v in res[lvl].items()]
        con.register("m", pd.DataFrame(rows))
        con.execute("create or replace table qa.er_metrics as select * from m")
        print(json.dumps({k: v for k, v in res.items()}, indent=2))
    con.close()


if __name__ == "__main__":
    main()
