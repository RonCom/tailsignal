# Models C and D Results

Synthetic platform data (8,490 households; 2022–2025). Hypotheses H5 and H6 are in [`preregistration.md`](preregistration.md). Code: `src/tailsignal/models/early_warning.py` and `src/tailsignal/models/uplift.py`. Outputs: `reports/early_warning/` and `reports/uplift/`.

## Model D: who should get a wellness-plan reminder (H6)

The wellness-plan provider randomized a reminder at month 6 for 2,927 memberships with full follow-up. Overall, the reminder cut 180-day lapse from 14.1% to 12.4%, about 17 members kept per 1,000 contacted.

**Pre-registered test** (train on campaigns to mid-2024, test on the next 12 months: 287 memberships): contact the top 30% by each score.

| Targeting rule | Members kept per 1,000 contacts | 95% CI |
|---|---|---|
| Uplift model (X-learner) | 58 | −93 to 193 |
| Uplift model (T-learner) | 41 | −90 to 199 |
| Lapse risk (usual churn model) | −82 | −226 to 75 |
| Random | 21 | −55 to 97 |

Uplift beat risk targeting by 140 per 1,000 (95% CI −14 to 273). **H6 fails: the interval includes zero.**

**Secondary** (5-fold cross-fitting over all 2,927): uplift 24, risk 12, random 17 per 1,000; all intervals overlap.

**Recovery check against the simulator's true effects.** Targeting by the *true* effect would keep 93 members per 1,000 contacts, five times the random rate, so the value is there to capture. The learned uplift scores only weakly track the truth (rank correlation 0.17; risk scores 0.05). Risk targeting points at the wrong people: in the simulator the most persuadable members are low-engagement and frequent-boarding households, while the highest-risk group includes members a reminder does not move.

**What it means.** At this pilot size the experiment can estimate the average effect but cannot reliably learn who benefits. Detecting a 5-point difference in effect between two member groups (at a 14% base lapse rate, 80% power) needs about 3,000 members per group; a 3-point difference needs about 8,400. Recommendation: expand the randomized reminder to roughly 6,000–9,000 members across partner clinics, stratified by segment, before switching to targeted outreach. Until then, remind everyone; the average effect is positive.

## Model C: early warning from non-vet channels (H5)

Unit: pet-month (392,838 snapshots). Outcome: a sick (non-wellness) vet visit in the next 60 days (8.4% of test snapshots). Train through April 2024; test from July 2024.

**Pre-registered contrast** (vet history only vs. vet history + all cross-channel features), platform data:

| | AUC |
|---|---|
| Vet history only | 0.709 |
| + cross-channel features | 0.715 |
| Lift | **+0.007** (95% CI 0.005–0.008) |

Pets seen at daycare, boarding, or grooming in the past 90 days: +0.012.

**Power study** (fresh simulations with true identities, varying how often an illness shows a warning sign in other channels):

| Share of illnesses with a prior warning sign | AUC lift | Linked pets for 80% power |
|---|---|---|
| 0% (no warning signal planted) | 0.009 | 2,000 |
| 25% | 0.011 | 2,000 |
| 50% (platform setting) | 0.012 | 2,000 |
| 100% | 0.015 | 1,000 |

None reach the pre-registered 0.02, 0.05, or 0.10 lifts, so those sample sizes are undefined.

**The key finding is in the first row.** With no warning signal planted, cross-channel data still lifts AUC by 0.009. That lift comes from *engagement* (households that use daycare and grooming also use vets differently), not from anything changing before the visit. An exploratory ablation (logged as an amendment) separates the two:

| Data | Engagement lift (uses other channels) | Warning-signal lift (attendance drop, concerning notes) | 95% CI | Warning lift, pets active in other channels |
|---|---|---|---|---|
| Sim, 0% signal | 0.010 | −0.000 | −0.001 to 0.000 | 0.000 |
| Sim, 25% | 0.010 | 0.002 | 0.001 to 0.002 | 0.004 |
| Sim, 50% | 0.010 | 0.003 | 0.002 to 0.004 | 0.009 |
| Sim, 100% | 0.010 | 0.005 | 0.004 to 0.006 | 0.022 |
| Platform (entity-resolved) | 0.004 | 0.001 | −0.000 to 0.002 | 0.008 |

The ablation behaves as a valid test should: zero when no signal exists, rising with signal strength. On the platform data the warning signal is not distinguishable from zero across all pets.

**H5 verdict: fails.** Cross-channel data improves prediction modestly, mostly through engagement. True early-warning value is confined to pets that are already active in other channels, and even there it is small unless most illnesses show visible signs.

**What it means for the business.** Do not sell "daycare data predicts illness" as a headline product. Its value is:
- As a **care-management feature for active pets** (daycare regulars): +0.009 to +0.022 AUC in that group.
- As a reason to **capture better notes**: the signal depends on staff recording concerns. A structured "health concern" checkbox at check-in would be worth more than any model change.
- As a **partner-recruitment target**: roughly 2,000 linked pets with cross-channel activity are needed before a lift of this size can be shown to a buyer.
