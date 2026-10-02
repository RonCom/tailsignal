"""Run the TailSignal build end to end.

    python -m tailsignal.pipeline                 # generate data if missing, then build
    python -m tailsignal.pipeline --regenerate    # force new synthetic data
    python -m tailsignal.pipeline --skip-er       # rebuild marts on existing clusters

Steps: synthetic data -> dbt seed -> dbt staging + intermediate -> entity resolution (Python)
-> dbt marts + all tests.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dbt.cli.main import dbtRunner

from tailsignal.er import link
from tailsignal.synth.generate import Config, generate

DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]


def dbt(*args: str) -> None:
    res = dbtRunner().invoke([*args, *DBT_ARGS])
    if not res.success:
        sys.exit(f"dbt {' '.join(args)} failed")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--households", type=int, default=9000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-er", action="store_true")
    a = ap.parse_args()

    if a.regenerate or not Path("data/raw/synthetic/vet_alpha_visits.csv").exists():
        print("== generating synthetic multi-channel data")
        print(generate(Config(seed=a.seed, n_households=a.households)))
    print("== dbt seed")
    dbt("seed")
    print("== dbt staging + intermediate")
    dbt("build", "--select", "staging", "intermediate", "--exclude", "source:er")
    if not a.skip_er:
        print("== entity resolution")
        sys.argv = ["link"]
        link.main()
    print("== dbt marts + tests")
    dbt("build", "--exclude", "staging", "intermediate")
    print("done: data/warehouse.duckdb, reports/er_metrics.json")


if __name__ == "__main__":
    main()
