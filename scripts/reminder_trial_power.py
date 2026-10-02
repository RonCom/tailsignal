"""Power for the proposed Destination Pet reminder trial (docs/destination_pet_reminder_trial.md).

    uv run python scripts/reminder_trial_power.py
"""
from scipy.stats import norm

Z = norm.ppf(0.975) + norm.ppf(0.80)
P0, P1 = 0.141, 0.124          # 180-day lapse without / with reminder (TailSignal pilot, simulated)
P_CELL = 0.135                 # planning lapse rate for each arm x segment cell


def n_average_effect():
    return Z ** 2 * (P0 * (1 - P0) + P1 * (1 - P1)) / (P0 - P1) ** 2


def n_interaction(diff):
    """Per-cell n to detect a difference of `diff` between two segments' reminder effects."""
    return Z ** 2 * 4 * P_CELL * (1 - P_CELL) / diff ** 2


def power_average(n_per_arm):
    se = ((P0 * (1 - P0) + P1 * (1 - P1)) / n_per_arm) ** 0.5
    return norm.cdf((P0 - P1) / se - norm.ppf(0.975))


if __name__ == "__main__":
    print(f"average effect, 80% power: {2 * n_average_effect():,.0f} households")
    print(f"5-point difference in effect: {4 * n_interaction(0.05):,.0f} households ({n_interaction(0.05):,.0f} per cell)")
    print(f"3-point difference in effect: {4 * n_interaction(0.03):,.0f} households")
    print(f"power for the average effect at 6,000 households: {power_average(3000):.0%}")
