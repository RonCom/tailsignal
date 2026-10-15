# Incremental load: stream and task graph

Run `20261015T140433-bed1e0`: the last 30 days of daycare visits (from 2025-12-02) removed from RAW.PAWSTAY_DAYCARE_VISITS (10,685 rows) and CORE.FCT_SERVICE_EVENT (10,685 rows), then replayed as 22 daily Parquet files through the task graph.

| Check | Result |
|---|---|
| First run | TS_LOAD_DAYCARE SUCCEEDED, TS_APPEND_DAYCARE_EVENTS SUCCEEDED |
| Visits loaded by COPY INTO | 10,685 of 10,685 |
| Stream left with data | no |
| Second run, no new files | TS_LOAD_DAYCARE SUCCEEDED, TS_APPEND_DAYCARE_EVENTS SKIPPED (Conditional expression for task evaluated to false.) |
| Appended fact rows matched to DuckDB | 10,685; only in DuckDB 0; only in Snowflake 0; differing columns: none |
| CORE.FCT_SERVICE_EVENT rows | DuckDB 865,797, Snowflake 865,797 |
| Root task schedule | suspended; run with EXECUTE TASK |

**Result: MATCH**
