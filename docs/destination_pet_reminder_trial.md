# Proposal: A Randomized Reminder Trial for Destination Pet (pre-registered design)

Written 2026-10-02. Power code: `scripts/reminder_trial_power.py`. Background: [models_cd_results.md](models_cd_results.md), Model D.

Destination Pet owns its clinics, so it can run the experiment the TailSignal pilot was too small for. The pilot (2,927 members) showed reminders help on average (14.1% to 12.4% lapse) but could not learn who they help. This design fixes the hypotheses, sample size and analysis before any data is seen.

| | Design |
|---|---|
| Question | Does an extra personal reminder (text, then a call) reduce lapsed wellness care, and does the effect differ between low- and high-engagement households? |
| Unit and randomization | Household, 1:1 to usual reminders or usual + personal reminder, stratified by clinic and engagement segment (defined from the prior 12 months, frozen before launch) |
| Primary outcome | No wellness visit within 180 days of the due date |
| Primary hypothesis | The reminder's effect differs by at least 5 percentage points between the two segments |
| Secondary | Average effect across all households; then an uplift model trained on trial data and tested on the next quarter's due dates |
| Sample size | 6,000 households (1,500 per arm per segment): 80% power for a 5-point difference in effect, two-sided 5% |
| Analysis | Risk difference by arm within segment, adjusted for clinic; interaction test for the primary hypothesis; fixed horizon, no early stopping |
| Decision rule | Effect differs: target reminders by segment. No difference: remind everyone if the average effect beats the cost per contact |

**Power assumptions.** Planning rates come from the TailSignal simulation (14.1% lapse without a reminder, 13.5% per cell). The average effect (1.7 points) has only 49% power at 6,000 households; detecting it at 80% needs about 12,500, and a 3-point difference in effect needs about 16,300. If Destination Pet's volume allows, choose 12,500 before launch, not after seeing results.

**To confirm with Destination Pet:** monthly wellness due dates across clinics (this sets enrollment time), its actual 180-day lapse rate, and the cost per personal reminder. The protocol, with these numbers filled in, is committed to the repository before the first reminder is sent.
