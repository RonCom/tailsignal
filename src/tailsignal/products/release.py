"""Versioned data-product releases: DuckLake catalog when available, versioned Parquet otherwise.

    uv run python -m tailsignal.products.release                 # build products and publish a release
    uv run python -m tailsignal.products.release --list          # release history
    uv run python -m tailsignal.products.release --store parquet # force the Parquet fallback

Spec: docs/productization_spec.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd

from tailsignal.products import health_index as HI

WAREHOUSE = Path("data/warehouse.duckdb")
LAKE_DIR = Path("data/lake")
PARQUET_DIR = Path("data/releases")
REPORTS = Path("reports")


# ----------------------------------------------------------------------------- product builders
def build_products() -> tuple[dict[str, pd.DataFrame], dict]:
    prods, notes = {}, {}
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    prev = con.sql("select * from product.product_condition_prevalence").df()
    ci = HI.condition_index(prev)
    prods["health_index_conditions"] = ci
    prods["health_index_composite"] = HI.composite(ci)
    notes["health_index_checks"] = HI.checks(prev, ci)
    prods["service_benchmark"] = con.sql("select * from product.product_service_benchmark order by all").df()
    con.close()

    sig = REPORTS / "model_a" / "dog" / "signals_all.csv"
    strata = REPORTS / "model_a" / "dog" / "signals_strata.csv"
    if sig.exists():
        prods["drug_signals"] = duckdb.sql(f"""
            select drug, event, n, round(E, 3) as expected, round(ebgm, 2) as ebgm, round(eb05, 2) as eb05,
                   round(prr, 2) as prr from '{sig}' where sig_mgps and n >= 3 order by eb05 desc, drug, event""").df()
    else:
        notes["drug_signals"] = "skipped: run tailsignal.models.pharmacovigilance first"
    if strata.exists():
        prods["drug_signals_breed"] = duckdb.sql(f"""
            select drug, event, stratum, n, round(h_ebgm, 2) as ebgm, round(h_eb05, 2) as eb05,
                   round(h_ratio05, 2) as ratio_to_all_dogs_lo, round(h_ratio_mean, 2) as ratio_to_all_dogs
            from '{strata}' where sig_excess_hier order by ratio_to_all_dogs_lo desc, drug, event""").df()
    abg, elig = REPORTS / "amr" / "antibiogram.csv", REPORTS / "amr" / "eligibility.csv"
    try:
        from tailsignal.models.amr import load as amr_load
        a = amr_load()
        a = a[a.year >= 2022]
        e = pd.read_csv(elig)
        ok = set(map(tuple, e[e.eligible][["organism", "source", "drug"]].values))
        a = a[[(o, s, d) in ok for o, s, d in zip(a.organism, a.source, a.drug)]]
        g = a.groupby(["region", "organism", "source", "drug"]).R.agg(n="size", resistant="sum").reset_index()
        g = g[g.n >= 30]
        g["pct_susceptible"] = (1 - g.resistant / g.n).round(3)
        prods["antibiogram"] = g.drop(columns="resistant").sort_values(["region", "organism", "source", "drug"]) \
            .reset_index(drop=True)
    except Exception as ex:  # NARMS not downloaded
        notes["antibiogram"] = f"skipped: {ex.__class__.__name__}: run ingest --source narms and models.amr first"
    sc = REPORTS / "clinic_benchmarks" / "1x" / "scorecard.csv"
    if sc.exists():
        prods["clinic_scorecard"] = pd.read_csv(sc)
    else:
        notes["clinic_scorecard"] = "skipped: run tailsignal.models.clinic_benchmarks first"
    return prods, notes


def table_hash(df: pd.DataFrame) -> str:
    d = df.copy()
    for c in d.columns:
        if d[c].dtype == object:
            d[c] = d[c].map(lambda v: json.dumps(list(v)) if hasattr(v, "__len__") and not isinstance(v, str) else v)
    d = d.sort_values(list(d.columns)).reset_index(drop=True)
    return hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()


def row_keys(df: pd.DataFrame) -> set[str]:
    return set(pd.util.hash_pandas_object(df.astype(str), index=False).astype(str))


# ----------------------------------------------------------------------------- stores
class ParquetStore:
    kind = "parquet"

    def __init__(self, root: Path = PARQUET_DIR):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def releases(self) -> list[dict]:
        out = []
        for m in sorted(self.root.glob("v*/manifest.json"), key=lambda p: int(p.parent.name[1:])):
            out.append(json.loads(m.read_text()))
        return out

    def read(self, name: str, version: int | None = None) -> pd.DataFrame:
        v = version or self.releases()[-1]["version"]
        return pd.read_parquet(self.root / f"v{v}" / f"{name}.parquet")

    def publish(self, prods: dict[str, pd.DataFrame], manifest: dict) -> dict:
        v = manifest["version"]
        d = self.root / f"v{v}"
        d.mkdir(parents=True, exist_ok=True)
        for n, df in prods.items():
            df.to_parquet(d / f"{n}.parquet", index=False)
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest


class LakeStore:
    """DuckLake catalog: one snapshot per release; release_log records version -> snapshot."""
    kind = "ducklake"

    def __init__(self, root: Path = LAKE_DIR):
        root.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect()
        self.con.sql("INSTALL ducklake")
        self.con.sql("LOAD ducklake")
        self.con.sql(f"ATTACH 'ducklake:{(root / 'tailsignal.ducklake').as_posix()}' AS lake "
                     f"(DATA_PATH '{(root / 'files').as_posix()}/')")
        self.con.sql("""CREATE TABLE IF NOT EXISTS lake.release_log (version INTEGER, released_at VARCHAR,
                        manifest VARCHAR)""")

    def releases(self) -> list[dict]:
        rows = self.con.sql("select manifest from lake.release_log order by version").fetchall()
        return [json.loads(r[0]) for r in rows]

    def _snapshot(self, version: int) -> int:
        for m in self.releases():
            if m["version"] == version:
                return m["snapshot_id"]
        raise KeyError(f"no release v{version}")

    def read(self, name: str, version: int | None = None) -> pd.DataFrame:
        if version is None:
            return self.con.sql(f"select * from lake.{name}").df()
        return self.con.sql(f"select * from lake.{name} AT (VERSION => {self._snapshot(version)})").df()

    def publish(self, prods: dict[str, pd.DataFrame], manifest: dict) -> dict:
        self.con.sql("BEGIN TRANSACTION")
        for n, df in prods.items():
            self.con.register("_df", df)
            self.con.sql(f"CREATE OR REPLACE TABLE lake.{n} AS SELECT * FROM _df")
            self.con.unregister("_df")
        self.con.execute("INSERT INTO lake.release_log VALUES (?, ?, ?)",
                         [manifest["version"], manifest["released_at"], json.dumps(manifest)])
        self.con.sql("COMMIT")
        snap = self.con.sql("select max(snapshot_id) from lake.snapshots()").fetchone()[0]
        manifest["snapshot_id"] = int(snap)
        self.con.execute("UPDATE lake.release_log SET manifest = ? WHERE version = ?",
                         [json.dumps(manifest), manifest["version"]])
        # the UPDATE is a later snapshot; reads by version use the data snapshot recorded above
        return manifest


def open_store(kind: str = "auto"):
    if kind in ("auto", "ducklake"):
        try:
            return LakeStore()
        except Exception as ex:
            if kind == "ducklake":
                raise
            print(f"DuckLake unavailable ({ex.__class__.__name__}); using versioned Parquet")
    return ParquetStore()


# ----------------------------------------------------------------------------- release
def release(store, prods, notes) -> dict:
    hist = store.releases()
    hashes = {n: table_hash(df) for n, df in prods.items()}
    if hist and hist[-1]["hashes"] == hashes:
        return {"status": "unchanged", "version": hist[-1]["version"], "store": store.kind}
    version = (hist[-1]["version"] + 1) if hist else 1
    diff = {}
    if hist:
        for n, df in prods.items():
            try:
                old = store.read(n, hist[-1]["version"])
                ko, kn = row_keys(old), row_keys(df)
                diff[n] = {"added": len(kn - ko), "removed": len(ko - kn)}
            except Exception:
                diff[n] = {"added": len(df), "removed": 0, "note": "new product"}
    manifest = {"version": version, "released_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "store": store.kind, "rows": {n: int(len(df)) for n, df in prods.items()}, "hashes": hashes,
                "diff_vs_previous": diff, "notes": notes}
    return store.publish(prods, manifest)


def verify(store, version: int) -> bool:
    m = next(r for r in store.releases() if r["version"] == version)
    return all(table_hash(store.read(n, version)) == h for n, h in m["hashes"].items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", choices=["auto", "ducklake", "parquet"], default="auto")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    store = open_store(a.store)
    if a.list:
        for r in store.releases():
            print(r["version"], r["released_at"], r["store"], r["rows"])
        return
    prods, notes = build_products()
    m = release(store, prods, notes)
    print(json.dumps({k: v for k, v in m.items() if k != "hashes"}, indent=1, default=str))
    if m.get("status") != "unchanged":
        print("read-back matches recorded hashes:", verify(store, m["version"]))


if __name__ == "__main__":
    main()
