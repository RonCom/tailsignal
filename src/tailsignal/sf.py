"""Snowflake target: load raw partner files, build the dbt project, reconcile against DuckDB.

Flow:  data/raw/synthetic/*  --parquet / JSON-->  @RAW.TS_STAGE  --COPY INTO-->  RAW.*
       dbt seed + staging + intermediate (Snowflake)
       intermediate.int_pet_clusters (Splink output in DuckDB)  --write_pandas-->  INTERMEDIATE.INT_PET_CLUSTERS
       dbt marts + tests (Snowflake)
       reconcile: every model's row count, then row-by-row comparison of the core and product tables

    uv sync --extra snowflake
    uv run python -m tailsignal.sf check       # connection and grants
    uv run python -m tailsignal.sf all         # load + build + reconcile

One-time setup: snowflake/setup.sql (run as ACCOUNTADMIN). Settings: config/snowflake.yaml, with the account in
config/snowflake.local.yaml (git-ignored) or SNOWFLAKE_ACCOUNT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

RAW_DIR = Path("data/raw/synthetic")
DUCK = Path("data/warehouse.duckdb")
OUT = Path("reports/snowflake")
EXPORT = Path("data/snowflake_export")
DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt", "--target", "snowflake"]

# file -> RAW table (CSV and pipe files load as all-varchar, like the DuckDB staging models read them)
DELIMITED = {
    "vet_alpha_visits.csv": ("VET_ALPHA_VISITS", ","),
    "vet_gamma_visits.txt": ("VET_GAMMA_VISITS", "|"),
    "groomly_appointments.csv": ("GROOMLY_APPOINTMENTS", ","),
    "pawstay_pets.csv": ("PAWSTAY_PETS", ","),
    "pawstay_daycare_visits.csv": ("PAWSTAY_DAYCARE_VISITS", ","),
    "pawstay_boarding_stays.csv": ("PAWSTAY_BOARDING_STAYS", ","),
    "wellplan_memberships.csv": ("WELLPLAN_MEMBERSHIPS", ","),
    "wellplan_campaign.csv": ("WELLPLAN_CAMPAIGN", ","),
    "locations.csv": ("LOCATIONS", ","),
}
JSONL = {"vet_beta_encounters.jsonl": "VET_BETA_ENCOUNTERS"}

# tables compared row by row: (schema.table, key columns)
COMPARE = {
    "intermediate.int_breed_map": ["breed_raw"],
    "intermediate.int_source_pet_profiles": ["unique_id"],
    "intermediate.int_vet_visits": ["source_system", "source_event_id"],
    "core.dim_pet": ["pet_id"],
    "core.fct_service_event": ["event_id"],
    "core.fct_wellness_membership": ["membership_id"],
    "product.product_pet_cohort": ["pet_token"],
    "product.product_condition_prevalence": ["year", "species", "breed_group", "market", "condition"],
    "product.product_service_benchmark": ["month", "market", "channel", "location_id"],
    "qa.qa_privacy_release": ["generalization"],
}
COUNT_ONLY = ["staging.stg_vet_alpha__visits", "staging.stg_vet_beta__encounters", "staging.stg_vet_gamma__visits",
              "staging.stg_groomly__appointments", "staging.stg_pawstay__pets", "staging.stg_pawstay__daycare_visits",
              "staging.stg_pawstay__boarding_stays", "staging.stg_wellplan__memberships",
              "staging.stg_wellplan__campaign", "staging.stg_locations", "core.dim_location",
              "intermediate.int_pet_clusters"]


# ----------------------------------------------------------------------------- settings and connection
def settings() -> dict:
    s: dict = {}
    for f in (Path("config/snowflake.yaml"), Path("config/snowflake.local.yaml")):
        if f.exists():
            s.update(yaml.safe_load(f.read_text()) or {})
    for k in ("account", "user", "role", "warehouse", "database"):
        s[k] = os.environ.get(f"SNOWFLAKE_{k.upper()}") or s.get(k)
    s["private_key_path"] = str(Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
                                     or s.get("private_key_path", "~/.snowflake/fwa_rsa_key.p8")).expanduser())
    if not s.get("account"):
        sys.exit("Snowflake account not set: put `account: <org-account>` in config/snowflake.local.yaml "
                 "or set SNOWFLAKE_ACCOUNT")
    if not Path(s["private_key_path"]).exists():
        sys.exit(f"private key not found at {s['private_key_path']} (set private_key_path or SNOWFLAKE_PRIVATE_KEY_PATH)")
    return s


def connect(schema: str = "RAW"):
    import snowflake.connector
    s = settings()
    return snowflake.connector.connect(account=s["account"], user=s["user"], role=s["role"],
                                       warehouse=s["warehouse"], database=s["database"], schema=schema,
                                       authenticator="SNOWFLAKE_JWT", private_key_file=s["private_key_path"])


def dbt(*args: str) -> None:
    from dbt.cli.main import dbtRunner
    s = settings()
    for k in ("account", "user", "role", "warehouse", "database", "private_key_path"):
        os.environ[f"SNOWFLAKE_{k.upper()}"] = str(s[k])
    res = dbtRunner().invoke([*args, *DBT_ARGS])
    if not res.success:
        sys.exit(f"dbt {' '.join(args)} failed on Snowflake: {res.exception or 'see the dbt log above'}")


# ----------------------------------------------------------------------------- steps
def check() -> None:
    con = connect()
    cur = con.cursor()
    row = cur.execute("select current_account(), current_user(), current_role(), current_warehouse(), "
                      "current_database(), current_version()").fetchone()
    print("connected:", dict(zip(["account", "user", "role", "warehouse", "database", "version"], row)))
    schemas = [r[1] for r in cur.execute("show schemas in database").fetchall()]
    print("schemas:", ", ".join(sorted(schemas)))
    con.close()


def load() -> None:
    """Raw files -> parquet (upper-case all-varchar columns) and JSON -> stage -> RAW tables."""
    EXPORT.mkdir(parents=True, exist_ok=True)
    dk = duckdb.connect()
    for f, (table, delim) in DELIMITED.items():
        src = (RAW_DIR / f).as_posix()
        cols = [r[0] for r in dk.execute(
            f"describe select * from read_csv('{src}', header = true, delim = '{delim}', all_varchar = true)").fetchall()]
        sel = ", ".join(f'"{c}" as "{c.upper()}"' for c in cols)
        dk.execute(f"copy (select {sel} from read_csv('{src}', header = true, delim = '{delim}', all_varchar = true)) "
                   f"to '{(EXPORT / (table.lower() + '.parquet')).as_posix()}' (format parquet)")
    dk.close()

    con = connect("RAW")
    cur = con.cursor()
    cur.execute("create file format if not exists RAW.TS_PARQUET type = parquet")
    cur.execute("create file format if not exists RAW.TS_JSON type = json")
    cur.execute("create stage if not exists RAW.TS_STAGE")
    for table, _ in DELIMITED.values():
        path = (EXPORT / (table.lower() + ".parquet")).resolve().as_posix()
        cur.execute(f"remove @RAW.TS_STAGE/{table}/")
        cur.execute(f"put 'file://{path}' @RAW.TS_STAGE/{table}/ auto_compress = false overwrite = true")
        cur.execute(f"""create or replace table RAW.{table} using template (
                          select array_agg(object_construct(*)) from table(infer_schema(
                            location => '@RAW.TS_STAGE/{table}/', file_format => 'RAW.TS_PARQUET')))""")
        cur.execute(f"copy into RAW.{table} from @RAW.TS_STAGE/{table}/ file_format = (format_name = 'RAW.TS_PARQUET') "
                    "match_by_column_name = case_insensitive")
        print(f"RAW.{table}: {cur.execute(f'select count(*) from RAW.{table}').fetchone()[0]:,} rows")
    for f, table in JSONL.items():
        path = (RAW_DIR / f).resolve().as_posix()
        cur.execute(f"remove @RAW.TS_STAGE/{table}/")
        cur.execute(f"put 'file://{path}' @RAW.TS_STAGE/{table}/ auto_compress = true overwrite = true")
        cur.execute(f"create or replace table RAW.{table} (V variant)")
        cur.execute(f"copy into RAW.{table} from @RAW.TS_STAGE/{table}/ file_format = (format_name = 'RAW.TS_JSON')")
        print(f"RAW.{table}: {cur.execute(f'select count(*) from RAW.{table}').fetchone()[0]:,} rows")
    con.close()


def push_clusters() -> None:
    """Entity resolution runs in Python (Splink on DuckDB); Snowflake gets its output table."""
    from snowflake.connector.pandas_tools import write_pandas
    dk = duckdb.connect(str(DUCK), read_only=True)
    df = dk.execute("select * from intermediate.int_pet_clusters").df()
    dk.close()
    df.columns = [c.upper() for c in df.columns]
    con = connect("INTERMEDIATE")
    ok, _, n, _ = write_pandas(con, df, "INT_PET_CLUSTERS", schema="INTERMEDIATE", auto_create_table=True,
                               overwrite=True, quote_identifiers=False)
    con.close()
    print(f"INTERMEDIATE.INT_PET_CLUSTERS: {n:,} rows ({'ok' if ok else 'FAILED'})")


def build() -> None:
    dbt("seed")
    dbt("build", "--select", "staging", "intermediate", "--exclude", "source:er")
    push_clusters()
    dbt("build", "--exclude", "staging", "intermediate")


def _fetch_sf(con, table: str) -> pd.DataFrame:
    df = con.cursor().execute(f"select * from {table}").fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def _norm(s: pd.Series) -> pd.Series:
    """Comparable form: numbers as float, arrays as sorted comma lists, everything else as text."""
    def one(v):
        if isinstance(v, (list, tuple, np.ndarray)):
            return ",".join(sorted(str(x) for x in v))
        if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, str) and v.startswith("[") and v.endswith("]"):      # Snowflake ARRAY arrives as JSON text
            try:
                return ",".join(sorted(str(x) for x in json.loads(v)))
            except ValueError:
                return v
        if isinstance(v, (pd.Timestamp,)) or hasattr(v, "isoformat"):
            return str(pd.Timestamp(v).date()) if pd.Timestamp(v).time() == pd.Timestamp(0).time() else str(pd.Timestamp(v))
        return v
    out = s.map(one)
    num = pd.to_numeric(out, errors="coerce")
    if out.notna().sum() and num.notna().sum() == out.notna().sum():
        return num.astype(float)
    return out.astype("string")


def reconcile() -> bool:
    OUT.mkdir(parents=True, exist_ok=True)
    dk = duckdb.connect(str(DUCK), read_only=True)
    con = connect("CORE")
    lines = ["# Reconciliation: Snowflake vs DuckDB", "", "## Row counts", "", "| Model | DuckDB | Snowflake | Match |",
             "|---|---|---|---|"]
    summary: dict = {"counts": {}, "columns": {}}
    ok = True
    for t in COUNT_ONLY + list(COMPARE):
        d = dk.execute(f"select count(*) from {t}").fetchone()[0]
        s = con.cursor().execute(f"select count(*) from {t}").fetchone()[0]
        summary["counts"][t] = {"duckdb": d, "snowflake": s}
        ok &= d == s
        lines.append(f"| {t} | {d:,} | {s:,} | {'yes' if d == s else '**no**'} |")
    lines += ["", "## Row-by-row comparison", "",
              "Rows are matched on the key; each cell counts rows whose value differs.", ""]
    for t, keys in COMPARE.items():
        d = dk.execute(f"select * from {t}").df()
        s = _fetch_sf(con, t)
        for k in keys:
            d[k], s[k] = _norm(d[k]).astype("string"), _norm(s[k]).astype("string")
        m = d.merge(s, on=keys, how="outer", suffixes=("_d", "_s"), indicator=True)
        only_d, only_s = int((m["_merge"] == "left_only").sum()), int((m["_merge"] == "right_only").sum())
        both = m["_merge"] == "both"
        diffs = {}
        for c in d.columns:
            if c in keys or f"{c}_s" not in m:
                continue
            a, b = _norm(m[f"{c}_d"]), _norm(m[f"{c}_s"])
            if a.dtype == float and b.dtype == float:
                same = np.isclose(a, b, rtol=1e-9, atol=1e-6) | (a.isna() & b.isna())
            else:
                same = (a.astype("string") == b.astype("string")).fillna(False) | (a.isna() & b.isna())
            n = int((~same & both).sum())
            if n:
                diffs[c] = n
        summary["columns"][t] = {"only_duckdb": only_d, "only_snowflake": only_s, "differing": diffs}
        ok &= only_d == 0 and only_s == 0 and not diffs
        detail = ", ".join(f"{c} {n:,}" for c, n in diffs.items()) or "none"
        lines.append(f"- **{t}**: {int(both.sum()):,} matched rows; only in DuckDB {only_d:,}; only in Snowflake "
                     f"{only_s:,}; differing columns: {detail}")
    dk.close()
    con.close()
    summary["match"] = bool(ok)
    lines += ["", f"**Result: {'MATCH' if ok else 'DIFFERENCES FOUND'}**", ""]
    (OUT / "reconciliation.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n".join(lines))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="TailSignal on Snowflake")
    ap.add_argument("step", choices=["check", "load", "build", "push-clusters", "reconcile", "all"])
    a = ap.parse_args()
    if a.step == "check":
        check()
    elif a.step == "load":
        load()
    elif a.step == "build":
        build()
    elif a.step == "push-clusters":
        push_clusters()
    elif a.step == "reconcile":
        reconcile()
    else:
        check()
        load()
        build()
        reconcile()


if __name__ == "__main__":
    main()
