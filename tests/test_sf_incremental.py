"""Offline checks for the Snowflake incremental load and owner masking (no Snowflake connection needed)."""
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from tailsignal import sf

WAREHOUSE = Path("data/warehouse.duckdb")


def test_daycare_increment_splits_by_day(tmp_path):
    csv = tmp_path / "visits.csv"
    pd.DataFrame({
        "visit_id": ["DV1", "DV2", "DV3", "DV4"],
        "pawstay_pet_id": ["P1", "P1", "P2", "P2"],
        "site_id": ["S"] * 4,
        "visit_date": ["2025-12-01", "2025-12-29", "2025-12-30", "2025-12-31"],
        "service": ["Full Day"] * 4,
        "price": ["38.0"] * 4,
        "staff_note": ["", "x", "", ""],
    }).to_csv(csv, index=False)
    cutoff, daily = sf.daycare_increment(csv, days=3)
    assert cutoff == "2025-12-29"
    assert [d for d, _ in daily] == ["2025-12-29", "2025-12-30", "2025-12-31"]
    assert list(daily[0][1].columns) == ["VISIT_ID", "PAWSTAY_PET_ID", "SITE_ID", "VISIT_DATE", "SERVICE", "PRICE",
                                         "STAFF_NOTE"]
    assert sum(len(g) for _, g in daily) == 3


def test_task_sql_wiring():
    load = sf.load_task_sql("FWA_WH")
    assert "copy into RAW.PAWSTAY_DAYCARE_VISITS" in load and "/incoming/" in load and "schedule" in load
    child = sf.append_task_sql("FWA_WH")
    assert f"after {sf.LOAD_TASK}" in child
    assert f"system$stream_has_data('{sf.STREAM}')" in child
    assert f"from {sf.STREAM} s" in child and "not exists" in child
    assert child.count(",") >= len(sf.FCT_COLS) - 1


@pytest.mark.parametrize("col,value,masked", [
    ("OWNER_FIRST", "***", True), ("OWNER_FIRST", "MARIA", False),
    ("OWNER_EMAIL", "***@example.com", True), ("OWNER_EMAIL", "maria@example.com", False),
    ("OWNER_PHONE", "***-***-1234", True), ("OWNER_PHONE", "6125551234", False),
    ("OWNER_ZIP", "551**", True), ("OWNER_ZIP", "55104", False),
    ("OWNER_LAST", None, True),
])
def test_is_masked(col, value, masked):
    assert sf.is_masked(col, value) is masked


@pytest.mark.skipif(not WAREHOUSE.exists(), reason="needs the local build (python -m tailsignal.pipeline)")
def test_append_sql_reproduces_dbt_daycare_rows():
    """The task's SELECT, run on DuckDB over the last 30 days, gives exactly dbt's fct_service_event rows."""
    cutoff, daily = sf.daycare_increment(sf.DAYCARE_CSV, days=30)
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    new = pd.concat([g for _, g in daily], ignore_index=True)
    con.register("increment", new)
    con.execute("create temp table empty_fact as select * from core.fct_service_event limit 0")
    got = con.execute(sf.append_select_sql("increment", "intermediate.int_pet_clusters",
                                           "reference.service_taxonomy", "empty_fact")).df()
    got.columns = sf.FCT_COLS
    want = con.execute("select * from core.fct_service_event where channel = 'daycare' and event_date >= ?",
                       [cutoff]).df()
    con.close()
    n_both, only_got, only_want, diffs = sf._compare(got, want, ["event_id"])
    assert len(got) == len(want) > 0
    assert (only_got, only_want, diffs) == (0, 0, {})
