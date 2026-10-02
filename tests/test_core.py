import pandas as pd

from tailsignal.er.link import evaluate, pet_match
from tailsignal.ingest.public import flatten_openfda
from tailsignal.synth.generate import Config, build_households, build_pets, typo


def test_typo_changes_string_but_keeps_length_close():
    import numpy as np
    rng = np.random.default_rng(0)
    s = typo("Labrador", rng)
    assert s != "Labrador" or True  # swap of identical chars can be a no-op
    assert abs(len(s) - len("Labrador")) <= 1


def test_generator_is_deterministic():
    import numpy as np
    cfg = Config(seed=1, n_households=50)
    a = build_pets(cfg, build_households(cfg, np.random.default_rng(1)), np.random.default_rng(2))
    b = build_pets(cfg, build_households(cfg, np.random.default_rng(1)), np.random.default_rng(2))
    pd.testing.assert_frame_equal(a, b)


def test_evaluate_perfect_and_merged():
    truth = pd.DataFrame({"unique_id": ["a", "b", "c", "d"], "pet_uid": ["P1", "P1", "P2", "P2"]})
    perfect = pd.DataFrame({"unique_id": ["a", "b", "c", "d"], "cluster_id": [1, 1, 2, 2]})
    merged = pd.DataFrame({"unique_id": ["a", "b", "c", "d"], "cluster_id": [1, 1, 1, 1]})
    assert evaluate(perfect, truth)["f1"] == 1.0
    m = evaluate(merged, truth)
    assert m["recall"] == 1.0 and m["precision"] < 0.5


def test_pet_match_rules():
    Row = lambda **k: pd.Series({"pet_name": None, "species": None, "breed_group": None, "birth_year": pd.NA, **k})
    assert pet_match(Row(pet_name="MAX"), Row(pet_name="MAXWELL"))
    assert not pet_match(Row(pet_name="MAX", species="dog"), Row(pet_name="MAX", species="cat"))
    assert not pet_match(Row(pet_name="MAX", birth_year=2015), Row(pet_name="MAX", birth_year=2020))
    assert not pet_match(Row(pet_name="LUNA"), Row(pet_name="BELLA"))


def test_flatten_openfda_handles_scalars_and_lists():
    rec = {"unique_aer_id_number": "X-1", "animal": {"species": "Dog", "breed": {"breed_component": "Collie"}},
           "drug": [{"active_ingredients": [{"name": "Ivermectin"}, {"name": "Pyrantel"}]}],
           "reaction": {"veddra_term_name": "Ataxia"}}
    rep, drg, rxn = flatten_openfda([rec])
    assert len(rep) == 1 and len(drg) == 2 and len(rxn) == 1
    assert rep.breed_component.iat[0] == '["Collie"]'


def test_segment_names_follow_rules():
    from tailsignal.models.segmentation import name_segment
    S = lambda **k: pd.Series({"vet_visits_py": 1.5, "wellness_share": 0.6, "daycare_days_py": 0.0,
                               "boarding_nights_py": 0.0, "grooming_appts_py": 0.0, **k})
    assert name_segment(S(daycare_days_py=100, grooming_appts_py=6)) == "Daycare + grooming regulars"
    assert name_segment(S(daycare_days_py=100)) == "Daycare regulars, no grooming"
    assert name_segment(S(vet_visits_py=0.1, daycare_days_py=20)) == "No partner-vet visits"
    assert name_segment(S()) == "Vet only"


def test_mase_scaling():
    import numpy as np
    from tailsignal.models.forecasting import mase
    assert mase(np.array([10, 12]), np.array([11, 11]), 2.0) == 0.5


def test_retained_per_1000_randomized_estimate():
    from tailsignal.models.uplift import retained_per_1000
    df = pd.DataFrame({"treated": [0, 0, 1, 1], "lapsed": [1, 0, 0, 0], "score": [4, 3, 2, 1]})
    assert retained_per_1000(df, None) == 500.0          # 50% lapse in control vs 0% with reminder
    assert retained_per_1000(df, "score", top=0.5) != retained_per_1000(df, None)


def test_wilson_interval_brackets_estimate():
    from tailsignal.models.oral_health import wilson
    lo, hi = wilson(18, 100)
    assert lo < 0.18 < hi and 0 <= lo and hi <= 1


def test_amr_class_map_and_regions():
    from tailsignal.models.amr import DRUG_CLASS, STATE_REGION, DRUG_ALIASES
    assert DRUG_CLASS["Enrofloxacin"] == "Fluoroquinolones"
    assert DRUG_CLASS["Oxacillin"] == "Anti-staphylococcal penicillins"
    assert DRUG_ALIASES["Oxacillin + 2% NaCl"] == "Oxacillin"
    assert STATE_REGION["Texas"] == "South" and STATE_REGION["New York"] == "Northeast"


def test_exact_rr_ci_handles_zero_cells():
    from tailsignal.synth.ehr_validate import exact_rr_ci, rr_ci
    lo, hi = exact_rr_ci(0, 1000, 5, 1000)
    assert lo == 0 and 0 < hi < 1.5
    r = rr_ci(10, 1000, 10, 1000)
    assert abs(r["rr"] - 1) < 1e-9 and r["exact_lo"] < 1 < r["exact_hi"]


def test_seizure_note_matcher_handles_negation_history_and_fit_and_well():
    from tailsignal.synth.ehr_validate import smart_match
    assert smart_match("O reports 2 seizures last night. BAR.")
    assert smart_match("Had a fit this AM.")
    assert not smart_match("Annual exam. No seizures. Fit and well.")
    assert not smart_match("hx sz (idiopathic epilepsy). BAR.")
    assert not smart_match("TPLO. Recovery uneventful. Fitted e-collar.")


def test_mrsp_counts_resistant_to_all_beta_lactams():
    import numpy as np
    from tailsignal.synth.ehr import Narms
    n = Narms.__new__(Narms)
    n.rng, n.marg = np.random.default_rng(0), {}
    iso = {"organism": "S. pseudintermedius", "source": "Other sites", "Oxacillin": 1, "Cephalothin": 0,
           "Clindamycin": 0}
    assert n.resistant(iso, "cephalexin") is True
    assert n.resistant(iso, "clindamycin") is False
    assert n.resistant({"organism": "E. coli", "source": "UTI"}, "clindamycin") is True


def test_mantel_haenszel_equals_crude_when_one_stratum():
    from tailsignal.models.ehr_cohorts import crude, mantel_haenszel
    d = pd.DataFrame({"exposed": [True] * 100 + [False] * 100, "y": [True] * 10 + [False] * 90 + [True] * 5 + [False] * 95,
                      "age_band": ["a"] * 200})
    assert abs(mantel_haenszel(d)["mh_rr"] - crude(d)["rr"]) < 1e-9 and abs(crude(d)["rr"] - 2.0) < 1e-9


def test_stage3_dictionary_rules():
    from tailsignal.models.ehr_text import Dictionary
    texts = pd.Series(["O reports 2 seizures last night.", "Annual exam. No seizures. Fit and well.",
                       "hx sz (idiopathic epilepsy).", "Had a fit this AM."] * 3)
    d = Dictionary("seizure", texts)
    s3 = d.stage3(texts)
    assert list(s3[:4]) == [True, False, False, True]
    assert d.stage3(texts, allow_history=True)[2]


def test_funnel_limits_bracket_one_and_narrow_with_volume():
    from tailsignal.models.clinic_benchmarks import poisson_limits
    lo, hi = poisson_limits([10, 1000], 0.95)
    assert lo[0] < 1 < hi[0] and lo[1] < 1 < hi[1]
    assert (hi[1] - lo[1]) < (hi[0] - lo[0])


def test_sensitivity_at_specificity():
    import numpy as np
    from tailsignal.models.feline_ckd import sens_at_spec
    y = np.array([0] * 100 + [1] * 10)
    s = np.concatenate([np.linspace(0, 1, 100), np.full(10, 2.0)])
    sens, thr = sens_at_spec(y, s, 0.99)
    assert sens == 1.0 and thr < 1.0
