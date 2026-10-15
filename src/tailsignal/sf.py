"""Snowflake target: load raw partner files, build the dbt project, reconcile against DuckDB.

Flow:  data/raw/synthetic/*  --parquet / JSON-->  @RAW.TS_STAGE  --COPY INTO-->  RAW.*
       dbt seed + staging + intermediate (Snowflake)
       intermediate.int_pet_clusters (Splink output in DuckDB)  --write_pandas-->  INTERMEDIATE.INT_PET_CLUSTERS
       dbt marts + tests (Snowflake)
       incremental: the last N days of daycare visits arrive as daily files and flow through a task graph
                    (COPY INTO -> append-only stream -> insert into CORE.FCT_SERVICE_EVENT)
       reconcile: every model's row count, then row-by-row comparison of the core and product tables
       masking-check: owner fields masked for TAILSIGNAL_ANALYST, clear for TAILSIGNAL_ROLE, RAW not readable

    uv sync --extra snowflake
    uv run python -m tailsignal.sf check          # connection and grants
    uv run python -m tailsignal.sf all            # load + build + incremental + reconcile + masking-check
    uv run python -m tailsignal.sf incremental --days 30
    uv run python -m tailsignal.sf masking-check

One-time setup: snowflake/setup.sql (run as ACCOUNTADMIN). Settings: config/snowflake.yaml, with the account in
config/snowflake.local.yaml (git-ignored) or SNOWFLAKE_ACCOUNT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
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
# differences that are understood and do not change any output a buyer or analysis uses
KNOWN = {
    ("intermediate.int_breed_map", "score"): "Snowflake's Jaro-Winkler returns whole percentages; the mapped breed is identical",
    ("product.product_service_benchmark", "revenue_per_active_pet"): "half-cent rounding of floating-point values differs by engine",
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
    cur.execute(f"alter task if exists {LOAD_TASK} suspend")   # tables are replaced below; `incremental` re-arms
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


def _compare(d: pd.DataFrame, s: pd.DataFrame, keys: list[str]) -> tuple[int, int, int, dict]:
    """Match rows on the key; return (matched rows, only in d, only in s, {column: rows that differ})."""
    d, s = d.copy(), s.copy()
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
    return int(both.sum()), only_d, only_s, diffs


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
        n_both, only_d, only_s, diffs = _compare(d, s, keys)
        summary["columns"][t] = {"only_duckdb": only_d, "only_snowflake": only_s, "differing": diffs}
        unexplained = {c: n for c, n in diffs.items() if (t, c) not in KNOWN}
        ok &= only_d == 0 and only_s == 0 and not unexplained
        detail = ", ".join(f"{c} {n:,}" + (" (known: " + KNOWN[(t, c)] + ")" if (t, c) in KNOWN else "")
                           for c, n in diffs.items()) or "none"
        lines.append(f"- **{t}**: {n_both:,} matched rows; only in DuckDB {only_d:,}; only in Snowflake "
                     f"{only_s:,}; differing columns: {detail}")
    dk.close()
    con.close()
    summary["match"] = bool(ok)
    lines += ["", f"**Result: {'MATCH' if ok else 'DIFFERENCES FOUND'}**", ""]
    (OUT / "reconciliation.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n".join(lines))
    return ok


# ----------------------------------------------------------------------------- incremental daycare load
# Daycare visits are the largest partner feed (~720K rows). In production new visits arrive as daily files;
# the task graph below loads only files it hasn't seen and appends only rows it hasn't seen:
#   TS_LOAD_DAYCARE (root):  COPY INTO RAW.PAWSTAY_DAYCARE_VISITS from @RAW.TS_STAGE/.../incoming/
#                            (Snowflake's load metadata skips files already loaded)
#   PAWSTAY_DAYCARE_VISITS_STREAM: append-only stream on that table
#   TS_APPEND_DAYCARE_EVENTS (child, runs only when the stream has rows): the same typing, taxonomy and
#                            pet-cluster joins as stg_pawstay__daycare_visits + fct_service_event, inserted
#                            into CORE.FCT_SERVICE_EVENT; reading the stream in the insert advances its offset.
# `incremental` replays the last N days through that graph and checks the result row by row against DuckDB.
DAYCARE_CSV = RAW_DIR / "pawstay_daycare_visits.csv"
DAYCARE_TABLE = "PAWSTAY_DAYCARE_VISITS"
STREAM = f"RAW.{DAYCARE_TABLE}_STREAM"
LOAD_TASK = "RAW.TS_LOAD_DAYCARE"
APPEND_TASK = "RAW.TS_APPEND_DAYCARE_EVENTS"
INCOMING = f"@RAW.TS_STAGE/{DAYCARE_TABLE}/incoming/"
FCT_COLS = ["event_id", "pet_id", "channel", "source_system", "location_id", "event_date", "service_code",
            "condition", "amount", "nights", "staff_note"]


def daycare_increment(csv: Path, days: int) -> tuple[str, list[tuple[str, pd.DataFrame]]]:
    """The last `days` calendar days of daycare visits, one frame per day, read the way `load` reads the file
    (all varchar, upper-case column names) so replayed rows are identical to the full load."""
    dk = duckdb.connect()
    src = f"read_csv('{csv.as_posix()}', header = true, all_varchar = true)"
    cols = [r[0] for r in dk.execute(f"describe select * from {src}").fetchall()]
    sel = ", ".join(f'"{c}" as "{c.upper()}"' for c in cols)
    cutoff = dk.execute(f"select strftime(max(visit_date::date) - (? - 1)::integer, '%Y-%m-%d') from {src}",
                        [days]).fetchone()[0]
    df = dk.execute(f"select {sel} from {src} where visit_date >= ? order by visit_date, visit_id", [cutoff]).df()
    dk.close()
    return cutoff, [(day, g.reset_index(drop=True)) for day, g in df.groupby("VISIT_DATE", sort=True)]


def load_task_sql(warehouse: str) -> str:
    return (f"create or replace task {LOAD_TASK} warehouse = {warehouse} schedule = '60 MINUTE' as "
            f"copy into RAW.{DAYCARE_TABLE} from {INCOMING} file_format = (format_name = 'RAW.TS_PARQUET') "
            "match_by_column_name = case_insensitive")


def append_select_sql(stream: str = STREAM, clusters: str = "INTERMEDIATE.INT_PET_CLUSTERS",
                      taxonomy: str = "REFERENCE.SERVICE_TAXONOMY", fact: str = "CORE.FCT_SERVICE_EVENT") -> str:
    """New daycare rows as fact rows. Mirrors stg_pawstay__daycare_visits and the daycare branch of
    fct_service_event (tests/test_sf_incremental.py holds it to the DuckDB build); rows already in the fact
    table are skipped, so a replayed file can't duplicate events."""
    return f"""select 'daycare:' || s.visit_id, c.pet_id, 'daycare', 'pawstay', s.site_id, cast(s.visit_date as date),
       t.service_code, cast(null as varchar), cast(s.price as double), cast(null as integer),
       nullif(trim(s.staff_note), '')
from {stream} s
join {clusters} c on c.unique_id = 'pawstay:' || s.pawstay_pet_id
left join {taxonomy} t on t.source_service = s.service and t.channel = 'daycare'
where not exists (select 1 from {fact} f where f.event_id = 'daycare:' || s.visit_id)"""


def append_task_sql(warehouse: str) -> str:
    """Child task: runs only when the stream has rows; the insert consumes them and advances the stream."""
    return (f"create or replace task {APPEND_TASK} warehouse = {warehouse} after {LOAD_TASK}\n"
            f"when system$stream_has_data('{STREAM}') as\n"
            f"insert into CORE.FCT_SERVICE_EVENT ({', '.join(FCT_COLS)})\n{append_select_sql()}")


def _wait_for_graph(cur, since_ms: int, timeout: int = 900) -> dict:
    """Poll TASK_HISTORY until both tasks of the run started after `since_ms` (epoch ms) reach a final state."""
    final = {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED", "FAILED_AND_AUTO_SUSPENDED"}
    names = {t.split(".")[-1] for t in (LOAD_TASK, APPEND_TASK)}
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = cur.execute(
            "select name, state, error_message from table(information_schema.task_history("
            "scheduled_time_range_start => to_timestamp_ltz(%s, 3), result_limit => 100)) "
            "where schema_name = 'RAW' order by scheduled_time", (since_ms,)).fetchall()
        state = {n: (st, err) for n, st, err in rows if n in names}
        root = state.get(LOAD_TASK.split(".")[-1])
        if root and root[0] in final - {"SUCCEEDED"}:
            return state                                    # the child never runs after a failed root
        if all(n in state and state[n][0] in final for n in names):
            return state
        time.sleep(5)
    sys.exit(f"task graph did not finish within {timeout} s; check TASK_HISTORY")


def _run_graph(cur) -> dict:
    since_ms = cur.execute("select date_part(epoch_millisecond, current_timestamp())").fetchone()[0]
    cur.execute(f"execute task {LOAD_TASK}")
    return _wait_for_graph(cur, int(since_ms))


def incremental(days: int = 30, schedule: bool = False) -> bool:
    """Replay the last `days` days of daycare visits through the stream + task graph and check the result."""
    OUT.mkdir(parents=True, exist_ok=True)
    s = settings()
    cutoff, daily = daycare_increment(DAYCARE_CSV, days)
    n_new = sum(len(g) for _, g in daily)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    print(f"increment: {len(daily)} daily files from {cutoff}, {n_new:,} visits (run {run_id})")

    con = connect("RAW")
    cur = con.cursor()
    # 1. state as of the cutoff: remove the increment from RAW and from the fact table
    cur.execute(f"alter task if exists {LOAD_TASK} suspend")
    raw_removed = cur.execute(f"delete from RAW.{DAYCARE_TABLE} where visit_date >= %s", (cutoff,)).fetchone()[0]
    fct_removed = cur.execute("delete from CORE.FCT_SERVICE_EVENT where channel = 'daycare' and event_date >= %s",
                              (cutoff,)).fetchone()[0]
    # 2. stream created after the delete, so it starts empty and sees only what the task graph loads
    cur.execute(f"create or replace stream {STREAM} on table RAW.{DAYCARE_TABLE} append_only = true")
    cur.execute(load_task_sql(s["warehouse"]))
    cur.execute(append_task_sql(s["warehouse"]))
    cur.execute(f"alter task {APPEND_TASK} resume")          # EXECUTE TASK skips suspended children
    # 3. the day files land in a new folder per run (a re-PUT under an old name would be skipped as loaded)
    folder = EXPORT / "incremental" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    for day, g in daily:
        f = folder / f"{day}.parquet"
        g.to_parquet(f, index=False)
        cur.execute(f"put 'file://{f.resolve().as_posix()}' {INCOMING}{run_id}/ auto_compress = false")
    # 4. run the graph, then run it again with no new files: the load copies nothing and the append skips
    first = _run_graph(cur)
    loaded = cur.execute(f"select count(*) from RAW.{DAYCARE_TABLE} where visit_date >= %s", (cutoff,)).fetchone()[0]
    stream_left = cur.execute(f"select system$stream_has_data('{STREAM}')").fetchone()[0]
    second = _run_graph(cur)
    if schedule:
        cur.execute(f"alter task {LOAD_TASK} resume")

    # 5. the appended fact rows against DuckDB's dbt build, row by row
    dk = duckdb.connect(str(DUCK), read_only=True)
    d = dk.execute("select * from core.fct_service_event where channel = 'daycare' and event_date >= ?",
                   [cutoff]).df()
    total_d = dk.execute("select count(*) from core.fct_service_event").fetchone()[0]
    dk.close()
    sf = _fetch_sf(con, f"(select * from CORE.FCT_SERVICE_EVENT where channel = 'daycare' "
                        f"and event_date >= '{cutoff}')")
    total_s = cur.execute("select count(*) from CORE.FCT_SERVICE_EVENT").fetchone()[0]
    con.close()
    n_both, only_d, only_s, diffs = _compare(d, sf, ["event_id"])

    fmt = lambda st: ", ".join(f"{n} {v[0]}" + (f" ({v[1]})" if v[1] else "") for n, v in st.items())
    ok = (first.get("TS_APPEND_DAYCARE_EVENTS", ("",))[0] == "SUCCEEDED"
          and second.get("TS_APPEND_DAYCARE_EVENTS", ("",))[0] == "SKIPPED"
          and loaded == n_new and not stream_left
          and only_d == 0 and only_s == 0 and not diffs and total_d == total_s)
    lines = ["# Incremental load: stream and task graph", "",
             f"Run `{run_id}`: the last {days} days of daycare visits (from {cutoff}) removed from "
             f"RAW.{DAYCARE_TABLE} ({raw_removed:,} rows) and CORE.FCT_SERVICE_EVENT ({fct_removed:,} rows), "
             f"then replayed as {len(daily)} daily Parquet files through the task graph.", "",
             "| Check | Result |", "|---|---|",
             f"| First run | {fmt(first)} |",
             f"| Visits loaded by COPY INTO | {loaded:,} of {n_new:,} |",
             f"| Stream left with data | {'yes' if stream_left else 'no'} |",
             f"| Second run, no new files | {fmt(second)} |",
             f"| Appended fact rows matched to DuckDB | {n_both:,}; only in DuckDB {only_d:,}; "
             f"only in Snowflake {only_s:,}; differing columns: {diffs or 'none'} |",
             f"| CORE.FCT_SERVICE_EVENT rows | DuckDB {total_d:,}, Snowflake {total_s:,} |",
             f"| Root task schedule | {'resumed (every 60 minutes)' if schedule else 'suspended; run with EXECUTE TASK'} |",
             "", f"**Result: {'MATCH' if ok else 'CHECK FAILED'}**", ""]
    (OUT / "incremental.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return ok


# ----------------------------------------------------------------------------- owner masking check
OWNER_COLS = ("OWNER_FIRST", "OWNER_LAST", "OWNER_NAME", "OWNER_EMAIL", "OWNER_PHONE", "OWNER_ZIP")
ANALYST = "TAILSIGNAL_ANALYST"


def is_masked(column: str, value) -> bool:
    """Whether a value is in the masked form the GOVERNANCE policies return."""
    if value is None:
        return True
    v = str(value)
    c = column.upper()
    if c == "OWNER_EMAIL":
        return v.startswith("***@") or v == "***"
    if c == "OWNER_PHONE":
        return v.startswith("***-***-")
    if c == "OWNER_ZIP":
        return v.endswith("**") and len(v) == 5
    return v == "***"


def masking_check() -> bool:
    """Every owner column in staging, intermediate, core and product carries a policy; the analyst role sees
    only masked values; the pipeline role sees clear values; the analyst role can't read RAW."""
    OUT.mkdir(parents=True, exist_ok=True)
    s = settings()
    con = connect("INTERMEDIATE")
    cur = con.cursor()
    cols = cur.execute(
        "select c.table_schema, c.table_name, c.column_name, t.table_type from information_schema.columns c "
        "join information_schema.tables t using (table_catalog, table_schema, table_name) "
        "where c.table_schema in ('STAGING', 'INTERMEDIATE', 'CORE', 'PRODUCT') "
        f"and c.column_name in ({', '.join(repr(c) for c in OWNER_COLS)}) order by 1, 2, 3").fetchall()
    rels: dict[tuple, list[str]] = {}
    for sch, tbl, col, ttype in cols:
        rels.setdefault((sch, tbl, "view" if ttype == "VIEW" else "table"), []).append(col)

    ok = True
    result: dict[tuple, dict] = {}
    clear_rows: dict[tuple, pd.DataFrame] = {}
    for key, owner in rels.items():
        sch, tbl, kind = key
        fq = f"{s['database']}.{sch}.{tbl}"
        refs = cur.execute(f"select ref_column_name from table(information_schema.policy_references("
                           f"ref_entity_name => '{fq}', ref_entity_domain => '{kind}')) "
                           "where policy_kind = 'MASKING_POLICY'").fetchall()
        result[key] = {"covered": len({r[0] for r in refs} & set(owner)), "n": len(owner)}
        clear_rows[key] = cur.execute(f"select {', '.join(owner)} from {fq} limit 500").fetch_pandas_all()
        result[key]["clear"] = any(not is_masked(c, v) for c in owner for v in clear_rows[key][c] if v is not None)

    cur.execute(f"use role {ANALYST}")
    cur.execute("use secondary roles none")              # the policies look at the primary role only
    for key, owner in rels.items():
        sch, tbl, _ = key
        masked = cur.execute(f"select {', '.join(owner)} from {s['database']}.{sch}.{tbl} limit 500").fetch_pandas_all()
        result[key]["masked"] = all(is_masked(c, v) for c in owner for v in masked[c])
        r = result[key]
        ok &= r["covered"] == r["n"] and r["clear"] and r["masked"]

    yn = lambda b: "yes" if b else "**no**"
    lines = ["# Owner-field masking", "", f"{sum(len(v) for v in rels.values())} owner columns in {len(rels)} "
             "relations; dim_pet and the other core and product tables hold none.", "",
             "| Relation | Columns with a policy | TAILSIGNAL_ROLE sees clear values | "
             f"{ANALYST} sees only masked values |", "|---|---|---|---|"]
    lines += [f"| {sch}.{tbl} | {r['covered']} of {r['n']} | {yn(r['clear'])} | {yn(r['masked'])} |"
              for (sch, tbl, _), r in result.items()]
    try:
        cur.execute(f"select count(*) from {s['database']}.RAW.PAWSTAY_PETS").fetchone()
        raw_blocked = False
    except Exception:
        raw_blocked = True
    ok &= raw_blocked
    sample = cur.execute(f"select owner_first, owner_last, owner_email, owner_phone, owner_zip from "
                         f"{s['database']}.INTERMEDIATE.INT_SOURCE_PET_PROFILES where owner_email is not null "
                         "and owner_zip is not null limit 3").fetchall()
    con.close()
    lines += ["", f"{ANALYST} reading RAW.PAWSTAY_PETS: {'refused' if raw_blocked else '**allowed**'}", "",
              f"What {ANALYST} sees in INTERMEDIATE.INT_SOURCE_PET_PROFILES:", "",
              "| owner_first | owner_last | owner_email | owner_phone | owner_zip |", "|---|---|---|---|---|"]
    lines += [f"| {' | '.join(str(v) for v in r)} |" for r in sample]
    lines += ["", f"**Result: {'PASS' if ok else 'FAILED'}**", ""]
    (OUT / "masking.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="TailSignal on Snowflake")
    ap.add_argument("step", choices=["check", "load", "build", "push-clusters", "incremental", "reconcile",
                                     "masking-check", "all"])
    ap.add_argument("--days", type=int, default=30, help="incremental: days of daycare visits to replay")
    ap.add_argument("--schedule", action="store_true",
                    help="incremental: leave the root task resumed so it runs every 60 minutes")
    a = ap.parse_args()
    if a.step == "check":
        check()
    elif a.step == "load":
        load()
    elif a.step == "build":
        build()
    elif a.step == "push-clusters":
        push_clusters()
    elif a.step == "incremental":
        sys.exit(0 if incremental(a.days, a.schedule) else 1)
    elif a.step == "reconcile":
        reconcile()
    elif a.step == "masking-check":
        sys.exit(0 if masking_check() else 1)
    else:
        check()
        load()
        build()
        ok = incremental(a.days, a.schedule)
        ok &= reconcile()
        ok &= masking_check()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
