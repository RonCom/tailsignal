"""Simulation check for Model A: planted signals must be recovered; null cells must stay quiet."""
import json

import numpy as np
import pandas as pd
import pytest

from tailsignal.models import pharmacovigilance as pv

BREEDS = {"mdr1_high": "Collie - Rough", "mdr1_low": "Shepherd Dog - German",
          "other_purebred": "Retriever - Labrador", "mixed_unknown": "Crossbred Canine/dog"}


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    rng = np.random.default_rng(11)
    n_rep, n_drug, n_evt = 30000, 40, 60
    drugs = ["ivermectin", "alphazol"] + [f"drug{i}" for i in range(n_drug - 2)]
    events = ["Convulsion", "Vomiting"] + [f"Event{j}" for j in range(n_evt - 2)]
    pd_ = 1 / np.arange(1, n_drug + 1) ** 0.8
    pe = 0.25 / np.arange(1, n_evt + 1) ** 0.7
    strata = rng.choice(list(BREEDS), n_rep, p=[0.05, 0.06, 0.59, 0.30])
    years = rng.integers(2010, 2020, n_rep)
    rep, drg, rxn = [], [], []
    for i in range(n_rep):
        rid = f"R{i}"
        ds = set(rng.choice(drugs, size=rng.integers(1, 3), p=pd_ / pd_.sum()))
        mult = np.ones(n_evt)
        if "alphazol" in ds:
            mult[1] *= 4.0  # overall signal: alphazol x Vomiting
        if "ivermectin" in ds and strata[i] == "mdr1_high":
            mult[0] *= 10.0  # breed-specific signal: ivermectin x Convulsion in MDR1 breeds only
        ev = [events[j] for j in np.flatnonzero(rng.random(n_evt) < np.clip(pe * mult, 0, 0.95))]
        if not ev:
            ev = [events[rng.integers(2, n_evt)]]
        rep.append(dict(report_id=rid, receive_date=f"{years[i]}0615", species="Dog", type_of_information="Safety Issue",
                        breed_component=json.dumps([BREEDS[strata[i]]])))
        drg += [dict(report_id=rid, ingredient=d.capitalize()) for d in ds]
        rxn += [dict(report_id=rid, veddra_term_name=e) for e in ev]
    d = tmp_path_factory.mktemp("openfda")
    pd.DataFrame(rep).to_parquet(d / "reports.parquet")
    pd.DataFrame(drg).to_parquet(d / "drugs.parquet")
    pd.DataFrame(rxn).to_parquet(d / "reactions.parquet")
    con = pv.load(d, "Dog")
    return pv.score(con)


def test_overall_signal_recovered(sim):
    a = sim["all"].set_index(["drug", "event"])
    assert a.loc[("alphazol", "Vomiting"), "sig_mgps"]
    assert a.loc[("alphazol", "Vomiting"), "eb05"] > 2


def test_breed_specific_signal_recovered(sim):
    s = sim["strata"].set_index(["drug", "event", "stratum"])
    assert s.loc[("ivermectin", "Convulsion", "mdr1_high"), "sig_excess_hier"]
    assert s.loc[("ivermectin", "Convulsion", "mdr1_high"), "h_p_departs"] > 0.5
    assert not s.loc[("ivermectin", "Convulsion", "other_purebred"), "sig_excess_hier"]


def test_null_cells_quiet(sim):
    s = sim["strata"]
    planted = (s.drug == "ivermectin") & (s.event == "Convulsion")
    planted |= (s.drug == "alphazol") & (s.event == "Vomiting")
    other = s[~planted & ~s.drug.str.startswith("class:") & (s.event != pv.NEURO)]
    assert other.sig_excess_hier.mean() < 0.01
    a = sim["all"]
    a = a[~((a.drug == "alphazol") & (a.event == "Vomiting")) & ~a.drug.str.startswith("class:") & (a.event != pv.NEURO)]
    assert a.sig_mgps.mean() < 0.01
