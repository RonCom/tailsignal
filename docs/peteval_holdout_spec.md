# PetEVAL Seizure Dictionary: Independent Check (pre-registered)

Written 2026-10-02, before any of the checks below were run. Code: `src/tailsignal/models/peteval_holdout.py`. Outputs: `reports/model_a2/peteval_holdout/summary.json`.

## Why this design

The first real-text check ([model_a2_results.md](model_a2_results.md)) read all 60 stage-3 hits in the public PetEVAL test set. The post-hoc "fit" rules (V2) were written from those same 60 notes, so their 64% precision is optimistic. The plan was to label a fresh sample of hits. That is not possible: the public release has 4,999 notes and every hit has been read. Two checks remain that do not depend on my earlier reading:

1. **My labels against PetEVAL's.** Each PetEVAL record carries ICD-11 chapter labels assigned by the dataset's annotators. Seizure disorders sit in "Diseases of the nervous system". If my true/false verdicts are sound, true hits should mostly carry that chapter and false hits rarely.
2. **Recall, measured for the first time.** I read every record labelled "Diseases of the nervous system" (150 records), with the dictionary's output hidden, and mark whether the note describes a seizure in this pet now or recently. Recall = share of those the dictionary flags.

## Pre-stated expectations

| Check | Expectation |
|---|---|
| True hits (my verdict) carrying the nervous-system chapter | at least 80% |
| False hits (my verdict) carrying the nervous-system chapter | at most 15% |
| Recall of the frozen stage-3 dictionary on nervous-system records I mark as seizures | at least 70% |
| True seizures lost by the post-hoc V2 rules among those records | at most 1 |

## Limits stated up front

- Recall is measured only inside the nervous-system chapter. A seizure note filed under another chapter is not counted, so this recall is an upper bound.
- I am the only reader. A second reader would let agreement be measured.
- ICD chapters are record-level: an epileptic dog seen for a skin problem may still carry the nervous-system chapter, so the agreement check cannot reach 100%.
