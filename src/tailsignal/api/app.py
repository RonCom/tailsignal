"""TailSignal scoring and data API (FastAPI), serving the latest or a pinned data-product release.

    uv run uvicorn tailsignal.api.app:app --reload
    curl -H "X-API-Key: demo-insurer" "http://127.0.0.1:8000/v1/health-index?species=dog&breed_group=Toy"

Keys and entitlements: config/api_keys.json (demo keys only). Every call is metered to data/api_usage.jsonl.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from tailsignal.products.release import open_store

KEYS_FILE = Path(os.environ.get("TAILSIGNAL_KEYS", "config/api_keys.json"))
USAGE_LOG = Path(os.environ.get("TAILSIGNAL_USAGE", "data/api_usage.jsonl"))
ENTITLEMENTS = {
    "admin": {"health_index", "drug_signals", "antibiogram", "scorecard_any", "benchmarks"},
    "insurer": {"health_index"},
    "pharma": {"drug_signals", "health_index"},
    "public_health": {"antibiogram", "drug_signals"},
    "clinic": {"antibiogram", "scorecard_own"},
}

app = FastAPI(title="TailSignal API", version="1.0",
              description="De-identified pet health data products: health index, drug-safety signals, "
                          "regional antibiograms, clinic scorecards.")
_store = None


def store():
    global _store
    if _store is None:
        _store = open_store(os.environ.get("TAILSIGNAL_STORE", "auto"))
    return _store


def keys() -> dict:
    return json.loads(KEYS_FILE.read_text())


def client(x_api_key: str | None = Header(default=None)) -> dict:
    k = keys().get(x_api_key or "")
    if not k:
        raise HTTPException(401, "Unknown or missing API key. Send it in the X-API-Key header.")
    return {**k, "key": x_api_key}


def need(c: dict, product: str):
    if product not in ENTITLEMENTS.get(c["role"], set()):
        raise HTTPException(403, f"Your plan does not include {product.replace('_', ' ')}.")


def meter(request: Request, c: dict, rows: int, version: int):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a") as f:
        f.write(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "key": c["key"],
                            "role": c["role"], "endpoint": request.url.path, "rows": rows, "release": version}) + "\n")


def table(name: str, version: int | None) -> tuple[pd.DataFrame, int]:
    s = store()
    rel = s.releases()
    if not rel:
        raise HTTPException(503, "No release published yet. Run tailsignal.products.release.")
    v = version or rel[-1]["version"]
    if v not in {r["version"] for r in rel}:
        raise HTTPException(404, f"Release v{v} does not exist.")
    try:
        return s.read(name, v), v
    except Exception:
        raise HTTPException(404, f"Product {name} is not in release v{v}.")


def records(df: pd.DataFrame, limit: int) -> list[dict]:
    return json.loads(df.head(limit).to_json(orient="records"))


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


PRODUCTS = {"health_index": "Pet Health Index", "drug_signals": "Drug-safety signals", "antibiogram": "Regional antibiogram",
            "scorecard_own": "Your clinic scorecard", "scorecard_any": "Clinic scorecards", "benchmarks": "Service benchmarks"}
STATIC = Path(__file__).parent / "static"


@app.get("/app", include_in_schema=False)
def customer_portal():
    """Customer portal front end; it calls this API with the customer's key."""
    return FileResponse(STATIC / "portal.html")


@app.get("/v1/me")
def me(c: dict = Depends(client)):
    """Who this key belongs to and which products its plan includes."""
    ent = sorted(ENTITLEMENTS.get(c["role"], set()))
    return {"name": c.get("name"), "role": c["role"], "clinic": c.get("clinic"), "entitlements": ent,
            "products": [PRODUCTS[e] for e in ent]}


@app.get("/v1/service-benchmarks")
def service_benchmarks(request: Request, market: str | None = None, channel: str | None = None,
                       location_id: str | None = None, release: int | None = None,
                       limit: int = Query(2000, le=5000), c: dict = Depends(client)):
    need(c, "benchmarks")
    df, v = table("service_benchmark", release)
    for col, val in [("market", market), ("channel", channel), ("location_id", location_id)]:
        if val:
            df = df[df[col] == val]
    meter(request, c, len(df), v)
    return {"release": v, "rows": len(df), "data": records(df, limit)}


@app.get("/v1/releases")
def releases(c: dict = Depends(client)):
    return [{k: r[k] for k in ("version", "released_at", "store", "rows")} for r in store().releases()]


@app.get("/v1/health-index")
def health_index(request: Request, species: str | None = None, breed_group: str | None = None,
                 market: str | None = None, year: int | None = None, condition: str | None = None,
                 composite: bool = False, release: int | None = None, limit: int = Query(500, le=5000),
                 c: dict = Depends(client)):
    need(c, "health_index")
    df, v = table("health_index_composite" if composite else "health_index_conditions", release)
    for col, val in [("species", species), ("breed_group", breed_group), ("market", market), ("year", year),
                     ("condition", condition)]:
        if val is not None and col in df:
            df = df[df[col] == val]
    meter(request, c, len(df), v)
    return {"release": v, "rows": len(df), "data": records(df, limit)}


@app.get("/v1/drug-signals")
def drug_signals(request: Request, drug: str | None = None, event: str | None = None, breed_stratum: str | None = None,
                 min_eb05: float = 2.0, release: int | None = None, limit: int = Query(200, le=5000),
                 c: dict = Depends(client)):
    need(c, "drug_signals")
    df, v = table("drug_signals_breed" if breed_stratum else "drug_signals", release)
    if breed_stratum:
        df = df[df.stratum == breed_stratum]
    if drug:
        df = df[df.drug.str.contains(drug, case=False, regex=False)]
    if event:
        df = df[df.event.str.contains(event, case=False, regex=False)]
    df = df[df.eb05 >= min_eb05]
    meter(request, c, len(df), v)
    return {"release": v, "rows": len(df), "data": records(df, limit)}


@app.get("/v1/antibiogram")
def antibiogram(request: Request, region: str | None = None, organism: str | None = None, source: str | None = None,
                release: int | None = None, c: dict = Depends(client)):
    need(c, "antibiogram")
    df, v = table("antibiogram", release)
    for col, val in [("region", region), ("organism", organism), ("source", source)]:
        if val:
            df = df[df[col] == val]
    meter(request, c, len(df), v)
    return {"release": v, "rows": len(df), "data": records(df, 5000)}


def scorecard_for(clinic: str, c: dict, release: int | None):
    if c["role"] == "clinic":
        if c.get("clinic") != clinic:
            raise HTTPException(403, "A clinic key can only read its own scorecard.")
    else:
        need(c, "scorecard_any")
    df, v = table("clinic_scorecard", release)
    row = df[df.clinic == clinic]
    if row.empty:
        raise HTTPException(404, f"No scorecard for {clinic}.")
    num = df.select_dtypes("number")
    bench = num.median().round(2).to_dict()
    return records(row, 1)[0], bench, v


@app.get("/v1/clinics/{clinic}/scorecard")
def scorecard(request: Request, clinic: str, release: int | None = None, c: dict = Depends(client)):
    row, bench, v = scorecard_for(clinic, c, release)
    meter(request, c, 1, v)
    return {"release": v, "clinic": row, "network_median": bench}


@app.get("/portal/{clinic}", response_class=HTMLResponse)
def portal(request: Request, clinic: str, c: dict = Depends(client)):
    row, bench, v = scorecard_for(clinic, c, None)
    meter(request, c, 1, v)
    items = [("Anesthetic procedures", "procedures", "{:,.0f}", None),
             ("Complications, observed ÷ expected", "complication_oe_shrunk", "{:.2f}", "lower is better"),
             ("Deaths (observed)", "deaths", "{:.0f}", f"expected {row.get('deaths_expected', '')}"),
             ("Dental disease recorded, observed ÷ expected", "dental_detection_oe", "{:.2f}", "below 1 may mean under-charting"),
             ("Cultures before treating urinary infections", "culture_before_uti_tx", "{:.0%}", "higher is better"),
             ("Critically important antibiotic as first choice", "critically_important_first", "{:.0%}", "lower is better"),
             ("Stewardship rank (of 9)", "stewardship_rank", "{:.0f}", "1 = best")]
    trs = "".join(
        f"<tr><td>{html.escape(lbl)}</td><td class=n>{fmt.format(row[k])}</td>"
        f"<td class=n>{fmt.format(bench[k]) if k in bench else ''}</td><td class=m>{html.escape(note or '')}</td></tr>"
        for lbl, k, fmt, note in items if k in row)
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>{html.escape(clinic)} · TailSignal partner portal</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f4f6f3;color:#1b2a2f}}
main{{max-width:820px;margin:auto;padding:24px 16px}}h1{{font:600 26px Georgia,serif}}
table{{width:100%;border-collapse:collapse;background:#fdfdfb}}td,th{{padding:10px;border-bottom:1px solid #d9dfda;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}}.m{{color:#56676c;font-size:13px}}</style></head>
<body><main><p class=m>TailSignal partner portal · release v{v}</p><h1>{html.escape(clinic)} quality scorecard</h1>
<table><tr><th>Measure</th><th class=n>Your clinic</th><th class=n>Network median</th><th></th></tr>{trs}</table>
<p class=m>Risk-adjusted for case mix recorded in your records. Review outliers with clinical leads before acting.</p>
</main></body></html>"""
