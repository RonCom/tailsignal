from tailsignal.models import pv_exposure as pe


def test_non_eu_denominator_and_rate():
    assert pe.FLU_NON_EU_2016 == 23.6e6
    r = pe.rates({"any_report": 2360}, pe.FLU_NON_EU_2016)
    assert abs(r["any_report"] - 1.0) < 1e-12


def test_lower_bound_scenario_is_largest_denominator():
    assert max(pe.US_SHARE_SCENARIOS.values()) == 1.0
