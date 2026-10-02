"""Export a sample of a data-product release for the static demo of the customer portal.

The live portal (served by the API at /app) reads the full release through the API. The demo on a static website
reads this file instead and mimics the API's entitlements and metering in the browser.

    uv run python scripts/export_portal_sample.py --release 1 --out portal_sample.json
"""
import argparse
import json
from pathlib import Path

from tailsignal.products.release import open_store

MIN_REPORTS = 100  # drug-signal pairs with at least this many reports (the full product has 53,656 pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=int, default=None)
    ap.add_argument("--out", type=Path, default=Path("reports/portal/portal_sample.json"))
    a = ap.parse_args()
    s = open_store("auto")
    rel = s.releases()
    v = a.release or rel[-1]["version"]
    meta = next(r for r in rel if r["version"] == v)
    t = {name: s.read(name, v) for name in meta["rows"]}
    t["drug_signals"] = t["drug_signals"][t["drug_signals"].n >= MIN_REPORTS]
    if "service_benchmark" in t:
        t["service_benchmark"]["month"] = t["service_benchmark"]["month"].astype(str).str[:10]
    out = {"release": v, "released_at": meta["released_at"], "full_rows": meta["rows"],
           "sample_note": f"Drug signals limited to pairs with at least {MIN_REPORTS} reports",
           "tables": {k: json.loads(df.to_json(orient="records")) for k, df in t.items()}}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, separators=(",", ":")))
    print(a.out, round(a.out.stat().st_size / 1e6, 2), "MB", {k: len(v) for k, v in out["tables"].items()})


if __name__ == "__main__":
    main()
