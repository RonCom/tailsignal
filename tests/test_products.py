import json

import pandas as pd
import pytest


@pytest.fixture()
def parquet_store(tmp_path):
    from tailsignal.products.release import ParquetStore
    return ParquetStore(tmp_path / "releases")


def test_release_versions_time_travel_and_unchanged(parquet_store):
    from tailsignal.products.release import release, verify
    p1 = {"t": pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})}
    m1 = release(parquet_store, p1, {})
    assert m1["version"] == 1 and verify(parquet_store, 1)
    assert release(parquet_store, p1, {})["status"] == "unchanged"
    p2 = {"t": pd.DataFrame({"a": [1, 3], "b": ["x", "z"]})}
    m2 = release(parquet_store, p2, {})
    assert m2["version"] == 2 and m2["diff_vs_previous"]["t"] == {"added": 1, "removed": 1}
    assert parquet_store.read("t", 1).a.tolist() == [1, 2]      # time travel
    assert parquet_store.read("t").a.tolist() == [1, 3]


def test_health_index_reference_is_100():
    from tailsignal.products.health_index import condition_index
    prev = pd.DataFrame({"year": 2024, "species": "dog", "breed_group": ["A", "B", "C"], "market": "PHL",
                         "condition": "otitis_externa", "pets_seen": [100, 200, 300],
                         "pets_with_condition": [10, 20, 30], "prevalence": [0.1, 0.1, 0.1], "suppressed": False})
    ci = condition_index(prev)
    assert (ci["index"].round(0) == 100).all()


@pytest.fixture()
def api(tmp_path, monkeypatch, parquet_store):
    from tailsignal.products.release import release
    release(parquet_store, {
        "clinic_scorecard": pd.DataFrame({"clinic": ["PHL-VET1", "AUS-VET2"], "procedures": [700, 560],
                                          "complication_oe_shrunk": [1.0, 1.04], "stewardship_rank": [3, 5]}),
        "antibiogram": pd.DataFrame({"region": ["South"], "organism": ["E. coli"], "source": ["UTI"],
                                     "drug": ["Ampicillin"], "n": [100], "pct_susceptible": [0.99]})}, {})
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({"k-clinic": {"role": "clinic", "clinic": "PHL-VET1"}, "k-ins": {"role": "insurer"}}))
    import tailsignal.api.app as A
    monkeypatch.setattr(A, "KEYS_FILE", keys)
    monkeypatch.setattr(A, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(A, "_store", parquet_store)
    from fastapi.testclient import TestClient
    return TestClient(A.app), tmp_path / "usage.jsonl"


def test_api_entitlements_and_metering(api):
    c, usage = api
    assert c.get("/v1/antibiogram").status_code == 401
    assert c.get("/v1/clinics/PHL-VET1/scorecard", headers={"X-API-Key": "k-clinic"}).status_code == 200
    assert c.get("/v1/clinics/AUS-VET2/scorecard", headers={"X-API-Key": "k-clinic"}).status_code == 403
    assert c.get("/v1/antibiogram", headers={"X-API-Key": "k-ins"}).status_code == 403
    r = c.get("/portal/PHL-VET1", headers={"X-API-Key": "k-clinic"})
    assert r.status_code == 200 and "PHL-VET1" in r.text
    lines = usage.read_text().strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["endpoint"] == "/v1/clinics/PHL-VET1/scorecard"


def test_root_redirects_to_docs(api):
    c, _ = api
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"


def test_me_and_customer_portal(api):
    c, _ = api
    r = c.get("/v1/me", headers={"X-API-Key": "k-clinic"})
    assert r.status_code == 200 and r.json()["clinic"] == "PHL-VET1"
    assert set(r.json()["entitlements"]) == {"antibiogram", "scorecard_own"}
    assert c.get("/v1/service-benchmarks", headers={"X-API-Key": "k-ins"}).status_code == 403
    r = c.get("/app")
    assert r.status_code == 200 and "TailSignal" in r.text
